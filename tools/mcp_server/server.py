"""sketchup-mcp — servidor MCP (FastMCP), fatias 1 + 2.

Expõe os "verbos" do pipeline como tools MCP estruturadas, pra um agente
(Claude Code / Claude Desktop / harness-app) chamar direto — JSON minúsculo
entra/sai, em vez de construir comando bash + parsear log, e com os gotchas
embutidos (ex.: PT_TO_M=0.0259 da planta_74).

Fatia 1: tools PURAS (sem SketchUp) — gates determinísticos, classes de móvel
(derive+gate), tradutor de referência Pinterest, promoção, inventário de SKP.

Fatia 2: o ESPECIALISTA EM SKETCHUP (`su_*`, implementado em tools/sketchup/)
— ciclo de vida do SketchUp, inspeção, render, edição do modelo, build do
shell, mobiliado e V-Ray. Sobem o SketchUp (Windows); fora dele respondem
UNAVAILABLE com o motivo, nunca sucesso fabricado.

Rodar:  python -m tools.mcp_server.server      (stdio)
Registrar em .mcp.json apontando pra este módulo via a venv do repo.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

# planta_74 tem escala verificada (core.scale.PLANT_PT_TO_M) e core.scale congela
# PT_TO_M no PRIMEIRO import — setar depois (como room_gates fazia) não corrige.
# Este servidor é planta_74: o default entra ANTES de qualquer import do pipeline.
# Env explícito do cliente continua vencendo.
os.environ.setdefault("PT_TO_M", "0.0259")

# Torna `tools.*` importável independente do cwd com que o MCP foi spawnado.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from mcp.server.fastmcp import FastMCP  # noqa: E402

# Extensões C carregadas JÁ, antes de o servidor começar a ler o stdin. No Windows,
# importar uma delas pela primeira vez DENTRO de uma tool (su_furnish/su_build_shell
# importam shapely sob demanda) travava para sempre no carregamento da DLL do numpy,
# com a leitura síncrona do pipe do JSON-RPC pendente (L2 2026-10-19, faulthandler:
# numpy/_core/multiarray.py <- shapely <- tools/rooms/bedroom/designer.py). Só as
# bibliotecas: os brains continuam carregando sob demanda.
import numpy  # noqa: E402,F401
import shapely.geometry  # noqa: E402,F401
import shapely.ops  # noqa: E402,F401
from PIL import Image as _PIL_Image  # noqa: E402,F401

# --- módulos do pipeline (todos presentes na develop) ----------------------
from tools.run_deterministic_gates import run_all  # noqa: E402
from tools.promote_canonical import promote  # noqa: E402
from tools.claude_bridge.skp_inventory import skp_inventory_v2  # noqa: E402
from tools.reference_grammar import (  # noqa: E402
    grammar_contract,
    normalize_grammar,
    validate_grammar_spec as _validate_grammar_spec,
)

from tools.rooms.living.sofa_class import derive_spec as _sofa_derive, sofa_class_gate  # noqa: E402
from tools.rooms.bedroom.bed_class import derive_bed_spec, bed_class_gate  # noqa: E402
from tools.rooms.living.armchair_class import derive_armchair_spec, armchair_class_gate  # noqa: E402
from tools.rooms.living.dining_table_class import derive_dining_spec, dining_class_gate  # noqa: E402
from tools.rooms.living.rack_class import derive_rack_spec, rack_class_gate  # noqa: E402
from tools.rooms.living.coffee_table_class import derive_coffee_spec, coffee_table_class_gate  # noqa: E402
from tools.sketchup import jobs as su_jobs  # noqa: E402
from tools.sketchup import ops as su_ops  # noqa: E402
from tools.mcp_server.stdio_isolation import isolate_stdio, quiet_tools  # noqa: E402

mcp = FastMCP(
    "sketchup-mcp",
    instructions=(
        "Pipeline PDF->.skp do sketchup-mcp. Tools puras (sem SketchUp): gates "
        "determinísticos, classes paramétricas de móvel (derive+gate), tradutor "
        "de referência visual (Pinterest) -> DesignGrammarSpec, promoção e "
        "inventário. Especialista em SketchUp (su_*): status/abrir/fechar, "
        "inspecionar, renderizar, editar (cópia nova, nunca o original), build do "
        "shell, mobiliar e V-Ray. REGRAS: o PDF/consensus manda na POSIÇÃO "
        "(arquitetura não aceita edição geométrica); nada escreve em fixtures/ ou "
        "artifacts/ (promoção só via promote_canonical); fechar SketchUp exige "
        "confirm=true e é por PID; aparência nova pede VISUAL_REVIEW do Felipe. "
        "Comece por list_capabilities e su_status."
    ),
)


# stdout é do protocolo: print/escrita em tool ou em processo filho vai para o stderr (stdio_isolation).
quiet_tools(mcp)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _spec_to_dict(spec: Any) -> dict[str, Any]:
    if hasattr(spec, "to_dict"):
        return spec.to_dict()
    if dataclasses.is_dataclass(spec):
        return dataclasses.asdict(spec)
    return dict(spec)


def _bbox(spec: Any) -> list[float] | None:
    if hasattr(spec, "bbox_m"):
        try:
            return [round(float(x), 4) for x in spec.bbox_m()]
        except Exception:
            return None
    return None


def _resolve_consensus(consensus_path: str | None) -> tuple[dict | None, str | None]:
    """Carrega um consensus; default = fixture planta_74. Retorna (dict, path)."""
    if consensus_path:
        p = Path(consensus_path)
    else:
        p = _REPO / "fixtures" / "planta_74" / "consensus_with_human_walls_and_soft_barriers.json"
    if not p.exists():
        return None, str(p)
    try:
        return json.loads(p.read_text(encoding="utf-8")), str(p)
    except Exception:
        return None, str(p)


# router das classes de móvel: kind -> (derive, gate, args-aceitos)
_FURN: dict[str, tuple[Any, Any, set[str]]] = {
    "sofa": (_sofa_derive, sofa_class_gate, {"seats", "archetype"}),
    "bed": (derive_bed_spec, bed_class_gate, {"size", "archetype"}),
    "armchair": (derive_armchair_spec, armchair_class_gate, {"archetype"}),
    "dining_table": (derive_dining_spec, dining_class_gate, {"seats", "archetype"}),
    "rack": (derive_rack_spec, rack_class_gate, {"tv", "archetype"}),
    "coffee_table": (derive_coffee_spec, coffee_table_class_gate, {"archetype"}),
}
_FURN_ALIASES = {"dining": "dining_table", "coffee": "coffee_table"}


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_capabilities() -> dict[str, Any]:
    """Catálogo do que este MCP expõe: tools puras (fatia 1) + especialista em
    SketchUp `su_*` (fatia 2).

    Leia isto primeiro — descreve as tools, seus argumentos e os gotchas
    embutidos, pra você não precisar adivinhar invocação de CLI."""
    return {
        "server": "sketchup-mcp",
        "slice": 2,
        "tools": {
            "run_deterministic_gates": "gates de consensus/render (PASS/FAIL/INCOMPLETE), sem SketchUp.",
            "furniture_class_derive": "deriva + valida uma classe de móvel (sofa/bed/armchair/dining_table/rack/coffee_table).",
            "reference_to_grammar": "tradutor Pinterest: sem draft devolve o CONTRATO; com draft normaliza pra DesignGrammarSpec.",
            "validate_grammar_spec": "valida a DesignGrammarSpec cruzando com a autoridade do PDF (posição imutável).",
            "room_gates": "overlap + coerência de estilo de um cômodo (PT_TO_M embutido).",
            "kitchen_ergonomics_audit": "auditoria ergonômica da cozinha (12 métricas); pode estar ausente neste checkout.",
            "promote_canonical": "promove um build abençoado pra artifacts/<plant>/.",
            "skp_inventory": "inventário categorizado dos .skp do repo (dedup + git status).",
        },
        # su_* que sobem o SketchUp: testadas só contra dublê; nenhuma rodou num
        # SketchUp real. Não tratar como capacidade comprovada.
        "sketchup_specialist_proof_state": su_jobs.PROOF_STATE,
        "sketchup_specialist": {
            "su_status": "SketchUp instalado? instâncias rodando (PID), plugin de autorun, V-Ray. Rápido, sem subir nada.",
            "su_open": "abre um .skp numa janela nova (desanexada).",
            "su_close": "fecha por PID ou todas — SÓ com confirm=true; gracioso (pergunta se salva) salvo force=true.",
            "su_inspect": "inventário do .skp: grupos/componentes (nome, PID persistente, tag, material, bbox em m), materiais, tags, cenas.",
            "su_render": "PNGs por preset (top/iso/front/back/left/right) ou câmera em metros; esconde/enquadra por nome.",
            "su_apply_edits": "material/cor/textura, mover, girar, tag, visibilidade, renomear, apagar, inserir componente — salva CÓPIA.",
            "su_build_shell": "consensus -> shell .skp + renders + gates determinísticos (não promove).",
            "su_furnish": "mobilia a planta_74 no shell (brains de layout -> place_layout_skp.rb).",
            "su_render_vray": "V-Ray de uma cena (scene.json + scene_closed.skp): exporta numa cópia pela PRÓPRIA instância e renderiza com vray.exe; saída em runs/.",
        },
        "furniture_kinds": sorted(_FURN),
        "edit_ops": sorted(su_ops.ALL_OPS),
        **su_ops.protection_params(),
        "gotchas": [
            "Unidade da API é METRO; o SketchUp guarda polegadas — a conversão é interna.",
            "Grupos de arquitetura (protected_prefixes/protected_substrings) não aceitam "
            "move/rotate/delete/rename: vêm do PDF.",
            "Edição sempre sai em .skp NOVO; nunca em fixtures/ ou artifacts/.",
            "mode: 'interactive' (default local) deixa o SketchUp aberto pra inspeção; "
            "'headless' (default no CI) fecha a instância que o job subiu — nunca outra.",
            "Jobs pesados levam 30-300 s (sobem o SketchUp). Alvo ambíguo é recusado: use persistent_id do su_inspect.",
            "Aparência nova (render/furnish/build) pede VISUAL_REVIEW do Felipe — nunca auto-aprovar.",
        ],
        "rule": "Tradutor de referência: referência=LINGUAGEM, PDF=POSIÇÃO (imutável).",
    }


@mcp.tool()
def run_deterministic_gates(
    fixture: str = "planta_74",
    consensus_path: str | None = None,
    render_path: str | None = None,
) -> dict[str, Any]:
    """Roda os gates determinísticos (opening_host, wall_overlap, e — se houver
    render + sidecar .proj.json — wall_presence/render_bbox). Sem SketchUp.

    Retorna {overall: PASS|FAIL|INCOMPLETE, gates: {...}}."""
    return run_all(fixture=fixture, consensus_path=consensus_path, render_path=render_path)


@mcp.tool()
def furniture_class_derive(
    kind: str,
    archetype: str | None = None,
    seats: int | None = None,
    size: str | None = None,
    tv: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deriva uma spec paramétrica de móvel por INTENÇÃO e a valida no gate da
    classe — sem SketchUp. kind ∈ {sofa, bed, armchair, dining_table, rack,
    coffee_table}.

    Ex.: furniture_class_derive("sofa", seats=3, archetype="lounge").
    `overrides` repassa parâmetros finos (arm_style, base_style, headboard, ...).

    Retorna {kind, spec, gate:{result,errors,warnings,metrics}, bbox_m}."""
    k = _FURN_ALIASES.get(kind.strip().lower(), kind.strip().lower())
    if k not in _FURN:
        return {"error": f"kind desconhecido: '{kind}'", "valid": sorted(_FURN)}
    derive, gate, accepts = _FURN[k]
    kw: dict[str, Any] = {}
    if "seats" in accepts and seats is not None:
        kw["seats"] = seats
    if "size" in accepts and size:
        kw["size"] = size
    if "tv" in accepts and tv:
        kw["tv"] = tv
    if "archetype" in accepts and archetype:
        kw["archetype"] = archetype
    kw.update(overrides or {})
    try:
        spec = derive(**kw)
    except TypeError as e:
        return {"error": f"args inválidos p/ {k}: {e}", "accepts": sorted(accepts) + ["overrides"]}
    return {
        "kind": k,
        "spec": _spec_to_dict(spec),
        "gate": gate(spec),
        "bbox_m": _bbox(spec),
    }


