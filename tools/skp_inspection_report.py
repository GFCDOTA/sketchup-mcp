"""skp_inspection_report.py — Stage 1.6 inspector v2 reader.

Exposes the schema-1.0 fields written by the modified
``tools/inspect_walls_report.rb``:

  - ``schema_version``                  ("1.0")
  - ``meta.skp_sha256`` + ``skp_size_bytes``
  - ``meta.consensus_path`` + ``consensus_sha256`` (when env set on
    inspector launch)
  - ``structural.{default_faces_count, materials_count,
                  wall_overlaps_count, components_count,
                  groups_by_layer}``
  - ``bounds_check.{skp_bbox_in, consensus_bbox_pt,
                    scaled_consensus_bbox_in, delta_in,
                    within_tol_in, delta_within_tol}``

Stage 1.6 boundary:
  - DOES NOT mutate the report file.
  - DOES NOT modify consensus / SKP / Ruby — only reads.
  - DOES NOT call SU; receives a JSON written by an earlier inspector run.
  - DOES NOT call any LLM.

CLI:

    python -m tools.skp_inspection_report runs/<run>/inspect_report.json

Default exit code 0. Pass ``--strict`` to exit 2 when:
  - schema_version != "1.0"
  - meta.skp_sha256 is null (file unreachable)
  - structural.default_faces_count > 0
  - structural.wall_overlaps_count > 0
  - structural.components_count > 0
  - bounds_check exists AND delta_within_tol is False
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

INSPECTION_REPORT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class InspectionReport:
    schema_version: str
    skp_path: str | None
    skp_sha256: str | None
    skp_size_bytes: int | None
    sketchup_version: str | None
    consensus_path: str | None
    consensus_sha256: str | None
    default_faces_count: int
    materials_count: int
    wall_overlaps_count: int
    components_count: int
    groups_by_layer: dict[str, int] = field(default_factory=dict)
    bounds_check: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_path(cls, path: Path | str) -> "InspectionReport":
        return cls.from_dict(
            json.loads(Path(path).read_text(encoding="utf-8"))
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InspectionReport":
        meta = data.get("meta") or {}
        structural = data.get("structural") or {}
        groups = data.get("groups") or []
        materials = data.get("materials") or []
        overlaps = data.get("wall_overlaps_top20") or []
        # Fallbacks let this parse legacy v0 reports too.
        return cls(
            schema_version=str(data.get("schema_version", "0")),
            skp_path=meta.get("skp_path"),
            skp_sha256=meta.get("skp_sha256"),
            skp_size_bytes=meta.get("skp_size_bytes"),
            sketchup_version=meta.get("sketchup_version"),
            consensus_path=meta.get("consensus_path"),
            consensus_sha256=meta.get("consensus_sha256"),
            default_faces_count=int(structural.get(
                "default_faces_count",
                data.get("default_faces_count", 0),
            )),
            materials_count=int(structural.get(
                "materials_count", len(materials),
            )),
            wall_overlaps_count=int(structural.get(
                "wall_overlaps_count", len(overlaps),
            )),
            components_count=int(structural.get(
                "components_count",
                sum(1 for g in groups
                    if isinstance(g, dict)
                    and g.get("kind") == "ComponentInstance"),
            )),
            groups_by_layer=dict(structural.get("groups_by_layer", {})),
            bounds_check=data.get("bounds_check"),
            raw=data,
        )

    def is_v2(self) -> bool:
        return self.schema_version == INSPECTION_REPORT_SCHEMA_VERSION

    def is_clean(self) -> bool:
        bounds_ok = (
            self.bounds_check is None
            or bool(self.bounds_check.get("delta_within_tol"))
        )
        return (
            self.default_faces_count == 0
            and self.wall_overlaps_count == 0
            and self.components_count == 0
            and bounds_ok
        )

    def strict_blockers(self) -> list[str]:
        blockers: list[str] = []
        if not self.is_v2():
            blockers.append(
                f"schema_version={self.schema_version!r} (expected '1.0')"
            )
        if self.skp_sha256 is None:
            blockers.append("meta.skp_sha256 is null")
        if self.default_faces_count > 0:
            blockers.append(
                f"default_faces_count={self.default_faces_count} > 0"
            )
        if self.wall_overlaps_count > 0:
            blockers.append(
                f"wall_overlaps_count={self.wall_overlaps_count} > 0"
            )
        if self.components_count > 0:
            blockers.append(
                f"components_count={self.components_count} > 0"
            )
        if self.bounds_check is not None and not bool(
                self.bounds_check.get("delta_within_tol")
        ):
            blockers.append(
                f"bounds_check.delta_within_tol=False "
                f"(delta_in={self.bounds_check.get('delta_in')})"
            )
        return blockers


def _format_summary(r: InspectionReport) -> str:
    lines = [
        f"  schema_version          {r.schema_version}",
        f"  skp_sha256              {(r.skp_sha256 or 'null')[:12]}...",
        f"  skp_size_bytes          {r.skp_size_bytes}",
        f"  default_faces_count     {r.default_faces_count}",
        f"  materials_count         {r.materials_count}",
        f"  wall_overlaps_count     {r.wall_overlaps_count}",
        f"  components_count        {r.components_count}",
        f"  groups_by_layer         {r.groups_by_layer}",
    ]
    if r.bounds_check:
        lines.append(
            f"  bounds_within_tol       {r.bounds_check.get('delta_within_tol')}"
        )
    lines.append(f"  -> is_clean:            {r.is_clean()}")
    return "\n".join(lines)


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Stage 1.6 inspector v2 reader. Surfaces the "
                    "schema-1.0 fields and reports is_clean status."
    )
    p.add_argument("report", type=Path, help="path to inspect_report.json")
    p.add_argument("--strict", action="store_true",
                    help="exit non-zero if any structural blocker is "
                         "present (default: always exit 0)")
    args = p.parse_args(argv)

    report = InspectionReport.from_path(args.report)
    print(f"report: {args.report}")
    print(_format_summary(report))
    blockers = report.strict_blockers()
    if blockers:
        print("\nstrict-mode blockers:")
        for b in blockers:
            print(f"  - {b}")
    if args.strict and blockers:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(_main())
