"""History / Fidelity view — Cycle 12f.

Pure-Python module (no streamlit imports) that powers the cockpit's
"History" tab. Discovers `runs/<dir>` candidates, summarises each
one without invoking the pipeline or SketchUp, compares two
summaries, and computes a Pre-SKP Review status (PASS / WARN / FAIL).

The motivating principle (Felipe): SKP cannot be the first time we
"see" the planta. The cockpit must surface fidelity + counts +
preview artifacts BEFORE the 60-90 s SU spawn cost.

Boundary (Cycle 12f, v0):
- READ-ONLY — never writes back to `runs/`, `ground_truth/`, or any
  pipeline artifact.
- DOES NOT generate SKP, DOES NOT depend on SketchUp.
- DOES NOT mutate or invoke the pipeline; it only consumes existing
  artifacts on disk.
- DOES NOT lower or raise any existing threshold; the pre-SKP review
  thresholds documented below are NEW advisory ones, defaulted to
  the values discussed in `docs/validation_cockpit.md`.

Schema discovery is intentionally tolerant: a run dir is anything
under `runs/` that contains at least one consensus-shaped JSON
(top-level `walls` + `rooms`). Missing artifacts (no
`fidelity_report.json`, no images, no `metadata.git`) degrade
gracefully — the summary still surfaces what IS there.

Public API:
- ``RunSummary``        — dataclass capturing one run's snapshot
- ``RunDiff``           — dataclass capturing the A vs B comparison
- ``discover_runs``     — walk `runs/` for run dirs
- ``summarise_run``     — parse all artifacts in a run dir
- ``compare_runs``      — produce a per-room delta + warning diff
- ``pre_skp_review``    — PASS/WARN/FAIL + recommendation
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Match the SketchUp-side pt-to-m anchor used everywhere else in the
# codebase (see CLAUDE.md §10 anchor + cockpit/render_overlay.py).
PT_TO_M_DEFAULT = 0.19 / 5.4

# Pre-SKP review thresholds — advisory only. Document any change in
# `docs/validation_cockpit.md`. Mirrors the fidelity engine's strict
# threshold (0.69 hard-fail cap) and adds an upper "safe" band.
PRE_SKP_PASS_FIDELITY = 0.85
PRE_SKP_WARN_FIDELITY = 0.69
PRE_SKP_PASS_WARNINGS = 3

# Image extensions the cockpit can preview when it walks a run dir.
_PREVIEW_EXTS = (".png", ".svg", ".jpg", ".jpeg")

# Filename hints the cockpit understands when categorising preview
# artifacts. Order matters — first match wins.
_OVERLAY_HINTS = ("overlay", "expected", "diff", "compare",
                  "fidelity", "axon", "top", "side")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RunSummary:
    """Per-run snapshot used by the cockpit history view.

    Fields are populated best-effort: anything missing on disk stays
    `None` (or 0 for counts) instead of raising. This way the cockpit
    can render a row with `?` placeholders for partial runs without
    blowing up the whole table.
    """
    run_id: str
    run_dir: Path
    consensus_path: Path | None = None
    fidelity_report_path: Path | None = None
    scorecard_path: Path | None = None
    expected_model_path: Path | None = None
    source_pdf_path: Path | None = None

    # Best-effort metadata derived from consensus.metadata or git
    branch: str | None = None
    commit: str | None = None
    stage: str | None = None
    generated_at: str | None = None

    # Aggregate counts
    rooms_count: int = 0
    walls_count: int = 0
    openings_count: int = 0
    soft_barriers_count: int = 0

    # Fidelity report excerpt (None when fidelity_report.json absent)
    fidelity_score: float | None = None
    hard_fails: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sub_scores: dict[str, Any] = field(default_factory=dict)

    # Image previews discovered in the run dir
    image_paths: list[Path] = field(default_factory=list)

    def as_dict(self) -> dict:
        """Plain-dict view for streamlit `st.dataframe` and tests."""
        return {
            "run_id": self.run_id,
            "branch": self.branch,
            "commit": (self.commit[:8] if self.commit else None),
            "stage": self.stage,
            "fidelity_score": self.fidelity_score,
            "hard_fails": len(self.hard_fails),
            "warnings": len(self.warnings),
            "rooms": self.rooms_count,
            "walls": self.walls_count,
            "openings": self.openings_count,
            "image_count": len(self.image_paths),
        }


@dataclass
class RunDiff:
    """Outcome of comparing run A vs run B.

    ``rooms`` mirrors the per-room rows from
    ``cockpit.render_overlay.diff_summary`` so the existing renderer
    logic stays the single source of truth on geometry.
    """
    run_a_id: str
    run_b_id: str
    fidelity_delta: float | None  # b - a; None when a side missing
    rooms_delta: int  # b - a
    walls_delta: int
    openings_delta: int
    rooms: list[dict]
    warnings_new: list[str]
    warnings_resolved: list[str]
    hard_fails_new: list[str]
    hard_fails_resolved: list[str]
    image_paths_a: list[Path]
    image_paths_b: list[Path]


# ---------------------------------------------------------------------------
# Run discovery
# ---------------------------------------------------------------------------

def _is_consensus_shaped(p: Path) -> bool:
    """Cheap pre-filter: top-level keys look like a c3 consensus."""
    try:
        with p.open("r", encoding="utf-8") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    return '"rooms"' in head and '"walls"' in head


def _consensus_score(p: Path) -> tuple[int, str]:
    """Sort key for picking a representative consensus inside a run
    dir. Lower tuple = preferred. Files that look like the
    post-classifier output (``c3``, ``classified``, ``with_room_context``)
    rank highest."""
    name = p.name.lower()
    if "c3" in name or "classified" in name or "room_context" in name:
        return (0, name)
    if "consensus" in name:
        return (1, name)
    return (2, name)


def discover_runs(repo: Path) -> list[Path]:
    """Walk `<repo>/runs/` and return every directory that contains
    at least one consensus-shaped JSON.

    Subdirectories like ``runs/_ci_quality_gates/intermediate/`` are
    each considered a candidate IF they carry their own consensus.
    The cockpit treats each consensus-bearing directory as a
    standalone run so multi-stage CI runs still surface every step.
    """
    runs_dir = repo / "runs"
    if not runs_dir.exists():
        return []
    seen: set[Path] = set()
    out: list[Path] = []
    for p in sorted(runs_dir.rglob("*.json")):
        if not _is_consensus_shaped(p):
            continue
        rd = p.parent
        if rd in seen:
            continue
        seen.add(rd)
        out.append(rd)
    return out


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _pick_consensus(run_dir: Path) -> Path | None:
    """Pick the most representative consensus JSON in a run dir."""
    candidates = [p for p in run_dir.glob("*.json")
                  if _is_consensus_shaped(p)]
    if not candidates:
        return None
    candidates.sort(key=_consensus_score)
    return candidates[0]


def _pick_pdf(run_dir: Path, repo: Path) -> Path | None:
    """Best-guess source PDF for a run.

    Search order:
    1. Any PDF directly inside the run dir (``runs/<dir>/*.pdf``).
    2. ``<repo>/<plant>.pdf`` if the run dir name carries a known
       plant prefix (``planta_74``, ``synth_l2``, ``proto_p10``).
    3. The first repo-root PDF as a fallback.
    """
    for p in sorted(run_dir.glob("*.pdf")):
        return p
    name = run_dir.name.lower()
    for plant in ("planta_74_clean", "planta_74", "synth_l2",
                  "synth_p10", "proto_p10"):
        if plant in name:
            cand = repo / f"{plant}.pdf"
            if cand.exists():
                return cand
    fallback = sorted(repo.glob("*.pdf"))
    return fallback[0] if fallback else None


def _collect_images(run_dir: Path) -> list[Path]:
    """Gather PNG/SVG/JPG previews in a run dir, sorted by name with
    overlay/expected/diff hints surfaced first."""
    out: list[Path] = []
    for ext in _PREVIEW_EXTS:
        out.extend(sorted(run_dir.glob(f"*{ext}")))

    def _rank(p: Path) -> tuple[int, str]:
        nm = p.name.lower()
        for i, hint in enumerate(_OVERLAY_HINTS):
            if hint in nm:
                return (i, nm)
        return (len(_OVERLAY_HINTS), nm)

    out.sort(key=_rank)
    return out


def _pick_expected_model(consensus: dict | None,
                          run_dir: Path,
                          repo: Path) -> Path | None:
    """Resolve the expected_model.json that should grade this run.

    Priority:
    1. ``run_dir/expected_model.json`` if a per-run expected was
       checkpointed.
    2. ``<repo>/ground_truth/<plan_id>/expected_model.json`` from
       ``consensus.metadata.plan_id`` or ``consensus.plan_id``.
    3. Heuristic: match the run directory name against
       ``ground_truth/*/expected_model.json``.
    """
    direct = run_dir / "expected_model.json"
    if direct.exists():
        return direct
    plan_id = None
    if consensus:
        md = consensus.get("metadata") or {}
        plan_id = (md.get("plan_id") or consensus.get("plan_id"))
    if plan_id:
        cand = repo / "ground_truth" / plan_id / "expected_model.json"
        if cand.exists():
            return cand
    nm = run_dir.name.lower()
    gt_dir = repo / "ground_truth"
    if gt_dir.exists():
        for sub in sorted(gt_dir.iterdir()):
            if not sub.is_dir():
                continue
            if sub.name.lower() in nm:
                cand = sub / "expected_model.json"
                if cand.exists():
                    return cand
    return None


def _extract_meta_from_consensus(consensus: dict | None) -> dict[str, str | None]:
    """Pull a couple of identifier-shaped fields out of consensus
    metadata, if present. None when the metadata block is missing or
    the key is not there. Keeps the cockpit immune to schema drift."""
    out: dict[str, str | None] = {
        "branch": None, "commit": None, "stage": None,
        "generated_at": None,
    }
    if not consensus:
        return out
    md = consensus.get("metadata") or {}
    git_md = md.get("git") or {}
    out["branch"] = git_md.get("branch") or md.get("branch")
    out["commit"] = git_md.get("commit") or md.get("commit")
    out["stage"] = md.get("stage") or md.get("pipeline_stage")
    out["generated_at"] = (md.get("generated_at")
                            or md.get("timestamp")
                            or consensus.get("generated_at"))
    return out


def _parse_fidelity_report(report_path: Path | None) -> dict[str, Any]:
    """Lift the cockpit-relevant fields off a fidelity report."""
    out: dict[str, Any] = {
        "fidelity_score": None,
        "hard_fails": [],
        "warnings": [],
        "sub_scores": {},
    }
    if report_path is None or not report_path.exists():
        return out
    data = _load_json(report_path)
    if not data:
        return out
    score = data.get("global_fidelity")
    if isinstance(score, (int, float)):
        out["fidelity_score"] = float(score)
    out["hard_fails"] = list(data.get("hard_fails") or [])
    out["warnings"] = list(data.get("warnings") or [])
    sub = data.get("sub_scores") or {}
    if isinstance(sub, dict):
        out["sub_scores"] = sub
    return out


def summarise_run(run_dir: Path,
                  repo: Path | None = None,
                  pt_to_m: float = PT_TO_M_DEFAULT) -> RunSummary:
    """Parse every artifact present in ``run_dir`` and return a
    ``RunSummary``. Missing artifacts degrade gracefully.

    ``repo`` defaults to ``run_dir.parent.parent`` (the standard
    layout: ``<repo>/runs/<run_id>``). Pass it explicitly when the
    layout is non-standard (e.g. tests using ``tmp_path``)."""
    if repo is None:
        repo = run_dir.parent.parent
    cons_path = _pick_consensus(run_dir)
    consensus = _load_json(cons_path) if cons_path else None

    fidelity_path = run_dir / "fidelity_report.json"
    if not fidelity_path.exists():
        fidelity_path = None  # type: ignore[assignment]
    scorecard_path = run_dir / "fidelity_scorecard.md"
    if not scorecard_path.exists():
        scorecard_path = None  # type: ignore[assignment]

    fidelity = _parse_fidelity_report(fidelity_path)
    meta = _extract_meta_from_consensus(consensus)
    images = _collect_images(run_dir)
    # Cycle 12g — when no PNG/SVG previews exist, render an
    # on-demand thumbnail from the consensus JSON so the History
    # view always has something to show. Local import to keep the
    # graceful-degradation guarantee: if the thumbnail module
    # itself fails to import (PIL missing on a stripped checkout),
    # we keep the empty image_paths list.
    if not images and cons_path is not None:
        try:
            from cockpit.thumbnails import ensure_thumbnail  # noqa: WPS433
            thumb = ensure_thumbnail(run_dir, cons_path)
            if thumb is not None:
                images = [thumb]
        except Exception:  # noqa: BLE001 — never break summarise_run
            pass
    pdf_path = _pick_pdf(run_dir, repo)
    expected_path = _pick_expected_model(consensus, run_dir, repo)

    walls = (consensus or {}).get("walls") or []
    rooms = (consensus or {}).get("rooms") or []
    openings = (consensus or {}).get("openings") or []
    soft_barriers = (consensus or {}).get("soft_barriers") or []

    # Best-effort PT_TO_M parameter is plumbed through so callers can
    # apply it consistently with the rest of the cockpit; not used in
    # v0 counts but reserved for downstream area-aware features.
    _ = pt_to_m

    return RunSummary(
        run_id=run_dir.name,
        run_dir=run_dir,
        consensus_path=cons_path,
        fidelity_report_path=fidelity_path,
        scorecard_path=scorecard_path,
        expected_model_path=expected_path,
        source_pdf_path=pdf_path,
        branch=meta.get("branch"),
        commit=meta.get("commit"),
        stage=meta.get("stage"),
        generated_at=meta.get("generated_at"),
        rooms_count=len(rooms),
        walls_count=len(walls),
        openings_count=len(openings),
        soft_barriers_count=len(soft_barriers),
        fidelity_score=fidelity["fidelity_score"],
        hard_fails=fidelity["hard_fails"],
        warnings=fidelity["warnings"],
        sub_scores=fidelity["sub_scores"],
        image_paths=images,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _diff_room_table(consensus_a: dict | None,
                     consensus_b: dict | None,
                     pt_to_m: float) -> list[dict]:
    """Delegates to ``cockpit.render_overlay.diff_summary`` so there
    is a single source of truth for room-level diffs. Imported lazily
    so this module stays import-clean when only the pure-Python pieces
    (discovery, summary) are needed."""
    if consensus_a is None or consensus_b is None:
        return []
    from cockpit.render_overlay import diff_summary  # local import
    return diff_summary(consensus_a, consensus_b, pt_to_m)


def compare_runs(a: RunSummary,
                 b: RunSummary,
                 pt_to_m: float = PT_TO_M_DEFAULT) -> RunDiff:
    """Compare two ``RunSummary`` objects and produce a ``RunDiff``.

    Returns a snapshot suitable for the cockpit's "Compare" tab:
    fidelity Δ, count Δ, per-room delta table, and the new/resolved
    sets for warnings + hard_fails. Image lists are exposed so the UI
    can render them side-by-side without re-walking the run dirs.

    All fields degrade gracefully when one side is missing
    artifacts (e.g. no fidelity_report.json).
    """
    consensus_a = _load_json(a.consensus_path) if a.consensus_path else None
    consensus_b = _load_json(b.consensus_path) if b.consensus_path else None
    rooms_table = _diff_room_table(consensus_a, consensus_b, pt_to_m)

    fidelity_delta: float | None = None
    if a.fidelity_score is not None and b.fidelity_score is not None:
        fidelity_delta = round(b.fidelity_score - a.fidelity_score, 3)

    warns_a = set(a.warnings)
    warns_b = set(b.warnings)
    hard_a = set(a.hard_fails)
    hard_b = set(b.hard_fails)
    return RunDiff(
        run_a_id=a.run_id,
        run_b_id=b.run_id,
        fidelity_delta=fidelity_delta,
        rooms_delta=b.rooms_count - a.rooms_count,
        walls_delta=b.walls_count - a.walls_count,
        openings_delta=b.openings_count - a.openings_count,
        rooms=rooms_table,
        warnings_new=sorted(warns_b - warns_a),
        warnings_resolved=sorted(warns_a - warns_b),
        hard_fails_new=sorted(hard_b - hard_a),
        hard_fails_resolved=sorted(hard_a - hard_b),
        image_paths_a=list(a.image_paths),
        image_paths_b=list(b.image_paths),
    )


# ---------------------------------------------------------------------------
# Pre-SKP review
# ---------------------------------------------------------------------------

def _load_pre_skp_review_report(run_dir: Path) -> dict | None:
    """Read ``pre_skp_review_report.json`` (Slice 3 / ADR-001 §2.8) if
    present. Returns None when the file is absent or unreadable.

    The F0 gate of the smoke harness writes this file. When present,
    the cockpit treats it as authoritative and skips the in-memory
    Cycle 12f computation."""
    path = run_dir / "pre_skp_review_report.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def pre_skp_review(run: RunSummary,
                   pass_fidelity: float = PRE_SKP_PASS_FIDELITY,
                   warn_fidelity: float = PRE_SKP_WARN_FIDELITY,
                   pass_warnings: int = PRE_SKP_PASS_WARNINGS) -> dict:
    """Compute a Pre-SKP Review verdict for one run.

    Slice 3 (ADR-001 §4): when a ``pre_skp_review_report.json`` file
    is present in the run dir, this function reads it directly and
    maps it to the existing return shape. The F0 gate of the smoke
    harness becomes the single source of truth.

    Otherwise (Cycle 12f fallback): the original in-memory computation
    runs against the ``RunSummary``. Behaviour for runs without F0
    reports is byte-equivalent to the Cycle 12f shipping version.

    Status tiers (advisory only — does NOT block SKP export):

    - ``PASS`` — fidelity ≥ ``pass_fidelity`` AND zero hard_fails AND
      ``warnings ≤ pass_warnings``. Recommendation: "safe to export
      SKP".
    - ``WARN`` — anything that fails PASS but stays above
      ``warn_fidelity`` AND has zero hard_fails. Recommendation:
      "review before SKP".
    - ``FAIL`` — fidelity below ``warn_fidelity`` OR any hard_fail OR
      no fidelity report at all. Recommendation: "review before SKP".

    Mirrors the fidelity engine's existing strict band so the cockpit
    cannot greenlight a run the engine would block.

    Returns:
        ``{"status": "PASS"|"WARN"|"FAIL", "reasons": [...],
        "recommendation": "safe"|"review", "fidelity_score": float|None,
        "hard_fails_count": int, "warnings_count": int,
        "thresholds": {...}, "source": "f0_report"|"in_memory"}``
    """
    f0 = _load_pre_skp_review_report(run.run_dir)
    if f0 is not None and f0.get("verdict") in {"PASS", "WARN", "FAIL"}:
        verdict = f0["verdict"]
        # F0's recommendation strings are different from the cockpit's
        # ("safe to export SKP" vs "safe"). Map to the cockpit shape.
        recommendation = "safe" if verdict == "PASS" else "review"
        out = {
            "status": verdict,
            "reasons": list(f0.get("reasons") or []),
            "recommendation": recommendation,
            "fidelity_score": f0.get("fidelity_score"),
            "hard_fails_count": int(f0.get("hard_fails_count") or 0),
            "warnings_count": int(f0.get("warnings_count") or 0),
            "thresholds": {
                "pass_fidelity": pass_fidelity,
                "warn_fidelity": warn_fidelity,
                "pass_warnings": pass_warnings,
            },
            "source": "f0_report",
            "f0_block_skp_export": bool(f0.get("block_skp_export")),
            "f0_active_overrides_count": int(
                f0.get("active_overrides_count") or 0,
            ),
            "f0_recommendation": f0.get("recommendation"),
        }
        # Slice 4-extra (Cycle 14): when the F0 report came from an
        # AMENDED fidelity run (Slice 5b/5c), surface both pre/post
        # scores + the delta. Lets the cockpit show the human's
        # impact on the verdict directly. Fields are additive on top
        # of the Slice 3 contract — readers ignoring them stay
        # back-compat.
        out["using_amended_fidelity"] = bool(
            f0.get("using_amended_fidelity"),
        )
        pre = f0.get("fidelity_score_pre_override")
        if isinstance(pre, (int, float)):
            out["fidelity_score_pre_override"] = float(pre)
        delta = f0.get("fidelity_delta")
        if isinstance(delta, (int, float)):
            out["fidelity_delta"] = float(delta)
        return out

    # ----- Cycle 12f fallback (unchanged behaviour) -----
    reasons: list[str] = []
    score = run.fidelity_score
    n_hard = len(run.hard_fails)
    n_warn = len(run.warnings)

    if score is None:
        reasons.append("no fidelity_report.json — cockpit cannot grade this run")
        status = "FAIL"
    elif n_hard > 0:
        reasons.append(
            f"{n_hard} hard_fail(s) reported by fidelity engine"
        )
        status = "FAIL"
    elif score < warn_fidelity:
        reasons.append(
            f"fidelity={score:.3f} < warn_threshold={warn_fidelity:.2f}"
        )
        status = "FAIL"
    elif score < pass_fidelity or n_warn > pass_warnings:
        if score < pass_fidelity:
            reasons.append(
                f"fidelity={score:.3f} < pass_threshold={pass_fidelity:.2f}"
            )
        if n_warn > pass_warnings:
            reasons.append(
                f"{n_warn} warnings (>{pass_warnings} passing budget)"
            )
        status = "WARN"
    else:
        reasons.append(
            f"fidelity={score:.3f} ≥ pass_threshold={pass_fidelity:.2f}, "
            f"0 hard_fails, {n_warn} warnings ≤ {pass_warnings}"
        )
        status = "PASS"

    recommendation = "safe" if status == "PASS" else "review"

    return {
        "status": status,
        "reasons": reasons,
        "recommendation": recommendation,
        "fidelity_score": score,
        "hard_fails_count": n_hard,
        "warnings_count": n_warn,
        "thresholds": {
            "pass_fidelity": pass_fidelity,
            "warn_fidelity": warn_fidelity,
            "pass_warnings": pass_warnings,
        },
        "source": "in_memory",
    }


# ---------------------------------------------------------------------------
# Convenience for the streamlit shell
# ---------------------------------------------------------------------------

_DATE_PATTERN = re.compile(r"(\d{4}[-_]\d{2}[-_]\d{2})")


def order_runs_for_history(runs: list[RunSummary]) -> list[RunSummary]:
    """Order runs newest-first for the history table.

    Sort key, in priority order:
    1. ``generated_at`` (ISO timestamp from consensus.metadata) when
       present, descending.
    2. Trailing ``YYYY-MM-DD`` or ``YYYY_MM_DD`` substring in
       ``run_id``, descending.
    3. ``run_dir`` modification time, descending.
    4. ``run_id`` lexical, ascending (stable tie-breaker).
    """
    def _key(rs: RunSummary) -> tuple:
        gen = rs.generated_at or ""
        m = _DATE_PATTERN.search(rs.run_id)
        date_in_name = (m.group(1).replace("_", "-") if m else "")
        try:
            mtime = rs.run_dir.stat().st_mtime
        except OSError:
            mtime = 0.0
        # Negative numerics sort newest first; strings reversed via
        # the bool-tuple-on-min trick — easier to negate downstream by
        # using `reverse=True` on the calling sort.
        return (gen, date_in_name, mtime, rs.run_id)

    return sorted(runs, key=_key, reverse=True)


def history_summary(repo: Path,
                    pt_to_m: float = PT_TO_M_DEFAULT) -> list[RunSummary]:
    """Top-level convenience: discover every run + summarise + sort.

    The cockpit shell calls this once per page load. Returns an
    empty list on a stripped checkout (``runs/`` missing or empty)."""
    runs = [summarise_run(rd, repo=repo, pt_to_m=pt_to_m)
            for rd in discover_runs(repo)]
    return order_runs_for_history(runs)