@mcp.tool()
def reference_to_grammar(
    room_type: str = "kitchen",
    draft: dict[str, Any] | None = None,
    plant: str | None = None,
    room_id: str | None = None,
) -> dict[str, Any]:
    """Tradutor de referência visual (Pinterest/print/foto) — esqueleto do
    especialista.

    SEM `draft`: devolve o CONTRATO (o que olhar na imagem + vocabulário
    canônico + formato de resposta). Você (Claude) é o modelo de visão: olhe a
    referência, monte o draft seguindo `draft_shape`.

    COM `draft`: normaliza o draft pra uma DesignGrammarSpec canônica (colapsa
    sinônimos de token, injeta fixed_anchors do PDF por construção).

    Regra: a referência define LINGUAGEM; o PDF define POSIÇÃO (imutável)."""
    if not draft:
        return {"mode": "contract", **grammar_contract(room_type)}
    return {"mode": "normalized", **normalize_grammar(draft, room_type, plant, room_id)}


@mcp.tool()
def validate_grammar_spec(
    spec: dict[str, Any],
    consensus_path: str | None = None,
    room_id: str | None = None,
) -> dict[str, Any]:
    """Valida uma DesignGrammarSpec. Reprova (FAIL) o que feriria a autoridade
    do PDF (fixed_anchors precisam vir do PDF; room_id precisa existir no
    consensus quando informado). Sinaliza (WARN) vocabulário fora do canônico.

    Retorna {result: PASS|WARN|FAIL, errors, warnings, ...}."""
    return _validate_grammar_spec(spec, consensus_path, room_id)


