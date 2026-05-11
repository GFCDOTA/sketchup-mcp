"""Apply human openings truth to a consensus_model.json.

Loads a ``human_openings_truth.json`` (per the schema in
``fixtures/planta_74/human_openings_truth.schema.json``) and writes it
into ``consensus.openings`` as the canonical source for the SKP export.

By default the human truth REPLACES the openings list (mode=replace).
Use ``--mode merge`` to keep non-human openings and append the human
ones; useful when the detector found extra non-required openings that
should also render.

Every emitted opening carries ``geometry_origin="human_annotation"`` so
the Ruby exporter's ``CARVING_OPENING_ORIGINS`` list (PR #111) carves
the wall correctly.

Companion: ``tools/extract_human_openings.py``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def apply_truth_to_consensus(consensus: dict,
                              truth: dict,
                              mode: str = "replace") -> dict:
    """Return a new consensus dict with human openings applied.
    Does NOT mutate the input dicts.
    """
    out = dict(consensus)
    walls_by_id = {w["id"]: w for w in out.get("walls", [])}
    human_openings: list[dict] = []
    for i, src in enumerate(truth.get("openings", [])):
        wall_id = src.get("wall_id")
        wall = walls_by_id.get(wall_id) if wall_id else None
        # When the image-derived orientation is ambiguous (square-ish
        # blob) and we matched a wall, the wall's orientation wins.
        # (Held here only for documentation; not part of the emitted
        # opening — Ruby reads wall.orientation directly via wall_id.)
        _ = (wall["orientation"]
             if wall and wall.get("orientation")
             else src.get("orientation"))
        center = src.get("center_pts", [0.0, 0.0])
        # Default hinge_side = "left" (the Ruby exporter falls back to
        # "left" when missing; reviewer can edit truth JSON to flip).
        hinge_side = src.get("hinge_side", "left")
        kind = src["kind"]
        kind_v5 = kind  # for planta_74 the canonical kind matches kind_v5
        op = {
            "id": f"h_o{i:03d}",
            "kind": "door" if kind == "interior_door" else (
                "window" if kind in ("window", "glazed_balcony") else "door"
            ),
            "kind_v5": kind_v5,
            "kind_v5_reason": "human_annotation_truth_file",
            "geometry_origin": "human_annotation",
            "confidence": 1.0,
            "decision": "clean",
            "required": True,
            "wall_id": wall_id,
            "center": list(center),
            "opening_width_pts": float(src.get("opening_width_pts", 0)),
            "hinge_side": hinge_side,
            "human_annotation": {
                "source_image": truth.get("source_image"),
                "bbox_px": src.get("bbox_px"),
                "bbox_pts": src.get("bbox_pts"),
                "color": src.get("color"),
            },
        }
        human_openings.append(op)

    if mode == "replace":
        out["openings"] = human_openings
    elif mode == "merge":
        existing = list(out.get("openings", []))
        # Drop any existing opening whose center is within 25pt of a human
        # opening center; the human one wins (FP-014 user rule).
        kept = []
        for ex in existing:
            ex_c = ex.get("center") or ex.get("center_pts")
            if not ex_c:
                kept.append(ex)
                continue
            cx, cy = float(ex_c[0]), float(ex_c[1])
            collides = False
            for ho in human_openings:
                hc = ho["center"]
                if abs(cx - hc[0]) <= 25.0 and abs(cy - hc[1]) <= 25.0:
                    collides = True
                    break
            if not collides:
                kept.append(ex)
        out["openings"] = human_openings + kept
    else:
        raise ValueError(f"unknown mode: {mode}")

    # Metadata stamp
    md = dict(out.get("metadata", {}))
    md["human_openings_truth"] = {
        "applied": True,
        "mode": mode,
        "n_openings_applied": len(human_openings),
        "source_truth": truth.get("source_image"),
        "required_counts": truth.get("required_counts"),
        "explicit_constraints_count": len(truth.get("explicit_constraints", [])),
    }
    out["metadata"] = md
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--mode", choices=["replace", "merge"], default="replace",
                    help="'replace' (default): wipe consensus.openings and "
                         "write only human openings. 'merge': keep "
                         "existing non-colliding openings plus human ones.")
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text())
    truth = json.loads(args.truth.read_text())
    out = apply_truth_to_consensus(consensus, truth, mode=args.mode)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))

    md = out["metadata"]["human_openings_truth"]
    print(f"[apply] mode={md['mode']} "
          f"openings_applied={md['n_openings_applied']} -> {args.out}")
    # Required-counts summary
    actual: dict[str, int] = {}
    for op in out["openings"]:
        if op.get("geometry_origin") == "human_annotation":
            k = op.get("kind_v5") or op.get("kind")
            actual[k] = actual.get(k, 0) + 1
    req = truth.get("required_counts", {}) or {}
    print("  required vs actual:")
    for kind in sorted(set(list(req.keys()) + list(actual.keys()))):
        r = req.get(kind, 0)
        a = actual.get(kind, 0)
        status = "OK" if a >= r else "FAIL"
        print(f"    {kind:18}: actual={a}, required={r} [{status}]")


if __name__ == "__main__":
    main()
