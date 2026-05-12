"""Apply human-painted soft barriers to a consensus_model.json.

Mirror of ``tools/apply_human_walls.py`` but appends to
``consensus.soft_barriers`` instead of ``consensus.walls``. Then re-
runs polygonize so the cell graph reforms around the augmented
soft_barrier set — peitoris act as splitting geometry (PR #112).

Per user mandate 2026-05-12: "Human_wall azul só deve representar
parede/drywall/alvenaria real. ... criar protocolo human_soft_barrier,
não pedir pintura azul." A soft_barrier protocol exists precisely so
the operator can close cells that need a low parapet/peitoril without
upgrading those barriers to full 3D walls.

Companion: ``tools/extract_human_soft_barriers.py``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))


def apply_soft_barriers_to_consensus(consensus: dict,
                                       barriers_truth: dict,
                                       rebuild_rooms: bool = True,
                                       labels: list[dict] | None = None
                                       ) -> dict:
    """Append human soft barriers + optionally re-polygonize.

    Mirrors apply_walls_to_consensus contract: pure function, returns
    new consensus dict. ``labels`` are the original per-room seeds
    from extract_room_labels.py — required to actually split merged
    cells (same caveat as walls).
    """
    out = dict(consensus)
    existing = list(out.get("soft_barriers", []))
    n_existing = len(existing)
    new: list[dict] = []
    for i, src in enumerate(barriers_truth.get("soft_barriers", [])):
        b = {
            "id": src.get("id", f"h_sb{i:03d}"),
            "barrier_type": src.get("barrier_type", "peitoril"),
            "polyline_pts": [list(p) for p in src["polyline_pts"]],
            "height_m": float(src.get("height_m", 1.10)),
            "orientation": src.get("orientation", "h"),
            "geometry_origin": "human_annotation",
            "human_annotation": {
                "source_image": barriers_truth.get("source_image"),
                "color": src.get("color"),
                "bbox_px": src.get("bbox_px"),
                "bbox_pts": src.get("bbox_pts"),
            },
        }
        new.append(b)
    out["soft_barriers"] = existing + new

    if rebuild_rooms and new:
        from rooms_from_seeds import detect_rooms_polygonize
        rebuild_labels: list[dict] = list(labels) if labels else []
        if not rebuild_labels:
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
        out["rooms"] = detect_rooms_polygonize(out, rebuild_labels)

    md = dict(out.get("metadata", {}))
    md["human_soft_barriers"] = {
        "applied": True,
        "n_barriers_applied": len(new),
        "n_barriers_existing_before": n_existing,
        "n_barriers_total_after": len(out["soft_barriers"]),
        "rebuilt_rooms": rebuild_rooms,
        "source_truth": barriers_truth.get("source_image"),
    }
    out["metadata"] = md
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True,
                    help="human_soft_barriers_truth.json from "
                         "extract_human_soft_barriers.")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--labels", type=Path, default=None)
    ap.add_argument("--no-rebuild-rooms", action="store_true")
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text())
    truth = json.loads(args.truth.read_text())
    labels = (json.loads(args.labels.read_text())
              if args.labels and args.labels.exists() else None)
    out = apply_soft_barriers_to_consensus(
        consensus, truth,
        rebuild_rooms=not args.no_rebuild_rooms,
        labels=labels,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))

    md = out["metadata"]["human_soft_barriers"]
    print(f"[apply] soft_barriers applied = {md['n_barriers_applied']} "
          f"-> {args.out}")
    print(f"  soft_barriers before: {md['n_barriers_existing_before']}")
    print(f"  soft_barriers after:  {md['n_barriers_total_after']}")
    print(f"  rooms after:          {len(out.get('rooms', []))}")
    merged = sum(1 for r in out.get("rooms", [])
                  if "|" in r.get("name", ""))
    print(f"  merged cells after:   {merged}")


if __name__ == "__main__":
    main()
