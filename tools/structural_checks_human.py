"""Gates that enforce the human openings truth contract.

Companion gate to ``tools/structural_checks.py``. Reads a consensus
that has had human openings applied (via ``tools/apply_human_openings.py``)
plus the source ``human_openings_truth.json`` and enforces:

- C-H1: Total human-annotated opening count.
- C-H2..C-H4: Per-kind required counts (interior_door / window /
  glazed_balcony).
- C-H5+: Each ``explicit_constraints`` entry — require_present /
  require_absent within ``search_region_pts``.

Emits a structured report with ``verdict``:
  ``PASS``  — every required count + every explicit constraint OK
  ``WARN``  — counts OK but at least one constraint flagged advisory
  ``FAIL``  — any required count short OR any require_present missing
              OR any require_absent violated

Wired into the F0 γ pipeline via
``scripts/smoke/smoke_skp_export.py --require-human-openings`` (added
in this same PR).

This is an ADDITIVE gate. The existing ``tools/structural_checks.py``
keeps emitting its 11 checks (C1..C11) unchanged.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    check_id: str
    severity: str   # PASS | WARN | FAIL
    message: str
    evidence: dict[str, Any]


def _bbox_contains(bbox: list[float], point: list[float]) -> bool:
    x0, y0, x1, y1 = bbox
    px, py = point
    return x0 <= px <= x1 and y0 <= py <= y1


SHIFT_WARN_PT = 8.0
SHIFT_FAIL_PT = 15.0


def check(consensus: dict, truth: dict) -> dict:
    """Run all human-openings gates. Returns the report dict."""
    findings: list[Finding] = []

    # Collect human openings actually present in consensus
    human_openings = [op for op in consensus.get("openings", [])
                      if op.get("geometry_origin") == "human_annotation"]

    # C-H1: total count
    total_required = sum(truth.get("required_counts", {}).values())
    total_actual = len(human_openings)
    sev = "PASS" if total_actual >= total_required else "FAIL"
    findings.append(Finding(
        check_id="C-H1",
        severity=sev,
        message=(f"Total human openings: actual={total_actual}, "
                  f"required={total_required}"),
        evidence={"actual": total_actual, "required": total_required},
    ))

    # C-H2..C-H4: per-kind required counts
    actual_by_kind: dict[str, int] = {}
    for op in human_openings:
        k = op.get("kind_v5") or op.get("kind")
        actual_by_kind[k] = actual_by_kind.get(k, 0) + 1
    for i, (kind, req_count) in enumerate(
        sorted(truth.get("required_counts", {}).items())
    ):
        actual = actual_by_kind.get(kind, 0)
        sev = "PASS" if actual >= req_count else "FAIL"
        findings.append(Finding(
            check_id=f"C-H{2 + i}",
            severity=sev,
            message=(f"{kind}: actual={actual}, required={req_count}"),
            evidence={"kind": kind, "actual": actual,
                      "required": req_count},
        ))

    # C-H5..C-H?: per-opening hosting / shift / drawn-or-not (new in
    # 2026-05-11 per "Não usar snap grande como correção silenciosa").
    next_id = 5
    n_unhosted = 0
    n_shift_warn = 0
    n_shift_fail = 0
    n_drawn = 0
    n_carved = 0
    for op in human_openings:
        ha = op.get("human_annotation", {}) or {}
        mode = op.get("host_mode", "unknown")
        shift = float(ha.get("shift_pt", 0))
        drawn = bool(ha.get("drawn_predicted", False))
        carved = bool(ha.get("carved_predicted", False))
        if drawn:
            n_drawn += 1
        if carved:
            n_carved += 1
        # Per-opening verdict
        if mode == "unhosted":
            sev = "FAIL"
            n_unhosted += 1
            msg = (f"{op['id']} ({op.get('kind_v5', '?')}): UNHOSTED — "
                   f"no wall or colinear gap matches the user-paint "
                   f"position. Door/window will NOT render. Painter "
                   f"must adjust blob OR add a human-annotated wall.")
        elif shift > SHIFT_FAIL_PT:
            sev = "FAIL"
            n_shift_fail += 1
            msg = (f"{op['id']} ({op.get('kind_v5', '?')}): "
                   f"shift={shift:.2f}pt > {SHIFT_FAIL_PT}pt FAIL "
                   f"threshold (mode={mode}, host={ha.get('gap_id') or op.get('wall_id')}). "
                   f"User-paint position drifted too far from any wall/gap; review required.")
        elif shift > SHIFT_WARN_PT:
            sev = "WARN"
            n_shift_warn += 1
            msg = (f"{op['id']} ({op.get('kind_v5', '?')}): "
                   f"shift={shift:.2f}pt > {SHIFT_WARN_PT}pt advisory "
                   f"(mode={mode}, host={ha.get('gap_id') or op.get('wall_id')}).")
        else:
            sev = "PASS"
            msg = (f"{op['id']} ({op.get('kind_v5', '?')}): "
                   f"mode={mode} host={ha.get('gap_id') or op.get('wall_id')} "
                   f"shift={shift:.2f}pt drawn={drawn} carved={carved}")
        findings.append(Finding(
            check_id=f"C-H{next_id}",
            severity=sev,
            message=msg,
            evidence={
                "opening_id": op["id"],
                "kind": op.get("kind_v5"),
                "mode": mode,
                "shift_pt": shift,
                "drawn": drawn,
                "carved": carved,
                "host_wall_id": op.get("wall_id"),
                "gap_id": ha.get("gap_id"),
                "original_center_pdf": ha.get("original_center_pdf"),
                "adjusted_center_pdf": ha.get("adjusted_center_pdf"),
            },
        ))
        next_id += 1

    # Aggregate hosting metrics
    findings.append(Finding(
        check_id=f"C-H{next_id}",
        severity="PASS" if (n_drawn == total_actual and n_unhosted == 0) else "FAIL",
        message=(f"Hosting summary: drawn={n_drawn}/{total_actual}, "
                  f"carved={n_carved}/{total_actual}, "
                  f"unhosted={n_unhosted}/{total_actual}"),
        evidence={
            "drawn": n_drawn,
            "carved": n_carved,
            "unhosted": n_unhosted,
            "shift_warn": n_shift_warn,
            "shift_fail": n_shift_fail,
        },
    ))
    next_id += 1

    # Explicit constraints
    constraints = truth.get("explicit_constraints", [])
    for i, c in enumerate(constraints):
        cid = f"C-H{next_id + i}"
        kind = c.get("kind")
        region = c.get("search_region_pts")
        policy = c.get("policy", "require_present")
        if not kind or not region:
            findings.append(Finding(
                check_id=cid,
                severity="WARN",
                message=(f"{c.get('name', '?')}: malformed constraint, "
                          f"missing kind or search_region_pts"),
                evidence={"constraint": c},
            ))
            continue
        matches = [op for op in human_openings
                   if (op.get("kind_v5") or op.get("kind")) == kind
                   and _bbox_contains(region, op.get("center", [0, 0]))]
        if policy == "require_present":
            sev = "PASS" if matches else "FAIL"
            msg_tail = (f"{len(matches)} {kind} in region" if matches
                        else f"NO {kind} in region {region}")
        elif policy == "require_absent":
            sev = "PASS" if not matches else "FAIL"
            msg_tail = (f"0 {kind} in region (correct)" if not matches
                        else f"{len(matches)} {kind} found in forbidden region {region}")
        else:
            sev = "WARN"
            msg_tail = f"unknown policy: {policy}"
        findings.append(Finding(
            check_id=cid,
            severity=sev,
            message=f"{c.get('name', '?')}: {msg_tail}",
            evidence={"constraint": c,
                      "matches": [op.get("id") for op in matches]},
        ))

    n_fail = sum(1 for f in findings if f.severity == "FAIL")
    n_warn = sum(1 for f in findings if f.severity == "WARN")
    n_pass = sum(1 for f in findings if f.severity == "PASS")

    if n_fail:
        verdict = "FAIL"
        recommendation = "do not export SKP — human openings contract violated"
    elif n_warn:
        verdict = "WARN"
        recommendation = "export with caveats — advisory warnings present"
    else:
        verdict = "PASS"
        recommendation = "safe to export SKP — human openings contract OK"

    return {
        "verdict": verdict,
        "recommendation": recommendation,
        "summary": {"pass": n_pass, "warn": n_warn, "fail": n_fail,
                    "total": len(findings)},
        "findings": [asdict(f) for f in findings],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--truth", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=None,
                    help="Optional output JSON path; if omitted, prints to stdout.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit non-zero on FAIL (CI gate behaviour).")
    args = ap.parse_args()

    consensus = json.loads(args.consensus.read_text())
    truth = json.loads(args.truth.read_text())
    report = check(consensus, truth)

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
        import sys
        sys.exit(2)


if __name__ == "__main__":
    main()
