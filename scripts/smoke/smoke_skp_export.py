"""SketchUp smoke harness — gates A through H + F0 (Slice 3).

Enforces the rule from CLAUDE.md §3: SketchUp is the LAST gate.
Cheap gates run first; SU spawns only after JSON, previews, and the
content-hash cache all agree the work is needed.

Gate sequence
-------------
A.  Preparation       — verify env, ensure out-dir, locate sketchup.exe.
B.  Acquire consensus — load JSON, defaults to runs/vector/consensus_model.json.
C.  JSON structural   — walls/rooms/openings shape sanity-checks.
D.  Preview PNG       — call tools.render_axon for top + axon (no SU).
E.  Hash + cache      — SHA256 of (consensus + skp_from_consensus.py +
                        consume_consensus.rb) compared to a per-run cache marker.
E2. Amend observed    — when review_overrides.json exists, runs
                        tools.apply_overrides → writes amended_observed.json
                        into out_dir (Slice 5a / ADR-001 §2.10.4). SKIPs
                        cleanly when no overrides file is found, so CI
                        runs are byte-equivalent. Opt-out via
                        --no-apply-overrides.
E3. Amended fidelity  — when BOTH expected_model AND review_overrides.json
                        exist, runs the fidelity engine in
                        apply_overrides=True mode and writes
                        fidelity_report_amended.json (Slice 5b /
                        ADR-001 §2.10.5). Emits both global_fidelity
                        and global_fidelity_pre_override so a review
                        cannot make the score look better without
                        leaving evidence. SKIPs cleanly when either
                        precondition is missing. Opt-out via
                        --no-amended-fidelity.
F0. Pre-SKP review    — read fidelity_report + (optional) review_overrides;
                        emit pre_skp_review_report.json (ADR-001 §2.8).
                        Verdict semantics gated by --review-mode={off,warn,block}.
F0pa. Proposed actions — opt-in (--emit-proposed-actions). When on,
                        runs tools.propose_skp_actions against consensus +
                        (optional) fidelity_report and writes
                        proposed_actions.json into out_dir for the cockpit
                        Review tab (ADR-001 §2.6). Default off keeps CI
                        byte-equivalent.
F.  Export .skp       — invoke tools.skp_from_consensus (skipped on
                        --skip-skp or cache hit unless --force-skp).
G.  Validate .skp     — file exists, size > 1 KiB.
G2. Inspector v2      — read inspect_report.json from out_dir, parse via
                        tools.skp_inspection_report, report InspectionReport
                        verdict (Stage 1.6 Cycle 5). SKIP on --skip-skp /
                        cache hit / no inspect_report.json. PASS in default
                        with would-block warning; FAIL on blockers when
                        --inspect-strict is passed. Cycle 6 will wire the
                        autorun plugin into gate F so the SKIP path becomes
                        the exception rather than the rule.
H.  Reports           — write sketchup_smoke_report.{json,md}; refresh cache.

Any FAIL gate short-circuits to H (so reports are always written).
F0 with --review-mode=off is a NO-OP from CI's perspective — it
writes the verdict to disk but never aborts the smoke run.

Companion doc: docs/validation/sketchup_smoke_workflow.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# Make ``tools.*`` and ``cockpit.*`` importable when this file is invoked
# as a script (``python scripts/smoke/smoke_skp_export.py``). Without
# this, Python only adds the script's directory (``scripts/smoke/``)
# to sys.path, which breaks the lazy ``from tools.X import Y`` calls
# inside gate_e_amend / gate_e_fidelity_amended / gate_f0_pa.
# Mirrors the cockpit/app.py bootstrap pattern (PR #68 / f11e13c).
# Discovered as a UX gap during the override-aware-flow dogfood
# session (2026-05-09): the gate would FAIL with
# ``failed to import tools.apply_overrides: No module named 'tools'``.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CONSENSUS = REPO_ROOT / "runs" / "vector" / "consensus_model.json"
DEFAULT_SKETCHUP = Path(
    r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
)
CACHE_KEY_INPUTS_BY_EXPORTER = {
    "consume": (
        Path("tools/skp_from_consensus.py"),
        Path("tools/consume_consensus.rb"),
    ),
    "plan-shell": (
        Path("tools/build_plan_shell_skp.py"),
        Path("tools/build_plan_shell_skp.rb"),
        Path("tools/disarm_sketchup_autoruns.py"),
    ),
}
# Back-compat alias — direct external readers used the old name.
CACHE_KEY_INPUTS = CACHE_KEY_INPUTS_BY_EXPORTER["consume"]
# SU 2026 trial blocks the autorun plugin behind a Welcome dialog
# unless a positional .skp is on the command line (FP-007 / LL-009).
# tools.skp_from_consensus auto-picks any .skp in the output dir, so
# we drop a template there before invoking it.
SU_TEMPLATE_CANDIDATES = (
    Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp"
         r"\resources\en-US\Templates\Temp01a - Simple.skp"),
    Path(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp"
         r"\resources\en-US\Templates\Temp01b - Simple.skp"),
)


@dataclass
class GateResult:
    name: str
    status: str  # "pass" | "fail" | "skip"
    message: str = ""
    started_at: str = ""
    finished_at: str = ""
    artifacts: list[str] = field(default_factory=list)


@dataclass
class SmokeReport:
    consensus_path: str
    out_dir: str
    started_at: str
    finished_at: str = ""
    verdict: str = "pending"  # "pass" | "fail" | "pending"
    gates: list[GateResult] = field(default_factory=list)
    cache_hit: bool = False
    consensus_sha256: str = ""
    cache_key: str = ""
    exporter: str = "consume"  # ADR-003: "consume" | "plan-shell"

    def add(self, gate: GateResult) -> GateResult:
        self.gates.append(gate)
        return gate


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relpath(path: Path) -> str:
    """Path relative to REPO_ROOT if possible, absolute string otherwise.

    Robust to out-dirs outside the repo (e.g. pytest tmp_path).
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _validate_consensus_shape(data: Any) -> None:
    """Cheap structural check. Raises ValueError on any violation."""
    if not isinstance(data, dict):
        raise ValueError("consensus root must be a JSON object")
    for key in ("walls", "rooms", "openings"):
        if key not in data:
            raise ValueError(f"missing required key: {key}")
        if not isinstance(data[key], list):
            raise ValueError(
                f"{key} must be a list, got {type(data[key]).__name__}"
            )
    for i, w in enumerate(data["walls"]):
        if not isinstance(w, dict):
            raise ValueError(f"walls[{i}] must be an object")
        for sub in ("start", "end"):
            v = w.get(sub)
            if not (
                isinstance(v, list)
                and len(v) == 2
                and all(isinstance(x, (int, float)) for x in v)
            ):
                raise ValueError(
                    f"walls[{i}].{sub} must be [x, y] floats, got {v!r}"
                )


