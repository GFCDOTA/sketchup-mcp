"""sofa_furnish_fase1_compare.py — BEFORE/AFTER do sofa da SALA (laco classe->.skp).

ANTES = heuristica antiga do furnish_apartment (sofa_spec manual, lugares = 3 se
w>=2.0 senao 2 — estica per_seat pra fora da classe). DEPOIS = Fase 1
(derive_living_sofa: a CLASSE escolhe os lugares + arquetipo VENEZIA curado pelo
Felipe). SU-free (render_parts_iso, mesma camera) -> sheet 2x2 pro veredito VISUAL.

Uso: python -m tools.sofa_furnish_fase1_compare [out_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.furniture_anatomy_spec import sofa_spec               # noqa: E402
from tools.render_parts_iso import render_parts                  # noqa: E402
from tools.sofa_builder import build_sofa                        # noqa: E402
from tools.sofa_class import derive_living_sofa, sofa_class_gate  # noqa: E402
from tools.sofa_class_matrix import _grid_sheet                  # noqa: E402

WIDTHS = (1.90, 2.80)   # nichos onde a heuristica antiga REPROVA a classe


def _old_furnish(width):
    seats = 3 if width >= 2.0 else 2
    return sofa_spec("straight", seats=seats, width=width, depth=0.95)


def _per_seat(s):
    return (s.width - 2 * s.arm_width) / s.seats


def main(out_dir):
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cells, report = [], []
    for w in WIDTHS:
        for tag, spec in (("ANTES_heuristica", _old_furnish(w)),
                          ("DEPOIS_venezia", derive_living_sofa(w))):
            parts, _ = build_sofa(spec)
            g = sofa_class_gate(spec, parts)
            name = f"{tag}_{w:.2f}m_{spec.seats}lug"
            png = out / f"{name}.png"
            render_parts(parts, png, elev=22, azim=-55,
                         title=f"{tag}  W={spec.width:.2f}m  {spec.seats}lug  "
                               f"per_seat={_per_seat(spec):.2f}  [{g['result']}]")
            cells.append((name, str(png), g["result"], ""))
            report.append((name, round(_per_seat(spec), 3), g["result"]))
    sheet = _grid_sheet(
        cells, out / "sofa_furnish_fase1_compare.png",
        "SOFA DA SALA — ANTES (heuristica: per_seat fora da classe) x "
        "DEPOIS (Fase 1: classe escolhe lugares + venezia curado)", cols=2)
    return sheet, report


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "artifacts/review/furniture/sofa/fase1")
    sheet, report = main(d)
    print("=== sofa da sala: ANTES x DEPOIS (Fase 1) ===")
    for n, ps, r in report:
        print(f"  {n:30} per_seat={ps:.3f}  class={r}")
    print(f"  -> {sheet}")
