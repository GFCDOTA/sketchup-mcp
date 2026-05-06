"""micro_truth_gate.py — Stage 1.5 Micro Ground Truth Gate.

Minimum viable validator that proves AT LEAST ONE room of a real
plant matches a versioned manual expectation. No IoU, no polygon
matching, no whole-plant ground truth — just label / area / openings
count / adjacencies / closure for ONE target room.

Why this gate exists:

The plan_truth_gate (sibling Stage 1.5 PR) locks the ENTIRE pipeline
output against a deterministic baseline derived from itself — useful
for catching silent regressions but circular: it doesn't prove the
detector got the building right. This module compares the consensus
against a manually curated ``ground_truth/<plant>_micro.json`` —
the FIRST piece of external truth in the repo.

Stage 1.5 boundary (PR feature/micro-truth-gate-planta-74):
  - DOES NOT change consensus geometry / SKP / Ruby exporter
  - DOES NOT compute polygon IoU (deferred — polygon perfection is
    not yet asserted by ground truth)
  - DOES NOT validate the whole plant — only labelled target rooms
  - DOES NOT call any LLM or external service
  - DOES NOT auto-correct mismatches

JSON schema for both inputs and outputs is versioned at "1.0".
See docs/SCHEMA-COHERENCE-REPORT.md for related artifacts.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

REPORT_SCHEMA_VERSION = "1.0"
GROUND_TRUTH_SCHEMA_VERSION = "1.0"

# Calibrated PT_TO_M for planta_74 (wall_thickness 5.4 pt -> 0.19 m).
# Extracted from consume_consensus.rb to keep the conversion one place
# and avoid drift. Future plants with different scales will need the
# detector to record per-PDF PT_TO_M in the consensus.
PT_TO_M_DEFAULT = 0.19 / 5.4


# ---- Geometry helpers ----

def _polygon_area_pt2(polygon: list[list[float]]) -> float:
    """Shoelace area, always >= 0."""
    n = len(polygon)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = polygon[i][0], polygon[i][1]
        x2, y2 = polygon[(i + 1) % n][0], polygon[(i + 1) % n][1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _polygon_is_closed(polygon: list[list[float]]) -> bool:
    """A polygon is "closed" for our purposes when it has at least 3
    distinct vertices. The actual rendering code (`add_face`) handles
    auto-closing — it only fails when n<3."""
    if len(polygon) < 3:
        return False
    distinct = {tuple(p) for p in polygon}
    return len(distinct) >= 3


# ---- Detectors (read-only audits) ----

def _detect_invalid_room_polygons(consensus: dict) -> list[str]:
    return [
        r.get("id", "<no-id>")
        for r in consensus.get("rooms") or []
        if not _polygon_is_closed(r.get("polygon_pts") or [])
    ]


def _detect_floating_openings(consensus: dict) -> list[str]:
    walls = {w["id"] for w in (consensus.get("walls") or []) if w.get("id")}
    return [
        op.get("id", "<no-id>")
        for op in consensus.get("openings") or []
        if not op.get("wall_id") or op["wall_id"] not in walls
    ]


def _detect_duplicate_walls(consensus: dict, tol_pt: float = 1.0) -> list[tuple]:
    walls = consensus.get("walls") or []
    out: list[tuple] = []
    for i, a in enumerate(walls):
        for b in walls[i + 1:]:
            if a.get("orientation") != b.get("orientation"):
                continue
            if a.get("orientation") == "h":
                if abs(a["start"][1] - b["start"][1]) > tol_pt:
                    continue
                ax = sorted([a["start"][0], a["end"][0]])
                bx = sorted([b["start"][0], b["end"][0]])
                if ax[1] < bx[0] - tol_pt or bx[1] < ax[0] - tol_pt:
                    continue
            else:
                if abs(a["start"][0] - b["start"][0]) > tol_pt:
                    continue
                ay = sorted([a["start"][1], a["end"][1]])
                by = sorted([b["start"][1], b["end"][1]])
                if ay[1] < by[0] - tol_pt or by[1] < ay[0] - tol_pt:
                    continue
            out.append((a.get("id"), b.get("id")))
    return out


# ---- Per-room audit ----

def _find_room_by_label(consensus: dict, label: str) -> dict | None:
    target = label.strip().upper()
    for r in consensus.get("rooms") or []:
        name = (r.get("name") or "").strip().upper()
        if name == target:
            return r
    return None


def _openings_touching_room(consensus: dict, room: dict) -> list[dict]:
    """An opening "touches" a room when its evidence (or legacy
    room_left_name / room_right_name) matches the room name. Falls
    back to room_id if names absent."""
    rid = room.get("id")
    rname = (room.get("name") or "").strip().upper()
    out = []
    for op in consensus.get("openings") or []:
        ev = op.get("evidence") or {}
        names = {
            (ev.get("room_left") or "").strip().upper(),
            (ev.get("room_right") or "").strip().upper(),
            (op.get("room_left_name") or "").strip().upper(),
            (op.get("room_right_name") or "").strip().upper(),
        }
        ids = {
            ev.get("room_left_id"),
            ev.get("room_right_id"),
            op.get("room_left_id"),
            op.get("room_right_id"),
        }
        if rname and rname in names:
            out.append(op)
        elif rid and rid in ids:
            out.append(op)
    return out


def _adjacent_labels_via_openings(consensus: dict, room: dict,
                                    openings: list[dict]) -> set[str]:
    """The set of OTHER room labels reached from `room` through any
    listed opening. Drops self-references and exterior."""
    rname = (room.get("name") or "").strip().upper()
    out: set[str] = set()
    for op in openings:
        ev = op.get("evidence") or {}
        for k in ("room_left", "room_right",
                   "room_left_name", "room_right_name"):
            n = (op.get(k) or ev.get(k) or "").strip().upper()
            if n and n != rname:
                out.add(n)
    return out


def _audit_one_room(consensus: dict, gt_room: dict,
                     pt_to_m: float, allow_debug_openings: bool,
                     ) -> dict:
    label = gt_room["label"]
    expected_area = gt_room.get("expected_area_m2_range")
    expected_count = gt_room.get("expected_openings_count_range")
    expected_adj = [
        s.strip().upper() for s in gt_room.get("expected_adjacent_labels") or []
    ]
    must_be_closed = bool(gt_room.get("must_be_closed", True))

    matched = _find_room_by_label(consensus, label)
    if matched is None:
        return {
            "label": label,
            "found": False,
            "matched_room_id": None,
            "checks": {"label_found": {"pass": False, "reason":
                "no room with this name in consensus"}},
            "score": 0.0,
        }

    polygon = matched.get("polygon_pts") or []
    area_pt2 = _polygon_area_pt2(polygon)
    area_m2 = round(area_pt2 * pt_to_m * pt_to_m, 3)
    is_closed = _polygon_is_closed(polygon)

    openings = _openings_touching_room(consensus, matched)
    if not allow_debug_openings:
        openings = [op for op in openings
                    if op.get("decision") in (None, "clean")]
    n_openings = len(openings)
    adjacents = _adjacent_labels_via_openings(consensus, matched, openings)

    checks: dict[str, dict] = {}
    checks["label_found"] = {"pass": True, "matched_room_id": matched.get("id")}

    if must_be_closed:
        checks["polygon_closed"] = {
            "expected": True, "actual": is_closed, "pass": is_closed,
        }

    if expected_area:
        lo, hi = float(expected_area[0]), float(expected_area[1])
        in_range = lo <= area_m2 <= hi
        checks["area_in_range"] = {
            "expected_m2": [lo, hi], "actual_m2": area_m2,
            "pass": in_range,
        }

    if expected_count:
        lo, hi = int(expected_count[0]), int(expected_count[1])
        in_range = lo <= n_openings <= hi
        checks["openings_count_in_range"] = {
            "expected": [lo, hi], "actual": n_openings,
            "pass": in_range,
            "openings": [op.get("id") for op in openings],
        }

    if expected_adj:
        missing = [a for a in expected_adj if a not in adjacents]
        checks["adjacents_present"] = {
            "expected": expected_adj,
            "actual": sorted(adjacents),
            "missing": missing,
            "pass": not missing,
        }

    passed = sum(1 for c in checks.values() if c.get("pass"))
    total = len(checks)
    score = round(passed / total, 3) if total else 0.0
    return {
        "label": label,
        "found": True,
        "matched_room_id": matched.get("id"),
        "area_m2": area_m2,
        "polygon_pts_count": len(polygon),
        "openings_count": n_openings,
        "adjacent_labels_found": sorted(adjacents),
        "checks": checks,
        "checks_passed": passed,
        "checks_total": total,
        "score": score,
    }


# ---- Public API ----

def _consensus_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_micro_truth_report(consensus: dict, consensus_path: Path,
                                ground_truth: dict,
                                ground_truth_path: Path,
                                pt_to_m: float = PT_TO_M_DEFAULT,
                                ) -> dict:
    """Pure function: return the report dict. Caller writes to disk."""
    gt_sv = ground_truth.get("schema_version")
    if gt_sv != GROUND_TRUTH_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported ground_truth schema_version {gt_sv!r}; "
            f"expected {GROUND_TRUTH_SCHEMA_VERSION!r}"
        )

    rooms_audited = []
    for gt_room in ground_truth.get("rooms") or []:
        rep = _audit_one_room(
            consensus, gt_room, pt_to_m,
            allow_debug_openings=bool(
                gt_room.get("allow_debug_openings", True)
            ),
        )
        rooms_audited.append(rep)

    invalid = _detect_invalid_room_polygons(consensus)
    floating = _detect_floating_openings(consensus)
    duplicate = _detect_duplicate_walls(consensus)
    inv_expected = ground_truth.get("invariants") or {}
    invariants_report = {
        "invalid_rooms": {
            "actual": len(invalid), "actual_ids": invalid,
            "expected_max": inv_expected.get("invalid_rooms", 0),
            "pass": len(invalid) <= inv_expected.get("invalid_rooms", 0),
        },
        "floating_openings": {
            "actual": len(floating), "actual_ids": floating,
            "expected_max": inv_expected.get("floating_openings", 0),
            "pass": len(floating) <= inv_expected.get("floating_openings", 0),
        },
        "duplicate_walls": {
            "actual": len(duplicate),
            "actual_pairs": [list(p) for p in duplicate],
            "expected_max": inv_expected.get("duplicate_walls", 0),
            "pass": len(duplicate) <= inv_expected.get("duplicate_walls", 0),
        },
    }

    # Aggregate score: average per-room score (0..1), penalise on
    # invariant fails by capping. Conservative.
    if rooms_audited:
        avg_room_score = sum(r["score"] for r in rooms_audited) / len(rooms_audited)
    else:
        avg_room_score = 0.0
    invariant_pass_ratio = (
        sum(1 for v in invariants_report.values() if v["pass"])
        / len(invariants_report)
    )
    overall_score = round(avg_room_score * invariant_pass_ratio, 3)

    # Strict-blocker labels that fired (caller decides what to do).
    fired: list[str] = []
    for r in rooms_audited:
        if not r.get("found"):
            fired.append(f"room_not_found:{r['label']}")
            continue
        for cname, c in (r.get("checks") or {}).items():
            if c.get("pass") is False:
                fired.append(f"{cname}:{r['label']}")
    if not invariants_report["floating_openings"]["pass"]:
        fired.append("floating_opening_present")
    if not invariants_report["duplicate_walls"]["pass"]:
        fired.append("duplicate_walls_present")
    if not invariants_report["invalid_rooms"]["pass"]:
        fired.append("invalid_room_present")

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "consensus_path": str(consensus_path),
        "consensus_sha256": _consensus_sha256(consensus_path),
        "ground_truth_path": str(ground_truth_path),
        "ground_truth_schema_version": gt_sv,
        "scope": ground_truth.get("scope", "micro"),
        "rooms_audited": rooms_audited,
        "invariants": invariants_report,
        "score": overall_score,
        "would_block_strict": fired,
    }


# ---- CLI ----

def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Stage 1.5 Micro Ground Truth Gate. "
                    "Audit one or more labelled rooms against a "
                    "versioned manual expectation. Non-blocking by "
                    "default."
    )
    p.add_argument("consensus", type=Path,
                    help="path to consensus_with_room_context.json "
                         "(post-classifier preferred for full check "
                         "coverage)")
    p.add_argument("--ground-truth", type=Path, required=True,
                    help="path to ground_truth/<plant>_micro.json")
    p.add_argument("--out", type=Path, default=None,
                    help="output micro_truth_report.json path "
                         "(default: <consensus>.parent / "
                         "micro_truth_report.json)")
    p.add_argument("--pt-to-m", type=float, default=PT_TO_M_DEFAULT,
                    help=f"PDF pt -> meters (default: {PT_TO_M_DEFAULT})")
    p.add_argument("--strict", action="store_true",
                    help="exit non-zero if any check fails (default: "
                         "always exit 0 if inputs readable)")
    args = p.parse_args(argv)

    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))
    gt = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    report = build_micro_truth_report(
        consensus, args.consensus, gt, args.ground_truth,
        pt_to_m=args.pt_to_m,
    )

    out = args.out or (args.consensus.parent / "micro_truth_report.json")
    out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    fired = report["would_block_strict"]
    summary = (
        f"[micro-truth] score={report['score']} "
        f"rooms={len(report['rooms_audited'])} fired={len(fired)}"
    )
    print(summary)
    print(f"[wrote] {out}")
    if args.strict and fired:
        print(f"[strict] blockers fired: {fired}", file=sys.stderr)
        return 2
    if fired:
        print(f"[non-strict] would-block: {fired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
