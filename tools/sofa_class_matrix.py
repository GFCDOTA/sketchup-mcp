"""sofa_class_matrix.py — FASE 3 do programa de classe: PROVA DE GENERALIZACAO
visual. Gera uma MATRIZ de variantes do sofa derivadas PELA CLASSE
(tools/sofa_class.derive_spec — nada e' ajustado a mao), valida cada uma no
sofa_class_gate + sofa_gate (anatomia), renderiza SU-free (render_parts_iso,
camera 3/4 identica em todas) e monta um GRID unico pro juiz GPT julgar:
identidade de familia, proporcao em escala, degradacao em extremos.

Uso: python -m tools.sofa_class_matrix [out_dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.render_parts_iso import render_parts            # noqa: E402
from tools.sofa_builder import build_sofa                   # noqa: E402
from tools.sofa_class import derive_spec, sofa_class_gate   # noqa: E402
from tools.sofa_gate import gate as sofa_gate               # noqa: E402

# 9 celulas cobrindo os eixos: arquetipo x lugares x braco x base (+1 chaise).
# Inclui extremos DELIBERADOS (4l chunky, lounge 4l) — degradacao em extremo
# e' exatamente o que o juiz precisa ver.
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


def _grid_sheet(cells, out_png, title, cols=3):
    """Grade NxM com label por celula (o _contact_sheet existente e' linear)."""
    from PIL import Image, ImageDraw
    CELL_W, BAND, GAP, HEAD = 480, 26, 10, 40
    tiles = []
    for name, path, cls_r, anat_r in cells:
        im = Image.open(path).convert("RGB")
        h = int(im.height * CELL_W / im.width)
        tiles.append((f"{name} [{cls_r}/{anat_r}]", im.resize((CELL_W, h))))
    rows = (len(tiles) + cols - 1) // cols
    cell_h = max(t.height for _, t in tiles) + BAND
    W = cols * CELL_W + GAP * (cols + 1)
    H = HEAD + rows * (cell_h + GAP) + GAP
    sheet = Image.new("RGB", (W, H), (246, 244, 240))
    dr = ImageDraw.Draw(sheet)
    dr.text((GAP, 12), title, fill=(40, 38, 36))
    for i, (label, t) in enumerate(tiles):
        r, c = divmod(i, cols)
        x = GAP + c * (CELL_W + GAP)
        y = HEAD + r * (cell_h + GAP)
        dr.text((x + 2, y + 4), label, fill=(90, 86, 80))
        sheet.paste(t, (x, y + BAND))
    sheet.save(out_png)
    return str(out_png)


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "runs/sofa_class/matrix")
    res = build_matrix(d)
    print(f"=== matriz da classe sofa: {len(res['report'])} celulas ===")
    for r in res["report"]:
        print(f"  {r['cell']:28} W={r['width_m']:.2f} class={r['class_gate']:4} "
              f"anatomia={r['anatomy_gate']:4} parts={r['n_parts']}")
    print(f"  -> {res['sheet']}")
    bad = [r for r in res["report"]
           if r["class_gate"] == "FAIL" or r["anatomy_gate"] == "FAIL"]
    sys.exit(1 if bad else 0)
