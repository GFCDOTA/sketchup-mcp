"""Four-axis fidelity verdict for human-augmented consensus.

Created 2026-05-12 per user mandate:

    "Quero os verdicts separados:
       1. wall_fidelity            — PASS if all physical walls
                                       represented + h_o005 carved.
       2. soft_barrier_fidelity    — WARN/FAIL while peitoris/
                                       guarda-corpos not represented
                                       as low wall/rail/soft divider.
       3. semantic_room_fidelity   — PASS/WARN if SALA|SALA merged by
                                       open plan, labels preserved.
       4. global_visual_fidelity   — only PASS after operator confirms
                                       side-by-side PDF vs SKP."

This wraps ``verify_after_human_walls`` (the gate-level machinery)
and projects its findings onto the four user-mandated axes.

Verdict ladder per axis:

  • wall_fidelity
      FAIL  if any pair in loop_closure_candidates has
            candidate_type=human_wall + should_user_paint=True
            (real masonry missing) OR h_o005 is not hosted
            (cut_into_wall or existing_gap).
      WARN  if h_o005 is hosted but only via existing_gap (not
            cut_into_wall — visually present but not carved).
      PASS  if all required walls painted AND h_o005 hosted via
            cut_into_wall (carved through a wall, drawn as door
            leaf).

  • soft_barrier_fidelity
      FAIL  if leak_map lists ≥1 cell with candidate_type=
            human_soft_barrier AND no human soft_barrier
            (geometry_origin=human_annotation) has been applied for
            that cell yet. The protocol exists; the operator must run
            it.
      WARN  if soft_barriers were applied but some target cells
            remain merged (post-soft-barrier polygonize didn't fully
            close — partial protocol execution).
      PASS  if every soft_barrier_target cell is now split OR no
            cells ever needed soft barriers.

  • semantic_room_fidelity
      PASS  if every still-merged cell whose pairs are all
            semantic_room_split has the original room labels
            preserved in the merged name (e.g. "SALA DE JANTAR |
            SALA DE ESTAR"). Floor zones reconstructible.
      WARN  if a semantic merge dropped a label.

  • global_visual_fidelity
      Always WARN (advisory) unless the operator passes
      --operator-confirmed-visual on the CLI, indicating they
      reviewed the side_by_side PNG and accept it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS))


def _classify_opening_runtime(opening_truth_entry: dict,
                                 walls: list[dict],
                                 thickness: float) -> dict:
    """Re-run host classification against the LIVE walls. Used so the
    verdict reflects the augmented wall set, not the (possibly stale)
    consensus.openings[].host_mode snapshot from before walls were
    applied."""
    from apply_human_openings import classify_opening_host_segment
    return classify_opening_host_segment(opening_truth_entry, walls,
                                            thickness)


def _wall_fidelity(consensus_after: dict,
                    candidates_report: dict) -> dict:
    walls = consensus_after.get("walls", [])
    thickness = float(consensus_after.get("wall_thickness_pts", 5.4))
    cands = candidates_report.get("candidates", [])

    # Real wall missing? (any human_wall + should_user_paint=True)
    missing_walls = [c for c in cands
                       if c.get("candidate_type") == "human_wall"
                       and c.get("should_user_paint")]

    # h_o005 specifically: find by id (or by index — h_o005 = 6th)
    h_o005_state = "missing"
    h_o005_carved = False
    h_o005_host = None
    for op in consensus_after.get("openings", []):
        if op.get("geometry_origin") != "human_annotation":
            continue
        if op.get("id") != "h_o005":
            continue
        ann = op.get("human_annotation", {}) or {}
        bbox_pts = ann.get("bbox_pts")
        if not bbox_pts:
            h_o005_state = "no_bbox"
            break
        # Derive orientation from bbox aspect (top-level op.orientation
        # may be absent on synthesized human_annotation openings).
        x0, y0, x1, y1 = bbox_pts
        derived_ori = "h" if (x1 - x0) >= (y1 - y0) else "v"
        entry = {
            "bbox_pts": bbox_pts,
            "center_pts": op.get("center"),
            "opening_width_pts": op.get("opening_width_pts", 0),
            "orientation": op.get("orientation") or derived_ori,
        }
        h = _classify_opening_runtime(entry, walls, thickness)
        h_o005_state = h["mode"]
        h_o005_carved = (h["mode"] == "cut_into_wall")
        h_o005_host = h.get("host_wall_id")
        break

    if missing_walls:
        verdict = "FAIL"
        reason = (f"{len(missing_walls)} physical wall(s) NOT painted in "
                   f"human_walls_annotation.png; the leak map flags them "
                   f"as candidate_type=human_wall + should_user_paint=True.")
    elif h_o005_state == "unhosted" or h_o005_state == "missing":
        verdict = "FAIL"
        reason = (f"h_o005 (A.S.<->COZINHA interior_door) is "
                   f"{h_o005_state}; no host wall covers its position.")
    elif h_o005_state == "existing_gap" and not h_o005_carved:
        verdict = "WARN"
        reason = ("h_o005 hosted via existing_gap (visually present but "
                   "not carved through a wall — door leaf drawn between "
                   "wall stubs).")
    elif h_o005_carved:
        verdict = "PASS"
        reason = ("all physical walls present; h_o005 cut_into_wall "
                   "(carved + door leaf drawn).")
    else:
        verdict = "WARN"
        reason = f"h_o005 in unrecognized state: {h_o005_state}"

    return {
        "verdict": verdict,
        "reason": reason,
        "n_walls_missing": len(missing_walls),
        "missing_wall_pairs": [
            f"{c['from_room']} <-> {c['to_room']}" for c in missing_walls
        ],
        "h_o005_host_mode": h_o005_state,
        "h_o005_carved": h_o005_carved,
        "h_o005_host_wall_id": h_o005_host,
    }


def _soft_barrier_fidelity(consensus_after: dict,
                              candidates_report: dict) -> dict:
    sbarriers = consensus_after.get("soft_barriers", [])
    h_sbarriers = [b for b in sbarriers
                    if b.get("geometry_origin") == "human_annotation"]
    cands = candidates_report.get("candidates", [])

    target_pairs = [c for c in cands
                     if c.get("candidate_type") == "human_soft_barrier"]
    # Group target pairs by merged cell name
    rooms = consensus_after.get("rooms", [])
    target_cells = set()
    merged_names = [r["name"] for r in rooms if "|" in r.get("name", "")]
    for cell_name in merged_names:
        names = {n.strip() for n in cell_name.split("|")}
        for c in target_pairs:
            if c.get("from_room") in names and c.get("to_room") in names:
                target_cells.add(cell_name)
                break

    if not target_pairs:
        return {
            "verdict": "PASS",
            "reason": ("no cell requires a soft_barrier (leak map "
                        "lists 0 candidate_type=human_soft_barrier)."),
            "n_target_pairs": 0,
            "n_target_cells": 0,
            "n_human_soft_barriers_applied": len(h_sbarriers),
            "target_cells": [],
        }

    if not h_sbarriers:
        return {
            "verdict": "FAIL",
            "reason": (f"{len(target_pairs)} pair(s) across "
                        f"{len(target_cells)} merged cell(s) need a "
                        f"soft_barrier (peitoril/grade/esquadria) but "
                        f"0 human soft_barriers have been applied. "
                        f"Run the human_soft_barriers protocol."),
            "n_target_pairs": len(target_pairs),
            "n_target_cells": len(target_cells),
            "n_human_soft_barriers_applied": 0,
            "target_cells": sorted(target_cells),
        }

    # Soft barriers were applied. If target cells are still merged →
    # WARN (partial); else PASS.
    still_merged = sorted(c for c in target_cells if c in merged_names)
    if still_merged:
        return {
            "verdict": "WARN",
            "reason": (f"{len(h_sbarriers)} human soft_barriers applied "
                        f"but {len(still_merged)} target cell(s) still "
                        f"merged — the painted barriers do not fully "
                        f"close the loops."),
            "n_target_pairs": len(target_pairs),
            "n_target_cells": len(target_cells),
            "n_human_soft_barriers_applied": len(h_sbarriers),
            "target_cells_still_merged": still_merged,
        }
    return {
        "verdict": "PASS",
        "reason": (f"{len(h_sbarriers)} human soft_barriers applied; "
                    f"all soft_barrier-target cells split."),
        "n_target_pairs": len(target_pairs),
        "n_target_cells": len(target_cells),
        "n_human_soft_barriers_applied": len(h_sbarriers),
    }


def _semantic_room_fidelity(consensus_after: dict,
                              candidates_report: dict,
                              labels: list[dict] | None) -> dict:
    cands = candidates_report.get("candidates", [])
    rooms = consensus_after.get("rooms", [])
    merged = [r for r in rooms if "|" in r.get("name", "")]

    # For each semantic-only merged cell, check label preservation
    semantic_cells: list[dict] = []
    for cell in merged:
        name = cell.get("name", "")
        cell_names = [n.strip() for n in name.split("|")]
        # All pairs semantic?
        pair_set = {n.strip() for n in cell_names}
        cell_pairs = [c for c in cands
                       if c.get("from_room") in pair_set
                       and c.get("to_room") in pair_set]
        if not cell_pairs:
            continue
        if not all(c.get("candidate_type") == "semantic_room_split"
                    for c in cell_pairs):
            continue
        # Check every constituent label still exists somewhere
        labels_present = []
        labels_missing = []
        if labels:
            label_names = {lb["name"] for lb in labels}
            for n in cell_names:
                if n in label_names:
                    labels_present.append(n)
                else:
                    labels_missing.append(n)
        semantic_cells.append({
            "cell_name": name,
            "constituent_labels": cell_names,
            "labels_present": labels_present,
            "labels_missing": labels_missing,
        })

    if not semantic_cells:
        return {
            "verdict": "PASS",
            "reason": "no semantic_room_split merges remain.",
            "n_semantic_cells": 0,
            "semantic_cells": [],
        }
    n_missing = sum(len(c["labels_missing"]) for c in semantic_cells)
    if n_missing:
        return {
            "verdict": "WARN",
            "reason": (f"{n_missing} label(s) dropped from semantic merges; "
                        f"floor zones not fully reconstructible."),
            "n_semantic_cells": len(semantic_cells),
            "semantic_cells": semantic_cells,
        }
    return {
        "verdict": "PASS",
        "reason": (f"{len(semantic_cells)} open-plan merge(s); all "
                    f"constituent labels preserved in cell names."),
        "n_semantic_cells": len(semantic_cells),
        "semantic_cells": semantic_cells,
    }


def _global_visual_fidelity(operator_confirmed: bool,
                               side_by_side_path: Path | None) -> dict:
    if operator_confirmed:
        return {
            "verdict": "PASS",
            "reason": "operator confirmed visual fidelity against PDF "
                        "side-by-side render.",
            "side_by_side_artifact": (str(side_by_side_path)
                                          if side_by_side_path else None),
        }
    return {
        "verdict": "WARN",
        "reason": ("operator review pending. Open the side-by-side "
                    "render and pass --operator-confirmed-visual if "
                    "it looks faithful to the PDF."),
        "side_by_side_artifact": (str(side_by_side_path)
                                      if side_by_side_path else None),
    }


# Visual Fidelity Gate Protocol (2026-05-14). See
# docs/protocols/visual_fidelity_gate_protocol.md.
#
# Keep the list ordered so the report's `missing_visual_artifacts`
# field is deterministic.
REQUIRED_VISUAL_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("original_floorplan", "original_floorplan.png"),
    ("skp_render", "skp_render.png"),
    ("overlay_pdf_skp", "overlay_pdf_skp.png"),
    ("diff_walls", "diff_walls.png"),
    ("diff_doors", "diff_doors.png"),
    ("diff_rooms", "diff_rooms.png"),
    ("mismatches_list", "mismatches_list.md"),
)

VISUAL_FIDELITY_POLICY_VIOLATION_TAG = (
    "2026-05-14_visual_fidelity_gate_required"
)


def _check_visual_evidence(visual_evidence_dir: Path | None
                              ) -> dict[str, Any]:
    """Inspect the visual-evidence directory for the seven required
    artifacts. PR-A artifact-presence mode: a >0-byte file at the
    expected path counts as `present`; everything else is `missing`.
    PR B will refine this with per-artifact checks that set
    `incomplete` when an artifact exists but fails its content gate.

    Returns a dict with:
      * `required`: ordered list of artifact keys (canonical).
      * `present`: list of keys for artifacts whose file exists.
      * `missing`: list of keys for artifacts whose file is absent
        or empty.
      * `status`: one of `present` (all 7), `incomplete` (some, but
        not all 7), `missing` (none).
      * `directory`: stringified `visual_evidence_dir` (or null
        when no dir was supplied).
      * `per_artifact`: list of dicts with `{key, expected_path,
        status}`.
    """
    required_keys = [k for k, _ in REQUIRED_VISUAL_ARTIFACTS]
    if visual_evidence_dir is None:
        return {
            "required": required_keys,
            "present": [],
            "missing": list(required_keys),
            "status": "missing",
            "directory": None,
            "per_artifact": [
                {"key": k, "expected_path": fname, "status": "missing"}
                for k, fname in REQUIRED_VISUAL_ARTIFACTS
            ],
        }
    base = Path(visual_evidence_dir)
    present: list[str] = []
    missing: list[str] = []
    per_artifact: list[dict] = []
    for key, fname in REQUIRED_VISUAL_ARTIFACTS:
        path = base / fname
        try:
            exists_nonempty = path.exists() and path.stat().st_size > 0
        except OSError:
            exists_nonempty = False
        if exists_nonempty:
            present.append(key)
            status = "present"
        else:
            missing.append(key)
            status = "missing"
        per_artifact.append({
            "key": key,
            "expected_path": str(path),
            "status": status,
        })
    if len(missing) == 0:
        overall = "present"
    elif len(present) == 0:
        overall = "missing"
    else:
        overall = "incomplete"
    return {
        "required": required_keys,
        "present": present,
        "missing": missing,
        "status": overall,
        "directory": str(base),
        "per_artifact": per_artifact,
    }


def verify_fidelities(consensus_after: dict,
                        candidates_report: dict,
                        labels: list[dict] | None = None,
                        operator_confirmed_visual: bool = False,
                        side_by_side_path: Path | None = None,
                        require_visual_evidence: bool = False,
                        visual_evidence_dir: Path | None = None,
                        ) -> dict[str, Any]:
    """Produce the 4 separated verdicts.

    When ``require_visual_evidence=True``, the Visual Fidelity Gate
    Protocol (2026-05-14) applies: the per-axis verdicts are computed
    as before, but the top-level verdict is **forced to FAIL** unless
    all seven artifacts described in
    ``REQUIRED_VISUAL_ARTIFACTS`` exist in
    ``visual_evidence_dir`` and are non-empty. The per-axis verdicts
    are preserved (the operator can still see which axes
    algorithmically pass); only the top-level reflects the gate.

    When ``require_visual_evidence=False`` (default), behaviour is
    byte-equivalent to the prior contract — existing callers and CI
    workflows are unaffected.
    """
    wf = _wall_fidelity(consensus_after, candidates_report)
    sbf = _soft_barrier_fidelity(consensus_after, candidates_report)
    srf = _semantic_room_fidelity(consensus_after, candidates_report, labels)
    gvf = _global_visual_fidelity(operator_confirmed_visual, side_by_side_path)

    # Top-level verdict = worst of (wall, soft_barrier, semantic, global)
    severity_rank = {"FAIL": 3, "WARN": 2, "PASS": 1}
    by_axis = {
        "wall_fidelity": wf,
        "soft_barrier_fidelity": sbf,
        "semantic_room_fidelity": srf,
        "global_visual_fidelity": gvf,
    }
    worst = max(severity_rank[v["verdict"]] for v in by_axis.values())
    top = next(k for k, v in severity_rank.items() if v == worst)
    # top-level uses the FAIL/WARN/PASS string, not "wall_fidelity"

    report: dict[str, Any] = {
        "schema_version": "1.0",
        "verdict_top_level": top,
        "fidelities": by_axis,
    }

    if require_visual_evidence:
        evidence = _check_visual_evidence(visual_evidence_dir)
        report["visual_evidence_required"] = True
        report["visual_evidence_status"] = evidence["status"]
        report["missing_visual_artifacts"] = evidence["missing"]
        report["visual_evidence"] = evidence
        if evidence["status"] != "present":
            report["verdict_top_level_pre_visual_gate"] = top
            report["verdict_top_level"] = "FAIL"
            report["policy_violation"] = VISUAL_FIDELITY_POLICY_VIOLATION_TAG
            report["policy_reason"] = (
                "Visual Fidelity Gate Protocol (2026-05-14): "
                f"visual_evidence_status={evidence['status']!r}; "
                f"missing {len(evidence['missing'])} of "
                f"{len(REQUIRED_VISUAL_ARTIFACTS)} required "
                "artifacts. Per-axis verdicts are preserved above; "
                "top-level is forced to FAIL until the seven "
                "artifacts are produced. See "
                "docs/protocols/visual_fidelity_gate_protocol.md."
            )

    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus-after", type=Path, required=True)
    ap.add_argument("--candidates", type=Path, required=True,
                    help="loop_closure_candidates_after_walls.json "
                         "(generated post-walls / post-soft-barriers).")
    ap.add_argument("--labels", type=Path, default=None,
                    help="Original labels.json (for semantic_room_fidelity "
                         "label-preservation check).")
    ap.add_argument("--side-by-side", type=Path, default=None)
    ap.add_argument("--operator-confirmed-visual", action="store_true",
                    help="Set when operator has reviewed the side-by-side "
                         "and accepts the global_visual_fidelity. Without "
                         "this flag global_visual_fidelity is WARN.")
    ap.add_argument(
        "--require-visual-evidence", action="store_true",
        help=(
            "Apply the Visual Fidelity Gate Protocol (2026-05-14, "
            "docs/protocols/visual_fidelity_gate_protocol.md). When set, "
            "the top-level verdict is FORCED to FAIL unless the seven "
            "required visual evidence artifacts exist under "
            "--visual-evidence-dir. Per-axis verdicts are preserved. "
            "Without this flag the script is byte-equivalent to the "
            "prior contract."
        ),
    )
    ap.add_argument(
        "--visual-evidence-dir", type=Path, default=None,
        help=(
            "Directory inspected for the seven required visual evidence "
            "artifacts (original_floorplan.png, skp_render.png, "
            "overlay_pdf_skp.png, diff_walls.png, diff_doors.png, "
            "diff_rooms.png, mismatches_list.md). Defaults to the parent "
            "directory of --consensus-after when --require-visual-evidence "
            "is set."
        ),
    )
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    consensus_after = json.loads(args.consensus_after.read_text())
    candidates_report = json.loads(args.candidates.read_text())
    labels = (json.loads(args.labels.read_text())
              if args.labels and args.labels.exists() else None)

    visual_evidence_dir = args.visual_evidence_dir
    if args.require_visual_evidence and visual_evidence_dir is None:
        visual_evidence_dir = args.consensus_after.parent

    report = verify_fidelities(
        consensus_after, candidates_report,
        labels=labels,
        operator_confirmed_visual=args.operator_confirmed_visual,
        side_by_side_path=args.side_by_side,
        require_visual_evidence=args.require_visual_evidence,
        visual_evidence_dir=visual_evidence_dir,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2))
        print(f"[ok] fidelity report -> {args.out}")

    # Pretty console summary
    print()
    print(f"=== Top-level verdict: {report['verdict_top_level']} ===")
    if report.get("policy_violation"):
        pre_gate = report.get("verdict_top_level_pre_visual_gate")
        print(f"  policy_violation: {report['policy_violation']}")
        print(f"  pre-gate top-level (per-axis worst): {pre_gate}")
        print(f"  visual_evidence_status: "
              f"{report.get('visual_evidence_status')}")
        if report.get("missing_visual_artifacts"):
            missing = ", ".join(report["missing_visual_artifacts"])
            print(f"  missing artifacts: {missing}")
    print()
    print(f"{'axis':>26}  {'verdict':>5}  reason")
    print(f"{'-'*26:>26}  {'-'*5:>5}  {'-'*60}")
    for axis, body in report["fidelities"].items():
        print(f"{axis:>26}  {body['verdict']:>5}  {body['reason']}")

    if args.strict and report["verdict_top_level"] == "FAIL":
        sys.exit(2)


if __name__ == "__main__":
    main()
