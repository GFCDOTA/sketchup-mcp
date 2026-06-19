"""sketchup-mcp — servidor MCP (FastMCP), fatia 1.

Expõe os "verbos" PUROS/rápidos do pipeline (sem SketchUp.exe) como tools MCP
estruturadas, pra o Claude chamar direto — JSON minúsculo entra/sai, em vez de
construir comando bash + parsear log (corta token), e com os gotchas embutidos
(ex.: PT_TO_M=0.0259 default nos gates de mobília).

Fatia 1 (esta): gates determinísticos, classes de móvel (derive+gate),
tradutor de referência Pinterest (contrato/normalizador/validador), promoção
de artefato, inventário de SKP. As tools PESADAS (build_shell/furnish/V-Ray,
que sobem o SketchUp) ficam pra fatia 2.

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

# Torna `tools.*` importável independente do cwd com que o MCP foi spawnado.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from mcp.server.fastmcp import FastMCP  # noqa: E402

# --- módulos do pipeline (todos presentes na develop) ----------------------
from tools.run_deterministic_gates import run_all  # noqa: E402
from tools.promote_canonical import promote  # noqa: E402
from tools.claude_bridge.skp_inventory import skp_inventory_v2  # noqa: E402
from tools.reference_grammar import (  # noqa: E402
    grammar_contract,
    normalize_grammar,
    validate_grammar_spec as _validate_grammar_spec,
)

from tools.sofa_class import derive_spec as _sofa_derive, sofa_class_gate  # noqa: E402
from tools.bed_class import derive_bed_spec, bed_class_gate  # noqa: E402
from tools.armchair_class import derive_armchair_spec, armchair_class_gate  # noqa: E402
from tools.dining_table_class import derive_dining_spec, dining_class_gate  # noqa: E402
from tools.rack_class import derive_rack_spec, rack_class_gate  # noqa: E402
from tools.coffee_table_class import derive_coffee_spec, coffee_table_class_gate  # noqa: E402

mcp = FastMCP(
    "sketchup-mcp",
    instructions=(
        "Pipeline PDF->.skp do sketchup-mcp. Tools puras (sem SketchUp): gates "
        "determinísticos, classes paramétricas de móvel (derive+gate), tradutor "
        "de referência visual (Pinterest) -> DesignGrammarSpec, promoção e "
        "inventário. REGRA-MÃE do tradutor: a referência manda na LINGUAGEM; o "
        "PDF/consensus manda na POSIÇÃO (imutável). Comece por list_capabilities."
    ),
)


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
    """Catálogo do que este MCP expõe (fatia 1) + o que está adiado pra fatia 2.

    Leia isto primeiro — descreve as tools, seus argumentos e os gotchas
    embutidos, pra você não precisar adivinhar invocação de CLI."""
    return {
        "server": "sketchup-mcp",
        "slice": 1,
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
        "furniture_kinds": sorted(_FURN),
        "deferred_to_slice2": [
            "build_shell (PDF->.skp, ~60-90s, sobe SketchUp)",
            "furnish_apartment (~180s, sobe SketchUp)",
            "render_scene_vray (~120-180s, SketchUp + V-Ray)",
            "consult_oracle (proxy do :8765)",
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
        from tools.kitchen_ergonomics import audit
    except Exception:  # noqa: BLE001
        return {
            "available": False,
            "note": "tools.kitchen_ergonomics não está neste checkout (branch-only; "
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
