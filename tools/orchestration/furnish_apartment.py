"""furnish_apartment.py — mobilia a planta INTEIRA num UNICO .skp: classifica
cada comodo (tools.room_type), roda o brain certo por tipo, junta TODOS os boxes
e materializa um so planta_74_furnished.skp (+ renders) no shell real. REUSA
tools/sketchup/furnish/place_layout_skp.rb (generico). Pasta fixa artifacts/planta_74/furnished/.

Hoje mobilia: BEDROOM (bedroom_layout). Arquitetura cresce: e so registrar mais
brains em BRAINS (KITCHEN, BATHROOM, LIVING). Felipe 2026-06-05. Placeholders,
NAO 3D Warehouse.

Sem --dry-run, abre uma instância própria do SketchUp; não encerra janelas humanas.
Uso: python tools/furnish_apartment.py [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # roda standalone
# Escala verificada da planta_74 (cota-anchored; core.scale.PLANT_PT_TO_M["planta_74"])
# DEVE ser setada ANTES de core.scale ser importado pelos brains abaixo. Sem isso o
# placement cai no default 0.0352 e a mobilia flutua ~1.36x FORA do shell 0.0259
# (top render: comodos embaixo, moveis soltos em cima). core.scale congela PT_TO_M no
# 1o import, entao nao da pra corrigir depois. Este pipeline e planta_74-only.
if not os.environ.get("PT_TO_M"):
    os.environ["PT_TO_M"] = "0.0259"
from tools.rooms.bedroom import designer as bedroom_designer  # noqa: E402  (quartos: brain novo GPT-approved)
from tools.rooms.shared.geometry import _oriented_box  # noqa: E402,F401 (re-export legado)
from tools.rooms.bathroom.layout import build_boxes as bath_boxes   # noqa: E402
from tools.rooms.kitchen.layout import build_boxes as kitchen_boxes   # noqa: E402
from tools.sketchup.furnish.place_layout_skp import build_boxes as living_boxes   # noqa: E402
from tools.room_type import (BATHROOM, BEDROOM, KITCHEN, LIVING,   # noqa: E402
                             SERVICE, classify_rooms)
from tools.rooms.service.layout import build_boxes as service_boxes   # noqa: E402
from tools.rooms.living.components import (  # noqa: E402,F401 (re-exports legados)
    _bwg_recolor, _dining_table_rect, _dining_table_square, _oct_in,
)
from tools.rooms.shared.decor import place_decor_boxes  # noqa: E402,F401 (re-export legado)
from tools.rooms.shared.furniture import _chair_parts  # noqa: E402,F401 (re-export legado)
from tools.rooms.bedroom.furnishing import bedroom_designer_boxes  # noqa: E402,F401 (re-export legado)
from tools.rooms.living.furnishing import living_room_boxes  # noqa: E402,F401 (re-export legado)

ROOT = Path(__file__).resolve().parents[2]
SKETCHUP_EXE = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
CONSENSUS = PLANTA_74_CONSENSUS
BASE_SKP = Path(os.environ.get("FURNISH_BASE_SKP") or str(ROOT / "artifacts/planta_74/planta_74.skp"))  # shell override p/ escala: @0.0259 usa o shell rebuildado (base default 0.0352 intacta)
OUT_DIR = ROOT / "artifacts/planta_74/furnished"   # pasta UNICA fixa
RB = ROOT / "tools/sketchup/furnish/place_layout_skp.rb"
PLANT = "planta_74"   # pipeline planta_74-only (mesmo escopo do resto do modulo)


def _gallery_corpus_root() -> Path:
    """Raiz do corpus de galeria = a MESMA do variant_sweep/feeder
    (data/runs/noc_variant_sweep sob a raiz do WORKSPACE), pra o apê mobiliado
    virar mais um item da UNICA galeria que a curadoria/RAG ja leem — nao um
    silo paralelo. Fallback repo-relativo se a raiz do workspace nao resolver."""
    try:
        from tools.claude_bridge._paths import WORKSPACE_ROOT
        return WORKSPACE_ROOT / "data" / "runs" / "noc_variant_sweep"
    except Exception:  # noqa: BLE001 — checkout solto / sem apps+ops: repo-relativo
        return ROOT / "data" / "runs" / "noc_variant_sweep"


GALLERY_CORPUS_ROOT = _gallery_corpus_root()



# Dispatch por tipo de cômodo, com providers legados explicitamente injetados.
# A composição não importa nenhum brain de dentro de tools.rooms.dispatch.
from tools.rooms.dispatch import build_brain_registry, get_brain

BRAINS = build_brain_registry(
    bedroom=bedroom_designer_boxes,
    kitchen=kitchen_boxes,
    living=living_room_boxes,
    bathroom=bath_boxes,
    service=service_boxes,
)


def collect_boxes(con):
    """Junta os boxes de TODOS os comodos com brain disponivel. Devolve
    (boxes, summary[(id,name,type,result,n_boxes)])."""
    rooms = classify_rooms(con)
    all_boxes, summary = [], []
    for r in rooms:
        brain = get_brain(BRAINS, r["room_type"])
        if brain is None:
            summary.append((r["id"], r["name"], r["room_type"], "skip(sem brain)", 0))
            continue
        boxes, out = brain(con, r["id"])
        # GATE DE FIDELIDADE: a pia da cozinha é ponto hidráulico do PDF (parede oeste).
        # Falha o build ANTES de render se a pia migrar (Felipe: KITCHEN_PDF_ANCHOR_FIX).
        if r["room_type"] == KITCHEN:
            from tools.rooms.kitchen.validation import require_kitchen_anchor
            require_kitchen_anchor(con, r["id"])
        for b in (boxes or []):              # cada box leva COMODO + MODULO -> grupos editaveis no .skp
            b["room"] = str(r.get("name") or r["id"])
            b.setdefault("module", str(b.get("kind", "movel")))
        # GUARD anti-regressao (wet room): banheiro so aceita kinds de LOUCA. Se um movel de
        # quarto/sala vazar pra ca, LOGA (nao aborta) -> pega regressao futura de roteamento.
        if r["room_type"] == BATHROOM:
            from tools.rooms.bathroom.validation import unexpected_wet_room_kinds
            estranhos = unexpected_wet_room_kinds(boxes)
            if estranhos:
                print(f"[furnish-apt] WARN wet-room {r['name']!r}: kind(s) fora da louca -> {estranhos}")
        # TRADE-OFF VISIVEL: peca que o brain teve que encolher/descartar por
        # circulacao vira linha no relatorio, nao some. Sem isto o apê "parecia
        # completo" enquanto quarto ficava sem guarda-roupa em silêncio.
        for why in (out.get("downgrades") or []):
            print(f"[furnish-apt] TRADE-OFF {r['name']!r}: {why}")
        for kind, why in (out.get("dropped") or []):
            print(f"[furnish-apt] TRADE-OFF {r['name']!r}: {kind} -> {why}")
        n = len(boxes) if boxes else 0
        all_boxes += boxes or []
        summary.append((r["id"], r["name"], r["room_type"], out.get("result"), n))
    # camada de ESTILO (gated): recolore por kind = fonte unica do material SU ph_<kind>,
    # ANTES de qualquer serializacao LAYOUT_BOXES. Kind fora do mapa fica intacto.
    style = os.environ.get("FURNISH_STYLE")
    if style:
        from tools.rooms.shared.materials import apply_style, attach_materials
        nrec = apply_style(all_boxes, style)
        print(f"[furnish-apt] estilo '{style}': {nrec} boxes recoloridos")
        # FP-037: resolve material por (familia_de_modulo, kind) e anexa por box. Destrava madeira
        # no rack/mesa (kinds base/top/front) SEM contaminar o sofa (sofa.base = flat/grafite).
        ntex = attach_materials(all_boxes, style)
        print(f"[furnish-apt] material por modulo: {ntex} boxes com textura resolvida")
    # contrato semântico único (geometry_intent/shape_policy/interaction_policy/
    # host) — achado 2026-08-12, consulta GPT-Docker: preenche o que os builders
    # não declararam explicitamente, com provenance rastreável (não silenciosa).
    # Ver core/spatial_semantics.py.
    from core.spatial_semantics import annotate_all
    annotate_all(all_boxes)
    return all_boxes, summary


def _emit_furnished_gallery_item(iso_png, *, skp, style, plant=PLANT,
                                 flat_white=None, corpus=None):
    """APARENCIA NAO-BLOQUEIA (Bloco 2): DEPOIS que o .skp canonico + renders +
    flat_white_gate ja rodaram (geracao INTACTA, isto e' additivo puro), emite um
    item de galeria PENDENTE do apê mobiliado canonico e SEGUE. human_verdict fica
    None; verdict = PENDING_VISION (o furnish nao coleta visao). O flat_white e'
    um sinal de APARENCIA — vai pro gate_detail (recuperavel pelo olho do Felipe),
    NUNCA como gate FAIL que travaria o item. Reusa variant_sweep.build_record via
    emit_gallery_item (fabrica canonica + append idempotente por variant_id).
    NUNCA espera veredito nem aborta o furnish."""
    from tools.variant_axes import Variant
    from tools.variant_sweep import emit_gallery_item
    corpus = Path(corpus) if corpus else (GALLERY_CORPUS_ROOT / plant / "corpus.jsonl")
    corpus.parent.mkdir(parents=True, exist_ok=True)
    v = Variant(plant=plant, style=style or None, theme="", layout_seed=0)
    gate_detail = {"source": "furnish_apartment", "skp": Path(skp).name if skp else None}
    if isinstance(flat_white, dict):  # sinal de aparencia, NAO-bloqueante
        gate_detail["flat_white"] = {"result": flat_white.get("result"),
                                     "flags": flat_white.get("flags", []),
                                     "fails": flat_white.get("fails", []),
                                     "warns": flat_white.get("warns", [])}
    # kitchen_validation PASSOU (o build abortaria em collect_boxes se nao); e' o
    # unico gate deterministico que conhecemos aqui, e nao e' FAIL -> PENDING_VISION.
    return emit_gallery_item(corpus, v, png=iso_png,
                             gates={"kitchen_validation": "PASS"},
                             gate_detail=gate_detail, findings=None,
                             renderer="sketchup")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    con = json.loads(CONSENSUS.read_text("utf-8"))
    boxes, summary = collect_boxes(con)
    n_rooms = sum(1 for s in summary if s[4])
    print(f"[furnish-apt] {len(boxes)} placeholders em {n_rooms} comodo(s):")
    for rid, name, rt, res, n in summary:
        print(f"  {str(rid):5} {str(name)[:28]:28} {rt:9} {str(res):16} {n} boxes")
    if args.dry_run or not boxes:
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    skp_out = OUT_DIR / "planta_74_furnished.skp"
    before = OUT_DIR / "planta_74_furnished_before_top.png"
    after_top = OUT_DIR / "planta_74_furnished_after_top.png"
    after_iso = OUT_DIR / "planta_74_furnished_after_iso.png"
    log_path = OUT_DIR / "planta_74_furnished_log.txt"
    # Nunca encerrar instâncias humanas; saídas scratch antigas podem estar em uso
    time.sleep(1)
    for p in (skp_out, before, after_top, after_iso, log_path):
        try:
            if p.exists():
                p.unlink()
        except PermissionError:
            pass

    env = os.environ.copy()
    env["LAYOUT_BOXES"] = json.dumps(boxes)
    # tex_png por peca (banhos do Estudio Banheiro) precisa do dir SEMPRE;
    # sem LAYOUT_TEX_MAP os demais comodos seguem em cor chapada (fallback)
    env.setdefault("LAYOUT_TEX_DIR", str((ROOT / "assets/textures/procedural").resolve()))
    env["LAYOUT_OUT"] = str(skp_out).replace("\\", "/")
    env["LAYOUT_BEFORE"] = str(before).replace("\\", "/")
    env["LAYOUT_AFTER_TOP"] = str(after_top).replace("\\", "/")
    env["LAYOUT_AFTER_ISO"] = str(after_iso).replace("\\", "/")
    env["LAYOUT_LOG"] = str(log_path).replace("\\", "/")

    # FP-036: textura por kind no path INTERATIVO — o .skp que o Felipe abre deixa de sair com
    # cor chapada. So sob FURNISH_STYLE; fonte unica = style_spec.texture_env (nunca a 1a peca em tudo).
    style = os.environ.get("FURNISH_STYLE")
    if style:
        from tools.rooms.shared.materials import texture_env
        tex_env = texture_env(style, (ROOT / "assets/textures/procedural").resolve())
        env.update(tex_env)
        if tex_env:
            print(f"[furnish-apt] textura interativa: "
                  f"{len(json.loads(tex_env['LAYOUT_TEX_MAP']))} kind(s) mapeados (estilo {style})")

    time.sleep(1)
    cmd = [SKETCHUP_EXE, str(BASE_SKP), "-RubyStartup", str(RB)]
    print("[furnish-apt] launching SU...")
    owned_su = subprocess.Popen(cmd, env=env, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    deadline = time.time() + 240
    while time.time() < deadline:
        if log_path.exists():
            time.sleep(2)
            break
        time.sleep(1)

    # Fecha somente o processo lançado por ESTA execução; nunca usa /IM.
    if owned_su.poll() is None:
        owned_su.terminate()

    if log_path.exists():
        print("[furnish-apt] LOG:")
        print(log_path.read_text("utf-8"))
    else:
        print("[furnish-apt] TIMEOUT — SU nao produziu log")
        sys.exit(1)

    # FP-036: gate DETERMINISTICO anti-chapado (nao julga estetica; so 'os moveis tem textura?').
    # Roda no render gerado ANTES de entregar pro veredito do Felipe. FAIL = provavel sem textura.
    fw = None
    if after_iso.exists():
        try:
            from tools.validation.flat_white_gate import flat_white_check
            fw = flat_white_check(after_iso, os.environ.get("FURNISH_STYLE"))
            print(f"\n[furnish-apt] flat_white_check({after_iso.name}) => {fw['result']}")
            for line in fw.get("fails", []) + fw.get("warns", []):
                print(f"    {line}")
            if fw["result"] == "FAIL":
                print("[furnish-apt] /!\\ render CHAPADO (provavel sem textura) — inspecionar antes do veredito")
        except Exception as e:  # noqa: BLE001
            print(f"[furnish-apt] flat_white_check pulado: {e}")

    # APARENCIA NAO-BLOQUEIA: o .skp canonico + renders JA existem (geracao acima
    # INTACTA). Emite um item de galeria PENDENTE (human_verdict=None) na MESMA
    # galeria do sweep e SEGUE — o veredito de aparencia e' do Felipe, offline, e
    # NUNCA trava o pipeline. Best-effort: falhar aqui nunca derruba o furnish.
    try:
        rec = _emit_furnished_gallery_item(
            after_iso if after_iso.exists() else None,
            skp=skp_out, style=os.environ.get("FURNISH_STYLE"), flat_white=fw)
        print(f"[furnish-apt] item de galeria: {rec['variant_id']} "
              f"=> {rec['verdict']} (human_verdict={rec['human_verdict']})")
    except Exception as e:  # noqa: BLE001 — galeria nunca bloqueia a cozinha/apê
        print(f"[furnish-apt] item de galeria pulado (nao-fatal): {e}")

    print(f"\n[furnish-apt] -> {OUT_DIR}/")
    print(f"  SKP:   {skp_out.name}")
    print(f"  AFTER: {after_top.name} / {after_iso.name}")


if __name__ == "__main__":
    main()
