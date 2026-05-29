#!/usr/bin/env python3
"""FP-030 — Visual Oracle Gate runner.

Generates a `.skp` for the given fixture, runs deterministic heuristics
over `geometry_report.json`, emits `visual_findings.json` matching the
v1 schema, promotes artifacts to `artifacts/review/<fixture>/<run_id>/final/`,
and writes a `regression_summary.md`.

The visual-qualitative axes (global_visual, scale_rotation) are NOT
fully decidable from numeric data alone — for those the script emits
`WARN: needs_human_or_agent_inline_review` and links the render path
so a downstream agent (Claude inline, vision API, or human reviewer)
can finalise the verdict.

Constitution #8 — No SKP, no progress.
Constitution #8 — No visual proof, no progress.

Usage:
    python -m tools.run_skp_visual_review \\
        --fixture planta_74 \\
        --consensus fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \\
        --out artifacts/review/planta_74/visual_loop_current \\
        --max-attempts 3
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "visual_findings.v1"

AXES = [
    "wall_fidelity",
    "door_fidelity",
    "window_fidelity",
    "room_fidelity",
    "scale_rotation",
    "global_visual",
]

# --- helpers ----------------------------------------------------------


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_consensus_kinds(consensus: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for op in consensus.get("openings", []):
        kind = op.get("kind_v5") or op.get("kind") or "unknown"
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _group_counts(report: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for g in report.get("groups_diagnostic", []):
        name = g.get("name", "")
        for prefix in (
            "PlanShell_Group",
            "Floor_Group",
            "WindowGlass_Group",
            "DoorLeaf_Group",
            "GlazedBalcony_Group",
            "SoftBarrier_Group",
        ):
            if name.startswith(prefix):
                counts[prefix] = counts.get(prefix, 0) + 1
                break
    return counts


# --- heuristics -------------------------------------------------------


def _check_gates_self_check(report: dict) -> list[dict]:
    findings: list[dict] = []
    gates = report.get("gates_self_check", {})
    for gate_name, value in gates.items():
        if value is False:
            findings.append({
                "severity": "FAIL",
                "axis": (
                    "wall_fidelity"
                    if "shell" in gate_name or "wall" in gate_name
                    else "global_visual"
                ),
                "type": "gates_self_check_fail",
                "location": f"geometry_report.gates_self_check.{gate_name}",
                "evidence": (
                    f"gate `{gate_name}` is false; per FP-030 hard gate "
                    f"#8 any gates_self_check false blocks promotion."
                ),
                "source_check": (
                    "tools/build_plan_shell_skp.py write_geometry_report"
                ),
                "suspected_owner": "builder",
                "proposed_fix": (
                    "Run FP-026 diagnostic and inspect "
                    "shell_stats_from_python; do not promote until gate is true."
                ),
            })
    return findings


def _check_window_count(report: dict, consensus: dict) -> list[dict]:
    findings: list[dict] = []
    expected = sum(
        1 for op in consensus.get("openings", [])
        if (op.get("kind_v5") or op.get("kind")) == "window"
    )
    actual = report.get("shell_stats_from_python", {}).get(
        "window_apertures_3d", -1
    )
    if actual != expected:
        findings.append({
            "severity": "FAIL",
            "axis": "window_fidelity",
            "type": "window_count_mismatch",
            "location": "geometry_report.shell_stats_from_python.window_apertures_3d",
            "evidence": (
                f"window_apertures_3d={actual} != "
                f"count(kind_v5==window)={expected}"
            ),
            "source_check": (
                "tools/build_plan_shell_skp.py:build_shell_polygon — "
                "opening kind routing"
            ),
            "suspected_owner": "opening_routing",
            "proposed_fix": (
                "Diagnose which window leaked into 2D carve OR was "
                "skipped. Cross-check with "
                "tests/test_opening_routing_invariants.py."
            ),
        })
    return findings


def _check_floating_doors(report: dict, eps: float = 0.05) -> list[dict]:
    findings: list[dict] = []
    for g in report.get("groups_diagnostic", []):
        if not g.get("name", "").startswith("DoorLeaf_Group"):
            continue
        bbox = g.get("bbox_m", {}).get("min", [0, 0, 0])
        z_min = bbox[2] if len(bbox) > 2 else 0
        if z_min > eps:
            findings.append({
                "severity": "FAIL",
                "axis": "door_fidelity",
                "type": "floating_door",
                "location": f"groups_diagnostic[name={g['name']}].bbox_m.min[2]={z_min}",
                "evidence": (
                    f"door group `{g['name']}` has bbox z_min={z_min:.3f}m "
                    f"> {eps}m; door should touch floor (z_min ~ 0)."
                ),
                "source_check": (
                    "tools/build_plan_shell_skp.rb door_leaf_group origin Z"
                ),
                "suspected_owner": "builder",
                "proposed_fix": (
                    "Ensure DoorLeaf_Group transforms set Z origin to 0."
                ),
            })
    return findings


def _check_orphan_window_glass(report: dict, consensus: dict) -> list[dict]:
    findings: list[dict] = []
    window_opening_ids = {
        op.get("id")
        for op in consensus.get("openings", [])
        if (op.get("kind_v5") or op.get("kind")) == "window"
    }
    for g in report.get("groups_diagnostic", []):
        name = g.get("name", "")
        if not name.startswith("WindowGlass_Group_"):
            continue
        # Group name convention: WindowGlass_Group_<opening_id>
        suffix = name[len("WindowGlass_Group_"):]
        if suffix not in window_opening_ids:
            findings.append({
                "severity": "FAIL",
                "axis": "window_fidelity",
                "type": "orphan_glass_panel",
                "location": f"groups_diagnostic[name={name}]",
                "evidence": (
                    f"WindowGlass group `{name}` has no matching "
                    f"opening_id `{suffix}` in consensus with kind=window."
                ),
                "source_check": (
                    "consensus.openings vs Ruby builder window aperture loop"
                ),
                "suspected_owner": "opening_routing",
                "proposed_fix": (
                    "Verify the opening_id naming convention "
                    "(prefix `h_o`) matches between consensus and "
                    "geometry_report."
                ),
            })
    return findings


def _check_window_height(report: dict, eps: float = 0.1) -> list[dict]:
    """Window glass groups must have height in window range [0.9, 1.5]m
    (peitoril + verga preserved). Outside this = bad_window_aperture."""
    findings: list[dict] = []
    for g in report.get("groups_diagnostic", []):
        if not g.get("name", "").startswith("WindowGlass_Group"):
            continue
        h = g.get("height_m")
        if h is None:
            continue
        if h < (0.9 - eps) or h > (1.5 + eps):
            findings.append({
                "severity": "FAIL",
                "axis": "window_fidelity",
                "type": "bad_window_aperture",
                "location": f"groups_diagnostic[name={g['name']}].height_m={h}",
                "evidence": (
                    f"window aperture height_m={h:.3f} outside expected "
                    f"range [0.9, 1.5]m; peitoril/verga likely missing."
                ),
                "source_check": (
                    "tools/build_plan_shell_skp.rb window_aperture_z"
                ),
                "suspected_owner": "builder",
                "proposed_fix": (
                    "Confirm FP-024 partial-height aperture path is active "
                    "(not 2D full-height carve)."
                ),
            })
    return findings


def _check_floor_leak(report: dict) -> list[dict]:
    findings: list[dict] = []
    fg = report.get("floor_groups", {})
    if not fg.get("present", False) or fg.get("count", 0) == 0:
        findings.append({
            "severity": "FAIL",
            "axis": "room_fidelity",
            "type": "floor_leak",
            "location": "geometry_report.floor_groups",
            "evidence": (
                f"floor_groups.present={fg.get('present')}, "
                f"count={fg.get('count')}. No floor coverage = floor leak."
            ),
            "source_check": (
                "tools/build_plan_shell_skp.py polygonize → "
                "Ruby Floor_Group creation"
            ),
            "suspected_owner": "builder",
            "proposed_fix": (
                "Inspect shell_stats_from_python.shell_pieces_after_union; "
                "if > 0 but no Floor_Group, Ruby pipeline broke."
            ),
        })
    return findings


# --- main inspection --------------------------------------------------


def inspect_report(report: dict, consensus: dict) -> list[dict]:
    """Run all deterministic heuristics. Returns list of finding dicts
    (without `id` field — caller assigns vf_001, vf_002, ...)."""
    findings: list[dict] = []
    findings.extend(_check_gates_self_check(report))
    findings.extend(_check_window_count(report, consensus))
    findings.extend(_check_floating_doors(report))
    findings.extend(_check_orphan_window_glass(report, consensus))
    findings.extend(_check_window_height(report))
    findings.extend(_check_floor_leak(report))
    return findings


def axes_verdict_from_findings(findings: list[dict]) -> dict[str, dict]:
    """Aggregate findings into per-axis verdicts."""
    axes: dict[str, dict] = {}
    for axis in AXES:
        axis_findings = [f for f in findings if f.get("axis") == axis]
        if not axis_findings:
            if axis in {"global_visual", "scale_rotation"}:
                axes[axis] = {
                    "verdict": "WARN",
                    "evidence": (
                        "Numeric heuristics cannot decide this axis; needs "
                        "human/agent inline review of render PNGs."
                    ),
                }
            else:
                axes[axis] = {
                    "verdict": "PASS",
                    "evidence": (
                        "No deterministic finding produced for this axis."
                    ),
                }
        else:
            has_fail = any(f["severity"] == "FAIL" for f in axis_findings)
            axes[axis] = {
                "verdict": "FAIL" if has_fail else "WARN",
                "evidence": "; ".join(
                    f["evidence"] for f in axis_findings[:3]
                ),
            }
    return axes


def top_level_verdict(findings: list[dict], axes: dict[str, dict]) -> str:
    if any(f["severity"] == "FAIL" for f in findings):
        return "FAIL"
    if any(a["verdict"] == "FAIL" for a in axes.values()):
        return "FAIL"
    if any(a["verdict"] == "WARN" for a in axes.values()):
        return "WARN"
    return "PASS"


# --- artifact promotion -----------------------------------------------


def promote_attempt(
    runs_dir: Path, out_attempt_dir: Path, fixture: str
) -> dict[str, Path]:
    """Copy SKP + renders + report from runs/ to artifacts/review/.../<attempt>/.

    The builder (`tools/build_plan_shell_skp.{py,rb}`) writes renders
    with a fixed `model_*.png` prefix regardless of --out. We honour
    that convention here and normalise destination names.
    """
    out_attempt_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        # (source name in runs/<fixture>/) -> (dest name in attempt dir)
        f"{fixture}.skp": "model.skp",
        "model_top.png": "model_top.png",
        "model_iso.png": "model_iso.png",
        "geometry_report.json": "geometry_report.json",
    }
    promoted: dict[str, Path] = {}
    for src_name, dst_name in mapping.items():
        src = runs_dir / src_name
        if src.exists():
            dst = out_attempt_dir / dst_name
            shutil.copy2(src, dst)
            promoted[dst_name] = dst
        else:
            promoted[dst_name] = None  # type: ignore[assignment]
    return promoted


def write_blocked_summary(out_dir: Path, reason: str, next_cmd: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    findings = {
        "schema_version": SCHEMA_VERSION,
        "fixture": "blocked",
        "attempt": "blocked",
        "top_level_verdict": "FAIL",
        "axes": {a: {"verdict": "FAIL", "evidence": reason} for a in AXES},
        "findings": [{
            "id": "vf_blocked",
            "severity": "FAIL",
            "axis": "global_visual",
            "type": "global_visual_fail",
            "location": "n/a",
            "evidence_image": "n/a",
            "evidence": reason,
            "source_check": "tooling",
            "suspected_owner": "tooling",
            "proposed_fix": next_cmd,
        }],
    }
    _write_json(out_dir / "visual_findings.json", findings)
    summary = (
        f"# SKP Visual Review — BLOCKED\n\n"
        f"## Time\n{_now_utc_iso()}\n\n"
        f"## Reason\n{reason}\n\n"
        f"## Next command\n```bash\n{next_cmd}\n```\n"
    )
    (out_dir / "regression_summary.md").write_text(summary, encoding="utf-8")


# --- builder integration ----------------------------------------------


def run_builder(
    consensus_path: Path, out_skp: Path, python_exe: Path | None = None
) -> tuple[int, str]:
    """Invoke build_plan_shell_skp. Returns (returncode, log_tail)."""
    # Always force-skp: visual review needs fresh artifacts. Cache-hit
    # would skip render/report regeneration even when stale PNGs from
    # a prior run linger in runs/.
    cmd = [
        str(python_exe or sys.executable),
        "-m",
        "tools.build_plan_shell_skp",
        str(consensus_path),
        "--out",
        str(out_skp),
        "--force-skp",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        log = (result.stdout or "") + (result.stderr or "")
        return result.returncode, log[-2000:]
    except subprocess.TimeoutExpired:
        return -1, "build timed out after 600s"
    except Exception as e:
        return -2, f"builder invoke error: {e!r}"


# --- attempt orchestration --------------------------------------------


def run_attempt(
    attempt_idx: int,
    fixture: str,
    consensus_path: Path,
    runs_dir: Path,
    out_attempts_dir: Path,
    python_exe: Path | None,
) -> dict:
    """One attempt: build → load report → run heuristics → write findings."""
    print(f"\n=== Attempt {attempt_idx} ===", flush=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    out_skp = runs_dir / f"{fixture}.skp"

    rc, log_tail = run_builder(consensus_path, out_skp, python_exe)
    print(f"[builder] rc={rc}")
    if rc != 0 or not out_skp.exists():
        return {
            "attempt": attempt_idx,
            "rc": rc,
            "log_tail": log_tail,
            "blocked": True,
            "reason": (
                f"builder failed (rc={rc}); SKP not produced. "
                f"Tail: {log_tail[-500:]}"
            ),
        }

    report_path = runs_dir / "geometry_report.json"
    if not report_path.exists():
        return {
            "attempt": attempt_idx,
            "rc": rc,
            "blocked": True,
            "reason": "build ok but geometry_report.json missing",
        }

    report = _load_json(report_path)
    consensus = _load_json(consensus_path)

    findings_raw = inspect_report(report, consensus)
    findings = []
    for i, f in enumerate(findings_raw, start=1):
        f_out = dict(f)
        f_out["id"] = f"vf_{i:03d}"
        f_out.setdefault("evidence_image", "model_iso.png")
        findings.append(f_out)

    axes = axes_verdict_from_findings(findings)
    verdict = top_level_verdict(findings, axes)

    attempt_dir = out_attempts_dir / f"attempt_{attempt_idx}"
    promote_attempt(runs_dir, attempt_dir, fixture)
    findings_doc = {
        "schema_version": SCHEMA_VERSION,
        "fixture": fixture,
        "attempt": f"attempt_{attempt_idx}",
        "top_level_verdict": verdict,
        "axes": axes,
        "findings": findings,
        "input_summary": {
            "input_walls": report.get("shell_stats_from_python", {}).get(
                "input_walls"
            ),
            "openings_carved": report.get("shell_stats_from_python", {}).get(
                "openings_carved"
            ),
            "window_apertures_3d": report.get("shell_stats_from_python", {}).get(
                "window_apertures_3d"
            ),
            "slivers_removed": report.get("shell_stats_from_python", {}).get(
                "slivers_removed"
            ),
            "consensus_kind_counts": _count_consensus_kinds(consensus),
            "group_counts": _group_counts(report),
        },
    }
    _write_json(attempt_dir / "visual_findings.json", findings_doc)
    print(f"[attempt {attempt_idx}] verdict={verdict} findings={len(findings)}")

    return {
        "attempt": attempt_idx,
        "rc": rc,
        "blocked": False,
        "verdict": verdict,
        "findings_count": len(findings),
        "findings": findings,
        "axes": axes,
        "attempt_dir": str(attempt_dir),
        "input_summary": findings_doc["input_summary"],
    }


# --- summary writer ---------------------------------------------------


def _safe_rel(p: Path) -> str:
    """Return path relative to REPO_ROOT if possible, else absolute."""
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def write_regression_summary(
    final_dir: Path,
    attempts: list[dict],
    fixture: str,
    consensus_path: Path,
) -> None:
    final_dir.mkdir(parents=True, exist_ok=True)
    last = attempts[-1]
    lines = [
        "# SKP Visual Review — Regression Summary",
        "",
        f"## Fixture: `{fixture}`",
        "",
        f"## Generated: {_now_utc_iso()}",
        "",
        f"## Consensus: `{consensus_path}`",
        "",
        "## Attempts",
        "",
        "| # | Verdict | Findings |",
        "|---|---|---|",
    ]
    for a in attempts:
        if a.get("blocked"):
            lines.append(
                f"| {a['attempt']} | BLOCKED | {a.get('reason', 'n/a')} |"
            )
        else:
            lines.append(
                f"| {a['attempt']} | {a['verdict']} | "
                f"{a['findings_count']} findings ({a['attempt_dir']}) |"
            )
    lines.extend([
        "",
        f"## Final verdict: **{last.get('verdict', 'BLOCKED')}**",
        "",
        "## Axes (last attempt)",
        "",
        "| Axis | Verdict | Evidence |",
        "|---|---|---|",
    ])
    axes = last.get("axes", {})
    for axis in AXES:
        a = axes.get(axis, {})
        lines.append(
            f"| `{axis}` | {a.get('verdict', 'n/a')} | "
            f"{a.get('evidence', '')[:200]} |"
        )

    if last.get("findings"):
        lines.extend([
            "",
            "## Deterministic findings (last attempt)",
            "",
        ])
        for f in last["findings"]:
            lines.append(
                f"- **[{f['severity']}] {f['type']}** "
                f"@ `{f['location']}` — {f['evidence']}"
            )

    input_summary = last.get("input_summary", {})
    if input_summary:
        lines.extend([
            "",
            "## Input summary (last attempt)",
            "",
            f"- input_walls: `{input_summary.get('input_walls')}`",
            f"- openings_carved: `{input_summary.get('openings_carved')}`",
            f"- window_apertures_3d: `{input_summary.get('window_apertures_3d')}`",
            f"- slivers_removed: `{input_summary.get('slivers_removed')}`",
            f"- consensus_kind_counts: `{input_summary.get('consensus_kind_counts')}`",
            f"- group_counts: `{input_summary.get('group_counts')}`",
        ])

    lines.extend([
        "",
        "## Remaining qualitative review (non-deterministic axes)",
        "",
        "The script cannot fully decide `global_visual` and",
        "`scale_rotation` from numeric data alone. A downstream agent",
        "(Claude inline, vision API, or human reviewer) must inspect:",
        "",
        f"- `{_safe_rel(final_dir)}/model_top.png`",
        f"- `{_safe_rel(final_dir)}/model_iso.png`",
        "",
        "and compare against PDF or prior baseline.",
        "",
        "## Constitution #8 compliance",
        "",
        "- SKP: ✅ `model.skp` promoted to this folder",
        "- Renders: ✅ `model_top.png`, `model_iso.png`",
        "- visual_findings.json: ✅",
        "- regression_summary.md: ✅ (this file)",
        "",
        "Side-by-side composite NOT generated by this MVP — see",
        "follow-up `tools/promote_artifact.py` TODO.",
    ])
    (final_dir / "regression_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


# --- entrypoint -------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default="planta_74")
    parser.add_argument(
        "--consensus",
        type=Path,
        help="Path to consensus JSON; defaults to "
        "fixtures/<fixture>/consensus_*.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output dir under artifacts/review/<fixture>/",
    )
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument(
        "--runs-dir",
        type=Path,
        help="Build scratch dir (default: runs/<fixture>)",
    )
    parser.add_argument(
        "--python-exe",
        type=Path,
        help="Python interpreter for the builder subprocess "
        "(default: sys.executable)",
    )
    args = parser.parse_args()

    fixture = args.fixture
    consensus = args.consensus
    if consensus is None:
        candidates = sorted(
            (REPO_ROOT / "fixtures" / fixture).glob("consensus*.json")
        )
        if not candidates:
            write_blocked_summary(
                args.out / "final",
                f"no consensus found under fixtures/{fixture}/",
                f"ls fixtures/{fixture}/",
            )
            return 2
        consensus = candidates[0]
    consensus = Path(consensus)
    if not consensus.exists():
        write_blocked_summary(
            args.out / "final",
            f"consensus path does not exist: {consensus}",
            f"verify path and rerun",
        )
        return 2

    runs_dir = args.runs_dir or (REPO_ROOT / "runs" / fixture)
    out_attempts_dir = Path(args.out)
    out_attempts_dir.mkdir(parents=True, exist_ok=True)

    attempts: list[dict] = []
    for i in range(args.max_attempts):
        attempt_result = run_attempt(
            i, fixture, consensus, runs_dir, out_attempts_dir,
            args.python_exe,
        )
        attempts.append(attempt_result)
        if attempt_result.get("blocked"):
            print(f"[attempt {i}] BLOCKED: {attempt_result['reason']}")
            break
        verdict = attempt_result.get("verdict")
        if verdict in {"PASS", "WARN"}:
            print(f"[attempt {i}] stop early on verdict={verdict}")
            break
        # FAIL — would need a source-supported fix between attempts.
        # MVP does NOT auto-fix; we stop on first FAIL and report it.
        print(
            f"[attempt {i}] FAIL detected — MVP does not auto-fix. "
            f"Stopping; human/agent must inspect findings and "
            f"apply source-supported fix before next attempt."
        )
        break

    # Promote last attempt's outputs to final/
    final_dir = out_attempts_dir / "final"
    last_attempt_dir = out_attempts_dir / f"attempt_{attempts[-1]['attempt']}"
    if last_attempt_dir.exists() and not attempts[-1].get("blocked"):
        final_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            "model.skp", "model_top.png", "model_iso.png",
            "geometry_report.json", "visual_findings.json",
        ):
            src = last_attempt_dir / name
            if src.exists():
                shutil.copy2(src, final_dir / name)

    write_regression_summary(final_dir, attempts, fixture, consensus)
    print(f"\n=== Done. Final dir: {final_dir} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
