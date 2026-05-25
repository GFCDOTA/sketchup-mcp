"""Re-classify ``geometry_origin=human_annotation`` openings against
the LIVE wall set.

The post-walls / post-soft-barriers consensus on planta_74 carried
stale ``wall_id`` + ``host_mode`` fields on some openings (e.g.
``h_o005`` pointing at ``w022`` while the actual host is
``h_w000``). The opening positions / bboxes themselves are correct —
the stale fields are an artifact of the wall set having grown after
the openings were first applied.

This tool re-runs the existing classifier
(``apply_human_openings.classify_opening_host_segment``) against
the current ``consensus.walls`` and updates each affected opening's
``wall_id`` + ``host_mode`` in place. Nothing else is invented —
the bbox + center / width / hinge_side are NOT touched, so the
fix is a pure host re-association, not a geometric claim.

Tag added per opening when the host changes:
``"_host_reclassified_at"`` (ISO timestamp) and ``"_host_was"``
(the previous ``{wall_id, host_mode}`` pair) so the audit trail
survives.

Usage::

    python -m tools.reclassify_human_openings \\
        --consensus fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \\
        --out fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \\
        [--dry-run]
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _derived_orientation(bbox_pts: list[float] | None,
                          fallback: str | None) -> str:
    if bbox_pts and len(bbox_pts) == 4:
        x0, y0, x1, y1 = bbox_pts
        return "h" if (x1 - x0) >= (y1 - y0) else "v"
    return fallback or "h"


def reclassify(consensus: dict, *, verbose: bool = False) -> dict:
    """Return a copy of ``consensus`` with re-classified human
    annotation openings + a summary block at
    ``metadata.host_reclassification``.
    """
    from apply_human_openings import classify_opening_host_segment

    out = copy.deepcopy(consensus)
    walls = out.get("walls", [])
    thickness = float(out.get("wall_thickness_pts") or 5.4)
    changes: list[dict] = []
    for op in out.get("openings", []):
        if op.get("geometry_origin") != "human_annotation":
            continue
        ann = op.get("human_annotation") or {}
        bbox_pts = ann.get("bbox_pts")
        if not bbox_pts:
            continue
        entry = {
            "bbox_pts": bbox_pts,
            "center_pts": op.get("center"),
            "opening_width_pts": op.get("opening_width_pts", 0),
            "orientation": op.get("orientation")
                or _derived_orientation(bbox_pts, None),
        }
        result = classify_opening_host_segment(entry, walls, thickness)
        new_mode = result.get("mode")
        new_host = result.get("host_wall_id")
        old_mode = op.get("host_mode")
        old_host = op.get("wall_id")
        if new_mode == old_mode and new_host == old_host:
            continue
        op["_host_was"] = {"wall_id": old_host, "host_mode": old_mode}
        op["_host_reclassified_at"] = _now_iso()
        op["host_mode"] = new_mode
        if new_host:
            op["wall_id"] = new_host
        changes.append({
            "opening_id": op.get("id"),
            "kind_v5": op.get("kind_v5"),
            "old": {"wall_id": old_host, "host_mode": old_mode},
            "new": {"wall_id": new_host, "host_mode": new_mode},
            "shift_pt": result.get("shift_pt"),
        })
        if verbose:
            print(
                f"  {op.get('id')}: {old_mode}@{old_host} -> "
                f"{new_mode}@{new_host} (shift {result.get('shift_pt')}pt)"
            )
    metadata = out.setdefault("metadata", {})
    metadata["host_reclassification"] = {
        "run_at": _now_iso(),
        "n_openings_inspected": sum(
            1 for o in out.get("openings", [])
            if o.get("geometry_origin") == "human_annotation"
        ),
        "n_changed": len(changes),
        "changes": changes,
    }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="reclassify_human_openings",
        description=(
            "Re-run the host classifier on every human_annotation "
            "opening + update wall_id + host_mode in place. "
            "Geometric claims (bbox, center, hinge_side) are NOT "
            "touched — this is a host re-association only."
        ),
    )
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the diff without writing --out.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    if not args.consensus.exists():
        print(f"[reclassify] consensus not found: {args.consensus}",
              file=sys.stderr)
        return 2
    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))
    out = reclassify(consensus, verbose=args.verbose)
    summary = out["metadata"]["host_reclassification"]
    print(f"[reclassify] inspected={summary['n_openings_inspected']} "
          f"changed={summary['n_changed']}")
    for ch in summary["changes"]:
        print(
            f"  {ch['opening_id']:>8}: "
            f"{ch['old']['host_mode']}@{ch['old']['wall_id']} -> "
            f"{ch['new']['host_mode']}@{ch['new']['wall_id']} "
            f"(shift {ch.get('shift_pt')})"
        )
    if args.dry_run:
        print("[reclassify] --dry-run: NOT writing --out")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[wrote] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