@mcp.tool()
def room_gates(
    room_id: str,
    style: str = "industrial",
    consensus_path: str | None = None,
    pt_to_m: float = 0.0259,
) -> dict[str, Any]:
    """Gates de um cômodo SEM SketchUp: furniture_overlap (móvel-sobre-móvel) +
    style_coherence (recoloração + escala compacta). PT_TO_M=0.0259 é embutido
    (gotcha de escala da planta_74; sobrescreva via `pt_to_m`).

    Retorna {overlap:{...}, style_coherence:{...}}."""
    os.environ["PT_TO_M"] = str(pt_to_m)
    con, path = _resolve_consensus(consensus_path)
    if con is None:
        return {"error": f"consensus não carregado: {path}"}
    out: dict[str, Any] = {"consensus": path, "pt_to_m": pt_to_m}
    try:
        from tools.furniture_overlap_gate import overlap_gate
        out["overlap"] = overlap_gate(con, room_id)
    except Exception as e:  # noqa: BLE001
        out["overlap"] = {"error": repr(e)}
    try:
        from tools.style_coherence_gate import style_coherence_gate
        out["style_coherence"] = style_coherence_gate(con, room_id, style)
    except Exception as e:  # noqa: BLE001
        out["style_coherence"] = {"error": repr(e)}
    return out


