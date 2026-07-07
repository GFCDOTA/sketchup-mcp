"""sofa_venezia_compare.py — MT-SOFA-004: compara o sofá VELHO (caixa) com o NOVO (venezia,
derivado da SOFA_BUILD_SPEC aprovada / LP-SOFA-001). Renderiza SU-free (render_parts_iso, mesma câmera)
e monta um sheet old×new pro veredito VISUAL do GPT (pela ponte). Gates por célula.

Uso: python -m tools.sofa_venezia_compare [out_dir]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.furniture_anatomy_spec import SofaSpec          # noqa: E402
from tools.render_parts_iso import render_parts            # noqa: E402
from tools.sofa_builder import build_sofa                  # noqa: E402
from tools.sofa_class import derive_spec, sofa_class_gate  # noqa: E402
from tools.sofa_class_matrix import _grid_sheet            # noqa: E402
from tools.sofa_gate import gate as sofa_gate              # noqa: E402


def old_box() -> SofaSpec:
    """O sofá-CAIXA que estamos substituindo: braço chunky no topo do encosto, plinto rente ao chão,
    almofada chapada, encosto quase vertical, quinas duras. DEVE falhar o gate de classe (é o anti)."""
    s = SofaSpec(variant="straight", seats=3, width=2.05, depth=0.95, height=0.85,
                 seat_height=0.45, seat_depth=0.55, back_thickness=0.20,
                 arm_width=0.30, arm_height=0.85, foot_height=0.02,
                 cushion_thickness=0.10, cushion_bevel=0.005, backrest_rake=4.0,
                 arm_cap=False, seat_overhang=0.0, base_recess=0.0)
    return s


def main(out_dir: str):
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cases = [
        ("OLD_caixa_3l", old_box()),
        ("NEW_venezia_3l", derive_spec(3, "venezia", "thin", "legs")),
        ("NEW_venezia_2l", derive_spec(2, "venezia", "thin", "legs")),
    ]
    cells, report = [], []
    for name, spec in cases:
        cls = sofa_class_gate(spec)
        parts, meta = build_sofa(spec)
        anat = sofa_gate(spec, parts)
        png = out / f"{name}.png"
        render_parts(parts, png, elev=22, azim=-55, title=f"{name}  W={spec.width:.2f}m")
        cells.append((name, png, cls["result"], anat["result"]))
        report.append({"name": name, "width_m": round(spec.width, 3), "bbox_m": meta["bbox_m"],
                       "class_gate": cls["result"], "class_errors": cls["errors"][:3],
                       "anatomy_gate": anat["result"], "n_parts": meta["n_parts"]})
    sheet = _grid_sheet(cells, out / "sofa_venezia_compare.png",
                        "SOFA — velho-caixa x novo (venezia, SOFA_BUILD_SPEC aprovado / LP-SOFA-001)")
    (out / "compare_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return sheet, report


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "artifacts/review/furniture/sofa/venezia")
    sheet, report = main(d)
    print("=== sofa venezia: velho-caixa x novo ===")
    for r in report:
        print(f"  {r['name']:16} W={r['width_m']:.2f} class={r['class_gate']:4} "
              f"anat={r['anatomy_gate']:4} parts={r['n_parts']}")
    print(f"  -> {sheet}")
