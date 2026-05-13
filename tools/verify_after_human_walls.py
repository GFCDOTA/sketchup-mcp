"""Gate: verify the consensus AFTER human walls were applied.

REWRITTEN 2026-05-12 per user mandate (architectural honesty):
"human_wall blue só deve representar parede/drywall/alvenaria real.
Não exigir G-W1/G-W2 como FAIL por ausência de parede física onde só
existe soft barrier/semantic split."

The new gate semantics distinguish THREE fidelities:

  • WALL fidelity (G-WW*)         — human walls extracted, hosted,
                                     no painted blob lost.
  • OPENING fidelity (G-WH*)      — every human opening hosted by
                                     either painted or detected wall.
  • CELL-CLOSURE honesty (G-WC*)  — every remaining merged cell has a
                                     documented closure type. A merge
                                     is HONEST if all its room-pairs
                                     are either human_soft_barrier
                                     (peitoril missing -> needs soft-
                                     barrier protocol, NOT more walls)
                                     or semantic_room_split (open
                                     plan, no physical divider). A
                                     merge is a WALL FAILURE only if
                                     loop_closure_candidates lists a
                                     pair as candidate_type=human_wall
                                     with should_user_paint=True (a
                                     real masonry/drywall that wasn't
                                     painted).

Verdict ladder:
  • FAIL  if at least one remaining merge contains a should_user_paint
          =True wall (a real wall was NOT painted).
  • WARN  if all remaining merges are explained by soft_barrier or
          semantic_split (visually closed via a separate protocol or
          deliberately open). Still advisory because the operator may
          want to ship the soft-barrier protocol.
  • PASS  if no merges remain.

The legacy G-W1/G-W2 are kept as ADVISORY counters (severity=INFO)
so the report still shows the room/merge deltas for context, but
they no longer drive the verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))


@dataclass
class Finding:
    check_id: str
    severity: str            # PASS | WARN | FAIL | INFO
    message: str
    evidence: dict[str, Any]


def _classify_merges(merged_cells: list[dict],
                       candidates_report: dict | None
                       ) -> dict[str, dict]:
    """For each merged cell, classify by the per-pair candidate_types
    from loop_closure_candidates.json. Returns:
        {
            cell_name: {
                "pairs": [{from, to, candidate_type, should_user_paint}],
                "needs_wall":   True/False,   # any pair=human_wall+paint
                "needs_sbarrier": True/False, # any pair=human_soft_barrier
                "semantic_only": True/False,  # all pairs=semantic
                "wall_failures": [pair, ...], # pairs missing painted wall
            }, ...
        }
    """
    out: dict[str, dict] = {}
    cands = (candidates_report or {}).get("candidates", [])
    for cell in merged_cells:
        name = cell.get("name", "")
        room_names = {n.strip() for n in name.split("|")}
        pairs = [c for c in cands
                  if c.get("from_room") in room_names
                  and c.get("to_room") in room_names]
        wall_failures = [c for c in pairs
                          if c.get("candidate_type") == "human_wall"
                          and c.get("should_user_paint")]
        needs_wall = bool(wall_failures)
        needs_sbarrier = any(c.get("candidate_type") == "human_soft_barrier"
                              for c in pairs)
        semantic_only = (pairs
                          and all(c.get("candidate_type") == "semantic_room_split"
                                   for c in pairs))
        out[name] = {
            "pairs": pairs,
            "needs_wall": needs_wall,
            "needs_sbarrier": needs_sbarrier,
            "semantic_only": semantic_only,
            "wall_failures": wall_failures,
            "n_pairs": len(pairs),
        }
    return out


def verify(consensus_after: dict,
            consensus_before: dict | None = None,
            truth_openings: dict | None = None,
            candidates_report: dict | None = None,
            expected_rooms_min: int = 10) -> dict:
    findings: list[Finding] = []
    rooms_after = consensus_after.get("rooms", [])
    rooms_before = consensus_before.get("rooms", []) if consensus_before else []
    merged_after = [r for r in rooms_after if "|" in r.get("name", "")]
    merged_before = [r for r in rooms_before if "|" in r.get("name", "")]

    # ----------- WALL FIDELITY (G-WW*) -----------
    walls = consensus_after.get("walls", [])
    h_walls = [w for w in walls if w.get("geometry_origin") == "human_annotation"]

    findings.append(Finding(
        check_id="G-WW1",
        severity="PASS" if h_walls else "WARN",
        message=f"human walls applied: {len(h_walls)}",
        evidence={"n_human_walls": len(h_walls),
                  "ids": [w["id"] for w in h_walls]},
    ))

    # ----------- OPENING FIDELITY (G-WH*) -----------
    from apply_human_openings import classify_opening_host_segment
    thickness = float(consensus_after.get("wall_thickness_pts", 5.4))
    n_unhosted = 0
    unhosted_ids: list[str] = []
    if truth_openings is None:
        truth_openings = {"openings": [
            {
                "bbox_px": (op.get("human_annotation", {}) or {}).get("bbox_px"),
                "bbox_pts": (op.get("human_annotation", {}) or {}).get("bbox_pts"),
                "orientation": ("h" if (
                    op.get("human_annotation", {}).get("bbox_pts")
                    and op["human_annotation"]["bbox_pts"][2]
                        - op["human_annotation"]["bbox_pts"][0]
                    >= op["human_annotation"]["bbox_pts"][3]
                        - op["human_annotation"]["bbox_pts"][1])
                else "v"),
                "center_pts": op.get("center"),
                "opening_width_pts": op.get("opening_width_pts", 0),
                "kind": op.get("kind_v5"),
            }
            for op in consensus_after.get("openings", [])
            if op.get("geometry_origin") == "human_annotation"
        ]}

    for i, src in enumerate(truth_openings["openings"]):
        if not src.get("bbox_pts"):
            continue
        h = classify_opening_host_segment(src, walls, thickness)
        if h["mode"] == "unhosted":
            n_unhosted += 1
            unhosted_ids.append(f"h_o{i:03d}")

    findings.append(Finding(
        check_id="G-WH1",
        severity="PASS" if n_unhosted == 0 else "FAIL",
        message=f"unhosted human openings after walls: {n_unhosted}",
        evidence={"unhosted_ids": unhosted_ids},
    ))

    findings.append(Finding(
        check_id="G-WH2",
        severity="PASS" if truth_openings["openings"] else "WARN",
        message=(f"human openings re-validated on augmented walls: "
                  f"{len(truth_openings['openings'])} total"),
        evidence={"n_human_openings": len(truth_openings["openings"])},
    ))

    # ----------- CELL-CLOSURE HONESTY (G-WC*) -----------
    merge_classification = _classify_merges(merged_after, candidates_report)
    wall_failure_cells = [name for name, c in merge_classification.items()
                            if c["needs_wall"]]
    softbarrier_cells = [name for name, c in merge_classification.items()
                           if c["needs_sbarrier"] and not c["needs_wall"]]
    semantic_cells = [name for name, c in merge_classification.items()
                        if c["semantic_only"]]
    undocumented_cells = [name for name, c in merge_classification.items()
                            if c["n_pairs"] == 0]

    # G-WC1: real wall missing? (drives FAIL)
    findings.append(Finding(
        check_id="G-WC1",
        severity="PASS" if not wall_failure_cells else "FAIL",
        message=(
            f"cells with real walls NOT painted: {len(wall_failure_cells)}. "
            "FAIL means human_wall classification with should_user_paint=True "
            "is still present — paint the wall in BLUE and re-run."
            if wall_failure_cells else
            "no merged cell needs a real wall painted (all merges explained "
            "by soft_barrier or semantic_split)."
        ),
        evidence={
            "wall_failure_cells": wall_failure_cells,
            "details": {n: merge_classification[n]["wall_failures"]
                          for n in wall_failure_cells},
        },
    ))

    # G-WC2: soft_barrier opportunities (advisory)
    findings.append(Finding(
        check_id="G-WC2",
        severity="WARN" if softbarrier_cells else "PASS",
        message=(
            f"cells that would close with soft_barrier (peitoril/grade): "
            f"{len(softbarrier_cells)}. These require the "
            "human_soft_barriers protocol — NOT more blue walls."
            if softbarrier_cells else
            "no cell needs a human soft barrier."
        ),
        evidence={"softbarrier_cells": softbarrier_cells},
    ))

    # G-WC3: semantic-only merges (always PASS — honest open plan)
    findings.append(Finding(
        check_id="G-WC3",
        severity="PASS",
        message=(f"cells merged honestly as semantic_room_split / open "
                  f"plan: {len(semantic_cells)}"),
        evidence={"semantic_cells": semantic_cells},
    ))

    # G-WC4: undocumented merges (no priors -> WARN, requires review)
    findings.append(Finding(
        check_id="G-WC4",
        severity="WARN" if undocumented_cells else "PASS",
        message=(
            f"merged cells with NO closure classification in "
            f"loop_closure_candidates.json: {len(undocumented_cells)}. "
            "Add priors before shipping."
            if undocumented_cells else
            "all remaining merges documented in loop_closure_candidates."
        ),
        evidence={"undocumented_cells": undocumented_cells},
    ))

    # ----------- ADVISORY DELTAS (informational) -----------
    findings.append(Finding(
        check_id="G-W1-info",
        severity="INFO",
        message=(f"room count: before={len(rooms_before)}, "
                  f"after={len(rooms_after)}, target≥{expected_rooms_min}"),
        evidence={"before": len(rooms_before), "after": len(rooms_after),
                  "expected_min": expected_rooms_min},
    ))
    findings.append(Finding(
        check_id="G-W2-info",
        severity="INFO",
        message=(f"merged cells: before={len(merged_before)}, "
                  f"after={len(merged_after)}"),
        evidence={
            "before": [r.get("name") for r in merged_before],
            "after": [r.get("name") for r in merged_after],
        },
    ))

    # G-W5: global visual fidelity advisory
    findings.append(Finding(
        check_id="G-W5",
        severity="WARN",
        message=("global_skp_visual_fidelity requires operator confirmation "
                  "against the PDF side-by-side. Advisory."),
        evidence={},
    ))

    n_pass = sum(1 for f in findings if f.severity == "PASS")
    n_warn = sum(1 for f in findings if f.severity == "WARN")
    n_fail = sum(1 for f in findings if f.severity == "FAIL")
    n_info = sum(1 for f in findings if f.severity == "INFO")

    # ---- VERDICT LADDER (per user mandate) ----
    if n_fail:
        verdict = "FAIL"
        rec = ("a real wall is missing from human annotation; paint it in "
                "BLUE and re-run extract_human_walls + apply_human_walls")
    elif softbarrier_cells:
        verdict = "WARN"
        rec = ("walls OK; remaining merges need human_soft_barriers "
                "protocol (peitoril / grade), not more walls. Acceptable "
                "to ship if peitoril fidelity is not required.")
    elif merged_after:
        verdict = "WARN"
        rec = ("walls OK; remaining merges are semantic_room_split (open "
                "plan). Acceptable per architectural honesty.")
    else:
        verdict = "PASS"
        rec = "safe to export final SKP — fully closed cells."
    return {
        "verdict": verdict,
        "recommendation": rec,
        "summary": {"pass": n_pass, "warn": n_warn, "fail": n_fail,
                    "info": n_info, "total": len(findings)},
        "merge_classification": merge_classification,
        "findings": [asdict(f) for f in findings],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus-after", type=Path, required=True,
                    help="consensus_with_human_walls.json (post-apply).")
    ap.add_argument("--consensus-before", type=Path, default=None,
                    help="consensus_human.json (pre-apply) for delta reporting.")
    ap.add_argument("--candidates", type=Path, default=None,
                    help="loop_closure_candidates.json (closure priors). "
                         "Required for honest verdict — without it every "
                         "remaining merge counts as WARN/undocumented.")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--expected-rooms-min", type=int, default=10)
    args = ap.parse_args()

    consensus_after = json.loads(args.consensus_after.read_text())
    consensus_before = (json.loads(args.consensus_before.read_text())
                         if args.consensus_before else None)
    candidates_report = (json.loads(args.candidates.read_text())
                          if args.candidates and args.candidates.exists()
                          else None)
    report = verify(consensus_after, consensus_before,
                     candidates_report=candidates_report,
                     expected_rooms_min=args.expected_rooms_min)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(f"[ok] report -> {args.out}")
    else:
        print(json.dumps(report, indent=2))

    print()
    print(f"=== verdict: {report['verdict']} ===")
    print(f"  {report['recommendation']}")
    s = report["summary"]
    print(f"  pass/warn/fail/info: "
          f"{s['pass']}/{s['warn']}/{s['fail']}/{s.get('info', 0)}")
    if args.strict and report["verdict"] == "FAIL":
        sys.exit(2)


if __name__ == "__main__":
    main()