@mcp.tool()
def kitchen_ergonomics_audit(room_id: str = "r004", pt_to_m: float = 0.0259) -> dict[str, Any]:
    """Auditoria ergonômica da cozinha (12 métricas: altura de bancada,
    clearances, profundidades...). PT_TO_M embutido.

    Pode estar AUSENTE neste checkout (módulo branch-only) — nesse caso retorna
    available=False em vez de quebrar."""
    os.environ["PT_TO_M"] = str(pt_to_m)
    try:
        from tools.rooms.kitchen.validation.ergonomics import audit
    except Exception:  # noqa: BLE001
        return {
            "available": False,
            "note": "tools.rooms.kitchen.validation.ergonomics não está neste checkout (branch-only; "
                    "merge a branch da cozinha pra habilitar).",
        }
    worst, rows, _by_mod = audit(room_id)
    return {
        "available": True,
        "result": worst,
        "room_id": room_id,
        "metrics": [
            {"key": k, "value": v, "lo": lo, "hi": hi, "tag": t}
            for (k, v, lo, hi, t) in rows
        ],
    }


@mcp.tool()
def promote_canonical(src_final: str, plant: str = "planta_74") -> dict[str, Any]:
    """Promove um build abençoado (dir com model.skp) pro caminho-entregável
    fixo artifacts/<plant>/<plant>.skp, reescrevendo o sidecar de metadados.

    Retorna {dst, copied, sha}."""
    p = Path(src_final)
    if not p.exists():
        return {"error": f"src_final não existe: {src_final}"}
    return promote(p, plant)