def _compute_cache_key(consensus_sha: str, repo_root: Path,
                       exporter: str = "consume") -> str:
    """Cache key combines consensus hash + exporter choice + the source
    files that produce the .skp for that exporter. If any of those
    changes, the cache is invalid. Two different exporters never share
    a cache slot (the exporter name is fed into the hash too).
    """
    h = hashlib.sha256()
    h.update(consensus_sha.encode("utf-8"))
    h.update(f"|exporter={exporter}|".encode("utf-8"))
    inputs = CACHE_KEY_INPUTS_BY_EXPORTER.get(
        exporter, CACHE_KEY_INPUTS_BY_EXPORTER["consume"]
    )
    for rel in inputs:
        p = repo_root / rel
        if p.exists():
            h.update(_sha256_path(p).encode("utf-8"))
        else:
            h.update(b"absent:" + rel.as_posix().encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def gate_a(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="A. Preparation", status="pass", started_at=_utc_now())
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.sketchup is None:
        env = os.environ.get("SKETCHUP_EXE")
        args.sketchup = Path(env) if env else DEFAULT_SKETCHUP
    if args.skip_skp:
        g.message = f"out_dir={out_dir}, --skip-skp set (sketchup not required)"
    elif not args.sketchup.exists():
        g.status = "fail"
        g.message = (
            f"sketchup not found at {args.sketchup}. Set --sketchup, "
            f"env SKETCHUP_EXE, or pass --skip-skp."
        )
    else:
        g.message = f"out_dir={out_dir}, sketchup={args.sketchup}"
    report.out_dir = str(out_dir)
    g.finished_at = _utc_now()
    return g


def gate_b(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="B. Acquire consensus", status="pass",
                   started_at=_utc_now())
    path = Path(args.consensus)
    if not path.exists():
        g.status = "fail"
        g.message = f"consensus not found at {path}"
        g.finished_at = _utc_now()
        return g
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        g.status = "fail"
        g.message = f"JSON parse error: {e}"
        g.finished_at = _utc_now()
        return g
    report.consensus_path = str(path)
    report.consensus_sha256 = _sha256_path(path)
    args._consensus_data = data
    g.message = f"loaded {path.name} ({path.stat().st_size:,} bytes)"
    g.finished_at = _utc_now()
    return g


def gate_c(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="C. JSON structural", status="pass",
                   started_at=_utc_now())
    data = getattr(args, "_consensus_data", None)
    if data is None:
        g.status = "skip"
        g.message = "no consensus data from B"
    else:
        try:
            _validate_consensus_shape(data)
        except ValueError as e:
            g.status = "fail"
            g.message = str(e)
        else:
            g.message = (
                f"walls={len(data['walls'])}, rooms={len(data['rooms'])}, "
                f"openings={len(data['openings'])}"
            )
    g.finished_at = _utc_now()
    return g


def gate_d(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="D. Preview PNG", status="pass", started_at=_utc_now())
    out_dir = Path(report.out_dir)
    consensus = Path(report.consensus_path)
    artifacts: list[str] = []
    for mode, fname in (("top", "preview_top.png"), ("axon", "preview_axon.png")):
        target = out_dir / fname
        cmd = [
            sys.executable, "-m", "tools.render_axon",
            str(consensus),
            "--out", str(target),
            "--mode", mode,
            "--no-history",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=str(REPO_ROOT), timeout=120, check=False,
            )
        except subprocess.TimeoutExpired:
            g.status = "fail"
            g.message = f"render_axon {mode} timed out after 120s"
            g.finished_at = _utc_now()
            return g
        if proc.returncode != 0 or not target.exists():
            g.status = "fail"
            g.message = (
                f"render_axon {mode} failed (rc={proc.returncode}): "
                f"{proc.stderr.strip()[:200]}"
            )
            g.finished_at = _utc_now()
            return g
        artifacts.append(_relpath(target))
    g.artifacts = artifacts
    g.message = "rendered top + axon previews"
    g.finished_at = _utc_now()
    return g


def gate_e(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="E. Hash + cache", status="pass", started_at=_utc_now())
    # Make sure the report knows which exporter was requested BEFORE
    # gate_e so the cache key is bound to it (otherwise two different
    # exporters could share / clobber a cache slot).
    if not report.exporter or report.exporter == "consume":
        report.exporter = getattr(args, "exporter", "consume")
    cache_key = _compute_cache_key(
        report.consensus_sha256, REPO_ROOT, exporter=report.exporter,
    )
    report.cache_key = cache_key
    cache_marker = Path(report.out_dir).parent / "_skp_cache.json"
    prev: dict[str, Any] | None = None
    if cache_marker.exists():
        try:
            prev = json.loads(cache_marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev = None
    if args.force_skp:
        g.message = f"--force-skp; cache_key={cache_key[:12]}"
    elif (
        prev
        and prev.get("cache_key") == cache_key
        and prev.get("verdict") == "pass"
    ):
        report.cache_hit = True
        g.message = (
            f"cache hit; previous run {prev.get('run_id', '?')} "
            f"produced {prev.get('skp_path', '?')}"
        )
    else:
        g.message = f"cache miss; cache_key={cache_key[:12]}"
    g.finished_at = _utc_now()
    return g


PRE_SKP_REVIEW_SCHEMA_VERSION = "pre_skp_review_v1"
PRE_SKP_PASS_FIDELITY = 0.85
PRE_SKP_WARN_FIDELITY = 0.69
PRE_SKP_PASS_WARNINGS = 3


def _compute_pre_skp_review(
    fidelity_report: dict | None,
    overrides_doc: dict | None,
    consensus_sha: str,
    using_amended_fidelity: bool = False,
    structural_report: dict | None = None,
) -> dict:
    """Pure verdict logic per ADR-001 §2.8 + FP-014 gamma gate.

    Inputs are the *already-loaded* fidelity report and optional
    overrides document. Returns the dict written to
    ``pre_skp_review_report.json``.

    Slice 5c: when ``using_amended_fidelity`` is True (caller selected
    the amended report from gate E3), the output dict carries an
    extra ``fidelity_score_pre_override`` field surfaced from the
    amended report's ``global_fidelity_pre_override``. The verdict
    itself uses the post-override ``global_fidelity`` — the human's
    intent IS the loop. The pre-override score is recorded so a
    review can never make the score look better without leaving
    evidence (ADR-001 §2.10.5).

    FP-014 gamma gate (2026-05-09): when ``structural_report`` is
    provided (output of ``tools.structural_checks.evaluate_structural_health``),
    structural_blockers_count > 0 forces verdict=FAIL regardless of
    fidelity score. structural_warnings_count > 0 demotes PASS to WARN.
    Top 10 blockers + top 10 warnings are surfaced into the output
    dict for cockpit display + audit. This is the FP-014 "gate that
    impede SKP export ruim" — additive to ADR-001 §2.8 logic.
    """
    reasons: list[str] = []
    fidelity_score: float | None = None
    fidelity_score_pre_override: float | None = None
    hard_fails_count = 0
    warnings_count = 0
    active_overrides_count = 0
    block_skp_export = False
    structural_blockers_count = 0
    structural_warnings_count = 0
    has_structural_blocker = False
    has_structural_warning = False
    if structural_report is not None:
        sb = structural_report.get("structural_blockers") or []
        sw = structural_report.get("structural_warnings") or []
        structural_blockers_count = len(sb)
        structural_warnings_count = len(sw)
        has_structural_blocker = structural_blockers_count > 0
        has_structural_warning = structural_warnings_count > 0

    if fidelity_report is None:
        reasons.append("no_fidelity_report")
        verdict = "FAIL"
    else:
        score_v = fidelity_report.get("global_fidelity")
        if isinstance(score_v, (int, float)):
            fidelity_score = float(score_v)
        if using_amended_fidelity:
            pre = fidelity_report.get("global_fidelity_pre_override")
            if isinstance(pre, (int, float)):
                fidelity_score_pre_override = float(pre)
        hard_fails = fidelity_report.get("hard_fails") or []
        warnings = fidelity_report.get("warnings") or []
        hard_fails_count = len(hard_fails)
        warnings_count = len(warnings)

    sha_mismatch = False
    has_high_suspect = False
    has_human_review_request = False
    if overrides_doc is not None:
        overrides = overrides_doc.get("overrides") or []
        active_overrides_count = len(overrides)
        bound_sha = overrides_doc.get("consensus_sha256") or ""
        if bound_sha and consensus_sha and bound_sha != consensus_sha:
            sha_mismatch = True
            reasons.append(
                f"consensus_sha256_mismatch: bound to {bound_sha[:12]}..., "
                f"live consensus is {consensus_sha[:12]}..."
            )
        if (overrides_doc.get("global") or {}).get("block_skp_export"):
            block_skp_export = True
            br = (overrides_doc.get("global") or {}).get("block_reason")
            reasons.append(
                f"block_skp_export=true ({br or 'no reason given'})"
            )
        for ov in overrides:
            if ov.get("type") == "block_skp_export":
                block_skp_export = True
                br = (ov.get("payload") or {}).get("reason")
                reasons.append(
                    f"override block_skp_export ({br or 'no reason given'})"
                )
            if ov.get("type") == "mark_suspect":
                if (ov.get("payload") or {}).get("severity") == "high":
                    has_high_suspect = True
            if ov.get("type") == "request_human_review":
                # Not a v1 override type (lives in proposed_actions),
                # but defensive support if it sneaks in.
                has_human_review_request = True

    # ADR-001 §2.8 verdict logic + FP-014 gamma gate
    if fidelity_report is None:
        verdict = "FAIL"
    elif (
        block_skp_export
        or sha_mismatch
        or (fidelity_score is not None and fidelity_score < PRE_SKP_WARN_FIDELITY)
        or hard_fails_count > 0
        or has_structural_blocker
    ):
        if fidelity_score is not None and fidelity_score < PRE_SKP_WARN_FIDELITY:
            reasons.append(
                f"fidelity={fidelity_score:.3f} < {PRE_SKP_WARN_FIDELITY:.2f}"
            )
        if hard_fails_count > 0:
            reasons.append(f"{hard_fails_count} hard_fail(s)")
        if has_structural_blocker:
            reasons.append(
                f"{structural_blockers_count} structural_blocker(s) "
                f"(FP-014 gamma gate)"
            )
        verdict = "FAIL"
    elif (
        (fidelity_score is not None and fidelity_score < PRE_SKP_PASS_FIDELITY)
        or warnings_count > PRE_SKP_PASS_WARNINGS
        or has_high_suspect
        or has_human_review_request
        or has_structural_warning
    ):
        if fidelity_score is not None and fidelity_score < PRE_SKP_PASS_FIDELITY:
            reasons.append(
                f"fidelity={fidelity_score:.3f} < {PRE_SKP_PASS_FIDELITY:.2f}"
            )
        if warnings_count > PRE_SKP_PASS_WARNINGS:
            reasons.append(
                f"{warnings_count} warning(s) > {PRE_SKP_PASS_WARNINGS} budget"
            )
        if has_high_suspect:
            reasons.append("mark_suspect.severity=high present")
        if has_human_review_request:
            reasons.append("request_human_review present")
        if has_structural_warning:
            reasons.append(
                f"{structural_warnings_count} structural_warning(s) "
                f"(FP-014 gamma gate)"
            )
        verdict = "WARN"
    else:
        verdict = "PASS"
        if fidelity_score is not None:
            reasons.append(
                f"fidelity={fidelity_score:.3f} ≥ {PRE_SKP_PASS_FIDELITY:.2f}, "
                f"0 hard_fails, {warnings_count} warnings"
            )

    if verdict == "PASS":
        recommendation = "safe to export SKP"
    elif verdict == "WARN":
        recommendation = "review before SKP"
    else:
        recommendation = "do not export SKP"

    out = {
        "schema_version": PRE_SKP_REVIEW_SCHEMA_VERSION,
        "verdict": verdict,
        "reasons": reasons,
        "fidelity_score": fidelity_score,
        "hard_fails_count": hard_fails_count,
        "warnings_count": warnings_count,
        "active_overrides_count": active_overrides_count,
        "block_skp_export": block_skp_export,
        "recommendation": recommendation,
        "using_amended_fidelity": bool(using_amended_fidelity),
        # FP-014 gamma gate fields (additive). Always present so a
        # downstream consumer never hits KeyError; zero/empty when
        # structural_report wasn't supplied.
        "structural_blockers_count": structural_blockers_count,
        "structural_warnings_count": structural_warnings_count,
    }
    # Surface top 10 of each for quick triage in the cockpit / CI logs.
    # Full evidence lives in `structural_report.json` written separately
    # by gate F0.
    if structural_report is not None:
        sb_full = structural_report.get("structural_blockers") or []
        sw_full = structural_report.get("structural_warnings") or []
        if sb_full:
            out["structural_blockers"] = sb_full[:10]
        if sw_full:
            out["structural_warnings"] = sw_full[:10]
    # Slice 5c — surface the pre-override fidelity score when the
    # caller used the amended report. Mirrors ADR-001 §2.10.5: a
    # review can never make the score look better without leaving
    # evidence.
    if using_amended_fidelity and fidelity_score_pre_override is not None:
        out["fidelity_score_pre_override"] = fidelity_score_pre_override
        if (fidelity_score is not None
                and fidelity_score_pre_override is not None):
            out["fidelity_delta"] = round(
                fidelity_score - fidelity_score_pre_override, 4,
            )
    # Slice 5d — surface per-sub-score deltas when amended.
    # Discovered as dogfood UX gap #3: global_fidelity rounds to 2
    # decimals and can show Δ=0.00 even when individual sub-scores
    # moved (e.g. adjacency_score went 0.421 → 0.333 = Δ -0.088 on
    # the planta_74 dogfood, but global_fidelity stayed 0.69).
    # Surface BOTH the pre/post sub-score blocks AND a per-key delta
    # dict so a reviewer (and the cockpit Pre-SKP pane) can see WHERE
    # the override moved the score, not just THAT it moved.
    if using_amended_fidelity and fidelity_report is not None:
        post_subs = fidelity_report.get("sub_scores")
        pre_subs = fidelity_report.get("sub_scores_pre_override")
        if isinstance(post_subs, dict) and isinstance(pre_subs, dict):
            out["sub_scores"] = dict(post_subs)
            out["sub_scores_pre_override"] = dict(pre_subs)
            delta_subs: dict[str, float] = {}
            for k in sorted(set(post_subs) | set(pre_subs)):
                p = pre_subs.get(k)
                q = post_subs.get(k)
                if (isinstance(p, (int, float))
                        and isinstance(q, (int, float))):
                    delta_subs[k] = round(float(q) - float(p), 4)
            if delta_subs:
                out["sub_scores_delta"] = delta_subs
    return out


def gate_e_amend(args: argparse.Namespace,
                  report: SmokeReport) -> GateResult:
    """Slice 5a — apply review_overrides → write amended_observed.json.

    When ``runs/<consensus_dir>/review_overrides.json`` (or the
    out_dir copy) exists, runs ``tools.apply_overrides.apply_overrides``
    against the source consensus and writes ``amended_observed.json``
    into ``out_dir``. Slice 5b/5c will then re-compute fidelity on
    the amended observation and let gate F0 prefer the amended report.

    Default semantics:
      - SKIP when no ``review_overrides.json`` is found (the common
        case in CI; preserves byte-equivalent behaviour)
      - SKIP when ``--no-apply-overrides`` is passed (opt-out
        escape hatch)
      - PASS when overrides exist + amended_observed.json was
        written; message reports the apply-count + dropped-count
      - FAIL on apply layer exception

    The gate is intentionally idempotent: writing
    ``amended_observed.json`` for the same inputs produces a
    byte-identical file (apply_overrides is a pure function).
    """
    g = GateResult(
        name="E2. Amend observed (apply overrides)",
        status="pass", started_at=_utc_now(),
    )
    if getattr(args, "no_apply_overrides", False):
        g.status = "skip"
        g.message = "--no-apply-overrides set"
        g.finished_at = _utc_now()
        return g

    consensus_path = Path(report.consensus_path)
    if not consensus_path.exists():
        g.status = "skip"
        g.message = (
            f"consensus path missing: {_relpath(consensus_path)} "
            "(gate_b should have failed already)"
        )
        g.finished_at = _utc_now()
        return g

    out_dir = Path(report.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pick review_overrides.json the same way gate_f0 does — out_dir
    # first, then sibling-of-consensus.
    overrides_path = out_dir / "review_overrides.json"
    if not overrides_path.exists():
        sibling = consensus_path.parent / "review_overrides.json"
        if sibling.exists():
            overrides_path = sibling
    if not overrides_path.exists():
        g.status = "skip"
        g.message = (
            "no review_overrides.json found in out_dir or "
            f"{_relpath(consensus_path.parent)}; nothing to amend"
        )
        g.finished_at = _utc_now()
        return g

    try:
        overrides_doc = json.loads(
            overrides_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError) as e:
        g.status = "fail"
        g.message = f"failed to load review_overrides.json: {e}"
        g.finished_at = _utc_now()
        return g

    try:
        consensus_doc = json.loads(
            consensus_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError) as e:
        g.status = "fail"
        g.message = f"failed to load consensus: {e}"
        g.finished_at = _utc_now()
        return g

    # Lazy import — keeps the cheap-gate path import-light.
    try:
        from tools.apply_overrides import apply_overrides
    except Exception as e:  # noqa: BLE001
        g.status = "fail"
        g.message = f"failed to import tools.apply_overrides: {e}"
        g.finished_at = _utc_now()
        return g

    try:
        amended = apply_overrides(
            consensus=consensus_doc,
            overrides_doc=overrides_doc,
            expected_sha=report.consensus_sha256 or None,
        )
    except Exception as e:  # noqa: BLE001
        g.status = "fail"
        g.message = (
            f"apply_overrides raised: {type(e).__name__}: {e}"
        )
        g.finished_at = _utc_now()
        return g

    out_path = out_dir / "amended_observed.json"
    try:
        out_path.write_text(
            json.dumps(amended, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        g.status = "fail"
        g.message = f"failed to write amended_observed.json: {e}"
        g.finished_at = _utc_now()
        return g

    meta = amended.get("_overrides_metadata") or {}
    applied = meta.get("overrides_applied_count", 0)
    dropped = meta.get("overrides_dropped_count", 0)
    block = bool(meta.get("block_skp_export", False))
    warnings = meta.get("warnings") or []
    g.artifacts = [_relpath(out_path)]
    g.message = (
        f"applied={applied} dropped={dropped} "
        f"block_skp_export={'yes' if block else 'no'}"
        + (f" warnings={len(warnings)}" if warnings else "")
    )
    g.finished_at = _utc_now()
    return g


def gate_e_fidelity_amended(args: argparse.Namespace,
                              report: SmokeReport) -> GateResult:
    """Slice 5b — re-compute fidelity on the amended observation.

    Companion to gate_e_amend (Slice 5a). When BOTH an expected
    model AND review_overrides.json are available for the run,
    invokes ``tools.fidelity.compare_generated_to_expected.compare``
    in ``apply_overrides=True`` mode and writes
    ``fidelity_report_amended.json`` into ``out_dir``. The engine
    emits BOTH ``global_fidelity`` (post-override) and
    ``global_fidelity_pre_override`` per ADR-001 §2.10.5 — a
    review can never make the score look better without leaving
    evidence.

    Default semantics:
      - SKIP when no expected_model is found (no ``--expected-model``
        flag AND auto-discover under ``ground_truth/<plant>/``
        fails). The common case in CI; preserves byte-equivalent
        behaviour.
      - SKIP when no review_overrides.json is found (nothing to
        amend with — the raw fidelity report from a separate
        invocation is already the authoritative score).
      - SKIP on ``--no-amended-fidelity`` flag (opt-out
        escape hatch for diagnostic runs).
      - PASS on success; message reports both pre and post fidelity
        scores so a smoke log shows the human's impact at a glance.
      - FAIL on fidelity engine exception.

    Slice 5c will then have gate_f0 prefer the amended report over
    the raw one when both are present.
    """
    g = GateResult(
        name="E3. Amended fidelity (apply_overrides=True)",
        status="pass", started_at=_utc_now(),
    )
    if getattr(args, "no_amended_fidelity", False):
        g.status = "skip"
        g.message = "--no-amended-fidelity set"
        g.finished_at = _utc_now()
        return g

    consensus_path = Path(report.consensus_path)
    if not consensus_path.exists():
        g.status = "skip"
        g.message = (
            f"consensus path missing: {_relpath(consensus_path)} "
            "(gate_b should have failed already)"
        )
        g.finished_at = _utc_now()
        return g

    out_dir = Path(report.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- Discover expected_model -----------------------------------
    expected_path: Path | None = None
    explicit = getattr(args, "expected_model", None)
    if explicit is not None:
        explicit_path = Path(explicit)
        if explicit_path.exists():
            expected_path = explicit_path
    if expected_path is None:
        # Auto-discover: ground_truth/<consensus_parent_name>/expected_model.json
        plant_name = consensus_path.parent.name
        candidate = REPO_ROOT / "ground_truth" / plant_name / "expected_model.json"
        if candidate.exists():
            expected_path = candidate
    if expected_path is None:
        g.status = "skip"
        g.message = (
            "no expected_model found "
            "(--expected-model not set AND auto-discover at "
            f"ground_truth/{consensus_path.parent.name}/expected_model.json failed)"
        )
        g.finished_at = _utc_now()
        return g

    # ---- Discover review_overrides.json -----------------------------
    overrides_path = out_dir / "review_overrides.json"
    if not overrides_path.exists():
        sibling = consensus_path.parent / "review_overrides.json"
        if sibling.exists():
            overrides_path = sibling
    if not overrides_path.exists():
        g.status = "skip"
        g.message = (
            "no review_overrides.json found in out_dir or "
            f"{_relpath(consensus_path.parent)}; nothing to amend "
            "(raw fidelity report from a separate invocation is "
            "already authoritative)"
        )
        g.finished_at = _utc_now()
        return g

    try:
        overrides_doc = json.loads(
            overrides_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError) as e:
        g.status = "fail"
        g.message = f"failed to load review_overrides.json: {e}"
        g.finished_at = _utc_now()
        return g

    try:
        consensus_doc = json.loads(
            consensus_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError) as e:
        g.status = "fail"
        g.message = f"failed to load consensus: {e}"
        g.finished_at = _utc_now()
        return g

    try:
        expected_doc = json.loads(
            expected_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError) as e:
        g.status = "fail"
        g.message = f"failed to load expected_model: {e}"
        g.finished_at = _utc_now()
        return g

    # Lazy import — keeps cheap-gate path import-light.
    try:
        from tools.fidelity.compare_generated_to_expected import compare
    except Exception as e:  # noqa: BLE001
        g.status = "fail"
        g.message = (
            f"failed to import fidelity engine: {e}"
        )
        g.finished_at = _utc_now()
        return g

    try:
        amended_report = compare(
            observed=consensus_doc,
            expected=expected_doc,
            observed_path=consensus_path,
            expected_path=expected_path,
            apply_overrides=True,
            overrides_doc=overrides_doc,
        )
    except Exception as e:  # noqa: BLE001
        g.status = "fail"
        g.message = (
            f"compare(apply_overrides=True) raised: "
            f"{type(e).__name__}: {e}"
        )
        g.finished_at = _utc_now()
        return g

    out_path = out_dir / "fidelity_report_amended.json"
    try:
        out_path.write_text(
            json.dumps(amended_report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as e:
        g.status = "fail"
        g.message = f"failed to write fidelity_report_amended.json: {e}"
        g.finished_at = _utc_now()
        return g

    g.artifacts = [_relpath(out_path)]
    pre = amended_report.get("global_fidelity_pre_override")
    post = amended_report.get("global_fidelity")
    delta = (
        round(float(post) - float(pre), 4)
        if isinstance(pre, (int, float)) and isinstance(post, (int, float))
        else None
    )
    n_applied = amended_report.get("overrides_applied_count")
    delta_str = (
        f" (Δ={delta:+.4f})" if delta is not None else ""
    )
    g.message = (
        f"global_fidelity={post} pre_override={pre}{delta_str} "
        f"overrides_applied={n_applied}"
    )
    g.finished_at = _utc_now()
    return g


def gate_f0(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    """Pre-SKP review gate (Slice 3 / ADR-001 §2.8).

    Reads the fidelity report + optional review_overrides, emits a
    pre_skp_review_report.json verdict file, and respects
    ``--review-mode``:
      - off (default): always pass; verdict written to disk
      - warn         : pass + stderr warning when verdict != PASS
      - block        : fail when verdict == FAIL

    Slice 5c: when ``fidelity_report_amended.json`` is present in
    ``out_dir`` (written by gate E3), F0 PREFERS it over the raw
    ``fidelity_report.json``. The verdict is then computed against
    the post-override score, and the pre-override score is surfaced
    in ``pre_skp_review_report.json`` so the human's impact on the
    fidelity number is auditable. When parsing the amended report
    fails, F0 falls back cleanly to the raw report.
    """
    g = GateResult(name="F0. Pre-SKP review", status="pass",
                    started_at=_utc_now())
    out_dir = Path(report.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fidelity_report: dict | None = None
    fidelity_path: Path | None = None
    using_amended = False

    # Slice 5c — prefer the amended report if gate E3 wrote one.
    amended_path = out_dir / "fidelity_report_amended.json"
    if amended_path.exists():
        try:
            fidelity_report = json.loads(
                amended_path.read_text(encoding="utf-8"),
            )
            fidelity_path = amended_path
            using_amended = True
        except json.JSONDecodeError:
            # Fall back to raw report; the amended file is corrupt.
            print(
                "[smoke][F0] fidelity_report_amended.json failed to "
                "parse; falling back to raw fidelity_report.json",
                file=sys.stderr,
            )
            fidelity_report = None
            fidelity_path = None

    if fidelity_report is None:
        fidelity_path = out_dir / "fidelity_report.json"
        if not fidelity_path.exists():
            # Fall back to per-consensus-dir report (some pipelines
            # write the fidelity report next to the consensus, not
            # into the smoke out_dir).
            sibling = Path(report.consensus_path).parent / "fidelity_report.json"
            if sibling.exists():
                fidelity_path = sibling
        if fidelity_path.exists():
            try:
                fidelity_report = json.loads(
                    fidelity_path.read_text(encoding="utf-8"),
                )
            except json.JSONDecodeError:
                fidelity_report = None

    overrides_doc: dict | None = None
    overrides_path = out_dir / "review_overrides.json"
    if not overrides_path.exists():
        sibling_ovs = (
            Path(report.consensus_path).parent / "review_overrides.json"
        )
        if sibling_ovs.exists():
            overrides_path = sibling_ovs
    if overrides_path.exists():
        try:
            overrides_doc = json.loads(
                overrides_path.read_text(encoding="utf-8"),
            )
        except json.JSONDecodeError:
            overrides_doc = None

    # FP-014 gamma gate: load consensus + (optional) expected_model and
    # run structural health checks. Output is additive — pre_skp_review
    # gets structural_*_count fields + top-10 lists; full evidence to
    # structural_report.json sibling. On any error, we WARN to stderr
    # and continue without structural fields (defensive — gamma gate
    # never crashes the pipeline).
    structural_report: dict | None = None
    consensus_doc: dict | None = None
    consensus_path = Path(report.consensus_path)
    if consensus_path.exists():
        try:
            consensus_doc = json.loads(
                consensus_path.read_text(encoding="utf-8"),
            )
        except (OSError, json.JSONDecodeError) as e:
            print(
                f"[smoke][F0] failed to load consensus for structural "
                f"checks: {e}",
                file=sys.stderr,
            )
    expected_model: dict | None = None
    expected_path_arg = getattr(args, "expected_model", None)
    if expected_path_arg:
        try:
            expected_model = json.loads(
                Path(expected_path_arg).read_text(encoding="utf-8"),
            )
        except (OSError, json.JSONDecodeError) as e:
            print(
                f"[smoke][F0] failed to load expected_model: {e}",
                file=sys.stderr,
            )
    if (
        consensus_doc is not None
        and not getattr(args, "no_structural_checks", False)
    ):
        try:
            from tools.structural_checks import (
                evaluate_structural_health,
            )
            structural_report = evaluate_structural_health(
                consensus_doc,
                fidelity_report=fidelity_report,
                expected_model=expected_model,
            )
            structural_path = out_dir / "structural_report.json"
            structural_path.write_text(
                json.dumps(
                    structural_report, indent=2, ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as e:  # noqa: BLE001
            print(
                f"[smoke][F0] structural_checks failed (continuing "
                f"without gamma gate): {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            structural_report = None

    review = _compute_pre_skp_review(
        fidelity_report, overrides_doc, report.consensus_sha256,
        using_amended_fidelity=using_amended,
        structural_report=structural_report,
    )
    review_path = out_dir / "pre_skp_review_report.json"
    review_path.write_text(
        json.dumps(review, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    artifacts = [_relpath(review_path)]
    if structural_report is not None:
        artifacts.append(_relpath(out_dir / "structural_report.json"))
    g.artifacts = artifacts
    args._pre_skp_verdict = review["verdict"]
    args._pre_skp_review = review

    mode = getattr(args, "review_mode", "off")
    verdict = review["verdict"]

    if mode == "off":
        g.status = "pass"
        g.message = (
            f"verdict={verdict} (review-mode=off; advisory only, "
            f"smoke continues)"
        )
        if verdict != "PASS":
            print(
                f"[smoke][F0] verdict={verdict} reasons="
                f"{review['reasons']}",
                file=sys.stderr,
            )
    elif mode == "warn":
        g.status = "pass"
        g.message = f"verdict={verdict} (review-mode=warn)"
        if verdict != "PASS":
            print(
                f"[smoke][F0][WARN] verdict={verdict} reasons="
                f"{review['reasons']}",
                file=sys.stderr,
            )
    elif mode == "block":
        if verdict == "FAIL":
            g.status = "fail"
            g.message = (
                f"verdict=FAIL (review-mode=block); reasons="
                f"{review['reasons']}"
            )
        else:
            g.status = "pass"
            g.message = (
                f"verdict={verdict} (review-mode=block; only FAIL aborts)"
            )
            if verdict == "WARN":
                print(
                    f"[smoke][F0][WARN] verdict=WARN reasons="
                    f"{review['reasons']}",
                    file=sys.stderr,
                )
    else:
        # Defensive — argparse choices should prevent this.
        g.status = "fail"
        g.message = f"unknown review-mode {mode!r}"

    g.finished_at = _utc_now()
    return g


def gate_f0_pa(args: argparse.Namespace,
                report: SmokeReport) -> GateResult:
    """Cycle 13b — emit ``proposed_actions.json`` for cockpit Slice 4.

    Runs ``tools.propose_skp_actions.propose_actions`` against the
    smoke harness's consensus + (optional) fidelity_report and
    writes ``proposed_actions.json`` into ``out_dir`` so the cockpit
    Review tab can render suggestion chips next to each
    affected element (per ADR-001 §2.6).

    Skipped by default — opt-in via ``--emit-proposed-actions`` so
    CI behaviour stays byte-equivalent (mirrors the
    ``--review-mode=off`` safety pattern from gate_f0).

    PASS on success with a per-action-count message. SKIP on
    consensus missing (defensive). FAIL on producer exception (so
    the human notices a regression in the producer).
    """
    g = GateResult(
        name="F0pa. Proposed actions (opt-in)",
        status="pass", started_at=_utc_now(),
    )
    if not getattr(args, "emit_proposed_actions", False):
        g.status = "skip"
        g.message = "--emit-proposed-actions not set (default off)"
        g.finished_at = _utc_now()
        return g

    consensus_path = Path(report.consensus_path)
    if not consensus_path.exists():
        g.status = "skip"
        g.message = (
            f"consensus path missing: {_relpath(consensus_path)} "
            "(gate_b should have failed already)"
        )
        g.finished_at = _utc_now()
        return g

    out_dir = Path(report.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pick fidelity_report.json the same way gate_f0 does — out_dir
    # first, then sibling-of-consensus.
    fidelity_path = out_dir / "fidelity_report.json"
    if not fidelity_path.exists():
        sibling = consensus_path.parent / "fidelity_report.json"
        if sibling.exists():
            fidelity_path = sibling
    fidelity_doc: dict | None = None
    if fidelity_path.exists():
        try:
            fidelity_doc = json.loads(
                fidelity_path.read_text(encoding="utf-8"),
            )
        except json.JSONDecodeError:
            fidelity_doc = None

    try:
        consensus_doc = json.loads(
            consensus_path.read_text(encoding="utf-8"),
        )
    except (OSError, json.JSONDecodeError) as e:
        g.status = "fail"
        g.message = f"failed to load consensus: {e}"
        g.finished_at = _utc_now()
        return g

    # Lazy import: keep the smoke harness usable when only the
    # cheap gates A-E are exercised.
    try:
        from tools.propose_skp_actions import (
            propose_actions,
            write_proposed_actions,
        )
    except Exception as e:  # noqa: BLE001
        g.status = "fail"
        g.message = f"failed to import tools.propose_skp_actions: {e}"
        g.finished_at = _utc_now()
        return g

    try:
        doc = propose_actions(
            consensus=consensus_doc,
            fidelity_report=fidelity_doc,
            consensus_sha256=report.consensus_sha256 or None,
            run_id=consensus_path.parent.name,
        )
        out_path = out_dir / "proposed_actions.json"
        write_proposed_actions(doc, out_path)
    except Exception as e:  # noqa: BLE001
        g.status = "fail"
        g.message = f"propose_actions raised: {type(e).__name__}: {e}"
        g.finished_at = _utc_now()
        return g

    g.artifacts = [_relpath(out_path)]
    n = len(doc.get("actions") or [])
    g.message = (
        f"emitted {n} proposed action{'s' if n != 1 else ''} "
        f"({_relpath(out_path)})"
        + (" — fidelity_report consumed" if fidelity_doc else "")
    )
    g.finished_at = _utc_now()
    return g


def gate_f(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="F. Export .skp", status="pass", started_at=_utc_now())
    if args.skip_skp:
        g.status = "skip"
        g.message = "--skip-skp"
        g.finished_at = _utc_now()
        return g
    if report.cache_hit and not args.force_skp:
        g.status = "skip"
        g.message = "cache hit"
        g.finished_at = _utc_now()
        return g
    out_dir = Path(report.out_dir)
    consensus = Path(report.consensus_path)
    # Both exporters' --out is a FILE path, not a directory.
    # Use a deterministic name inside out_dir; gate_g and gate_h
    # reference it back via args._skp_path.
    skp_target = out_dir / "model.skp"
    # Bootstrap template so SU 2026 trial doesn't show its Welcome
    # dialog (FP-007). Best-effort: if no template is reachable we
    # still try, and the existing premature-exit error explains why.
    bootstrap_target = out_dir / "_bootstrap.skp"
    if not bootstrap_target.exists():
        template = next(
            (t for t in SU_TEMPLATE_CANDIDATES if t.exists()), None
        )
        if template is not None:
            shutil.copy2(template, bootstrap_target)

    # ADR-003: dispatch to the chosen exporter. Both share the same
    # CLI surface (positional consensus path, --out, --sketchup,
    # --timeout, --plugins, --force-skp) so the command shape is
    # symmetric — only the entry-point module name differs.
    exporter_choice = getattr(args, "exporter", "consume")
    if exporter_choice == "plan-shell":
        exporter_module = "tools.build_plan_shell_skp"
        log_path = out_dir / "build_plan_shell_skp.log"
        report.exporter = "plan-shell"
    else:
        exporter_module = "tools.skp_from_consensus"
        log_path = out_dir / "skp_from_consensus.log"
        report.exporter = "consume"

    cmd = [
        sys.executable, "-m", exporter_module,
        str(consensus),
        "--out", str(skp_target),
        "--sketchup", str(args.sketchup),
        "--timeout", str(args.timeout),
    ]
    if args.plugins:
        cmd += ["--plugins", str(args.plugins)]
    # Propagate --force-skp so the inner sidecar-based skip in both
    # exporters stays consistent with the outer smoke cache layer.
    # When the smoke cache hits we never reach F; this matters only
    # when the smoke cache missed but the inner sidecar might still
    # match — explicit force overrides both layers.
    if args.force_skp:
        cmd.append("--force-skp")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(REPO_ROOT), check=False,
            timeout=max(args.timeout + 30, 60),
        )
    except subprocess.TimeoutExpired as e:
        log_path.write_text(
            f"TIMEOUT after {args.timeout + 30}s\nstdout:\n{e.stdout or ''}"
            f"\nstderr:\n{e.stderr or ''}",
            encoding="utf-8",
        )
        g.status = "fail"
        g.message = f"skp_from_consensus timed out after {args.timeout + 30}s"
        g.artifacts = [_relpath(log_path)]
        g.finished_at = _utc_now()
        return g
    log_path.write_text(
        f"rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
        encoding="utf-8",
    )
    g.artifacts = [_relpath(log_path)]
    if proc.returncode != 0:
        # Combine stdout + stderr because both exporters use plain
        # print() for both info and error messages.
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        g.status = "fail"
        g.message = (
            f"{exporter_module} failed (rc={proc.returncode}); "
            f"see {log_path.name}: {' | '.join(tail)[:300]}"
        )
        g.finished_at = _utc_now()
        return g
    if not skp_target.exists():
        g.status = "fail"
        g.message = (
            f"{exporter_module} succeeded (rc=0) but {skp_target.name} "
            f"not found; see {log_path.name}"
        )
    else:
        g.artifacts.insert(0, _relpath(skp_target))
        g.message = f"exported {skp_target.name} via {exporter_choice}"
        args._skp_path = skp_target
    g.finished_at = _utc_now()
    return g


def gate_g(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="G. Validate .skp", status="pass",
                   started_at=_utc_now())
    if args.skip_skp:
        g.status = "skip"
        g.message = "--skip-skp"
        g.finished_at = _utc_now()
        return g
    if report.cache_hit and not args.force_skp:
        g.status = "skip"
        g.message = "cache hit; previous .skp not re-validated"
        g.finished_at = _utc_now()
        return g
    skp: Path | None = getattr(args, "_skp_path", None)
    if skp is None or not skp.exists():
        g.status = "fail"
        g.message = "no .skp path from F"
    elif skp.stat().st_size < 1024:
        g.status = "fail"
        g.message = f".skp size {skp.stat().st_size} bytes < 1 KiB threshold"
    else:
        g.message = f".skp size {skp.stat().st_size:,} bytes"
    g.finished_at = _utc_now()
    return g


def gate_g2(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    """Gate G2 — Inspector v2 structural check (Stage 1.6 Cycle 5).

    Reads an existing ``inspect_report.json`` from the out_dir, parses it
    with :mod:`tools.skp_inspection_report`, and reports the
    ``InspectionReport.is_clean`` verdict. Optionally **fails** the
    smoke run when ``--inspect-strict`` is passed and any structural
    blocker is present (default_faces > 0 / overlaps > 0 / components
    > 0 / bounds out of tol / null sha / non-1.0 schema).

    Skipped when:
      - ``--skip-skp`` (no SKP, no inspector)
      - cache hit and not ``--force-skp`` (last inspector run still valid)
      - no ``inspect_report.json`` next to the SKP (the autorun
        inspector plugin has not yet fired for this run; smoke does
        not launch SU twice — Cycle 6 wires the producer)

    This gate NEVER launches SketchUp itself; it only consumes a
    report produced upstream.
    """
    g = GateResult(name="G2. Inspector v2 (strict={})".format(
        bool(getattr(args, "inspect_strict", False))),
        status="pass", started_at=_utc_now())
    if args.skip_skp:
        g.status = "skip"
        g.message = "--skip-skp"
        g.finished_at = _utc_now()
        return g
    if report.cache_hit and not args.force_skp:
        g.status = "skip"
        g.message = "cache hit; previous inspect_report.json not re-validated"
        g.finished_at = _utc_now()
        return g
    out_dir = Path(report.out_dir)
    inspect_path = out_dir / "inspect_report.json"
    if not inspect_path.exists():
        g.status = "skip"
        g.message = (
            "no inspect_report.json in out_dir — autorun inspector "
            "plugin did not fire for this smoke run (deferred)"
        )
        g.finished_at = _utc_now()
        return g
    # Lazy import: keep smoke harness usable even when only the
    # cheap gates A-E are exercised.
    try:
        from tools.skp_inspection_report import InspectionReport
    except Exception as e:
        g.status = "fail"
        g.message = f"failed to import skp_inspection_report: {e}"
        g.finished_at = _utc_now()
        return g
    try:
        ir = InspectionReport.from_path(inspect_path)
    except Exception as e:
        g.status = "fail"
        g.message = f"failed to parse inspect_report.json: {e}"
        g.finished_at = _utc_now()
        return g
    blockers = ir.strict_blockers()
    g.artifacts = [_relpath(inspect_path)]
    if not blockers:
        g.message = (
            f"clean (schema={ir.schema_version}, "
            f"materials={ir.materials_count}, "
            f"overlaps={ir.wall_overlaps_count}, "
            f"defaults={ir.default_faces_count})"
        )
    elif getattr(args, "inspect_strict", False):
        g.status = "fail"
        g.message = "strict blockers fired: " + "; ".join(blockers[:5])
    else:
        g.status = "pass"
        g.message = (
            "non-strict; would-block: "
            + "; ".join(blockers[:3])
        )
    g.finished_at = _utc_now()
    return g


def gate_h(args: argparse.Namespace, report: SmokeReport) -> GateResult:
    g = GateResult(name="H. Reports", status="pass", started_at=_utc_now())
    out_dir = Path(report.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fail = any(x.status == "fail" for x in report.gates)
    report.verdict = "fail" if fail else "pass"
    report.finished_at = _utc_now()

    json_path = out_dir / "sketchup_smoke_report.json"
    md_path = out_dir / "sketchup_smoke_report.md"
    json_path.write_text(
        json.dumps(asdict(report), indent=2), encoding="utf-8"
    )
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    g.artifacts = [_relpath(json_path), _relpath(md_path)]

    if report.verdict == "pass" and not args.skip_skp:
        skp: Path | None = getattr(args, "_skp_path", None)
        if skp is not None or report.cache_hit:
            cache_marker = out_dir.parent / "_skp_cache.json"
            cache_data = {
                "cache_key": report.cache_key,
                "consensus_sha256": report.consensus_sha256,
                "skp_path": _relpath(skp) if skp else None,
                "run_id": out_dir.name,
                "verdict": report.verdict,
                "finished_at": report.finished_at,
            }
            cache_marker.write_text(
                json.dumps(cache_data, indent=2), encoding="utf-8"
            )
            g.artifacts.append(_relpath(cache_marker))
    g.finished_at = _utc_now()
    return g


def _render_markdown(report: SmokeReport) -> str:
    lines = [
        "# SketchUp Smoke Report",
        "",
        f"- consensus: `{report.consensus_path}`",
        f"- out_dir: `{report.out_dir}`",
        f"- consensus sha256: `{report.consensus_sha256[:12]}...`",
        f"- cache_key: `{report.cache_key[:12]}...`",
        f"- cache_hit: {report.cache_hit}",
        f"- started: {report.started_at}",
        f"- finished: {report.finished_at}",
        f"- verdict: **{report.verdict.upper()}**",
        "",
        "## Gates",
        "",
        "| Gate | Status | Message |",
        "|---|---|---|",
    ]
    for g in report.gates:
        msg = g.message.replace("\n", " ").replace("|", "\\|")
        lines.append(f"| {g.name} | {g.status.upper()} | {msg} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="smoke_skp_export",
        description="SketchUp smoke harness — gates A through H",
    )
    ap.add_argument("--consensus", type=Path, default=DEFAULT_CONSENSUS,
                    help="path to consensus_model.json (default: %(default)s)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="output dir (default: runs/smoke/<UTC timestamp>)")
    ap.add_argument("--sketchup", type=Path, default=None,
                    help="path to SketchUp.exe (default: env SKETCHUP_EXE or "
                         "the canonical SU 2026 path on Windows)")
    ap.add_argument("--plugins", type=Path, default=None,
                    help="plugins dir passed through to tools.skp_from_consensus")
    ap.add_argument("--timeout", type=int, default=180,
                    help="SU export timeout in seconds (default: %(default)s)")
    ap.add_argument("--skip-skp", action="store_true",
                    help="run gates A-E + H only, no SU spawn")
    ap.add_argument("--force-skp", action="store_true",
                    help="bypass cache hit, always run F")
    ap.add_argument(
        "--exporter", choices=("consume", "plan-shell"), default="consume",
        help=(
            "Gate F exporter (ADR-003). 'consume' (default): the "
            "production per-wall paradigm via tools.skp_from_consensus + "
            "tools/consume_consensus.rb (35 wall groups for planta_74). "
            "'plan-shell': experimental parallel exporter via "
            "tools.build_plan_shell_skp (1 PlanShell_Group with "
            "footprint union; no door leaves / windows in this phase, "
            "openings render as gaps in the shell). Both exporters "
            "consume the same consensus and write `model.skp` into "
            "out_dir; --skip-skp and --force-skp behave identically."
        ),
    )
    ap.add_argument("--open", dest="open_after", action="store_true",
                    help="reserved; current implementation always quits SU")
    ap.add_argument(
        "--review-mode", dest="review_mode",
        choices=("off", "warn", "block"), default="off",
        help=(
            "Pre-SKP review (gate F0) verdict mode (ADR-001 §2.8). "
            "'off' (default): F0 writes the verdict file but NEVER "
            "aborts the smoke. 'warn': verdict != PASS warns to "
            "stderr. 'block': verdict == FAIL aborts the smoke run. "
            "Default 'off' preserves byte-equivalent CI behaviour."
        ),
    )
    ap.add_argument("--inspect-strict", action="store_true",
                    help="Gate G2 fails the smoke run when "
                         "inspect_report.json has structural blockers "
                         "(default: non-blocking; report-only)")
    ap.add_argument(
        "--emit-proposed-actions", dest="emit_proposed_actions",
        action="store_true",
        help=(
            "Opt-in: gate F0pa runs tools.propose_skp_actions and "
            "writes proposed_actions.json into out_dir for the "
            "cockpit Review tab to consume (ADR-001 §2.6). "
            "Default off keeps CI byte-equivalent — mirrors the "
            "--review-mode=off safety pattern."
        ),
    )
    ap.add_argument(
        "--no-apply-overrides", dest="no_apply_overrides",
        action="store_true",
        help=(
            "Opt-out escape hatch: skip gate E2 (Slice 5a) even when "
            "review_overrides.json exists. Default behaviour is to "
            "auto-apply overrides → write amended_observed.json when "
            "the file is present, and to SKIP cleanly when it isn't. "
            "Use this flag for diagnostic runs that want to see "
            "fidelity against the raw detector output."
        ),
    )
    ap.add_argument(
        "--no-structural-checks", dest="no_structural_checks",
        action="store_true",
        help=(
            "Opt-out escape hatch: skip the FP-014 gamma gate "
            "structural checks (tools.structural_checks) inside "
            "gate F0. Default behaviour is to ALWAYS run structural "
            "checks; their findings flow into pre_skp_review_v1 as "
            "structural_blockers/structural_warnings. Use this flag "
            "ONLY for legacy/synthetic fixtures whose minimal "
            "wall topology trips C9 envelope_decomposition or C7 "
            "short_wall_fragments cosmetic warnings unrelated to "
            "FP-014. Production runs should NOT pass this flag."
        ),
    )
    ap.add_argument(
        "--expected-model", dest="expected_model", type=Path,
        default=None,
        help=(
            "Optional explicit path to ground_truth/<plant>/expected_model.json. "
            "When omitted, gate E3 (Slice 5b) auto-discovers at "
            "ground_truth/<consensus_parent_dir>/expected_model.json. "
            "Required for amended-fidelity computation; gate E3 SKIPs "
            "cleanly when no expected model is found."
        ),
    )
    ap.add_argument(
        "--no-amended-fidelity", dest="no_amended_fidelity",
        action="store_true",
        help=(
            "Opt-out escape hatch: skip gate E3 (Slice 5b) even when "
            "expected_model + review_overrides are both available. "
            "Default behaviour is to compute amended fidelity when "
            "all preconditions are met."
        ),
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.out_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.out_dir = REPO_ROOT / "runs" / "smoke" / ts

    report = SmokeReport(
        consensus_path=str(args.consensus),
        out_dir=str(args.out_dir),
        started_at=_utc_now(),
    )

    pipeline = (gate_a, gate_b, gate_c, gate_d, gate_e,
                gate_e_amend, gate_e_fidelity_amended,
                gate_f0, gate_f0_pa, gate_f, gate_g, gate_g2)
    for gate in pipeline:
        result = report.add(gate(args, report))
        if result.status == "fail":
            report.add(gate_h(args, report))
            print(f"smoke verdict: FAIL ({result.name})", file=sys.stderr)
            return 1

    report.add(gate_h(args, report))
    print(f"smoke verdict: {report.verdict.upper()}")
    print(f"reports: {Path(report.out_dir) / 'sketchup_smoke_report.md'}")
    return 0 if report.verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
