"""compare_generated_to_expected.py — Fidelity Engine v1.

Reads a manual ground-truth ``expected_model.json`` (schema 1.0 in
``ground_truth/schema/expected_model.schema.json``) and an observed
pipeline output (post-classifier ``consensus_with_room_context.json``
preferred) and emits TWO artifacts:

  - fidelity_report.json    — structured per-metric scores + facts
  - fidelity_scorecard.md   — short human-readable summary

Boundary (v1):
  - DOES NOT mutate either input
  - DOES NOT compute polygon IoU (deferred to v2)
  - DOES NOT compute exact opening position errors (deferred to v2)
  - DOES NOT call SketchUp / Ruby / LLM
  - Default exits 0 if it could read both inputs; ``--strict`` opts
    in to non-zero exit when any hard_fail is present.

Metrics in v1:
  - count_deltas: rooms / openings / walls (vs expected with tolerance)
  - global_bbox_drift: width / height drift % vs expected
  - room_label_match: % of expected rooms found in observed by name
  - room_area_in_range: per-room area inside expected_area_m2_range
  - room_polygon_closed: per-room polygon closure
  - adjacency_precision / recall / f1: edges via openings.evidence
  - opening_count_delta + opening_kind_distribution_delta

Hard-fail conditions (v1, default thresholds):
  - room_count_delta > expected.expected_counts.tolerance.rooms_delta
  - room_label_match_ratio < 0.7
  - adjacency_f1 < 0.6 (when expected.adjacency is non-empty)
  - any room with manual_confidence == 'high' fails area_in_range OR
    polygon_closed

Warning conditions:
  - opening_count_delta > tolerance.openings_delta
  - global_bbox drift > tolerance_pct
  - any low/medium-confidence room out of range

Usage:
    python -m tools.fidelity.compare_generated_to_expected \\
        runs/.../consensus_with_room_context.json \\
        --expected ground_truth/planta_74/expected_model.json \\
        --out runs/.../fidelity_report.json \\
        [--scorecard runs/.../fidelity_scorecard.md] \\
        [--pt-to-m 0.0352] [--strict]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

REPORT_SCHEMA_VERSION = "1.0"
EXPECTED_SCHEMA_VERSION = "1.0"

PT_TO_M_DEFAULT = 0.19 / 5.4  # 0.03518... — see CLAUDE.md §10 anchor


# ---------- Geometry helpers (independent of shapely for unit-test
# portability; falls back to shapely only if the input demands it) ----

def _polygon_area_pt2(pts: list[list[float]]) -> float:
    if len(pts) < 3:
        return 0.0
    a = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) * 0.5


def _polygon_is_closed(pts: list[list[float]]) -> bool:
    if len(pts) < 3:
        return False
    seen = {(round(p[0], 3), round(p[1], 3)) for p in pts}
    return len(seen) >= 3


def _bbox_pt(pts: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


# ---------- Observed-side helpers --------------------------------------

def _find_room_by_label(observed: dict, label: str) -> dict | None:
    target = label.strip().upper()
    for r in observed.get("rooms") or []:
        if (r.get("name") or "").strip().upper() == target:
            return r
    return None


def _observed_adjacency_edges(observed: dict) -> set[tuple[str, str]]:
    """Set of frozenset({label_a, label_b}) reachable through openings'
    room_left/right evidence. Self-loops dropped, EXTERIOR dropped.
    Always returns each edge in canonical (sorted) tuple form so set
    operations work."""
    out: set[tuple[str, str]] = set()
    for op in observed.get("openings") or []:
        ev = op.get("evidence") or {}
        a = (op.get("room_left_name") or ev.get("room_left") or "").strip().upper()
        b = (op.get("room_right_name") or ev.get("room_right") or "").strip().upper()
        if not a or not b or a == b:
            continue
        edge = tuple(sorted((a, b)))
        out.add(edge)
    return out


def _observed_global_bbox_pt(observed: dict) -> tuple[float, float] | None:
    walls = observed.get("walls") or []
    if not walls:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for w in walls:
        for pt in (w.get("start"), w.get("end")):
            if pt is None:
                continue
            xs.append(float(pt[0]))
            ys.append(float(pt[1]))
    if not xs or not ys:
        return None
    return (max(xs) - min(xs), max(ys) - min(ys))


# ---------- Per-metric evaluators --------------------------------------

def _metric_count_deltas(observed: dict, expected: dict) -> dict:
    ec = expected.get("expected_counts") or {}
    tol = ec.get("tolerance") or {}
    out: dict = {"checks": {}}
    for key, tol_default in (
        ("rooms", 1), ("openings", 2), ("walls", 4),
    ):
        if key not in ec:
            continue
        exp = int(ec[key])
        actual = len(observed.get(key) or [])
        delta = actual - exp
        tol_v = int(tol.get(f"{key}_delta", tol_default))
        within = abs(delta) <= tol_v
        out["checks"][f"{key}_count_delta"] = {
            "expected": exp,
            "actual": actual,
            "delta": delta,
            "tolerance": tol_v,
            "pass": within,
        }
    return out


def _metric_global_bbox_drift(observed: dict, expected: dict,
                                pt_to_m: float) -> dict:
    gb = expected.get("global_bbox") or {}
    if not gb or "width" not in gb or "height" not in gb:
        return {"check": None, "skipped": "no global_bbox in expected"}
    obs_pt = _observed_global_bbox_pt(observed)
    if obs_pt is None:
        return {"check": None, "skipped": "no walls in observed"}
    obs_w_m = obs_pt[0] * pt_to_m
    obs_h_m = obs_pt[1] * pt_to_m
    exp_w = float(gb["width"])
    exp_h = float(gb["height"])
    tol_pct = float(gb.get("tolerance_pct", 10))

    drift_w = (obs_w_m - exp_w) / exp_w * 100 if exp_w > 0 else 0.0
    drift_h = (obs_h_m - exp_h) / exp_h * 100 if exp_h > 0 else 0.0
    within = abs(drift_w) <= tol_pct and abs(drift_h) <= tol_pct
    return {
        "expected_m": [exp_w, exp_h],
        "actual_m": [round(obs_w_m, 3), round(obs_h_m, 3)],
        "drift_pct": [round(drift_w, 2), round(drift_h, 2)],
        "tolerance_pct": tol_pct,
        "pass": within,
    }


def _evaluate_room(gt_room: dict, observed: dict, pt_to_m: float) -> dict:
    label = gt_room["label"]
    matched = _find_room_by_label(observed, label)
    confidence = gt_room.get("manual_confidence", "medium")

    base: dict = {
        "id": gt_room.get("id"),
        "label": label,
        "manual_confidence": confidence,
        "found": matched is not None,
        "matched_room_id": matched.get("id") if matched else None,
        "checks": {},
    }
    if not matched:
        base["checks"]["label_found"] = {"pass": False}
        return base

    base["checks"]["label_found"] = {"pass": True}

    if gt_room.get("must_be_closed", True):
        polygon = matched.get("polygon_pts") or []
        is_closed = _polygon_is_closed(polygon)
        base["checks"]["polygon_closed"] = {
            "expected": True, "actual": is_closed, "pass": is_closed,
        }

    if gt_room.get("expected_area_m2_range"):
        lo, hi = gt_room["expected_area_m2_range"]
        area_pt2 = float(matched.get("area_pts2") or 0)
        area_m2 = round(area_pt2 * pt_to_m * pt_to_m, 3)
        in_range = lo <= area_m2 <= hi
        base["checks"]["area_in_range"] = {
            "expected_m2": [lo, hi],
            "actual_m2": area_m2,
            "pass": in_range,
        }

    return base


def _metric_rooms(observed: dict, expected: dict, pt_to_m: float) -> dict:
    rows = [
        _evaluate_room(r, observed, pt_to_m)
        for r in expected.get("rooms") or []
    ]
    n_total = len(rows)
    n_found = sum(1 for r in rows if r["found"])
    label_match_ratio = (n_found / n_total) if n_total else 0.0
    return {
        "rows": rows,
        "label_match_ratio": round(label_match_ratio, 3),
        "expected_rooms": n_total,
        "matched_rooms": n_found,
    }


def _metric_adjacency(observed: dict, expected: dict) -> dict:
    edges_expected: set[tuple[str, str]] = set()
    label_by_id = {
        r["id"]: r["label"].strip().upper()
        for r in expected.get("rooms") or []
    }
    for e in expected.get("adjacency") or []:
        a = label_by_id.get(e["a"])
        b = label_by_id.get(e["b"])
        if a and b and a != b:
            edges_expected.add(tuple(sorted((a, b))))
    if not edges_expected:
        return {"skipped": "no adjacency edges in expected"}

    edges_observed = _observed_adjacency_edges(observed)
    tp = edges_expected & edges_observed
    fp = edges_observed - edges_expected
    fn = edges_expected - edges_observed
    precision = len(tp) / (len(tp) + len(fp)) if (tp or fp) else 0.0
    recall = len(tp) / (len(tp) + len(fn)) if (tp or fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "true_positive": sorted(tp),
        "false_positive": sorted(fp),
        "false_negative": sorted(fn),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "n_expected_edges": len(edges_expected),
        "n_observed_edges": len(edges_observed),
    }


def _metric_opening_kinds(observed: dict, expected: dict) -> dict:
    """Compares the by-kind histogram. Doesn't try to match individual
    openings (deferred to v2 with positions)."""
    expected_kinds: dict[str, int] = {}
    for op in expected.get("openings") or []:
        kind = op.get("kind") or "unknown"
        expected_kinds[kind] = expected_kinds.get(kind, 0) + 1
    observed_kinds: dict[str, int] = {}
    for op in observed.get("openings") or []:
        kind = op.get("kind_v5") or op.get("kind") or "unknown"
        observed_kinds[kind] = observed_kinds.get(kind, 0) + 1
    return {
        "expected_by_kind": expected_kinds,
        "observed_by_kind": observed_kinds,
    }


# ---------- Aggregation -------------------------------------------------

def _aggregate(observed_path: Path, expected_path: Path,
                count_metrics: dict, bbox: dict, rooms_metric: dict,
                adjacency: dict, kind_metric: dict,
                expected: dict) -> dict:
    """Combines per-metric outputs into the final fidelity report.

    Score combination (v1, intentionally simple — interpretability >
    aggregation accuracy):
      - room_score = label_match_ratio * (1 - hard_high_failure_ratio)
      - adjacency_score = f1
      - count_score = 1 if all count_deltas pass else 0
      - bbox_score = 1 if bbox passes (or skipped) else 0
      - global_fidelity = mean of available scores, capped at 0.69
        when ANY hard_fail is present
    """
    hard_fails: list[str] = []
    warnings: list[str] = []

    # -- Counts
    for k, c in count_metrics.get("checks", {}).items():
        if not c["pass"]:
            severity = "hard_fail" if k == "rooms_count_delta" else "warning"
            (hard_fails if severity == "hard_fail" else warnings).append(
                f"{severity}:{k} delta={c['delta']} tol={c['tolerance']}"
            )

    # -- Rooms
    high_conf_failures = 0
    high_conf_total = 0
    for row in rooms_metric.get("rows", []):
        if not row["found"]:
            warnings.append(f"warning:room_missing:{row['label']}")
            if row.get("manual_confidence") == "high":
                hard_fails.append(f"hard_fail:room_missing_high_conf:{row['label']}")
                high_conf_failures += 1
                high_conf_total += 1
            continue
        for ck, cv in (row.get("checks") or {}).items():
            if ck == "label_found":
                continue
            if not cv.get("pass"):
                if row.get("manual_confidence") == "high":
                    hard_fails.append(
                        f"hard_fail:{ck}:{row['label']} actual="
                        f"{cv.get('actual_m2', cv.get('actual'))}"
                    )
                    high_conf_failures += 1
                else:
                    warnings.append(
                        f"warning:{ck}:{row['label']} actual="
                        f"{cv.get('actual_m2', cv.get('actual'))}"
                    )
        if row.get("manual_confidence") == "high":
            high_conf_total += 1

    label_ratio = rooms_metric.get("label_match_ratio", 0.0)
    if label_ratio < 0.7:
        hard_fails.append(f"hard_fail:label_match_ratio={label_ratio:.2f}<0.70")

    # -- Adjacency
    adj_score = None
    if "f1" in adjacency:
        adj_score = adjacency["f1"]
        if adj_score < 0.6:
            hard_fails.append(f"hard_fail:adjacency_f1={adj_score:.2f}<0.60")
        elif adj_score < 0.8:
            warnings.append(f"warning:adjacency_f1={adj_score:.2f}<0.80")

    # -- BBox
    bbox_score = None
    if "pass" in bbox:
        bbox_score = 1.0 if bbox["pass"] else 0.0
        if not bbox["pass"]:
            warnings.append(
                f"warning:global_bbox_drift_pct={bbox.get('drift_pct')}"
            )

    # -- Score
    high_conf_pass_ratio = 1.0
    if high_conf_total > 0:
        high_conf_pass_ratio = max(
            0.0, 1.0 - (high_conf_failures / high_conf_total)
        )
    room_score = label_ratio * high_conf_pass_ratio
    count_score = 1.0 if not any(
        not c["pass"] for c in count_metrics.get("checks", {}).values()
    ) else 0.0
    parts = [room_score, count_score]
    if adj_score is not None:
        parts.append(adj_score)
    if bbox_score is not None:
        parts.append(bbox_score)
    global_fidelity = sum(parts) / len(parts) if parts else 0.0
    if hard_fails:
        global_fidelity = min(global_fidelity, 0.69)
    global_fidelity = round(global_fidelity, 3)

    sub_scores = {
        "room_score": round(room_score, 3),
        "count_score": round(count_score, 3),
        "adjacency_score": (
            round(adj_score, 3) if adj_score is not None else None
        ),
        "bbox_score": (
            round(bbox_score, 3) if bbox_score is not None else None
        ),
    }

    suggested_fixes = []
    for hf in hard_fails:
        if hf.startswith("hard_fail:area_in_range"):
            suggested_fixes.append(
                "tighten or promote tools.rooms_from_seeds "
                "--use-concave-hull (FP-012); recalibrate "
                "expected_area_m2_range only after the algorithm flips"
            )
            break
    for hf in hard_fails:
        if "label_match_ratio" in hf:
            suggested_fixes.append(
                "investigate room-label extractor; consensus.rooms is "
                "missing labels expected by ground truth"
            )
    for hf in hard_fails:
        if "adjacency_f1" in hf:
            suggested_fixes.append(
                "verify tools.classify_openings_by_room_context: "
                "openings.evidence.room_left/right are how adjacency "
                "is materialized today"
            )

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "observed_path": str(observed_path),
        "observed_sha256": _sha256(observed_path),
        "expected_path": str(expected_path),
        "expected_schema_version": expected.get("schema_version"),
        "plan_id": expected.get("plan_id"),
        "scope": "whole_plant_v1",
        "metrics": {
            "counts": count_metrics,
            "global_bbox": bbox,
            "rooms": rooms_metric,
            "adjacency": adjacency,
            "opening_kinds": kind_metric,
        },
        "hard_fails": hard_fails,
        "warnings": warnings,
        "suggested_fixes": suggested_fixes,
        "sub_scores": sub_scores,
        "global_fidelity": global_fidelity,
        "would_block_strict": list(hard_fails),
    }


def _sha256(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


# ---------- Public + CLI ------------------------------------------------

def compare(observed: dict, expected: dict, pt_to_m: float = PT_TO_M_DEFAULT,
             observed_path: Path | str = "<dict>",
             expected_path: Path | str = "<dict>",
             *,
             apply_overrides: bool = False,
             overrides_doc: dict | None = None) -> dict:
    """Compare an observed consensus against an expected ground-truth.

    Slice 3 (ADR-001 §2.10.5): when ``apply_overrides=True`` AND
    ``overrides_doc`` is supplied, the comparison is run TWICE: once
    on the raw observed (for ``global_fidelity_pre_override``) and
    once on the amended observed (for ``global_fidelity``). Both
    scores are emitted in the report so a review can never make the
    score look better without leaving evidence.

    When ``apply_overrides=False`` (default), behaviour is byte-
    equivalent to v1: only ``global_fidelity`` is computed, and
    ``global_fidelity_pre_override`` / ``overrides_applied_count``
    are NOT present in the report.
    """
    if expected.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        raise ValueError(
            f"expected_model schema_version "
            f"{expected.get('schema_version')!r} != "
            f"{EXPECTED_SCHEMA_VERSION!r}"
        )

    def _run_metrics(obs: dict) -> dict:
        counts = _metric_count_deltas(obs, expected)
        bbox = _metric_global_bbox_drift(obs, expected, pt_to_m)
        rooms = _metric_rooms(obs, expected, pt_to_m)
        adjacency = _metric_adjacency(obs, expected)
        kinds = _metric_opening_kinds(obs, expected)
        return _aggregate(
            Path(str(observed_path)), Path(str(expected_path)),
            counts, bbox, rooms, adjacency, kinds, expected,
        )

    if not apply_overrides:
        return _run_metrics(observed)

    # Slice 3 mode: produce both pre and post scores.
    pre_report = _run_metrics(observed)
    # Local import keeps fidelity engine import-clean for callers
    # that don't enable overrides.
    from tools.apply_overrides import apply_overrides as _apply
    amended = _apply(observed, overrides_doc)
    post_report = _run_metrics(amended)

    # Merge: post_report becomes the canonical report; pre values
    # are surfaced as additional fields per ADR-001 §2.10.5.
    post_report["global_fidelity_pre_override"] = pre_report[
        "global_fidelity"
    ]
    post_report["sub_scores_pre_override"] = pre_report["sub_scores"]
    post_report["hard_fails_pre_override"] = pre_report["hard_fails"]
    post_report["warnings_pre_override"] = pre_report["warnings"]
    md = amended.get("_overrides_metadata") or {}
    post_report["overrides_applied_count"] = md.get(
        "overrides_applied_count", 0,
    )
    post_report["overrides_dropped_count"] = md.get(
        "overrides_dropped_count", 0,
    )
    # ADR-002 §2.6 — finer-grained breakdown of geometry-mutating
    # overrides. Always present in amended reports; readers older than
    # ADR-002 can ignore.
    post_report["polygon_overrides_applied_count"] = md.get(
        "polygon_overrides_applied_count", 0,
    )
    post_report["override_warnings"] = md.get("warnings") or []
    post_report["block_skp_export"] = md.get("block_skp_export", False)
    post_report["block_reason"] = md.get("block_reason")
    return post_report


def render_scorecard(report: dict) -> str:
    lines = [
        f"# Fidelity Scorecard — {report.get('plan_id') or 'unknown'}",
        "",
        f"- generated_at: `{report.get('generated_at')}`",
        f"- expected: `{report.get('expected_path')}`",
        f"- observed: `{report.get('observed_path')}`",
        f"- global_fidelity: **{report.get('global_fidelity')}**",
        "",
        "## Sub-scores",
        "",
    ]
    for k, v in (report.get("sub_scores") or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Hard fails", ""]
    if report.get("hard_fails"):
        for hf in report["hard_fails"]:
            lines.append(f"- {hf}")
    else:
        lines.append("_(none)_")
    lines += ["", "## Warnings", ""]
    if report.get("warnings"):
        for w in report["warnings"]:
            lines.append(f"- {w}")
    else:
        lines.append("_(none)_")
    if report.get("suggested_fixes"):
        lines += ["", "## Suggested fixes", ""]
        for s in report["suggested_fixes"]:
            lines.append(f"- {s}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fidelity Engine v1: compare observed pipeline output "
        "to manual ground-truth expected_model.json."
    )
    ap.add_argument("observed", type=Path,
                     help="path to consensus_with_room_context.json (post-classifier preferred)")
    ap.add_argument("--expected", type=Path, required=True,
                     help="path to ground_truth/<plant>/expected_model.json")
    ap.add_argument("--out", type=Path, default=None,
                     help="fidelity_report.json output path "
                     "(default: <observed>.parent/fidelity_report.json)")
    ap.add_argument("--scorecard", type=Path, default=None,
                     help="optional fidelity_scorecard.md output path")
    ap.add_argument("--pt-to-m", type=float, default=PT_TO_M_DEFAULT,
                     help=f"PDF pt -> meters (default: {PT_TO_M_DEFAULT})")
    ap.add_argument("--strict", action="store_true",
                     help="exit non-zero if any hard_fail is present "
                     "(default: always exit 0 if inputs readable)")
    args = ap.parse_args(argv)

    observed = json.loads(args.observed.read_text(encoding="utf-8"))
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    report = compare(
        observed, expected,
        pt_to_m=args.pt_to_m,
        observed_path=args.observed,
        expected_path=args.expected,
    )
    out_path = args.out or (args.observed.parent / "fidelity_report.json")
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"[fidelity] global={report['global_fidelity']} "
        f"hard_fails={len(report['hard_fails'])} "
        f"warnings={len(report['warnings'])}"
    )
    print(f"[wrote] {out_path}")
    if args.scorecard:
        args.scorecard.write_text(
            render_scorecard(report), encoding="utf-8",
        )
        print(f"[wrote] {args.scorecard}")
    if args.strict and report["hard_fails"]:
        print(
            f"[strict] {len(report['hard_fails'])} hard_fail(s); exit 1",
            file=sys.stderr,
        )
        return 1
    print("[non-strict] would-block:", report["would_block_strict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