@mcp.tool()
def skp_inventory() -> dict[str, Any]:
    """Inventário categorizado dos .skp do repo (tamanho, sha, git status,
    dedup, ação sugerida KEEP/ARCHIVE/...). Sem SketchUp."""
    return skp_inventory_v2()


# ---------------------------------------------------------------------------
# especialista em SketchUp (fatia 2) — implementação em tools/sketchup/
# ---------------------------------------------------------------------------

@mcp.tool()
def su_status() -> dict[str, Any]:
    """Estado do SketchUp nesta máquina, sem subir nada: executável encontrado,
    instâncias rodando (PID + memória), plugin de autorun legado (informativo), V-Ray,
    como o servidor está preso a um Job Object do Windows (`server_job`), jobs Ruby disponíveis e o modo padrão. Chame antes das outras su_*.

    `proof_state` = UNVERIFIED_ON_SKETCHUP: as su_* ainda não rodaram num
    SketchUp real — o resultado delas não é capacidade comprovada."""
    return su_jobs.status()


@mcp.tool()
def su_open(skp_path: str) -> dict[str, Any]:
    """Abre um .skp numa janela nova do SketchUp, DESANEXADA (fechar o MCP não
    fecha o SketchUp). Retorna {status: OPENED, pid}."""
    return su_jobs.open_model(skp_path)


