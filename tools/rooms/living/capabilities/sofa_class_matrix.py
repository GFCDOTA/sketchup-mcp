"""sofa_class_matrix.py — FASE 3 do programa de classe: PROVA DE GENERALIZACAO
visual. Gera uma MATRIZ de variantes do sofa derivadas PELA CLASSE
(tools.rooms.living.sofa_class.derive_spec — nada e' ajustado a mao), valida cada uma no
sofa_class_gate + sofa_gate (anatomia), renderiza SU-free (render_parts_iso,
camera 3/4 identica em todas) e monta um GRID unico pro juiz GPT julgar:
identidade de familia, proporcao em escala, degradacao em extremos.

Uso: python -m tools.rooms.living.capabilities.sofa_class_matrix [out_dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from tools.rendering.render_parts_iso import render_parts            # noqa: E402
from tools.rooms.shared.sofa import build_sofa                   # noqa: E402
from tools.rooms.living.sofa_class import derive_spec, sofa_class_gate   # noqa: E402
from tools.rooms.living.validation.sofa_gate import gate as sofa_gate               # noqa: E402

# 9 celulas cobrindo os eixos: arquetipo x lugares x braco x base (+1 chaise).
# Inclui extremos DELIBERADOS (4l chunky, lounge 4l) — degradacao em extremo
# e' exatamente o que o juiz precisa ver.
from tools.rooms.shared.contact_sheet import grid_sheet as _grid_sheet  # noqa: E402,F401  (D-012: implementacao unica em shared)

MATRIX = [
    ("formal-2l-slim-legs", dict(seats=2, archetype="formal", arm_style="slim",
                                 base_style="legs")),
    ("formal-3l-med-plinth", dict(seats=3, archetype="formal", arm_style="medium",
                                  base_style="plinth")),
    ("formal-4l-chunky-legs", dict(seats=4, archetype="formal", arm_style="chunky",
                                   base_style="legs")),
    ("standard-2l-med-legs", dict(seats=2, archetype="standard", arm_style="medium",
                                  base_style="legs")),
    ("standard-3l-med-legs", dict(seats=3, archetype="standard", arm_style="medium",
                                  base_style="legs")),
    ("standard-3l-chaiseR-plinth", dict(seats=3, archetype="standard",
                                        arm_style="medium", base_style="plinth",
                                        variant="chaise_right")),
    ("lounge-2l-chunky-plinth", dict(seats=2, archetype="lounge", arm_style="chunky",
                                     base_style="plinth")),
    ("lounge-3l-slim-legs", dict(seats=3, archetype="lounge", arm_style="slim",
                                 base_style="legs")),
    ("lounge-4l-med-plinth", dict(seats=4, archetype="lounge", arm_style="medium",
                                  base_style="plinth")),
]


def build_matrix(out_dir):
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = []
    cells = []
    for name, kw in MATRIX:
        spec = derive_spec(**kw)
        cls = sofa_class_gate(spec)
        parts, meta = build_sofa(spec)
        anat = sofa_gate(spec, parts)
        png = out / f"cell_{name}.png"
        render_parts(parts, png, elev=22, azim=-55,
                     title=f"{name}  W={spec.width:.2f}m")
        report.append({"cell": name, "params": kw,
                       "width_m": spec.width, "bbox_m": meta["bbox_m"],
                       "class_gate": cls["result"], "class_errors": cls["errors"],
                       "class_warnings": cls["warnings"],
                       "anatomy_gate": anat["result"], "n_parts": meta["n_parts"]})
        cells.append((name, png, cls["result"], anat["result"]))
    sheet = _grid_sheet(cells, out / "sofa_class_matrix.png",
                        "CLASSE SOFA — matriz de generalizacao (derivada por "
                        "arquetipo, zero ajuste manual)")
    (out / "matrix_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"sheet": sheet, "report": report}



def build_matrix_skp(out_skp, cols=3, pitch_x=4.0, pitch_y=3.2):
    """SKP REAL da matriz: as 9 variantes derivadas, em grade no chao (showroom).
    Reusa o provider SU (no-disrupt: pula se SketchUp aberto)."""
    from interior.renderers.render_provider import RenderRequest
    from interior.renderers.sketchup_basic_provider import SketchUpBasicProvider
    from tools.rooms.shared.parts import parts_to_boxes
    boxes = []
    for i, (name, kw) in enumerate(MATRIX):
        spec = derive_spec(**kw)
        parts, _ = build_sofa(spec)
        r, c = divmod(i, cols)
        for b in parts_to_boxes(parts, ox=c * pitch_x, oy=r * pitch_y):
            b["label"] = f"{name}__{b['label']}"
            boxes.append(b)
    prov = SketchUpBasicProvider()
    if not prov.available():
        return {"status": "skipped", "reason": "SU indisponivel"}
    out_skp = Path(out_skp).resolve()
    req = RenderRequest(boxes=boxes, out_skp=str(out_skp), renderer="furniture",
                        label="sofa_class_matrix",
                        renders={"iso": str(out_skp.with_suffix("")) + "_iso.png"})
    res = prov.render(req)
    return {"status": res.status, "skp": res.skp, "renders": res.renders,
            "error": res.error, "n_boxes": len(boxes)}


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "runs/sofa_class/matrix")
    if "--skp" in sys.argv:
        r = build_matrix_skp(Path(d) / "sofa_class_matrix.skp")
        print(json.dumps(r, indent=2))
        sys.exit(0 if r["status"] == "success" else 1)
    res = build_matrix(d)
    print(f"=== matriz da classe sofa: {len(res['report'])} celulas ===")
    for r in res["report"]:
        print(f"  {r['cell']:28} W={r['width_m']:.2f} class={r['class_gate']:4} "
              f"anatomia={r['anatomy_gate']:4} parts={r['n_parts']}")
    print(f"  -> {res['sheet']}")
    bad = [r for r in res["report"]
           if r["class_gate"] == "FAIL" or r["anatomy_gate"] == "FAIL"]
    sys.exit(1 if bad else 0)
