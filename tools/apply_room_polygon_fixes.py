"""Apply Frente-3 room-polygon fixes to an existing consensus.

Two opt-in layers, applied in order:

  1. **Near-miss soft_barrier extension** (``--extend-near-miss-sbs``).
     For each soft_barrier that survives the FP-006 wall-overlap gate
     AND has a semantic origin (``human_annotation`` or
     ``barrier_type in {peitoril, mureta, guarda_corpo, esquadria,
     parapet}``), probe each polyline endpoint for a near-miss
     extension within ``--near-miss-gap-tol-pt`` (default 8 pt).
     The extension is APPLIED only if a downstream polygonize check
     confirms it changes cell topology (delta ≥ 1 cell OR a baseline
     suspicious cell shrinks by ≥ 20%). Rejected candidates are still
     written to the provenance log with ``applied=False`` so the audit
     trail shows what was tried.

  2. **Voronoi sub-division of merged-seed cells** (``--voronoi-subdivide``).
     When ``polygonize_rooms`` returns a cell containing >1 seed
     (the ``seeds_share_cell`` case), split the cell by a bounded
     Voronoi tessellation of the seed positions. Each Voronoi region
     is clipped against the cell polygon, so every sub-polygon is
     strictly contained in the original cell. Produces ONE room per
     seed instead of one merged room per cell.

Conservative defaults: BOTH layers are opt-in. Without flags this
tool is a strict no-op on the consensus (it still rewrites
metadata.rooms_from_seeds to reflect the run, which is what the
production pipeline does too).

Outputs:

  - ``--out`` (or in-place): rewritten consensus.
  - ``--provenance-out`` (default: <out>.fix_provenance.json): JSON
    log with ``soft_barrier_extension`` (list) + ``voronoi_subdivision``
    (list) + ``room_count_before`` + ``room_count_after``.

This tool does NOT touch ``tools/consume_consensus.rb``, the production
exporter, the SCHEMA, or any threshold. It re-runs
``rooms_from_seeds.detect_rooms_polygonize`` with the optional
guardrails and writes the new ``rooms`` array. The fix is fully
reversible: ``git checkout consensus.json`` (or use ``--out``).

Companion docs: ``docs/adr/ADR-003-plan-shell-exporter.md`` §12,
``docs/learning/failure_patterns.md`` FP-016 (when fix lands).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.rooms_from_seeds import detect_rooms_polygonize


def _reconstruct_labels_from_rooms(rooms: list[dict]) -> list[dict]:
    """Reconstruct a labels list from an existing consensus.rooms[].

    Each room contributes ONE label (single-seed rooms) OR multiple
    labels (rooms with merged_seeds). The label dict carries the
    minimum the rooms_from_seeds detector needs: ``id``, ``name``,
    ``seed_pt``. ``id`` falls back to ``r{idx}_l{idx}`` if neither
    ``label_id`` nor ``label_ids`` are present.
    """
    labels: list[dict] = []
    for r in rooms:
        name = r.get("name", "") or ""
        seed = r.get("seed_pt")
        if " | " in name and r.get("merged_seeds"):
            names = name.split(" | ")
            seeds = r["merged_seeds"]
            ids = r.get("label_ids") or [None] * len(names)
            for n, sp, lid in zip(names, seeds, ids):
                labels.append({
                    "id": lid or f"{r.get('id', 'r')}_{n[:6]}",
                    "name": n,
                    "seed_pt": list(sp),
                })
        elif seed:
            labels.append({
                "id": r.get("label_id") or r.get("id"),
                "name": name,
                "seed_pt": list(seed),
            })
    return labels


def apply(consensus: dict, *, extend_near_miss_sbs: bool = False,
          near_miss_gap_tol_pt: float = 8.0,
          near_miss_require_semantic: bool = True,
          voronoi_subdivide_merged_cells: bool = False,
          door_min_pts: float = 15.0,
          door_max_pts: float = 150.0,
          envelope_margin_pts: float = 2.0,
          min_room_area_factor: float = 12.0,
          ) -> tuple[dict, dict[str, Any]]:
    """Apply room-polygon fixes to a consensus in-place (returns a
    shallow copy with rewritten ``rooms``). Returns (consensus_new,
    provenance_dict).
    """
    rooms_before = consensus.get("rooms", [])
    labels = _reconstruct_labels_from_rooms(rooms_before)

    ext_prov: list[dict] = []
    vor_prov: list[dict] = []
    new_rooms = detect_rooms_polygonize(
        consensus, labels,
        door_min=door_min_pts, door_max=door_max_pts,
        envelope_margin_pts=envelope_margin_pts,
        min_room_area_factor=min_room_area_factor,
        extend_near_miss_sbs=extend_near_miss_sbs,
        near_miss_gap_tol_pt=near_miss_gap_tol_pt,
        near_miss_require_semantic=near_miss_require_semantic,
        voronoi_subdivide_merged_cells=voronoi_subdivide_merged_cells,
        extension_provenance_out=ext_prov,
        voronoi_provenance_out=vor_prov,
    )

    new_consensus = dict(consensus)
    new_consensus["rooms"] = new_rooms
    # Stamp the run into metadata so downstream can tell which fixes
    # ran. Stays inside the existing schema-additive convention.
    md = dict(consensus.get("metadata") or {})
    fix_record = md.get("room_polygon_fixes") or {}
    fix_record.update({
        "tool": "apply_room_polygon_fixes",
        "extend_near_miss_sbs": extend_near_miss_sbs,
        "near_miss_gap_tol_pt": near_miss_gap_tol_pt,
        "near_miss_require_semantic": near_miss_require_semantic,
        "voronoi_subdivide_merged_cells": voronoi_subdivide_merged_cells,
        "applied_extensions": [p for p in ext_prov if p.get("applied")],
        "rejected_extensions": [p for p in ext_prov if not p.get("applied")],
        "voronoi_subdivisions": vor_prov,
        "rooms_before": len(rooms_before),
        "rooms_after": len(new_rooms),
    })
    md["room_polygon_fixes"] = fix_record
    new_consensus["metadata"] = md

    provenance = {
        "soft_barrier_extension": ext_prov,
        "voronoi_subdivision": vor_prov,
        "rooms_before": len(rooms_before),
        "rooms_after": len(new_rooms),
        "rooms_names_before": [r.get("name") for r in rooms_before],
        "rooms_names_after": [r.get("name") for r in new_rooms],
    }
    return new_consensus, provenance


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("consensus", type=Path,
                    help="path to consensus_model.json (with rooms[] already populated)")
    ap.add_argument("--out", type=Path,
                    help="output consensus path (default: overwrite input)")
    ap.add_argument("--provenance-out", type=Path,
                    help="provenance JSON output path (default: <out>.fix_provenance.json)")
    ap.add_argument("--extend-near-miss-sbs", action="store_true",
                    help="Enable Layer 1: extend near-miss soft_barrier polylines.")
    ap.add_argument("--near-miss-gap-tol-pt", type=float, default=8.0,
                    help="Max endpoint extension distance, in PDF points.")
    ap.add_argument("--no-semantic-guard", action="store_true",
                    help="Disable the semantic-origin guard (allows extending SBs "
                         "without geometry_origin=human_annotation or "
                         "barrier_type in {peitoril/mureta/...}). USE WITH CAUTION.")
    ap.add_argument("--voronoi-subdivide", action="store_true",
                    help="Enable Layer 2: Voronoi sub-division of cells containing "
                         "multiple seed labels (seeds_share_cell case).")
    ap.add_argument("--door-min", type=float, default=15.0)
    ap.add_argument("--door-max", type=float, default=150.0)
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))
    new_consensus, provenance = apply(
        consensus,
        extend_near_miss_sbs=args.extend_near_miss_sbs,
        near_miss_gap_tol_pt=args.near_miss_gap_tol_pt,
        near_miss_require_semantic=not args.no_semantic_guard,
        voronoi_subdivide_merged_cells=args.voronoi_subdivide,
        door_min_pts=args.door_min,
        door_max_pts=args.door_max,
    )
    out_path = args.out or args.consensus
    out_path.write_text(json.dumps(new_consensus, indent=2), encoding="utf-8")
    prov_path = args.provenance_out or out_path.with_suffix(out_path.suffix + ".fix_provenance.json")
    prov_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")

    print(f"[ok] rooms_before={provenance['rooms_before']} "
          f"rooms_after={provenance['rooms_after']}")
    n_applied = sum(1 for p in provenance["soft_barrier_extension"]
                    if p.get("applied"))
    n_rejected = sum(1 for p in provenance["soft_barrier_extension"]
                     if not p.get("applied"))
    print(f"     SB extensions: applied={n_applied}, rejected={n_rejected}")
    print(f"     Voronoi subdivisions: {len(provenance['voronoi_subdivision'])}")
    print(f"     wrote consensus -> {out_path}")
    print(f"     wrote provenance -> {prov_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
