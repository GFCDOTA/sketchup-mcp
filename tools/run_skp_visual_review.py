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

from tools.oracle_providers import (
    OracleRequest, available_provider_names, get_provider,
    write_oracle_request_package,
)
from tools.ask_gpt_gate import (
    CANONICAL_TRIGGERS as GPT_CANONICAL_TRIGGERS,
    GateInput as GPTGateInput,
    run_gate as run_gpt_gate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "visual_findings.v1"

# Verdict severity ranking. `WARN_documented` is a final-verdict-only
# state used when known architectural WARNs are carried for a fixture
# even though the oracle/deterministic checks would say PASS.
_VERDICT_RANK = {
    "PASS": 0,
    "WARN_documented": 1,
    "WARN": 2,
    "FAIL": 3,
    "BLOCKED": 4,
}


def worst_verdict(*verdicts: str) -> str:
    """Return the most severe verdict. Empty input -> PASS."""
    if not verdicts:
        return "PASS"
    valid = [v for v in verdicts if v]
    if not valid:
        return "PASS"
    return max(valid, key=lambda v: _VERDICT_RANK.get(v, 0))


# ---- FP-032 promotion gate (only PROVEN eyes cast a hard FAIL) ------


def load_latest_discrimination(fixture: str, backend: str) -> dict | None:
    """Return the most recent `discrimination_report.json` (from
    `tools/negative_dogfood.py`) for (fixture, backend), or None if no dogfood
    evidence exists for that backend.

    Legacy reports (pre-multi-backend) omit the `backend` key; those were all
    `ollama_vision`, so a missing key is treated as `ollama_vision`. Absence of
    any matching report -> None -> the runner treats the backend as NOT-yet-
    proven (honest: no evidence is not proof).
    """
    base = REPO_ROOT / "artifacts" / "review" / fixture
    if not base.exists():
        return None
    best: dict | None = None
    best_mtime = -1.0
    for rp in base.glob("**/discrimination_report.json"):
        try:
            data = json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("backend", "ollama_vision") != backend:
            continue
        m = rp.stat().st_mtime
        if m > best_mtime:
            best_mtime = m
            best = data
    return best


def promote_oracle_verdict(
    oracle_verdict: str, discriminated: bool
) -> tuple[str, str]:
    """FP-032 promotion rule.

    An oracle **FAIL** only stands as a HARD FAIL if the backend was PROVEN
    discriminative for this fixture (negative_dogfood == DISCRIMINATED). Absent
    that proof, an oracle FAIL is a *weak* signal — degrade it to WARN so it is
    recorded but does not block. PASS / WARN pass through unchanged (never
    escalated).

    Returns (effective_verdict, note). `note` is empty when nothing changed.
    """
    if oracle_verdict == "FAIL" and not discriminated:
        return "WARN", (
            "oracle FAIL degraded to WARN (FP-032): backend not proven "
            "discriminative for this fixture - no DISCRIMINATED negative_dogfood "
            "report. Weak signal recorded, does not harden the gate."
        )
    return oracle_verdict, ""


# ---- GPT auto-consult trigger detection ----------------------------


_GPT_TRIGGER_QUESTIONS = {
    "final_fail_non_obvious_fix": (
        "Visual oracle pipeline produced final_verdict=FAIL on a "
        "deliberate validation run. What is the highest-ROI "
        "source-supported fix? Should we patch builder, consensus, "
        "renderer, or open a new spec? Stay strict: no inventing geometry."
    ),
    "require_oracle_blocks_backend": (
        "Visual oracle required (--require-oracle or --gpt-consult required) "
        "but the chosen backend cannot deliver. Should we (A) extend the "
        "backend, (B) switch to a different provider, or (C) accept the "
        "BLOCKED state until backend is fixed?"
    ),
    "oracle_verdict_neq_final_verdict": (
        "Oracle verdict and final aggregate verdict disagree. Which path "
        "correctly reflects the model state, and should the PR merge under "
        "the final aggregate?"
    ),
    "oracle_pass_but_known_warnings": (
        "The visual oracle returned PASS, but known architectural warnings "
        "carried for this fixture keep final_verdict at WARN_documented. "
        "Should this validation merge, block, or require another fix? "
        "What is the risk of merging while these warnings remain?"
    ),
}


def detect_gpt_consult_trigger(state: dict) -> str | None:
    """Detect canonical GPT-consult trigger from pipeline state.

    Returns the trigger name (one of GPT_CANONICAL_TRIGGERS) or None
    when no trigger applies. Priority:

    1. final_verdict == "FAIL"            -> final_fail_non_obvious_fix
    2. final_verdict == "BLOCKED" / oracle status unavailable/incompatible/blocked
                                          -> require_oracle_blocks_backend
    3. oracle_verdict != final_verdict    -> oracle_verdict_neq_final_verdict
    4. oracle PASS + known warnings carry -> oracle_pass_but_known_warnings
    5. carried_known_warnings_verdict == WARN_documented (defensive)
                                          -> oracle_pass_but_known_warnings
    """
    oracle_v = state.get("oracle_verdict")
    final_v = state.get("final_verdict") or state.get("top_level_verdict")
    carried_v = state.get("carried_known_warnings_verdict")
    known = state.get("known_warnings_carried", [])
    oracle_status = state.get("oracle_status")

    if final_v == "FAIL":
        return "final_fail_non_obvious_fix"
    if final_v == "BLOCKED":
        return "require_oracle_blocks_backend"
    if oracle_status in ("unavailable", "incompatible", "blocked"):
        return "require_oracle_blocks_backend"
    # The known-warnings case is a *specific* form of disagreement and
    # must be evaluated before the generic "oracle != final" trigger,
    # otherwise the planta_74 canonical case fires the wrong question.
    if oracle_v == "PASS" and known:
        return "oracle_pass_but_known_warnings"
    if carried_v == "WARN_documented":
        return "oracle_pass_but_known_warnings"
    if oracle_v and final_v and oracle_v != final_v:
        return "oracle_verdict_neq_final_verdict"
    return None


def question_for_trigger(trigger: str) -> str:
    return _GPT_TRIGGER_QUESTIONS.get(
        trigger,
        "An auto-trigger fired but no canonical question is registered. "
        "Please advise.",
    )


def load_known_warnings(fixture: str) -> list[dict]:
    """Load fixtures/<fixture>/known_warnings.json or return []."""
    path = REPO_ROOT / "fixtures" / fixture / "known_warnings.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("warnings", []) or []
    except (json.JSONDecodeError, OSError):
        return []

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
    """Window glass groups: altura em [0.9, 1.5]m (janela normal, FP-024
    peitoril+verga). EXCECAO: BASCULANTE — janela baixa LEGITIMA quando esta alta
    na parede (z_min >= 1.3m, peitoril ~1,5m de banheiro/servico) -> [0.4, 1.0]m.
    O check de full-height void continua via _check_window_z_min_nonzero."""
    findings: list[dict] = []
    for g in report.get("groups_diagnostic", []):
        if not g.get("name", "").startswith("WindowGlass_Group"):
            continue
        h = g.get("height_m")
        if h is None:
            continue
        zmin = (g.get("bbox_m", {}).get("min") or [0, 0, 0])[2]
        is_basculante = zmin >= 1.3   # peitoril alto -> basculante (janela baixa OK)
        lo, hi = (0.4, 1.0) if is_basculante else (0.9, 1.5)
        if h < (lo - eps) or h > (hi + eps):
            findings.append({
                "severity": "FAIL",
                "axis": "window_fidelity",
                "type": "bad_window_aperture",
                "location": f"groups_diagnostic[name={g['name']}].height_m={h}",
                "evidence": f"window aperture height_m={h:.3f} fora do range esperado "
                            f"[{lo}, {hi}]m ({'basculante' if is_basculante else 'janela'}); "
                            f"peitoril/verga provavelmente faltando — possivel full-height void.",
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
    oracle_status: str,
    fail_findings: int,
) -> tuple[dict, int]:
    """Return (rows, estimated_pct). Honest classification.

    `oracle_status` is one of:
    - `ok`               — provider returned valid normalized findings
    - `unavailable`      — provider could not be reached
    - `incompatible`     — reachable but cannot accept image payload
    - `not_implemented`  — provider is a stub (future_vision_api)
    - `invalid_response` — returned but payload could not be parsed
    - `n/a`              — --oracle none
    """
    rows = []
    pct = 0

    def row(layer, status, notes=""):
        rows.append({"layer": layer, "status": status, "notes": notes})

    if skp_ok:
        row("SKP generation", "PASS"); pct += 15
    else:
        row("SKP generation", "FAIL", "no .skp produced (or --image-source canonical)")
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
        row("Visual oracle bridge", "PASS",
            "provider returned normalized v1 findings"); pct += 25
    elif oracle_status == "unavailable":
        row("Visual oracle bridge", "WARN",
            "provider unreachable; package written for manual review"); pct += 5
    elif oracle_status == "incompatible":
        row("Visual oracle bridge", "WARN",
            "provider reachable but rejected image payload; package written"); pct += 5
    elif oracle_status == "not_implemented":
        row("Visual oracle bridge", "WARN",
            "provider is a stub; package written"); pct += 5
    elif oracle_status == "invalid_response":
        row("Visual oracle bridge", "WARN",
            "provider returned but payload could not be normalized; package written"); pct += 5
    else:
        row("Visual oracle bridge", "N/A", "--oracle none"); pct += 0

    if oracle_status == "ok":
        row("Human review required", "no",
            "oracle bridge + deterministic checks cover decision")
    else:
        row("Human review required", "yes",
            "qualitative axes still need human/agent inline OR external review of oracle_request_package")

    pct = min(pct, 70 if oracle_status != "ok" else 85)
    return {"rows": rows, "estimated_pct": pct}, pct


# --- summary writer ---------------------------------------------------


def write_regression_summary(
    final_dir: Path, attempts: list[dict], fixture: str,
    consensus_path: Path, oracle_status: str, oracle_status_detail: str,
    blocked_by_require_oracle: bool = False,
) -> None:
    final_dir.mkdir(parents=True, exist_ok=True)
    last = attempts[-1]
    effective_verdict = (
        "BLOCKED" if blocked_by_require_oracle
        else last.get("verdict", "BLOCKED")
    )

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
    # Verdict aggregation block (only when oracle ran with status=ok)
    oracle_v = last.get("oracle_verdict")
    det_v = last.get("deterministic_verdict")
    carried_v = last.get("carried_known_warnings_verdict")
    known_list = last.get("known_warnings_carried", [])
    verdict_block: list[str] = []
    if oracle_v is not None:
        verdict_block.extend([
            "",
            "## Verdict aggregation",
            "",
            f"- **oracle_verdict**: `{oracle_v}`",
            f"- **deterministic_verdict**: `{det_v}`",
            f"- **carried_known_warnings_verdict**: `{carried_v}`",
            f"- **final_verdict = worst(oracle, deterministic, carried_known_warnings)** = `{effective_verdict}`",
            "",
            "> The visual oracle provider is working, but its PASS does",
            "> not override known architectural WARNs. The canonical",
            f"> `{fixture}` status remains the aggregate above.",
        ])
        if known_list:
            verdict_block.extend(["", "### Known warnings carried for this fixture", ""])
            for w in known_list:
                verdict_block.append(f"- {w}")

    # ---- LL-024 GPT Auto-Consult Gate block ----
    gpt_consult = last.get("gpt_consult")
    gpt_block: list[str] = []
    if gpt_consult is not None:
        gpt_block.extend([
            "",
            "## GPT Auto-Consult Gate (LL-024)",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| mode | `{gpt_consult.get('mode')}` |",
            f"| triggered | `{'yes' if gpt_consult.get('triggered') else 'no'}` |",
            f"| trigger | `{gpt_consult.get('trigger') or 'n/a'}` |",
            f"| status | `{gpt_consult.get('status')}` |",
            f"| question_file | `{gpt_consult.get('question_path') or 'n/a'}` |",
            f"| response_file | `{gpt_consult.get('response_path') or 'n/a'}` |",
            f"| decision | `{gpt_consult.get('decision') or 'unknown'}` |",
            "",
        ])
        status = gpt_consult.get("status")
        mode = gpt_consult.get("mode")
        if gpt_consult.get("triggered"):
            if status == "ok":
                gpt_block.append(
                    "> GPT bridge responded. See `response_file` for the raw "
                    "answer; fill in `decision` after acting on it."
                )
            elif status == "SKIPPED_OFFLINE":
                gpt_block.append(
                    "> GPT consult was triggered but skipped because bridge "
                    "is offline. The question was still written to "
                    "`.ai_bridge/questions/`."
                )
            elif status == "BLOCKED_BRIDGE_OFFLINE":
                gpt_block.append(
                    "> GPT consult was required but bridge is offline. "
                    "Validation BLOCKED."
                )

    lines.extend([
        "",
        f"## Final verdict: **{effective_verdict}**",
        ""
        + (
            f"> **BLOCKED reason**: --require-oracle was set but oracle "
            f"status = `{oracle_status}` ({oracle_status_detail}). "
            f"See `oracle_request_package/` for the request that would have "
            f"been sent.\n"
            if blocked_by_require_oracle else ""
        ),
        *verdict_block,
        *gpt_block,
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


# --- GPT auto-consult wiring -----------------------------------------


def _build_consult_state(
    attempts: list[dict], oracle_status: str | None,
) -> dict:
    """Pipeline state shape used by detect_gpt_consult_trigger."""
    if not attempts:
        return {}
    last = attempts[-1]
    return {
        "oracle_verdict": last.get("oracle_verdict"),
        "deterministic_verdict": last.get("deterministic_verdict"),
        "carried_known_warnings_verdict": last.get("carried_known_warnings_verdict"),
        "final_verdict": last.get("verdict"),
        "top_level_verdict": last.get("verdict"),
        "known_warnings_carried": last.get("known_warnings_carried", []),
        "oracle_status": oracle_status,
    }


def _maybe_run_gpt_consult(
    mode: str,
    attempts: list[dict],
    fixture: str,
    final_dir: Path,
    *,
    oracle_status: str | None,
    oracle_status_detail: str | None,
    require_oracle_block: bool,
) -> bool:
    """Run the LL-024 GPT Auto-Consult Gate when triggered.

    Stashes the result on ``attempts[-1]['gpt_consult']`` so the summary
    writer can render it. Returns True only when ``mode == 'required'``
    and the gate could not deliver — caller should set exit code != 0.
    """
    if mode == "off":
        if attempts:
            attempts[-1]["gpt_consult"] = {
                "mode": mode, "triggered": False,
                "trigger": None, "status": "not_applicable",
                "detail": "--gpt-consult off",
            }
        return False

    state = _build_consult_state(attempts, oracle_status)
    if require_oracle_block:
        # Override final to surface trigger #5 when --require-oracle blocked
        state["final_verdict"] = "BLOCKED"
        state["top_level_verdict"] = "BLOCKED"

    trigger = detect_gpt_consult_trigger(state)
    if trigger is None:
        if attempts:
            attempts[-1]["gpt_consult"] = {
                "mode": mode, "triggered": False, "trigger": None,
                "status": "not_applicable",
                "detail": "no canonical trigger fired",
            }
        return False

    question = question_for_trigger(trigger)
    repo_state = {
        "branch": _git_branch_safe(),
        "develop_sha": _git_sha_safe(),
        "fixture": fixture,
        "oracle_status": oracle_status,
    }
    artifact_paths = {
        name: str(final_dir / name)
        for name in (
            "model.skp", "model_top.png", "model_iso.png",
            "side_by_side_pdf_vs_skp.png", "geometry_report.json",
            "visual_findings.json", "regression_summary.md",
            "visual_oracle_raw_response.json",
            "visual_oracle_normalized.json",
        )
    }
    context = dict(state)
    context["artifacts"] = artifact_paths
    context["fixture"] = fixture
    context["oracle_status_detail"] = oracle_status_detail

    gate_input = GPTGateInput(
        trigger=trigger, question=question,
        context=context, repo_state=repo_state,
    )
    # Always write to the repo-level .ai_bridge/ dirs
    q_dir = REPO_ROOT / ".ai_bridge" / "questions"
    r_dir = REPO_ROOT / ".ai_bridge" / "responses"
    result = run_gpt_gate(
        gate_input,
        questions_dir=q_dir, responses_dir=r_dir,
        # In `required` mode, we want the gate itself to NOT exit early;
        # this orchestrator handles the BLOCKED state and reports the
        # final answer to the caller via the return value.
        require_consult=False,
    )

    consult_record = {
        "mode": mode, "triggered": True, "trigger": trigger,
        "status": result.status, "detail": result.detail,
        "question_path": (
            _safe_rel(result.question_path) if result.question_path else None
        ),
        "response_path": (
            _safe_rel(result.response_path) if result.response_path else None
        ),
        "decision": "merge" if result.status == "ok" else "unknown",
    }
    if attempts:
        attempts[-1]["gpt_consult"] = consult_record

    print(
        f"[gpt-consult] mode={mode} trigger={trigger} "
        f"status={result.status}"
    )
    if result.question_path:
        print(f"[gpt-consult] question: {_safe_rel(result.question_path)}")
    if result.response_path:
        print(f"[gpt-consult] response: {_safe_rel(result.response_path)}")

    # In required mode, anything other than `ok` blocks
    if mode == "required" and result.status != "ok":
        print(
            f"[gpt-consult] BLOCKED: --gpt-consult required + "
            f"status={result.status}"
        )
        return True
    return False


def _git_branch_safe() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except Exception:
        pass
    return None


def _git_sha_safe() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except Exception:
        pass
    return None


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
        "--oracle",
        choices=available_provider_names(),
        default="none",
        help=(
            "Visual oracle backend (default: none = deterministic only). "
            "chatgpt_bridge_image: tries multipart POST to localhost:8765, "
            "writes oracle_request_package on incompatibility. "
            "future_vision_api: stub; not_implemented status."
        ),
    )
    parser.add_argument(
        "--require-oracle", action="store_true",
        help=(
            "If oracle is requested but did not return status=ok "
            "(unavailable/incompatible/not_implemented/invalid_response), "
            "BLOCK the run with a non-zero exit code."
        ),
    )
    parser.add_argument(
        "--gpt-consult",
        choices=["off", "auto", "required"],
        default="auto",
        help=(
            "LL-024 GPT Auto-Consult Gate mode. "
            "off: never invoke. "
            "auto (default): invoke when a canonical trigger fires "
            "(see tools.run_skp_visual_review.detect_gpt_consult_trigger); "
            "if bridge offline, write question file and continue. "
            "required: same triggers, but BLOCK with non-zero exit when "
            "the bridge cannot deliver."
        ),
    )
    parser.add_argument(
        "--image-source",
        choices=["build", "canonical"],
        default="build",
        help=(
            "Where the images for oracle/composer come from. "
            "build (default): build fresh SKP + renders. "
            "canonical: skip build, reuse artifacts/<fixture>/*.png as inputs. "
            "Useful to test the oracle path without consuming SU time."
        ),
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

    # Resolve provider (always; `none` is a no-op provider)
    provider = get_provider(args.oracle)
    oracle_status = "n/a"
    oracle_status_detail = f"--oracle {args.oracle}"

    final_dir = out_attempts_dir / "final"

    # --image-source canonical: skip the builder, reuse the canonical
    # artifacts/<fixture>/*.png as inputs to the oracle/composer.
    if args.image_source == "canonical":
        canonical_dir = REPO_ROOT / "artifacts" / fixture
        canonical_top = canonical_dir / f"{fixture}_top.png"
        canonical_iso = canonical_dir / f"{fixture}_iso.png"
        canonical_report = canonical_dir / "geometry_report.json"
        missing = [p for p in (canonical_top, canonical_iso, canonical_report)
                   if not p.exists()]
        if missing:
            write_blocked_summary(
                final_dir,
                f"--image-source canonical but inputs missing: {missing}",
                f"build the canonical artifact at artifacts/{fixture}/ first",
            )
            return 4
        final_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(canonical_top, final_dir / "model_top.png")
        shutil.copy2(canonical_iso, final_dir / "model_iso.png")
        shutil.copy2(canonical_report, final_dir / "geometry_report.json")
        # Side-by-side compose from canonical
        sxs_path, sxs_err = build_side_by_side(final_dir, pdf_path, fixture)
        if sxs_err:
            print(f"[side_by_side] FAILED: {sxs_err}")
        # Synthesize a single "attempt" record from canonical
        report = _load_json(canonical_report)
        consensus_data = _load_json(consensus)
        findings_raw = inspect_report(report, consensus_data)
        findings = []
        for i, f in enumerate(findings_raw, start=1):
            f_out = dict(f)
            f_out["id"] = f"vf_{i:03d}"
            f_out.setdefault("evidence_image", "model_iso.png")
            findings.append(f_out)
        axes = axes_verdict_from_findings(findings)
        verdict = top_level_verdict(findings, axes)
        # Write the deterministic-only visual_findings.json into final/
        # (the oracle call below may overwrite with normalized result)
        canonical_findings_doc = {
            "schema_version": SCHEMA_VERSION,
            "fixture": fixture,
            "attempt": "canonical",
            "top_level_verdict": verdict,
            "axes": axes,
            "findings": findings,
            "source": "deterministic_only",
        }
        _write_json(final_dir / "visual_findings.json", canonical_findings_doc)
        attempts = [{
            "attempt": "canonical", "rc": 0, "blocked": False,
            "verdict": verdict, "findings_count": len(findings),
            "findings": findings, "axes": axes,
            "attempt_dir": str(final_dir),
            "input_summary": {
                "input_walls": report.get("shell_stats_from_python", {}).get("input_walls"),
                "openings_carved": report.get("shell_stats_from_python", {}).get("openings_carved"),
                "window_apertures_3d": report.get("shell_stats_from_python", {}).get("window_apertures_3d"),
                "slivers_removed": report.get("shell_stats_from_python", {}).get("slivers_removed"),
                "consensus_kind_counts": _count_consensus_kinds(consensus_data),
                "group_counts": _group_counts(report),
            },
            "side_by_side": sxs_path,
            "side_by_side_err": sxs_err,
            "report": report,
        }]
    else:
        # --image-source build: run the full build attempt loop
        attempts = []
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

    # Oracle call via provider (skipped for `none`)
    if args.oracle != "none" and not attempts[-1].get("blocked"):
        try:
            prompt_text = args.prompt_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            prompt_text = (
                "You are a visual oracle. Review the images and return "
                "JSON per visual_findings.v1."
            )

        image_paths: list[Path] = []
        for name in ("model_top.png", "model_iso.png",
                     "side_by_side_pdf_vs_skp.png"):
            p = final_dir / name
            if p.exists():
                image_paths.append(p)

        report_excerpt = {
            "gates_self_check": attempts[-1].get("report", {}).get(
                "gates_self_check", {}
            ),
            "shell_stats_from_python": {
                k: v
                for k, v in attempts[-1].get("report", {}).get(
                    "shell_stats_from_python", {}
                ).items()
                if not isinstance(v, (list, dict))
            },
        }
        req = OracleRequest(
            prompt=prompt_text,
            image_paths=image_paths,
            context=report_excerpt,
            expected_schema={"schema_version": SCHEMA_VERSION},
        )
        oracle_resp = provider.call(req, out_dir=final_dir)
        oracle_status = oracle_resp.status
        oracle_status_detail = oracle_resp.detail

        # Persist raw + normalized
        if oracle_resp.raw is not None:
            _write_json(final_dir / "visual_oracle_raw_response.json",
                        oracle_resp.raw)
        if oracle_resp.normalized_findings is not None:
            _write_json(final_dir / "visual_oracle_normalized.json",
                        oracle_resp.normalized_findings)
            print("[oracle] response normalized and saved")
            # If oracle returned a usable verdict, merge into the
            # canonical visual_findings.json: oracle takes precedence
            # for qualitative axes (global_visual, scale_rotation) and
            # complements deterministic findings.
            if oracle_resp.status == "ok":
                normalized = oracle_resp.normalized_findings
                oracle_verdict = normalized.get("top_level_verdict", "PASS")
                # FP-032 promotion gate: an oracle FAIL only HARDENS the gate
                # if THIS backend proved it discriminates on this fixture
                # (negative_dogfood == DISCRIMINATED). No proof -> weak signal.
                disc_report = load_latest_discrimination(fixture, args.oracle)
                oracle_discriminated = bool(
                    disc_report and disc_report.get("result") == "DISCRIMINATED"
                )
                effective_oracle_verdict, promotion_note = promote_oracle_verdict(
                    oracle_verdict, oracle_discriminated
                )
                # deterministic_verdict from actual findings (ignoring
                # qualitative-auto-WARN fallback)
                det_findings_for_agg = attempts[-1].get("findings", [])
                if any(f.get("severity") == "FAIL" for f in det_findings_for_agg):
                    deterministic_verdict = "FAIL"
                elif any(f.get("severity") == "WARN" for f in det_findings_for_agg):
                    deterministic_verdict = "WARN"
                else:
                    deterministic_verdict = "PASS"

                # Known WARNs carried for this fixture
                known = load_known_warnings(fixture)
                known_descriptions = [
                    f"{w.get('axis','?')}: {w.get('description','')}"
                    for w in known
                ]
                carried_warnings_verdict = (
                    "WARN_documented" if known else "PASS"
                )

                # worst(effective_oracle, deterministic, carried_known_warnings).
                # The oracle verdict feeds in only AFTER the promotion gate, so a
                # non-proven backend can never harden the gate to FAIL on its own.
                final_v = worst_verdict(
                    effective_oracle_verdict,
                    deterministic_verdict,
                    carried_warnings_verdict,
                )

                # Per-axis: downgrade oracle PASS to WARN where known
                # warnings apply
                axes_out = dict(normalized.get("axes", {}))
                axes_with_known = {w.get("axis") for w in known if w.get("axis")}
                for ax_name in axes_with_known:
                    a = axes_out.get(ax_name) or {}
                    if a.get("verdict") == "PASS":
                        a["verdict"] = "WARN"
                        a["evidence"] = (
                            (a.get("evidence", "") + " | ").lstrip(" |")
                            + "Downgraded by known_warnings_carried for this fixture."
                        )
                        axes_out[ax_name] = a

                # FP-032: a non-proven backend's per-axis FAIL is also degraded
                # to WARN, so axes stay consistent with the gated top level.
                if not oracle_discriminated:
                    for ax_name, a in list(axes_out.items()):
                        if isinstance(a, dict) and a.get("verdict") == "FAIL":
                            a["verdict"] = "WARN"
                            a["evidence"] = (
                                (a.get("evidence", "") + " | ").lstrip(" |")
                                + "FP-032: oracle FAIL degraded to WARN "
                                  "(backend not proven discriminative)."
                            )
                            axes_out[ax_name] = a

                merged = dict(normalized)
                merged["fixture"] = fixture
                merged["attempt"] = "final"
                merged["axes"] = axes_out
                merged["source"] = normalized.get("source", "oracle")
                merged["oracle_verdict"] = oracle_verdict
                merged["oracle_verdict_effective"] = effective_oracle_verdict
                merged["oracle_discriminated"] = oracle_discriminated
                merged["discrimination_result"] = (
                    disc_report.get("result") if disc_report else "NO_DOGFOOD_EVIDENCE"
                )
                if promotion_note:
                    merged["promotion_note"] = promotion_note
                merged["deterministic_verdict"] = deterministic_verdict
                merged["carried_known_warnings_verdict"] = carried_warnings_verdict
                merged["known_warnings_carried"] = known_descriptions
                merged["final_verdict"] = final_v
                merged["top_level_verdict"] = final_v
                merged["aggregation_note"] = (
                    "final_verdict = worst(effective_oracle_verdict, "
                    "deterministic_verdict, carried_known_warnings_verdict), where "
                    "effective_oracle_verdict applies the FP-032 promotion gate "
                    "(oracle FAIL only hardens if the backend proved DISCRIMINATED). "
                    "The oracle's PASS does not override known architectural WARNs."
                )
                det_findings = attempts[-1].get("findings", [])
                if det_findings:
                    merged["deterministic_findings"] = det_findings
                _write_json(final_dir / "visual_findings.json", merged)
                print(
                    f"[oracle] verdicts: oracle={oracle_verdict} "
                    f"(effective={effective_oracle_verdict}, "
                    f"discriminated={oracle_discriminated}) "
                    f"deterministic={deterministic_verdict} "
                    f"carried_known={carried_warnings_verdict} "
                    f"-> final={final_v}"
                )

                # Update in-memory attempt for regression_summary
                attempts[-1]["verdict"] = final_v
                attempts[-1]["axes"] = axes_out
                attempts[-1]["oracle_verdict"] = oracle_verdict
                attempts[-1]["deterministic_verdict"] = deterministic_verdict
                attempts[-1]["carried_known_warnings_verdict"] = (
                    carried_warnings_verdict
                )
                attempts[-1]["known_warnings_carried"] = known_descriptions

        print(
            f"[oracle] provider={oracle_resp.provider} "
            f"status={oracle_resp.status} :: {oracle_resp.detail}"
        )
        if oracle_resp.package_dir is not None:
            print(
                f"[oracle] request package written to "
                f"{_safe_rel(oracle_resp.package_dir)}"
            )

        if args.require_oracle and oracle_status != "ok":
            print(f"[oracle] BLOCKED: --require-oracle + status={oracle_status}")
            # Run GPT auto-consult on the BLOCKED case too (trigger #5/#6)
            _maybe_run_gpt_consult(
                args.gpt_consult, attempts, fixture, final_dir,
                oracle_status=oracle_status,
                oracle_status_detail=oracle_status_detail,
                require_oracle_block=True,
            )
            write_regression_summary(
                final_dir, attempts, fixture, consensus,
                oracle_status, oracle_status_detail,
                blocked_by_require_oracle=True,
            )
            return 3

    # ----- GPT Auto-Consult Gate (LL-024) ---------------------------
    consult_block_required = _maybe_run_gpt_consult(
        args.gpt_consult, attempts, fixture, final_dir,
        oracle_status=oracle_status,
        oracle_status_detail=oracle_status_detail,
        require_oracle_block=False,
    )

    write_regression_summary(
        final_dir, attempts, fixture, consensus,
        oracle_status, oracle_status_detail,
    )
    print(f"\n=== Done. Final dir: {_safe_rel(final_dir)} ===")
    return 5 if consult_block_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