@mcp.tool()
def su_close(
    pid: int | None = None,
    all_instances: bool = False,
    force: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    """Fecha SketchUp por PID (ou todas as instâncias com all_instances=true).

    SEM confirm=true só devolve o que fecharia (CONFIRMATION_REQUIRED) — fechar
    pode descartar trabalho não salvo. Padrão é gracioso (o SketchUp pergunta
    se quer salvar); force=true mata sem perguntar. Nunca fecha por nome de
    imagem."""
    return su_jobs.close(pid=pid, all_instances=all_instances, force=force, confirm=confirm)


@mcp.tool()
def su_inspect(skp_path: str, max_depth: int = 2, mode: str | None = None) -> dict[str, Any]:
    """Inventário estruturado de um .skp (não modifica): grupos/componentes até
    `max_depth` níveis com nome, definição, persistent_id, tag, material,
    bbox_local_m (referencial do pai) e bbox_world_m (mundo), se é arquitetura
    protegida (própria ou herdada do pai) e `contexts` (>1 = definição
    compartilhada entre instâncias); materiais, tags e cenas.

    Use o `pid` daqui como alvo inequívoco em su_apply_edits."""
    return su_jobs.inspect_model(skp_path, max_depth=max_depth, mode=mode)


@mcp.tool()
def su_render(
    skp_path: str,
    views: list[dict[str, Any]] | None = None,
    width: int = 1600,
    height: int = 1200,
    hide_contains: list[str] | None = None,
    focus_contains: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Renderiza PNGs de um .skp (não salva o modelo).

    views: [{name, preset}] com preset ∈ top/iso/front/back/left/right, ou
    [{name, eye_m:[x,y,z], target_m:[x,y,z], fov?}] em METROS. Default: top+iso.
    hide_contains: esconde grupos cujo nome contém o texto (ex. "PeleTeto").
    focus_contains: enquadra só os grupos cujo nome contém o texto."""
    return su_jobs.render_views(skp_path, views=views, width=width, height=height,
                                hide_contains=hide_contains, focus_contains=focus_contains,
                                mode=mode)


@mcp.tool()
def su_apply_edits(
    skp_path: str,
    ops: list[dict[str, Any]],
    out_path: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Aplica edições e salva numa CÓPIA (.skp novo; o original fica intacto).
    Tudo-ou-nada: um erro aborta todas as ops e nada é salvo.

    Cada op tem "op" e, exceto insert_component, um "target":
    {name | name_contains | persistent_id, expect: "one"(default)|"all"}.
      set_material {color:[r,g,b] | material:"nome" | texture:"x.png", texture_size_m?}
      move {by_m:[dx,dy,dz]}        rotate {degrees}   (eixos do MUNDO; rotate em Z no
                                     centro do bbox de mundo)
      set_tag {tag}  set_hidden {hidden}  rename {name}  delete {}
      insert_component {skp_path, position_m:[x,y,z], rotation_deg?, name?, tag?}
    Medidas são explícitas e em METROS. move/rotate/delete/rename são recusados
    quando o alvo, um ancestral ou um descendente é arquitetura do PDF (paredes,
    piso, portas, janelas, laje do banho), quando ele ou um ancestral está travado
    (locked) ou quando vive numa definição compartilhada (faça make_unique antes).
    insert_component recusa um .skp que traga arquitetura dentro; caminhos
    relativos são do repo."""
    return su_jobs.apply_edits(skp_path, ops, out_path=out_path, mode=mode)


@mcp.tool()
def su_build_shell(
    consensus_path: str | None = None,
    out_path: str | None = None,
    force: bool = False,
    mode: str | None = None,
) -> dict[str, Any]:
    """Gera o shell .skp a partir de um consensus (default: fixture planta_74)
    + renders + geometry_report, e roda os gates determinísticos em cima.
    Saída em runs/ (nunca promove). force=true ignora o cache por hash."""
    return su_jobs.build_shell(consensus_path, out_path=out_path, force=force, mode=mode)


@mcp.tool()
def su_furnish(
    style: str | None = None,
    base_skp: str | None = None,
    consensus_path: str | None = None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Mobilia a planta_74 inteira: classifica cômodos, roda os brains de
    layout e coloca os móveis no shell (default: artifacts/planta_74/planta_74.skp,
    só leitura). Saída em runs/. `style` aplica a textura por peça do estilo."""
    return su_jobs.furnish(style=style, base_skp=base_skp, consensus_path=consensus_path,
                           mode=mode)


@mcp.tool()
def su_render_vray(
    scene_dir: str,
    out_png: str | None = None,
    width: int = 1500,
    height: int = 1000,
    fov: float = 65,
) -> dict[str, Any]:
    """Render V-Ray de uma cena composta: scene_dir com scene.json (câmera em
    metros) + scene_closed.skp. Exporta o .vrscene numa CÓPIA pela própria
    instância do SketchUp (nunca fecha outra janela) e renderiza com vray.exe
    headless. scene_dir é só leitura; PNG/.vrscene/log saem em runs/ (ou
    out_png, nunca em fixtures/ ou artifacts/). Aparência = VISUAL_REVIEW."""
    return su_jobs.render_vray(scene_dir, out_png=out_png, width=width, height=height, fov=fov)


def main() -> None:
    isolate_stdio()
    mcp.run()


if __name__ == "__main__":
    main()
