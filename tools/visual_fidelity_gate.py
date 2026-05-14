"""Visual Fidelity Gate — reader scaffolding for the Visual Fidelity
Gate Protocol (2026-05-14).

This is **PR B2**. The full flow:

  PR B1  produce the 7 evidence artifacts        (tools/produce_visual_evidence.py)
  PR B2  read those artifacts + emit gate_report (this module)              ← here
  PR B3  add 8 algorithmic checks                (replaces not_yet_checked)
  PR B4  hook into verify_fidelities.py          (definitive top-level wire)

PR B2 ships the **scaffolding**: load each of the 7 artifacts,
validate presence + non-emptiness, emit a structured
``gate_report.json`` whose ``checks`` array has one entry per failure
condition. Every check starts in ``not_yet_checked`` state. PR B3
overwrites those statuses with ``pass`` / ``warn`` / ``fail``.

Top-level verdict (B2 only):
  * any artifact missing/empty           → ``FAIL`` (with policy_violation)
  * artifacts present + 0 FAIL checks    → ``WARN`` (advisory: checks
                                            pending B3 implementation)
  * any FAIL check                       → ``FAIL``
  * all checks PASS                      → ``PASS`` (only reachable once
                                            B3 lands)

The eight checks come from the protocol:

  1. door_without_opening
  2. door_crossing_or_displaced
  3. door_swing_diverges
  4. room_polygon_not_closed
  5. room_polygon_bleeds_outside
  6. invented_or_wrong_height_exterior
  7. wet_or_terrace_adjacency_wrong
  8. room_rendered_as_bbox

CLI::

    python -m tools.visual_fidelity_gate \\
        --evidence-dir fixtures/planta_74/visual_evidence \\
        --consensus fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \\
        --pdf planta_74.pdf \\
        --out fixtures/planta_74/visual_fidelity_gate_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Mirror the protocol's canonical artifact list (also used by
# ``tools/verify_fidelities.py`` and ``tools/produce_visual_evidence.py``).
REQUIRED_VISUAL_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("original_floorplan", "original_floorplan.png"),
    ("skp_render", "skp_render.png"),
    ("overlay_pdf_skp", "overlay_pdf_skp.png"),
    ("diff_walls", "diff_walls.png"),
    ("diff_doors", "diff_doors.png"),
    ("diff_rooms", "diff_rooms.png"),
    ("mismatches_list", "mismatches_list.md"),
)

# Eight failure conditions from the protocol. ``description`` is the
# operator-facing English. ``severity_on_fail`` is the level the
# check emits when it trips — uniform ``FAIL`` for PR B2 because PR
# B3 is the first cycle where checks actually run; if the protocol
# later needs WARN-level checks (advisory) the column can split.
EIGHT_CHECKS: tuple[dict, ...] = (
    {
        "key": "door_without_opening",
        "description":
            "Door drawn without a real opening in its host wall.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "door_crossing_or_displaced",
        "description":
            "Door crossing the wall (no carve) or displaced from "
            "the gap.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "door_swing_diverges",
        "description":
            "Door swing / orientation diverges from the PDF arc.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "room_polygon_not_closed",
        "description": "Room with a non-closed polygon.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "room_polygon_bleeds_outside",
        "description":
            "Room polygon bleeding outside the building outline.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "invented_or_wrong_height_exterior",
        "description":
            "Exterior wall / esquadria / peitoril invented or with "
            "the wrong height.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "wet_or_terrace_adjacency_wrong",
        "description":
            "Bathroom / lavabo / A.S. / terraço with wrong adjacency.",
        "severity_on_fail": "FAIL",
    },
    {
        "key": "room_rendered_as_bbox",
        "description":
            "Room rendered as a bounding box / block instead of real "
            "geometry.",
        "severity_on_fail": "FAIL",
    },
)

GATE_REPORT_SCHEMA_VERSION = "visual_fidelity_gate_v1"

VISUAL_FIDELITY_POLICY_VIOLATION_TAG = (
    "2026-05-14_visual_fidelity_gate_required"
)


# ---------------------------------------------------------------------------
# Artifact loading
# ---------------------------------------------------------------------------

def _inspect_artifact(evidence_dir: Path, key: str,
                       fname: str) -> dict[str, Any]:
    """Return a status dict for one artifact."""
    path = evidence_dir / fname
    try:
        exists = path.exists()
        size = path.stat().st_size if exists else 0
    except OSError:
        exists = False
        size = 0
    if exists and size > 0:
        status = "present"
    elif exists:
        status = "empty"
    else:
        status = "missing"
    return {
        "key": key,
        "filename": fname,
        "expected_path": str(path),
        "exists": exists,
        "size_bytes": size,
        "status": status,
    }


def load_artifacts(evidence_dir: Path) -> dict[str, Any]:
    """Inspect each of the seven required artifacts under
    ``evidence_dir``.

    Returns::

        {
          "directory": <str>,
          "per_artifact": [{key, filename, expected_path, exists,
                             size_bytes, status}, ...],
          "present_keys":   [...],
          "missing_keys":   [...],
          "empty_keys":     [...],
          "overall_status": "present" | "incomplete" | "missing",
        }

    ``overall_status`` is ``present`` only when ALL seven artifacts
    are ``present`` (>0 bytes). Anything else is ``incomplete`` or
    ``missing`` (when *no* artifact is present).
    """
    per_artifact = [
        _inspect_artifact(evidence_dir, k, f)
        for k, f in REQUIRED_VISUAL_ARTIFACTS
    ]
    present = [a["key"] for a in per_artifact if a["status"] == "present"]
    empty = [a["key"] for a in per_artifact if a["status"] == "empty"]
    missing = [a["key"] for a in per_artifact if a["status"] == "missing"]
    if not present and not empty:
        overall = "missing"
    elif missing or empty:
        overall = "incomplete"
    else:
        overall = "present"
    return {
        "directory": str(evidence_dir),
        "per_artifact": per_artifact,
        "present_keys": present,
        "missing_keys": missing,
        "empty_keys": empty,
        "overall_status": overall,
    }


# ---------------------------------------------------------------------------
# Per-check scaffolding
# ---------------------------------------------------------------------------

def _scaffold_check(check_def: dict) -> dict[str, Any]:
    """Build the default 'not_yet_checked' entry for one check."""
    return {
        "key": check_def["key"],
        "description": check_def["description"],
        "severity_on_fail": check_def["severity_on_fail"],
        "status": "not_yet_checked",
        "verdict": "WARN",  # advisory until B3 supplies an algorithm
        "failing_elements": [],
        "notes": (
            "Algorithm not yet implemented (lands in PR B3). The "
            "scaffold record keeps the gate report shape stable so "
            "downstream consumers (verify_fidelities, cockpit) can "
            "rely on it before B3 ships."
        ),
    }


def _scaffold_all_checks() -> list[dict[str, Any]]:
    return [_scaffold_check(d) for d in EIGHT_CHECKS]


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def _summarise_checks(checks: list[dict]) -> dict[str, int]:
    counts = {
        "checks_pass": 0,
        "checks_warn": 0,
        "checks_fail": 0,
        "checks_not_yet_checked": 0,
    }
    for c in checks:
        status = c.get("status", "not_yet_checked")
        verdict = (c.get("verdict") or "WARN").upper()
        if status == "not_yet_checked":
            counts["checks_not_yet_checked"] += 1
        elif verdict == "PASS":
            counts["checks_pass"] += 1
        elif verdict == "FAIL":
            counts["checks_fail"] += 1
        else:
            counts["checks_warn"] += 1
    return counts


def _compute_top_level(artifacts_status: str,
                        check_counts: dict[str, int]) -> str:
    """Compute the gate's top-level verdict.

    Precedence (highest wins):
      * any missing/empty artifact   → FAIL
      * any check FAIL                → FAIL
      * any check WARN OR not_yet_checked → WARN
      * all checks PASS              → PASS

    PR B2 always lands in WARN once artifacts are present (because
    the 8 checks are all ``not_yet_checked``). PR B3 supplies the
    algorithms; PASS becomes reachable then.
    """
    if artifacts_status != "present":
        return "FAIL"
    if check_counts.get("checks_fail", 0) > 0:
        return "FAIL"
    if (check_counts.get("checks_warn", 0) > 0
            or check_counts.get("checks_not_yet_checked", 0) > 0):
        return "WARN"
    return "PASS"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_gate(evidence_dir: Path,
              consensus_path: Path | None = None,
              pdf_path: Path | None = None) -> dict[str, Any]:
    """Inspect the evidence directory and produce the gate report.

    ``consensus_path`` and ``pdf_path`` are accepted but not yet
    consumed in PR B2 — they exist in the public signature so PR B3
    can wire the algorithmic checks without an API change.
    """
    artifacts = load_artifacts(evidence_dir)
    checks = _scaffold_all_checks()
    summary = {
        "artifacts_present": len(artifacts["present_keys"]),
        "artifacts_empty": len(artifacts["empty_keys"]),
        "artifacts_missing": len(artifacts["missing_keys"]),
        **_summarise_checks(checks),
    }
    top_level = _compute_top_level(
        artifacts["overall_status"], summary,
    )
    report: dict[str, Any] = {
        "schema_version": GATE_REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ",
        ),
        "evidence_dir": str(evidence_dir),
        "consensus_path": (
            str(consensus_path) if consensus_path is not None else None
        ),
        "pdf_path": (
            str(pdf_path) if pdf_path is not None else None
        ),
        "verdict_top_level": top_level,
        "artifacts": artifacts,
        "checks": checks,
        "summary": summary,
    }
    if artifacts["overall_status"] != "present":
        report["policy_violation"] = VISUAL_FIDELITY_POLICY_VIOLATION_TAG
        report["policy_reason"] = (
            "Visual Fidelity Gate Protocol (2026-05-14): "
            f"artifact-presence check failed "
            f"(overall_status={artifacts['overall_status']!r}; "
            f"missing={len(artifacts['missing_keys'])}, "
            f"empty={len(artifacts['empty_keys'])}). The gate cannot "
            "judge artifact content until all seven artifacts exist "
            "and are non-empty. Produce them via "
            "`python -m tools.produce_visual_evidence`."
        )
    if summary["checks_not_yet_checked"] > 0:
        # Stable hint so downstream consumers (cockpit, CI) know
        # which slice of B is still pending.
        report["pending_algorithmic_checks_pr"] = "B3"
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="visual_fidelity_gate",
        description=(
            "Visual Fidelity Gate (PR B2, reader scaffolding). "
            "Inspects the seven evidence artifacts produced by "
            "`tools/produce_visual_evidence.py` and emits a "
            "gate_report.json. Algorithmic checks land in PR B3."
        ),
    )
    ap.add_argument(
        "--evidence-dir", type=Path, required=True,
        help=(
            "Directory containing the seven required artifacts "
            "(original_floorplan.png, skp_render.png, "
            "overlay_pdf_skp.png, diff_walls.png, diff_doors.png, "
            "diff_rooms.png, mismatches_list.md)."
        ),
    )
    ap.add_argument(
        "--consensus", type=Path, default=None,
        help=(
            "Source consensus JSON. Not consumed in PR B2; reserved "
            "so PR B3 can wire the algorithmic checks without a "
            "CLI change."
        ),
    )
    ap.add_argument(
        "--pdf", type=Path, default=None,
        help=(
            "Source PDF. Not consumed in PR B2; reserved for the "
            "PR B3 algorithmic checks."
        ),
    )
    ap.add_argument("--out", type=Path, default=None,
                    help="Path to write gate_report.json.")
    ap.add_argument(
        "--strict", action="store_true",
        help=(
            "Exit 2 when the top-level verdict is FAIL. Without "
            "--strict the script always exits 0 so callers can "
            "inspect the report regardless."
        ),
    )
    args = ap.parse_args(argv)

    if not args.evidence_dir.exists():
        print(f"[visual_fidelity_gate] evidence directory does not "
              f"exist: {args.evidence_dir}", file=sys.stderr)
        return 2

    report = run_gate(
        evidence_dir=args.evidence_dir,
        consensus_path=args.consensus,
        pdf_path=args.pdf,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2),
                              encoding="utf-8")
        print(f"[ok] gate report -> {args.out}")

    print()
    print(f"=== Visual Fidelity Gate verdict: "
          f"{report['verdict_top_level']} ===")
    if report.get("policy_violation"):
        print(f"  policy_violation: {report['policy_violation']}")
    print(f"  evidence_dir:     {report['evidence_dir']}")
    print(f"  artifacts:        "
          f"{report['summary']['artifacts_present']}/"
          f"{len(REQUIRED_VISUAL_ARTIFACTS)} present, "
          f"{report['summary']['artifacts_missing']} missing, "
          f"{report['summary']['artifacts_empty']} empty")
    print(f"  checks:           "
          f"{report['summary']['checks_pass']} pass, "
          f"{report['summary']['checks_warn']} warn, "
          f"{report['summary']['checks_fail']} fail, "
          f"{report['summary']['checks_not_yet_checked']} "
          f"not_yet_checked (pending PR B3)")

    if args.strict and report["verdict_top_level"] == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
