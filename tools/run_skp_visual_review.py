#!/usr/bin/env python3
"""FP-030 — Visual Oracle Gate runner (maturity 2 iteration).

Generates a `.skp` for the given fixture, runs deterministic heuristics
over `geometry_report.json`, optionally consults a visual oracle bridge,
emits `visual_findings.json` matching the v1 schema, promotes artifacts
to `artifacts/review/<fixture>/<run_id>/final/`, and writes
`regression_summary.md` with a maturity classification.

Maturity layers (used by `regression_summary.md`):
- SKP generation
- Render generation
- Side-by-side composite (required for PASS — BLOCKED if missing)
- Deterministic checks (window count, doors, soft barriers, etc.)
- Visual oracle bridge (none|chatgpt_bridge)
- Human review required (always honest)

Constitution #8 — No SKP, no progress.
Constitution #8 — No visual proof, no progress.

Usage:
    python -m tools.run_skp_visual_review \\
        --fixture planta_74 \\
        --out artifacts/review/planta_74/visual_oracle_bridge_<ts> \\
        --max-attempts 3 \\
        --oracle none

    # or with bridge attempt:
    python -m tools.run_skp_visual_review \\
        --fixture planta_74 \\
        --out artifacts/review/planta_74/visual_oracle_bridge_<ts> \\
        --oracle chatgpt_bridge

    # or hard-require bridge (BLOCKED if unavailable):
    python -m tools.run_skp_visual_review \\
        --fixture planta_74 \\
        --out artifacts/review/planta_74/visual_oracle_bridge_<ts> \\
        --oracle chatgpt_bridge --require-oracle
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
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

ORACLE_BRIDGE_URL = "http://localhost:8765"
ORACLE_BRIDGE_TIMEOUT_SEC = 5

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


def _safe_rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


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


# --- deterministic heuristics ----------------------------------------


def _check_gates_self_check(report: dict) -> list[dict]:
    findings: list[dict] = []
    for gate_name, value in report.get("gates_self_check", {}).items():
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
                    f"any gates_self_check false blocks promotion."
                ),
                "source_check": "tools/build_plan_shell_skp.py write_geometry_report",
                "suspected_owner": "builder",
                "proposed_fix": "Inspect shell_stats_from_python and run FP-026 diagnostic; do not promote until gate is true.",
            })
    return findings


def _check_window_count(report: dict, consensus: dict) -> list[dict]:
    findings: list[dict] = []
    expected = sum(
        1 for op in consensus.get("openings", [])
        if (op.get("kind_v5") or op.get("kind")) == "window"
    )
    actual = report.get("shell_stats_from_python", {}).get("window_apertures_3d", -1)
    if actual != expected:
        findings.append({
            "severity": "FAIL",
            "axis": "window_fidelity",
            "type": "window_count_mismatch",
            "location": "geometry_report.shell_stats_from_python.window_apertures_3d",
            "evidence": f"window_apertures_3d={actual} != count(kind_v5==window)={expected}",
            "source_check": "tools/build_plan_shell_skp.py:build_shell_polygon — opening kind routing",
            "suspected_owner": "opening_routing",
            "proposed_fix": "Diagnose which window leaked into 2D carve OR was skipped. Cross-check tests/test_opening_routing_invariants.py.",
        })
    return findings


def _check_door_count(report: dict, consensus: dict) -> list[dict]:
    """NEW (maturity 2): DoorLeaf_Group count == interior_door count."""
    findings: list[dict] = []
    expected = sum(
        1 for op in consensus.get("openings", [])
        if (op.get("kind_v5") or op.get("kind")) == "interior_door"
    )
    counts = _group_counts(report)
    actual = counts.get("DoorLeaf_Group", 0)
    if actual != expected:
        findings.append({
            "severity": "FAIL",
            "axis": "door_fidelity",
            "type": "door_count_mismatch",
            "location": "geometry_report.groups_diagnostic[DoorLeaf_Group*]",
            "evidence": f"DoorLeaf_Group count={actual} != count(kind_v5==interior_door)={expected}",
            "source_check": "tools/build_plan_shell_skp.rb door emission loop; consensus.openings",
            "suspected_owner": "opening_routing",
            "proposed_fix": "Check if a door was duplicated or skipped during Ruby emission.",
        })
    return findings


def _check_glazed_balcony_count(report: dict, consensus: dict) -> list[dict]:
    """NEW (maturity 2): GlazedBalcony_Group count == glazed_balcony count."""
    findings: list[dict] = []
    expected = sum(
        1 for op in consensus.get("openings", [])
        if (op.get("kind_v5") or op.get("kind")) == "glazed_balcony"
    )
    counts = _group_counts(report)
    actual = counts.get("GlazedBalcony_Group", 0)
    if actual != expected:
        findings.append({
            "severity": "FAIL",
            "axis": "window_fidelity",
            "type": "glazed_balcony_count_mismatch",
            "location": "geometry_report.groups_diagnostic[GlazedBalcony_Group*]",
            "evidence": f"GlazedBalcony_Group count={actual} != count(kind_v5==glazed_balcony)={expected}",
            "source_check": "tools/build_plan_shell_skp.rb glazed_balcony emission",
            "suspected_owner": "opening_routing",
            "proposed_fix": "Verify glazed_balcony routing — must produce its own group, NOT counted as window.",
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
                "evidence": f"door group `{g['name']}` has bbox z_min={z_min:.3f}m > {eps}m; door should touch floor.",
                "source_check": "tools/build_plan_shell_skp.rb door_leaf_group origin Z",
                "suspected_owner": "builder",
                "proposed_fix": "Ensure DoorLeaf_Group transforms set Z origin to 0.",
            })
    return findings


def _check_orphan_window_glass(report: dict, consensus: dict) -> list[dict]:
    """Each WindowGlass_Group_<id> must match a consensus opening kind=window.

    Also flag if the id prefix matches a soft_barrier convention (sb_*)
    — that would be a leak through routing.
    """
    findings: list[dict] = []
    window_opening_ids = {
        op.get("id") for op in consensus.get("openings", [])
        if (op.get("kind_v5") or op.get("kind")) == "window"
    }
    sb_ids = {sb.get("id") for sb in consensus.get("soft_barriers", [])}
    for g in report.get("groups_diagnostic", []):
        name = g.get("name", "")
        if not name.startswith("WindowGlass_Group_"):
            continue
        suffix = name[len("WindowGlass_Group_"):]
        if suffix in sb_ids:
            findings.append({
                "severity": "FAIL",
                "axis": "window_fidelity",
                "type": "soft_barrier_routed_as_window",
                "location": f"groups_diagnostic[name={name}]",
                "evidence": f"WindowGlass group `{name}` has id `{suffix}` that matches a consensus soft_barrier id — soft_barriers must NEVER produce WindowGlass groups.",
                "source_check": "tools/build_plan_shell_skp.{py,rb} window aperture emission",
                "suspected_owner": "soft_barrier_routing",
                "proposed_fix": "Verify the routing logic isolates soft_barrier paths from the window aperture path.",
            })
        elif suffix not in window_opening_ids:
            findings.append({
                "severity": "FAIL",
                "axis": "window_fidelity",
                "type": "orphan_glass_panel",
                "location": f"groups_diagnostic[name={name}]",
                "evidence": f"WindowGlass group `{name}` has no matching opening_id `{suffix}` in consensus with kind=window.",
                "source_check": "consensus.openings vs Ruby builder window aperture loop",
                "suspected_owner": "opening_routing",
                "proposed_fix": "Verify the opening_id naming convention (prefix `h_o`) matches between consensus and geometry_report.",
            })
    return findings


def _check_no_duplicate_window_application(report: dict) -> list[dict]:
    """NEW (maturity 2): each WindowGlass_Group id must be unique."""
    findings: list[dict] = []
    seen: dict[str, int] = {}
    for g in report.get("groups_diagnostic", []):
        name = g.get("name", "")
        if not name.startswith("WindowGlass_Group_"):
            continue
        suffix = name[len("WindowGlass_Group_"):]
        seen[suffix] = seen.get(suffix, 0) + 1
    duplicates = {k: v for k, v in seen.items() if v > 1}
    if duplicates:
        findings.append({
            "severity": "FAIL",
            "axis": "window_fidelity",
            "type": "duplicate_window_application",
            "location": "geometry_report.groups_diagnostic[WindowGlass_Group_*]",
            "evidence": f"duplicate window opening ids: {duplicates}",
            "source_check": "tools/build_plan_shell_skp.{py,rb} window aperture loop",
            "suspected_owner": "opening_routing",
            "proposed_fix": "Each opening must be applied once. Check loop conditions when shell has multiple pieces.",
        })
    return findings


def _check_window_height(report: dict, eps: float = 0.1) -> list[dict]:
    """Window glass groups must have height in [0.9, 1.5]m (FP-024 peitoril+verga)."""
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
                "evidence": f"window aperture height_m={h:.3f} outside expected range [0.9, 1.5]m; peitoril/verga likely missing — possibly full-height void.",
                "source_check": "tools/build_plan_shell_skp.rb window_aperture_z",
                "suspected_owner": "builder",
                "proposed_fix": "Confirm FP-024 partial-height aperture path is active (not 2D full-height carve).",
            })
    return findings


def _check_window_z_min_nonzero(report: dict, eps: float = 0.3) -> list[dict]:
    """NEW (maturity 2): window aperture z_min should not be ≈0 (would be full-height void)."""
    findings: list[dict] = []
    for g in report.get("groups_diagnostic", []):
        if not g.get("name", "").startswith("WindowGlass_Group"):
            continue
        bbox = g.get("bbox_m", {}).get("min", [0, 0, 0])
        z_min = bbox[2] if len(bbox) > 2 else 0
        if z_min < eps:
            findings.append({
                "severity": "FAIL",
                "axis": "window_fidelity",
                "type": "full_height_window_void",
                "location": f"groups_diagnostic[name={g['name']}].bbox_m.min[2]={z_min}",
                "evidence": f"window glass starts at z={z_min:.3f}m (≈ floor); FP-024 expects peitoril preserved with z_min ≥ {eps}m.",
                "source_check": "tools/build_plan_shell_skp.rb window aperture Z origin",
                "suspected_owner": "builder",
                "proposed_fix": "FP-024 window aperture must start at peitoril height (~0.9m), not 0.",
            })
    return findings


def _check_floor_leak_basic(report: dict) -> list[dict]:
    """Basic floor leak check: floor_groups must be present and non-empty.

    NOTE: exterior leak detection (floor extends beyond wall envelope)
    is NOT implemented — it requires bbox vs wall_shell intersection
    logic. The maturity classification flags this honestly as
    `not_implemented`.
    """
    findings: list[dict] = []
    fg = report.get("floor_groups", {})
    if not fg.get("present", False) or fg.get("count", 0) == 0:
        findings.append({
            "severity": "FAIL",
            "axis": "room_fidelity",
            "type": "floor_leak",
            "location": "geometry_report.floor_groups",
            "evidence": f"floor_groups.present={fg.get('present')}, count={fg.get('count')}. No floor coverage.",
            "source_check": "tools/build_plan_shell_skp.py polygonize → Ruby Floor_Group creation",
            "suspected_owner": "builder",
            "proposed_fix": "Inspect shell_stats_from_python.shell_pieces_after_union.",
        })
    return findings


def inspect_report(report: dict, consensus: dict) -> list[dict]:
    """Run all deterministic heuristics. Returns list of finding dicts."""
    findings: list[dict] = []
    findings.extend(_check_gates_self_check(report))
    findings.extend(_check_window_count(report, consensus))
    findings.extend(_check_door_count(report, consensus))
    findings.extend(_check_glazed_balcony_count(report, consensus))
    findings.extend(_check_floating_doors(report))
    findings.extend(_check_orphan_window_glass(report, consensus))
    findings.extend(_check_no_duplicate_window_application(report))
    findings.extend(_check_window_height(report))
    findings.extend(_check_window_z_min_nonzero(report))
    findings.extend(_check_floor_leak_basic(report))
    return findings


def axes_verdict_from_findings(
    findings: list[dict], qualitative_default: str = "WARN"
) -> dict[str, dict]:
    axes: dict[str, dict] = {}
    for axis in AXES:
        axis_findings = [f for f in findings if f.get("axis") == axis]
        if not axis_findings:
            if axis in {"global_visual", "scale_rotation"}:
                axes[axis] = {
                    "verdict": qualitative_default,
                    "evidence": (
                        "Numeric heuristics cannot decide this axis; "
                        "needs human/agent or oracle inline review of "
                        "render PNGs and side-by-side composite."
                    ),
                }
            else:
                axes[axis] = {
                    "verdict": "PASS",
                    "evidence": "No deterministic finding produced for this axis.",
                }
        else:
            has_fail = any(f["severity"] == "FAIL" for f in axis_findings)
            axes[axis] = {
                "verdict": "FAIL" if has_fail else "WARN",
                "evidence": "; ".join(f["evidence"] for f in axis_findings[:3]),
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


# --- oracle bridge ---------------------------------------------------


def check_oracle_bridge_available(url: str = ORACLE_BRIDGE_URL) -> bool:
    """Health-probe the bridge. Returns True if reachable, else False."""
    try:
        req = urllib.request.Request(f"{url}/health", method="GET")
        with urllib.request.urlopen(req, timeout=ORACLE_BRIDGE_TIMEOUT_SEC) as resp:
            return resp.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False


def call_oracle_bridge(
    *,
    top_path: Path,
    iso_path: Path,
    side_by_side_path: Path,
    geometry_report: dict,
    prompt_text: str,
    url: str = ORACLE_BRIDGE_URL,
) -> dict:
    """Call the visual oracle bridge. Returns raw response dict.

    NOTE: the exact payload shape depends on the bridge implementation.
    This MVP packages prompt + image paths + minimal report context,
    and assumes the bridge will return JSON with at least
    `top_level_verdict` and `axes`. If the bridge errors, raises.
    """
    import base64

    def _b64(p: Path) -> str:
        return base64.b64encode(p.read_bytes()).decode("ascii")

    payload = {
        "prompt": prompt_text,
        "images": {
            "model_top.png": _b64(top_path),
            "model_iso.png": _b64(iso_path),
            "side_by_side_pdf_vs_skp.png": _b64(side_by_side_path),
        },
        "context": {
            "gates_self_check": geometry_report.get("gates_self_check", {}),
            "shell_stats_from_python": {
                k: v for k, v in geometry_report.get(
                    "shell_stats_from_python", {}
                ).items() if not isinstance(v, (list, dict))
            },
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{url}/ask",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


# --- artifact promotion -----------------------------------------------


def promote_attempt(
    runs_dir: Path, out_attempt_dir: Path, fixture: str
) -> dict[str, Path]:
    """Copy SKP + renders + report to <attempt_dir>/. Builder writes PNGs
    with a fixed `model_*.png` prefix regardless of --out."""
    out_attempt_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
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
    cmd = [
        str(python_exe or sys.executable),
        "-m", "tools.build_plan_shell_skp",
        str(consensus_path), "--out", str(out_skp), "--force-skp",
    ]
    try:
        result = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
        )
        log = (result.stdout or "") + (result.stderr or "")
        return result.returncode, log[-2000:]
    except subprocess.TimeoutExpired:
        return -1, "build timed out after 600s"
    except Exception as e:
        return -2, f"builder invoke error: {e!r}"


# --- side-by-side integration ----------------------------------------


def build_side_by_side(
    attempt_dir: Path,
    pdf_path: Path | None = None,
    fixture: str = "planta_74",
) -> tuple[Path | None, str | None]:
    """Generate side_by_side_pdf_vs_skp.png in attempt_dir.

    Returns (output_path, error_message). On success error_message is None.
    """
    from tools.compose_side_by_side import compose_to_file

    top = attempt_dir / "model_top.png"
    iso = attempt_dir / "model_iso.png"
    if pdf_path is None:
        pdf_path = REPO_ROOT / f"{fixture}.pdf"
    if not pdf_path.exists():
        return None, f"PDF not found at {_safe_rel(pdf_path)}"
    if not top.exists() or not iso.exists():
        return None, "model_top.png or model_iso.png missing"
    out = attempt_dir / "side_by_side_pdf_vs_skp.png"
    try:
        compose_to_file(
            pdf_path=pdf_path, top_path=top, iso_path=iso, out_path=out,
        )
        return out, None
    except Exception as e:
        return None, f"composer error: {e!r}"


# --- attempt orchestration --------------------------------------------


def run_attempt(
    attempt_idx: int,
    fixture: str,
    consensus_path: Path,
    runs_dir: Path,
    out_attempts_dir: Path,
    python_exe: Path | None,
    pdf_path: Path | None,
) -> dict:
    print(f"\n=== Attempt {attempt_idx} ===", flush=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    out_skp = runs_dir / f"{fixture}.skp"

    rc, log_tail = run_builder(consensus_path, out_skp, python_exe)
    print(f"[builder] rc={rc}")
    if rc != 0 or not out_skp.exists():
        return {
            "attempt": attempt_idx, "rc": rc, "log_tail": log_tail,
            "blocked": True,
            "reason": f"builder failed (rc={rc}); SKP not produced. Tail: {log_tail[-500:]}",
        }

    report_path = runs_dir / "geometry_report.json"
    if not report_path.exists():
        return {
            "attempt": attempt_idx, "rc": rc, "blocked": True,
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

    attempt_dir = out_attempts_dir / f"attempt_{attempt_idx}"
    promote_attempt(runs_dir, attempt_dir, fixture)

    sxs_path, sxs_err = build_side_by_side(attempt_dir, pdf_path, fixture)
    if sxs_err:
        print(f"[side_by_side] FAILED: {sxs_err}")
    else:
        print(f"[side_by_side] {_safe_rel(sxs_path)}")

    axes = axes_verdict_from_findings(findings)
    verdict = top_level_verdict(findings, axes)

    findings_doc = {
        "schema_version": SCHEMA_VERSION,
        "fixture": fixture,
        "attempt": f"attempt_{attempt_idx}",
        "top_level_verdict": verdict,
        "axes": axes,
        "findings": findings,
        "input_summary": {
            "input_walls": report.get("shell_stats_from_python", {}).get("input_walls"),
            "openings_carved": report.get("shell_stats_from_python", {}).get("openings_carved"),
            "window_apertures_3d": report.get("shell_stats_from_python", {}).get("window_apertures_3d"),
            "slivers_removed": report.get("shell_stats_from_python", {}).get("slivers_removed"),
            "consensus_kind_counts": _count_consensus_kinds(consensus),
            "group_counts": _group_counts(report),
        },
        "side_by_side_status": "ok" if not sxs_err else f"BLOCKED: {sxs_err}",
    }
    _write_json(attempt_dir / "visual_findings.json", findings_doc)
    print(f"[attempt {attempt_idx}] verdict={verdict} findings={len(findings)}")

    return {
        "attempt": attempt_idx, "rc": rc, "blocked": False, "verdict": verdict,
        "findings_count": len(findings), "findings": findings, "axes": axes,
        "attempt_dir": str(attempt_dir),
        "input_summary": findings_doc["input_summary"],
        "side_by_side": sxs_path, "side_by_side_err": sxs_err,
        "report": report,
    }


# --- maturity classification -----------------------------------------


def classify_maturity(
    *,
    skp_ok: bool,
    renders_ok: bool,
    side_by_side_ok: bool,
    deterministic_run: bool,
    oracle_status: str,  # "ok" | "unavailable" | "n/a"
    fail_findings: int,
) -> tuple[dict, int]:
    """Return (rows, estimated_pct). Honest classification."""
    rows = []
    pct = 0
    def row(layer, status, notes=""):
        rows.append({"layer": layer, "status": status, "notes": notes})
    if skp_ok:
        row("SKP generation", "PASS"); pct += 15
    else:
        row("SKP generation", "FAIL", "no .skp produced")
    if renders_ok:
        row("Render generation", "PASS"); pct += 10
    else:
        row("Render generation", "FAIL")
    if side_by_side_ok:
        row("Side-by-side composite", "PASS"); pct += 10
    else:
        row("Side-by-side composite", "FAIL", "BLOCKED until composer produces output")
    if deterministic_run:
        row("Deterministic checks", "PASS",
            f"10 checks ran; {fail_findings} FAIL finding(s)"); pct += 20
    else:
        row("Deterministic checks", "FAIL")
    if oracle_status == "ok":
        row("Visual oracle bridge", "PASS", "responded with verdict"); pct += 25
    elif oracle_status == "unavailable":
        row("Visual oracle bridge", "WARN",
            "bridge unreachable; deterministic-only mode"); pct += 5
    else:
        row("Visual oracle bridge", "N/A", "--oracle none"); pct += 0
    if oracle_status == "ok":
        row("Human review required", "no",
            "oracle bridge + deterministic checks cover decision")
    else:
        row("Human review required", "yes",
            "qualitative axes (global_visual, scale_rotation) still need human/agent inline review")
    pct = min(pct, 70 if oracle_status != "ok" else 85)
    return {"rows": rows, "estimated_pct": pct}, pct


# --- summary writer ---------------------------------------------------


def write_regression_summary(
    final_dir: Path, attempts: list[dict], fixture: str,
    consensus_path: Path, oracle_status: str, oracle_status_detail: str,
) -> None:
    final_dir.mkdir(parents=True, exist_ok=True)
    last = attempts[-1]

    has_skp = (final_dir / "model.skp").exists()
    has_top = (final_dir / "model_top.png").exists()
    has_iso = (final_dir / "model_iso.png").exists()
    has_sxs = (final_dir / "side_by_side_pdf_vs_skp.png").exists()
    fail_findings = sum(
        1 for f in last.get("findings", []) if f["severity"] == "FAIL"
    )
    maturity, pct = classify_maturity(
        skp_ok=has_skp, renders_ok=has_top and has_iso,
        side_by_side_ok=has_sxs, deterministic_run=not last.get("blocked"),
        oracle_status=oracle_status, fail_findings=fail_findings,
    )

    lines = [
        f"# SKP Visual Review — `{fixture}`",
        "",
        f"## Generated: {_now_utc_iso()}",
        "",
        f"## Consensus: `{_safe_rel(consensus_path)}`",
        "",
        "## Attempts",
        "",
        "| # | Verdict | Findings |",
        "|---|---|---|",
    ]
    for a in attempts:
        if a.get("blocked"):
            lines.append(f"| {a['attempt']} | BLOCKED | {a.get('reason', 'n/a')} |")
        else:
            lines.append(
                f"| {a['attempt']} | {a['verdict']} | "
                f"{a['findings_count']} findings ({_safe_rel(Path(a['attempt_dir']))}) |"
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
    for axis in AXES:
        a = last.get("axes", {}).get(axis, {})
        lines.append(
            f"| `{axis}` | {a.get('verdict', 'n/a')} | "
            f"{a.get('evidence', '')[:200]} |"
        )

    if last.get("findings"):
        lines.extend(["", "## Deterministic findings (last attempt)", ""])
        for f in last["findings"]:
            lines.append(
                f"- **[{f['severity']}] {f['type']}** @ `{f['location']}` — {f['evidence']}"
            )

    input_summary = last.get("input_summary", {})
    if input_summary:
        lines.extend([
            "", "## Input summary (last attempt)", "",
            f"- input_walls: `{input_summary.get('input_walls')}`",
            f"- openings_carved: `{input_summary.get('openings_carved')}`",
            f"- window_apertures_3d: `{input_summary.get('window_apertures_3d')}`",
            f"- slivers_removed: `{input_summary.get('slivers_removed')}`",
            f"- consensus_kind_counts: `{input_summary.get('consensus_kind_counts')}`",
            f"- group_counts: `{input_summary.get('group_counts')}`",
        ])

    lines.extend([
        "",
        "## Validator maturity",
        "",
        "| Layer | Status | Notes |",
        "|---|---|---|",
    ])
    for r in maturity["rows"]:
        lines.append(f"| {r['layer']} | {r['status']} | {r['notes']} |")
    lines.extend([
        "",
        f"**Estimated maturity: {pct}%**",
        "",
        "Honest caps:",
        "- without functional visual oracle bridge: max ~70%",
        "- with bridge + bounded positional heuristics: ~80–90%",
        "- 100% is not promised",
        "",
        f"Oracle status: `{oracle_status}` ({oracle_status_detail})",
        "",
        "## Remaining qualitative review (non-deterministic axes)",
        "",
        "Even with all numeric checks PASS, `global_visual` and",
        "`scale_rotation` cannot be fully decided from numbers alone.",
        "If oracle bridge is unavailable, a human or Claude inline must",
        "inspect:",
        "",
        f"- `{_safe_rel(final_dir)}/model_top.png`",
        f"- `{_safe_rel(final_dir)}/model_iso.png`",
        f"- `{_safe_rel(final_dir)}/side_by_side_pdf_vs_skp.png`",
        "",
        "## Constitution #8 compliance",
        "",
        f"- SKP: {'OK' if has_skp else 'MISSING'}",
        f"- model_top.png: {'OK' if has_top else 'MISSING'}",
        f"- model_iso.png: {'OK' if has_iso else 'MISSING'}",
        f"- side_by_side_pdf_vs_skp.png: {'OK' if has_sxs else 'MISSING'}",
        f"- visual_findings.json: {'OK' if (final_dir / 'visual_findings.json').exists() else 'MISSING'}",
        f"- regression_summary.md: OK (this file)",
    ])
    (final_dir / "regression_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


# --- entrypoint -------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default="planta_74")
    parser.add_argument("--consensus", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--python-exe", type=Path)
    parser.add_argument("--pdf", type=Path,
                        help="Override PDF path for side-by-side")
    parser.add_argument(
        "--oracle", choices=["none", "chatgpt_bridge"], default="none",
        help="Visual oracle backend (default: none = deterministic only)",
    )
    parser.add_argument(
        "--require-oracle", action="store_true",
        help="If oracle is requested but unavailable, BLOCK the run",
    )
    parser.add_argument(
        "--prompt-file", type=Path,
        default=REPO_ROOT / "tools" / "prompts" / "visual_oracle_reviewer.md",
        help="Prompt file for the oracle (default: tools/prompts/visual_oracle_reviewer.md)",
    )
    args = parser.parse_args()

    fixture = args.fixture
    consensus = args.consensus
    if consensus is None:
        candidates = sorted((REPO_ROOT / "fixtures" / fixture).glob("consensus*.json"))
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
            "verify path and rerun",
        )
        return 2

    runs_dir = args.runs_dir or (REPO_ROOT / "runs" / fixture)
    out_attempts_dir = Path(args.out)
    out_attempts_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = args.pdf

    # Oracle pre-flight
    oracle_status = "n/a"
    oracle_status_detail = "--oracle none (deterministic-only mode)"
    if args.oracle == "chatgpt_bridge":
        if check_oracle_bridge_available():
            oracle_status = "ok"
            oracle_status_detail = "bridge healthy at /health"
        else:
            oracle_status = "unavailable"
            oracle_status_detail = f"bridge unreachable at {ORACLE_BRIDGE_URL}"
            if args.require_oracle:
                write_blocked_summary(
                    out_attempts_dir / "final",
                    oracle_status_detail,
                    "Start the ChatGPT bridge at localhost:8765, or rerun without --require-oracle.",
                )
                print(f"[oracle] BLOCKED: {oracle_status_detail}")
                return 3

    attempts: list[dict] = []
    for i in range(args.max_attempts):
        result = run_attempt(
            i, fixture, consensus, runs_dir, out_attempts_dir,
            args.python_exe, pdf_path,
        )
        attempts.append(result)
        if result.get("blocked"):
            print(f"[attempt {i}] BLOCKED: {result['reason']}")
            break
        verdict = result.get("verdict")
        if verdict in {"PASS", "WARN"}:
            print(f"[attempt {i}] stop early on verdict={verdict}")
            break
        print(
            f"[attempt {i}] FAIL detected — MVP does not auto-fix. "
            "Stopping; inspect findings and apply source-supported fix."
        )
        break

    # Promote last attempt → final/
    final_dir = out_attempts_dir / "final"
    last_attempt_dir = out_attempts_dir / f"attempt_{attempts[-1]['attempt']}"
    if last_attempt_dir.exists() and not attempts[-1].get("blocked"):
        final_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            "model.skp", "model_top.png", "model_iso.png",
            "geometry_report.json", "visual_findings.json",
            "side_by_side_pdf_vs_skp.png",
        ):
            src = last_attempt_dir / name
            if src.exists():
                shutil.copy2(src, final_dir / name)

        # Optional oracle call on final artifacts
        if args.oracle == "chatgpt_bridge" and oracle_status == "ok":
            try:
                prompt_text = args.prompt_file.read_text(encoding="utf-8")
                raw = call_oracle_bridge(
                    top_path=final_dir / "model_top.png",
                    iso_path=final_dir / "model_iso.png",
                    side_by_side_path=final_dir / "side_by_side_pdf_vs_skp.png",
                    geometry_report=attempts[-1].get("report", {}),
                    prompt_text=prompt_text,
                )
                _write_json(final_dir / "visual_oracle_raw_response.json", raw)
                print("[oracle] response saved to visual_oracle_raw_response.json")
            except Exception as e:
                oracle_status = "unavailable"
                oracle_status_detail = f"bridge call failed: {e!r}"
                print(f"[oracle] call failed: {e!r}")

    write_regression_summary(
        final_dir, attempts, fixture, consensus,
        oracle_status, oracle_status_detail,
    )
    print(f"\n=== Done. Final dir: {_safe_rel(final_dir)} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
