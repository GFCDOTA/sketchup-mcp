"""Apply human-painted walls to a consensus_model.json.

Adds each wall in ``human_walls_truth.json`` to ``consensus.walls``
with ``geometry_origin="human_annotation"``. Then re-runs the
``polygonize_rooms`` step so the rooms reform around the augmented
wall set — this is what splits merged cells.

Default mode is ``additive``: human walls APPEND to the existing
wall list. Use ``--mode replace-rooms`` to also rebuild
``consensus.rooms`` from scratch using polygonize after applying the
new walls. Default is ``append`` (no room rebuild) so the operator
can inspect the diff first; pipeline run normally uses ``polygonize``.

Companion: ``tools/extract_human_walls.py``,
``tools/render_human_walls_annotation_base.py``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))


def apply_walls_to_consensus(consensus: dict,
                               walls_truth: dict,
                               rebuild_rooms: bool = True,
                               labels: list[dict] | None = None) -> dict:
    """Return a new consensus dict with human walls applied + (optional)
    rooms rebuilt via polygonize. Does NOT mutate inputs.

    ``labels`` are the ORIGINAL per-room seeds (from extract_room_labels).
    When provided AND ``rebuild_rooms`` is True, polygonize re-runs with
    one seed per room name — this is what lets a previously-merged cell
    split into its constituent rooms once augmented walls form closed
    loops. Without labels, the rebuild collapses all original labels to
    the merged cell's single seed and polygonize can't tell the rooms
    apart.
    """
    out = dict(consensus)
    existing_walls = list(out.get("walls", []))
    n_existing = len(existing_walls)
    new_walls: list[dict] = []
    for i, src in enumerate(walls_truth.get("walls", [])):
        w = {
            "id": src.get("id", f"h_w{i:03d}"),
            "start": list(src["start"]),
            "end": list(src["end"]),
            "thickness": float(src.get("thickness",
                                         out.get("wall_thickness_pts", 5.4))),
            "orientation": src["orientation"],
            "geometry_origin": "human_annotation",
            "human_annotation": {
                "source_image": walls_truth.get("source_image"),
                "color": src.get("color"),
                "bbox_px": src.get("bbox_px"),
                "bbox_pts": src.get("bbox_pts"),
            },
        }
        new_walls.append(w)
    out["walls"] = existing_walls + new_walls

    # Rebuild rooms via polygonize (the whole point of adding walls)
    if rebuild_rooms and new_walls:
        from rooms_from_seeds import detect_rooms_polygonize
        rebuild_labels: list[dict] = []
        if labels:
            # Use the original per-room labels (preferred path).
            rebuild_labels = list(labels)
        else:
            # Fallback: synthesise from existing rooms by collapsing
            # merged names to a SHARED seed. This will NOT split merged
            # cells (all child labels resolve to the same polygon).
            for r in out.get("rooms", []):
                sp = r.get("seed_pt")
                if not sp:
                    continue
                name = r.get("name", "")
                for n in name.split("|"):
                    rebuild_labels.append({
                        "id": f"l_{n.strip().lower().replace(' ', '_')}",
                        "name": n.strip(),
                        "seed_pt": sp,
                    })
        rooms = detect_rooms_polygonize(out, rebuild_labels)
        out["rooms"] = rooms

    md = dict(out.get("metadata", {}))
    md["human_walls"] = {
        "applied": True,
        "n_walls_applied": len(new_walls),
        "n_walls_existing_before": n_existing,
        "n_walls_total_after": len(out["walls"]),
        "rebuilt_rooms": rebuild_rooms,
        "source_truth": walls_truth.get("source_image"),
    }
    out["metadata"] = md
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", type=Path, required=True,
                    help="Input consensus (typically consensus_human.json).")
    ap.add_argument("--truth", type=Path, required=True,
                    help="human_walls_truth.json from extract_human_walls.")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--no-rebuild-rooms", action="store_true",
                    help="Skip the room rebuild step (useful for inspecting "
                         "the wall diff before recomputing cells).")
    ap.add_argument("--labels", type=Path, default=None,
                    help="Original labels.json from extract_room_labels. "
                         "Required to actually split merged cells (without "
                         "this the rebuild gives all merged labels the same "
                         "seed and the cells stay merged).")
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text())
    truth = json.loads(args.truth.read_text())
    labels = (json.loads(args.labels.read_text())
              if args.labels and args.labels.exists() else None)
    out = apply_walls_to_consensus(consensus, truth,
                                     rebuild_rooms=not args.no_rebuild_rooms,
                                     labels=labels)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))

    md = out["metadata"]["human_walls"]
    print(f"[apply] walls applied = {md['n_walls_applied']} -> {args.out}")
    print(f"  walls before: {md['n_walls_existing_before']}")
    print(f"  walls after:  {md['n_walls_total_after']}")
    print(f"  rooms after:  {len(out.get('rooms', []))}")
    merged = sum(1 for r in out.get("rooms", []) if "|" in r.get("name", ""))
    print(f"  merged cells after: {merged}")


if __name__ == "__main__":
    main()
