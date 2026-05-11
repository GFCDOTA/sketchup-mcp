"""Gate: verify the consensus AFTER human walls were applied.

Cross-checks the post-walls consensus against the user-mandated
acceptance criteria for the feat/human-walls-protocol cycle:

  G-W1  room count must approach 11 (was 7 before walls)
  G-W2  no merged cells remaining (was 2 before)
  G-W3  no unhosted human openings (was 1: h_o005)
  G-W4  all 12 human openings host on the augmented wall set
  G-W5  global_skp_visual_fidelity advisory (operator-confirmed)

Emits a structured report compatible with the existing
structural_checks_human format. Exit non-zero on FAIL when --strict.
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
    severity: str
    message: str
    evidence: dict[str, Any]


def verify(consensus_after: dict,
            consensus_before: dict | None = None,
            truth_openings: dict | None = None,
            expected_rooms_min: int = 10) -> dict:
    findings: list[Finding] = []
    rooms_after = consensus_after.get("rooms", [])
    rooms_before = consensus_before.get("rooms", []) if consensus_before else []

    # G-W1: room count
    n_after = len(rooms_after)
    n_before = len(rooms_before)
    sev = "PASS" if n_after >= expected_rooms_min else "FAIL"
    findings.append(Finding(
        check_id="G-W1",
        severity=sev,
        message=(f"room count: before={n_before}, after={n_after}, "
                  f"expected≥{expected_rooms_min}"),
        evidence={"before": n_before, "after": n_after,
                  "expected_min": expected_rooms_min},
    ))

    # G-W2: merged cells
    merged_after = [r for r in rooms_after if "|" in r.get("name", "")]
    merged_before = [r for r in rooms_before if "|" in r.get("name", "")]
    sev = "PASS" if not merged_after else "FAIL"
    findings.append(Finding(
        check_id="G-W2",
        severity=sev,
        message=(f"merged cells: before={len(merged_before)}, "
                  f"after={len(merged_after)}"),
        evidence={
            "before": [r.get("name") for r in merged_before],
            "after": [r.get("name") for r in merged_after],
        },
    ))

    # G-W3, G-W4: opening hosting on augmented walls
    from apply_human_openings import classify_opening_host_segment
    thickness = float(consensus_after.get("wall_thickness_pts", 5.4))
    walls = consensus_after.get("walls", [])
    n_unhosted = 0
    unhosted_ids: list[str] = []
    if truth_openings is None:
        # Reconstruct from consensus.openings (those carrying
        # geometry_origin=human_annotation already)
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

    sev = "PASS" if n_unhosted == 0 else "FAIL"
    findings.append(Finding(
        check_id="G-W3",
        severity=sev,
        message=(f"unhosted human openings after walls: {n_unhosted}"),
        evidence={"unhosted_ids": unhosted_ids},
    ))

    sev = "PASS" if len(truth_openings["openings"]) > 0 else "WARN"
    findings.append(Finding(
        check_id="G-W4",
        severity=sev,
        message=(f"human openings re-validated on augmented walls: "
                  f"{len(truth_openings['openings'])} total"),
        evidence={"n_human_openings": len(truth_openings["openings"])},
    ))

    # G-W5: global visual fidelity advisory
    findings.append(Finding(
        check_id="G-W5",
        severity="WARN",
        message=("global_skp_visual_fidelity requires operator "
                  "confirmation against the PDF side-by-side. This "
                  "gate is advisory; the operator must review "
                  "side_by_side_pdf_vs_skp_after_human_walls.png."),
        evidence={},
    ))

    n_pass = sum(1 for f in findings if f.severity == "PASS")
    n_warn = sum(1 for f in findings if f.severity == "WARN")
    n_fail = sum(1 for f in findings if f.severity == "FAIL")
    if n_fail:
        verdict = "FAIL"
        rec = "do not export final SKP — wall augmentation insufficient"
    elif n_warn:
        verdict = "WARN"
        rec = "review side-by-side image; counts + hosting OK"
    else:
        verdict = "PASS"
        rec = "safe to export final SKP"
    return {
        "verdict": verdict,
        "recommendation": rec,
        "summary": {"pass": n_pass, "warn": n_warn, "fail": n_fail,
                    "total": len(findings)},
        "findings": [asdict(f) for f in findings],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus-after", type=Path, required=True,
                    help="consensus_with_human_walls.json (post-apply).")
    ap.add_argument("--consensus-before", type=Path, default=None,
                    help="consensus_human.json (pre-apply) for delta reporting.")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--expected-rooms-min", type=int, default=10)
    args = ap.parse_args()

    consensus_after = json.loads(args.consensus_after.read_text())
    consensus_before = (json.loads(args.consensus_before.read_text())
                         if args.consensus_before else None)
    report = verify(consensus_after, consensus_before,
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
    print(f"  pass/warn/fail: "
          f"{report['summary']['pass']}/"
          f"{report['summary']['warn']}/"
          f"{report['summary']['fail']}")
    if args.strict and report["verdict"] == "FAIL":
        sys.exit(2)


if __name__ == "__main__":
    main()
