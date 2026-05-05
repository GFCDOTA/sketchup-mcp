"""Extract SKP fidelity metrics from `tools/inspect_walls_report.rb` output.

The Ruby inspector writes a rich JSON (~35 KB) with materials, layers,
groups, default-face classifications, and wall overlaps. This module
condenses that into the small set of numbers that matter for tracking
SKP fidelity over time:

- ``default_faces_count`` — faces without an assigned material. The
  primary whiteness signal. Should be 0 on a clean build of planta_74
  (see ``docs/validation/skp_fidelity_2026-05-04.md``).
- ``materials_count`` — total materials. The canonical post-fix value
  is 13 for planta_74 (1 wall_dark + 1 parapet + 11 room_r000..r010);
  any extra usually means re-execution without ``reset_model`` or a
  template figure leak (Sree).
- ``wall_overlaps_count`` — auto-overlap signals from the inspector's
  top-20 list. Triplication produces non-zero values.
- ``components_count`` — leftover ComponentInstances (Sree etc.).
- ``groups_count``, ``faces_count`` — totals for sanity-checking.
- ``wall_dark_variant_count`` — number of materials whose name matches
  ``^wall_dark\\d+$`` (the silent rename Sketchup applies when
  ``materials.add`` collides). Should be 0.
- ``sree_material_count`` — number of materials whose name starts with
  ``Sree_``. Should be 0.

Usage:

    from tools.inspect_metrics import FidelityMetrics, compare
    before = FidelityMetrics.from_inspect_report(Path("runs/old/inspect_report.json"))
    after  = FidelityMetrics.from_inspect_report(Path("runs/new/inspect_report.json"))
    print(compare(before, after))

CLI:

    python -m tools.inspect_metrics runs/skp_current_<ts>/inspect_report.json
    python -m tools.inspect_metrics --before runs/old.json --after runs/new.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

WALL_DARK_VARIANT_RE = re.compile(r"^wall_dark\d+$", re.IGNORECASE)
SREE_RE = re.compile(r"^sree_", re.IGNORECASE)


@dataclass(frozen=True)
class FidelityMetrics:
    """Compact fidelity signature of a SKP inspect report."""

    default_faces_count: int
    materials_count: int
    wall_overlaps_count: int
    components_count: int
    groups_count: int
    faces_count: int
    wall_dark_variant_count: int
    sree_material_count: int

    @classmethod
    def from_inspect_report(cls, path: Path) -> "FidelityMetrics":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FidelityMetrics":
        materials = data.get("materials") or []
        groups = data.get("groups") or []
        overlaps = data.get("wall_overlaps_top20") or []
        components = (
            data.get("components")
            or data.get("component_instances")
            or []
        )
        totals = data.get("totals") or {}

        wall_dark_variants = sum(
            1 for m in materials
            if isinstance(m, dict)
            and WALL_DARK_VARIANT_RE.match(str(m.get("name", "")))
        )
        sree_mats = sum(
            1 for m in materials
            if isinstance(m, dict)
            and SREE_RE.match(str(m.get("name", "")))
        )

        return cls(
            default_faces_count=int(data.get("default_faces_count", 0)),
            materials_count=len(materials),
            wall_overlaps_count=len(overlaps),
            components_count=len(components),
            groups_count=len(groups),
            faces_count=int(totals.get("faces", data.get("faces_count", 0))),
            wall_dark_variant_count=wall_dark_variants,
            sree_material_count=sree_mats,
        )

    def is_clean(self) -> bool:
        """True if the build shows no whiteness / triplication / template leak."""
        return (
            self.default_faces_count == 0
            and self.wall_overlaps_count == 0
            and self.components_count == 0
            and self.wall_dark_variant_count == 0
            and self.sree_material_count == 0
        )


def compare(before: FidelityMetrics, after: FidelityMetrics) -> dict[str, dict]:
    """Per-field delta between two metric snapshots."""
    out: dict[str, dict] = {}
    for field, b in asdict(before).items():
        a = asdict(after)[field]
        out[field] = {"before": b, "after": a, "delta": a - b}
    return out


def _format_table(metrics: FidelityMetrics) -> str:
    rows = [
        f"  default_faces_count       {metrics.default_faces_count}",
        f"  materials_count           {metrics.materials_count}",
        f"  wall_overlaps_count       {metrics.wall_overlaps_count}",
        f"  components_count          {metrics.components_count}",
        f"  groups_count              {metrics.groups_count}",
        f"  faces_count               {metrics.faces_count}",
        f"  wall_dark_variant_count   {metrics.wall_dark_variant_count}",
        f"  sree_material_count       {metrics.sree_material_count}",
        f"  -> is_clean: {metrics.is_clean()}",
    ]
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("report", nargs="?", type=Path,
                    help="path to inspect_report.json")
    ap.add_argument("--before", type=Path,
                    help="path to baseline inspect_report.json (for compare)")
    ap.add_argument("--after", type=Path,
                    help="path to current inspect_report.json (for compare)")
    args = ap.parse_args(argv)

    if args.before and args.after:
        b = FidelityMetrics.from_inspect_report(args.before)
        a = FidelityMetrics.from_inspect_report(args.after)
        print(f"before: {args.before}")
        print(_format_table(b))
        print(f"\nafter:  {args.after}")
        print(_format_table(a))
        print("\ndelta:")
        for k, v in compare(b, a).items():
            sign = "+" if v["delta"] > 0 else ""
            print(f"  {k:<26} {v['before']} -> {v['after']}  ({sign}{v['delta']})")
        return 0

    if args.report is None:
        ap.error("either positional REPORT or both --before and --after required")

    m = FidelityMetrics.from_inspect_report(args.report)
    print(f"report: {args.report}")
    print(_format_table(m))
    return 0 if m.is_clean() else 1


if __name__ == "__main__":
    sys.exit(main())
