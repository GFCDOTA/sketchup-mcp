"""Validation Cockpit — Streamlit entry point.

Run from the repo root:

    pip install -e ".[cockpit]"
    streamlit run cockpit/app.py

Then point your browser at the URL Streamlit prints (usually
http://localhost:8501). The sidebar lets you pick a `runs/<dir>`
that contains a `c3` consensus + an `expected_model.json` (or any
combination of those — partial views still work).

Cycle 12 MVP boundary:
- Read-only — never writes back to consensus / GT files.
- Does NOT depend on SketchUp / SKP.
- Does NOT mutate runs/ or ground_truth/ — pure read.
- No baseline / threshold change.
- Keeps the pipeline contract intact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Make ``cockpit`` package importable when launched via
# ``streamlit run cockpit/app.py`` regardless of cwd. Streamlit only
# adds the script's directory (cockpit/) to sys.path; we also need the
# repo root so the absolute ``cockpit.*`` imports below resolve.
_REPO_ROOT_BOOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT_BOOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_BOOT))

import streamlit as st

from cockpit.history_view import (
    PRE_SKP_PASS_FIDELITY,
    PRE_SKP_WARN_FIDELITY,
    RunSummary,
    compare_runs,
    history_summary,
    pre_skp_review,
)
from cockpit.overrides import (
    OPENING_KIND_VALUES,
    SUSPECT_SEVERITIES,
    load_overrides,
    overrides_apply_view,
    overrides_for_element,
    remove_override,
    save_override,
    set_block_skp_export,
)
from cockpit.proposed_actions import (
    action_already_applied,
    actions_for_target,
    apply_proposed_action,
    load_proposed_actions,
)
from cockpit.render_overlay import (
    PT_TO_M_DEFAULT,
    OverlayToggles,
    diff_summary,
    expected_match_summary,
    opening_summary_rows,
    pdf_page_to_data_url,
    render_overlay_svg,
    room_summary_rows,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------- File discovery ----------------------------------------------

def _find_consensus_candidates(repo: Path) -> list[Path]:
    """Find any *.json file in `runs/` whose top-level keys look
    like a c3-style consensus (has rooms, walls, openings)."""
    out: list[Path] = []
    runs_dir = repo / "runs"
    if not runs_dir.exists():
        return out
    for p in runs_dir.rglob("*.json"):
        try:
            with p.open("r", encoding="utf-8") as fh:
                head = fh.read(2048)
            # Cheap pre-filter
            if '"rooms"' in head and '"walls"' in head:
                out.append(p)
        except OSError:
            continue
    return sorted(out)


def _find_expected_models(repo: Path) -> list[Path]:
    gt_dir = repo / "ground_truth"
    if not gt_dir.exists():
        return []
    out: list[Path] = []
    for sub in gt_dir.iterdir():
        if sub.is_dir():
            cand = sub / "expected_model.json"
            if cand.exists():
                out.append(cand)
    return sorted(out)


def _find_pdf_candidates(repo: Path,
                          consensus_path: Path | None = None) -> list[Path]:
    """Find candidate source PDFs that the user might want to use as
    the cockpit underlay.

    Search order (deduplicated):
    1. PDFs sitting next to the active consensus (`<run>/*.pdf`).
    2. PDFs in the repo root (`planta_*.pdf`, `proto_*.pdf`).
    3. Any PDF found anywhere under `runs/`.
    """
    seen: set[Path] = set()
    out: list[Path] = []

    def _add(p: Path) -> None:
        rp = p.resolve()
        if rp not in seen and rp.exists():
            seen.add(rp)
            out.append(rp)

    if consensus_path is not None:
        for p in sorted(consensus_path.parent.glob("*.pdf")):
            _add(p)
    for p in sorted(repo.glob("*.pdf")):
        _add(p)
    runs_dir = repo / "runs"
    if runs_dir.exists():
        for p in sorted(runs_dir.rglob("*.pdf")):
            _add(p)
    return out


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    except json.JSONDecodeError:
        return None


# ---------- App ---------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="sketchup-mcp · Validation Cockpit",
        layout="wide",
    )

    # Top-level page selector — Cycle 12f added the History view
    # alongside the existing Single Run view. Each page has its own
    # sidebar layout below; the selector itself lives at the top of
    # the sidebar so it's the first thing the user sees.
    with st.sidebar:
        st.header("View")
        page = st.radio(
            "Page",
            options=["Single run", "History"],
            index=0,
            help=("`Single run` is the original cockpit (overlay + "
                  "inspector tabs). `History` lists every run under "
                  "`runs/` with fidelity + Pre-SKP Review status."),
            label_visibility="collapsed",
        )

    if page == "History":
        _render_history_page()
        return
    _render_single_run_page()


def _render_single_run_page() -> None:
    """Cycle 12 MVP — single-consensus visualisation."""
    st.title("Validation Cockpit — Single run")
    st.caption(
        "Read-only viewer. Pick a consensus + (optional) expected_model "
        "in the sidebar; toggle layers; inspect rooms / openings / "
        "fidelity inline. No SketchUp dependency."
    )

    # --- Sidebar: file pickers + toggles ----------------------------
    with st.sidebar:
        st.header("Inputs")
        cons_paths = _find_consensus_candidates(REPO_ROOT)
        if not cons_paths:
            st.error(
                "No consensus JSONs found under `runs/`. "
                "Run the pipeline first."
            )
            return
        cons_choice_default = 0
        # Prefer c3_classified files when present
        for i, p in enumerate(cons_paths):
            if "c3" in p.name or "classified" in p.name:
                cons_choice_default = i
                break
        cons_path = st.selectbox(
            "Consensus (post-classifier preferred)",
            cons_paths,
            index=cons_choice_default,
            format_func=lambda p: str(p.relative_to(REPO_ROOT)),
        )
        consensus = _load_json(cons_path) or {}

        gt_paths = _find_expected_models(REPO_ROOT)
        gt_options = [None, *gt_paths]
        gt_choice = st.selectbox(
            "Ground truth (optional)",
            gt_options,
            index=0 if not gt_paths else 1,
            format_func=lambda p: ("(none)" if p is None
                                    else str(p.relative_to(REPO_ROOT))),
        )
        expected = _load_json(gt_choice) if gt_choice else None

        st.divider()
        st.header("Diff (run B)")
        # Reuse the same consensus discovery used for the primary
        # picker — Cycle 12e uses two consensuses.
        cons_b_options = [None, *cons_paths]
        cons_b_choice = st.selectbox(
            "Second consensus (run B, optional)",
            cons_b_options,
            index=0,
            format_func=lambda p: ("(none)" if p is None
                                    else str(p.relative_to(REPO_ROOT))),
            help=("When set + the `Diff overlay` toggle is on, B's "
                  "rooms render as dashed magenta outlines over A's "
                  "render. The Diff inspector tab shows per-room "
                  "area deltas (B − A)."),
        )
        consensus_b = (_load_json(cons_b_choice)
                       if cons_b_choice is not None else None)

        st.divider()
        st.header("PDF underlay")
        pdf_paths = _find_pdf_candidates(REPO_ROOT, cons_path)
        pdf_options = [None, *pdf_paths]
        pdf_choice = st.selectbox(
            "Source PDF (optional)",
            pdf_options,
            index=0,
            format_func=lambda p: ("(none)" if p is None
                                    else str(p.relative_to(REPO_ROOT))),
            help=("When set, the cockpit rasterises the page via "
                  "pypdfium2 and renders it BEHIND the consensus "
                  "overlay so you can verify alignment with the "
                  "original drawing."),
        )
        pdf_underlay_opacity = st.slider(
            "Underlay opacity", min_value=0.0, max_value=1.0,
            value=0.55, step=0.05,
            help="0 = invisible (overlay only); 1 = fully opaque PDF.",
        )
        pdf_underlay_dpi = st.select_slider(
            "Underlay DPI", options=[72, 96, 144, 200, 300],
            value=144,
            help=("Higher = sharper text but bigger payload sent to "
                  "the browser."),
        )

        st.divider()
        st.header("Layers")
        toggles = OverlayToggles(
            walls=st.checkbox("Walls", value=True),
            rooms=st.checkbox("Rooms", value=True),
            labels=st.checkbox("Labels", value=True),
            openings=st.checkbox("Openings", value=True),
            ground_truth_overlay=st.checkbox(
                "Ground truth overlay", value=False),
            diff_overlay=st.checkbox(
                "Diff overlay (run B as dashed magenta)",
                value=False),
            warnings=st.checkbox("Warnings", value=True),
        )
        st.divider()
        st.header("Scale")
        pt_to_m = st.number_input(
            "PT_TO_M", value=PT_TO_M_DEFAULT,
            min_value=0.001, max_value=1.0, step=0.001, format="%.5f",
        )

    # --- Main: SVG overlay + inspectors -----------------------------
    col_overlay, col_inspect = st.columns([3, 2], gap="medium")

    # Build the PDF underlay once (if requested) so we don't pay the
    # rasterisation cost twice.
    underlay = None
    underlay_error: str | None = None
    if pdf_choice is not None:
        try:
            underlay = pdf_page_to_data_url(
                pdf_choice, dpi=pdf_underlay_dpi,
                opacity=pdf_underlay_opacity,
            )
        except Exception as e:  # noqa: BLE001
            underlay_error = f"PDF underlay failed: {e}"

    # Cycle 12h — build the overrides apply view ONCE so both the
    # SVG annotation and the Review tab share the same snapshot.
    # Graceful degradation: any failure leaves overrides_view=None
    # and the renderer reverts to byte-equivalent v1.x behaviour.
    overrides_view: dict | None = None
    try:
        overrides_doc = load_overrides(
            cons_path.parent, consensus_path=cons_path,
        )
        overrides_view = overrides_apply_view(
            consensus, overrides_doc.get("overrides") or [],
            pt_to_m=pt_to_m,
        )
    except Exception:  # noqa: BLE001
        overrides_view = None

    with col_overlay:
        st.subheader("Top-down overlay")
        caption_bits = [
            f"Source: `{cons_path.relative_to(REPO_ROOT)}`",
            f"PT_TO_M = {pt_to_m:.5f}",
        ]
        if pdf_choice is not None:
            caption_bits.append(
                f"Underlay: `{pdf_choice.relative_to(REPO_ROOT)}` "
                f"@ {pdf_underlay_dpi}dpi · α={pdf_underlay_opacity}"
            )
        st.caption(" · ".join(caption_bits))
        if underlay_error:
            st.warning(underlay_error)
        try:
            svg = render_overlay_svg(
                consensus=consensus,
                toggles=toggles,
                pdf_underlay=underlay,
                pt_to_m=pt_to_m,
                expected_model=expected,
                consensus_b=consensus_b,
                overrides_view=overrides_view,
            )
        except Exception as e:  # noqa: BLE001
            st.error(f"Renderer error: {e}")
            svg = ""
        if svg:
            st.markdown(svg, unsafe_allow_html=True)

        if toggles.warnings:
            _render_warnings_panel(consensus)

    with col_inspect:
        st.subheader("Inspector")
        (tab_rooms, tab_openings, tab_fidelity, tab_expected,
         tab_diff, tab_review, tab_meta) = st.tabs(
            ["Rooms", "Openings", "Fidelity", "Expected",
             "Diff", "Review", "Meta"]
        )
        with tab_rooms:
            rows = room_summary_rows(consensus, pt_to_m=pt_to_m)
            if rows:
                st.dataframe(rows, use_container_width=True,
                              hide_index=True)
                total = sum(r["area_m2"] for r in rows)
                st.caption(
                    f"{len(rows)} rooms · total polygon area "
                    f"{total:.2f} m²"
                )
            else:
                st.info("No rooms in this consensus.")

        with tab_openings:
            rows = opening_summary_rows(consensus)
            if rows:
                st.dataframe(rows, use_container_width=True,
                              hide_index=True)
                from collections import Counter
                kinds = Counter(r.get("kind") for r in rows)
                decs = Counter(r.get("decision") for r in rows)
                st.caption(
                    f"by_kind: {dict(kinds)} · by_decision: {dict(decs)}"
                )
            else:
                st.info("No openings in this consensus.")

        with tab_fidelity:
            _render_fidelity_panel(consensus, expected, pt_to_m)

        with tab_expected:
            _render_expected_panel(consensus, expected, pt_to_m)

        with tab_diff:
            _render_diff_panel(consensus, consensus_b, pt_to_m)

        with tab_review:
            _render_review_panel(consensus, cons_path, pt_to_m)

        with tab_meta:
            md = consensus.get("metadata") or {}
            if md:
                st.json(md)
            else:
                st.info("No `metadata` block on this consensus.")
            st.caption(
                f"schema_version = "
                f"{consensus.get('schema_version', '(unset)')}"
            )


def _render_history_page() -> None:
    """Cycle 12f — multi-run history view with Pre-SKP Review.

    Lists every run under `runs/`, surfaces fidelity + counts +
    image previews per run, lets the user pick two runs to compare
    side-by-side, and grades each with the Pre-SKP Review status
    (PASS / WARN / FAIL — advisory only, never blocks SKP export).
    """
    st.title("Validation Cockpit — History")
    st.caption(
        "Read-only browser of every consensus-bearing dir under "
        "`runs/`. Surfaces fidelity + Pre-SKP Review BEFORE the SKP "
        "spawn cost. Cycle 12f."
    )

    runs = history_summary(REPO_ROOT)
    if not runs:
        st.info(
            "No consensus-bearing dirs under `runs/`. Run the "
            "pipeline first (e.g. `python -m tools.build_vector_consensus "
            "...`) to populate `runs/<dir>/consensus_*.json`."
        )
        return

    with st.sidebar:
        st.header("History view")
        st.caption(
            f"Discovered **{len(runs)}** run(s) under `runs/`."
        )
        st.divider()
        st.subheader("Pre-SKP thresholds")
        pass_fidelity = st.slider(
            "PASS fidelity ≥",
            min_value=0.50, max_value=1.00, step=0.01,
            value=PRE_SKP_PASS_FIDELITY,
            help=("Runs at or above this score with zero hard_fails "
                  "and few warnings are flagged 'safe to export SKP'."),
        )
        warn_fidelity = st.slider(
            "WARN fidelity ≥",
            min_value=0.50, max_value=1.00, step=0.01,
            value=PRE_SKP_WARN_FIDELITY,
            help=("Runs below this score are flagged FAIL — they "
                  "need review before exporting SKP."),
        )
        pass_warnings = st.number_input(
            "PASS warnings budget ≤",
            min_value=0, max_value=99, value=3, step=1,
            help=("Maximum number of fidelity warnings tolerated for "
                  "PASS status. Anything above demotes to WARN."),
        )

    # --- 1) Master table ---------------------------------------------
    st.subheader(f"Runs discovered ({len(runs)})")
    rows: list[dict] = []
    for rs in runs:
        review = pre_skp_review(
            rs,
            pass_fidelity=pass_fidelity,
            warn_fidelity=warn_fidelity,
            pass_warnings=int(pass_warnings),
        )
        snap = rs.as_dict()
        snap["pre_skp"] = (
            f"{_status_emoji(review['status'])} {review['status']}"
        )
        snap["recommendation"] = review["recommendation"]
        rows.append(snap)
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Histogram of statuses for quick eyeballing
    from collections import Counter
    status_counts = Counter(
        pre_skp_review(
            r,
            pass_fidelity=pass_fidelity,
            warn_fidelity=warn_fidelity,
            pass_warnings=int(pass_warnings),
        )["status"] for r in runs
    )
    st.caption(
        "Pre-SKP histogram: "
        + " · ".join(
            f"{_status_emoji(k)} {k}: {v}"
            for k, v in sorted(status_counts.items())
        )
    )

    # --- 2) Single-run detail panel ----------------------------------
    st.divider()
    st.subheader("Run detail")
    by_id = {rs.run_id: rs for rs in runs}
    detail_id = st.selectbox(
        "Run", options=list(by_id.keys()), index=0,
        format_func=lambda rid: rid,
    )
    detail = by_id[detail_id]
    _render_run_detail(detail, pass_fidelity, warn_fidelity,
                       int(pass_warnings))

    # --- 3) Compare two runs -----------------------------------------
    st.divider()
    st.subheader("Compare two runs (before / after)")
    if len(runs) < 2:
        st.info(
            "Need at least 2 runs to compare. Run the pipeline a "
            "second time on the same plant to populate the diff."
        )
        return
    c1, c2 = st.columns(2)
    with c1:
        a_id = st.selectbox(
            "Run A (baseline)", options=list(by_id.keys()),
            index=min(1, len(runs) - 1),
        )
    with c2:
        b_id = st.selectbox(
            "Run B (candidate)", options=list(by_id.keys()),
            index=0,
        )
    if a_id == b_id:
        st.info("Pick two different runs to see the diff.")
        return
    diff = compare_runs(by_id[a_id], by_id[b_id])
    _render_run_compare(diff, by_id[a_id], by_id[b_id])


def _render_run_detail(rs: RunSummary,
                        pass_fidelity: float,
                        warn_fidelity: float,
                        pass_warnings: int) -> None:
    """One-run drilldown: identifiers + counts + Pre-SKP verdict +
    image previews. Pure read-only; mirrors the master-table row but
    with text-friendly layout for screenshotting into PR reviews."""
    review = pre_skp_review(
        rs,
        pass_fidelity=pass_fidelity,
        warn_fidelity=warn_fidelity,
        pass_warnings=pass_warnings,
    )
    cols = st.columns(3)
    with cols[0]:
        st.markdown("**Identifiers**")
        st.write({
            "run_id": rs.run_id,
            "branch": rs.branch or "—",
            "commit": rs.commit or "—",
            "stage": rs.stage or "—",
            "generated_at": rs.generated_at or "—",
        })
    with cols[1]:
        st.markdown("**Counts**")
        st.write({
            "rooms": rs.rooms_count,
            "walls": rs.walls_count,
            "openings": rs.openings_count,
            "soft_barriers": rs.soft_barriers_count,
        })
    with cols[2]:
        emoji = _status_emoji(review["status"])
        # Slice 4-extra: when the F0 report came from gate E3
        # (apply_overrides=True), badge the verdict so a reviewer
        # knows the score reflects their overrides.
        amended_badge = (
            " · 🧑 amended"
            if review.get("using_amended_fidelity") else ""
        )
        st.markdown(
            f"**Pre-SKP Review:** {emoji} `{review['status']}` · "
            f"recommendation = `{review['recommendation']}`"
            f"{amended_badge}"
        )
        if rs.fidelity_score is None:
            st.caption("fidelity_report.json missing — cannot grade.")
        else:
            base_caption = (
                f"fidelity = {rs.fidelity_score:.3f} · "
                f"hard_fails = {len(rs.hard_fails)} · "
                f"warnings = {len(rs.warnings)}"
            )
            st.caption(base_caption)

        # Slice 4-extra (Cycle 14): when the verdict was computed
        # against the amended fidelity report (Slice 5b/5c output),
        # surface both pre/post scores + the delta. The human sees
        # exactly how much their overrides moved the score — and
        # the file proves it cannot be silently masked
        # (ADR-001 §2.10.5).
        if (review.get("using_amended_fidelity")
                and review.get("fidelity_score_pre_override") is not None):
            pre = float(review["fidelity_score_pre_override"])
            post = (
                float(review["fidelity_score"])
                if review.get("fidelity_score") is not None
                else None
            )
            delta = review.get("fidelity_delta")
            delta_str = (
                f" · Δ = {float(delta):+.3f}"
                if isinstance(delta, (int, float))
                else ""
            )
            post_str = (
                f"post-override = {post:.3f}"
                if post is not None
                else "post-override = (missing)"
            )
            st.caption(
                f"🧑 amended fidelity in use · "
                f"{post_str} · "
                f"pre-override = {pre:.3f}"
                f"{delta_str}"
            )

        if review["reasons"]:
            st.write("Reasons:")
            for r in review["reasons"]:
                st.code(r, language="text")

    # Files surfaced
    st.markdown("**Artifacts**")
    facts: list[str] = []
    if rs.consensus_path is not None:
        facts.append(f"consensus → `{rs.consensus_path.relative_to(REPO_ROOT)}`")
    if rs.fidelity_report_path is not None:
        facts.append(
            f"fidelity_report → `{rs.fidelity_report_path.relative_to(REPO_ROOT)}`"
        )
    if rs.scorecard_path is not None:
        facts.append(
            f"scorecard → `{rs.scorecard_path.relative_to(REPO_ROOT)}`"
        )
    if rs.expected_model_path is not None:
        facts.append(
            f"expected_model → `{rs.expected_model_path.relative_to(REPO_ROOT)}`"
        )
    if rs.source_pdf_path is not None:
        facts.append(
            f"source_pdf → `{rs.source_pdf_path.relative_to(REPO_ROOT)}`"
        )
    for line in facts:
        st.markdown(f"- {line}")
    if not facts:
        st.caption("No identifying artifacts found in this run dir.")

    # Hard fails + warnings (if any)
    if rs.hard_fails:
        st.error(f"{len(rs.hard_fails)} hard_fail(s):")
        for hf in rs.hard_fails:
            st.code(hf, language="text")
    if rs.warnings:
        with st.expander(f"{len(rs.warnings)} warning(s)", expanded=False):
            for w in rs.warnings:
                st.code(w, language="text")

    # Sub-scores (if present)
    if rs.sub_scores:
        with st.expander("sub_scores", expanded=False):
            st.json(rs.sub_scores)

    # Image previews — best-effort. PNG/JPG render directly; SVG is
    # surfaced as a relative link (Streamlit's `st.image` doesn't load
    # SVG natively; markdown links are the friendlier path).
    if rs.image_paths:
        st.markdown("**Image previews**")
        png_jpg = [p for p in rs.image_paths
                   if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
        svgs = [p for p in rs.image_paths if p.suffix.lower() == ".svg"]
        if png_jpg:
            st.image(
                [str(p) for p in png_jpg],
                caption=[p.name for p in png_jpg],
                use_container_width=True,
            )
        for svg in svgs:
            try:
                st.markdown(
                    f"- `{svg.relative_to(REPO_ROOT)}` "
                    f"({svg.stat().st_size} bytes)"
                )
            except OSError:
                pass
    else:
        st.caption(
            "No image previews discovered in this run dir "
            "(searched for *.png / *.svg / *.jpg)."
        )


def _render_run_compare(diff, a: RunSummary, b: RunSummary) -> None:
    """Render the before/after comparison panel for two runs."""
    cols = st.columns(2)
    with cols[0]:
        st.markdown(f"**Run A** = `{a.run_id}`")
        st.write({
            "fidelity": a.fidelity_score,
            "hard_fails": len(a.hard_fails),
            "warnings": len(a.warnings),
            "rooms": a.rooms_count,
            "walls": a.walls_count,
            "openings": a.openings_count,
        })
    with cols[1]:
        st.markdown(f"**Run B** = `{b.run_id}`")
        st.write({
            "fidelity": b.fidelity_score,
            "hard_fails": len(b.hard_fails),
            "warnings": len(b.warnings),
            "rooms": b.rooms_count,
            "walls": b.walls_count,
            "openings": b.openings_count,
        })

    delta_lines: list[str] = []
    if diff.fidelity_delta is not None:
        delta_lines.append(
            f"fidelity Δ = `{diff.fidelity_delta:+.3f}` (B − A)"
        )
    delta_lines.append(f"rooms Δ = `{diff.rooms_delta:+d}`")
    delta_lines.append(f"walls Δ = `{diff.walls_delta:+d}`")
    delta_lines.append(f"openings Δ = `{diff.openings_delta:+d}`")
    st.markdown(" · ".join(delta_lines))

    if diff.warnings_resolved:
        st.success(f"Resolved {len(diff.warnings_resolved)} warning(s)")
        with st.expander("warnings resolved", expanded=False):
            for w in diff.warnings_resolved:
                st.code(w, language="text")
    if diff.warnings_new:
        st.warning(f"{len(diff.warnings_new)} new warning(s)")
        with st.expander("warnings new", expanded=False):
            for w in diff.warnings_new:
                st.code(w, language="text")
    if diff.hard_fails_resolved:
        st.success(
            f"Resolved {len(diff.hard_fails_resolved)} hard_fail(s)"
        )
    if diff.hard_fails_new:
        st.error(f"{len(diff.hard_fails_new)} new hard_fail(s)")
        for hf in diff.hard_fails_new:
            st.code(hf, language="text")

    # Per-room delta table (delegates to render_overlay.diff_summary)
    if diff.rooms:
        st.markdown("**Per-room delta**")
        pretty = []
        for r in diff.rooms:
            pretty.append({
                "name": r.get("name"),
                "status": r.get("status"),
                "area_a_m2": r.get("area_a_m2"),
                "area_b_m2": r.get("area_b_m2"),
                "delta_m2 (B−A)": r.get("delta_m2"),
            })
        st.dataframe(pretty, use_container_width=True, hide_index=True)
    else:
        st.caption(
            "No per-room rows produced — at least one consensus is "
            "missing or unparseable."
        )

    # Side-by-side image rows
    if a.image_paths or b.image_paths:
        st.markdown("**Image previews — side-by-side**")
        cols2 = st.columns(2)
        with cols2[0]:
            st.caption(f"A: `{a.run_id}`")
            png_a = [p for p in a.image_paths
                     if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
            if png_a:
                st.image([str(p) for p in png_a],
                          caption=[p.name for p in png_a],
                          use_container_width=True)
            else:
                st.caption("(no PNG/JPG previews in A)")
        with cols2[1]:
            st.caption(f"B: `{b.run_id}`")
            png_b = [p for p in b.image_paths
                     if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
            if png_b:
                st.image([str(p) for p in png_b],
                          caption=[p.name for p in png_b],
                          use_container_width=True)
            else:
                st.caption("(no PNG/JPG previews in B)")


def _status_emoji(status: str) -> str:
    return {"PASS": "✅", "WARN": "🟧", "FAIL": "❌"}.get(status, "?")


def _render_warnings_panel(consensus: dict) -> None:
    md = consensus.get("metadata") or {}
    warns: list[str] = []
    cohere = md.get("coherence") or {}
    if cohere.get("would_block_strict"):
        warns.extend(
            f"coherence: {x}"
            for x in cohere.get("would_block_strict", [])
        )
    if warns:
        st.warning("Detected issues in metadata:")
        for w in warns:
            st.code(w, language="text")


def _render_diff_panel(consensus_a: dict,
                        consensus_b: dict | None,
                        pt_to_m: float) -> None:
    """Cycle 12e — show the per-room diff table between two
    consensuses. Pairs with the dashed-magenta `Diff overlay` toggle
    on the SVG side."""
    if consensus_b is None:
        st.info(
            "No second consensus selected — pick `Second consensus "
            "(run B, optional)` in the sidebar to see the diff "
            "table + the dashed-magenta overlay on the SVG."
        )
        return
    rows = diff_summary(consensus_a, consensus_b, pt_to_m)
    if not rows:
        st.info("No rooms in either consensus to compare.")
        return
    status_label = {
        "matched": "✅ matched",
        "only_in_a": "⬅ only in A",
        "only_in_b": "➡ only in B",
    }
    pretty = []
    for r in rows:
        pretty.append({
            "name": r.get("name"),
            "status": status_label.get(
                r.get("status") or "", r.get("status") or "?"),
            "area_a_m2": r.get("area_a_m2"),
            "area_b_m2": r.get("area_b_m2"),
            "delta_m2 (B−A)": r.get("delta_m2"),
            "verts_a": r.get("verts_a"),
            "verts_b": r.get("verts_b"),
        })
    st.dataframe(pretty, use_container_width=True, hide_index=True)
    from collections import Counter
    by_status = Counter(r.get("status") for r in rows)
    matched = [r for r in rows if r.get("status") == "matched"
               and r.get("delta_m2") is not None]
    if matched:
        total_delta = sum(r["delta_m2"] for r in matched)
        st.caption(
            f"by_status: {dict(by_status)} · "
            f"sum(matched Δ): {total_delta:+.2f} m²"
        )
    else:
        st.caption(f"by_status: {dict(by_status)}")
    st.caption(
        "Toggle `Diff overlay` in the sidebar to render B's rooms "
        "as dashed magenta outlines over A on the SVG."
    )


def _render_review_panel(consensus: dict,
                          consensus_path: Path,
                          pt_to_m: float) -> None:
    """Slice 2 — Review tab.

    The cockpit's first mutation surface. Reads / writes
    `runs/<run_id>/review_overrides.json` for the active run
    (per ADR-001 §3 / §2.3). The pipeline still IGNORES the file
    at this Phase (per ADR-001 §2.9 Phase 1) — Slice 3 introduces
    `tools/apply_overrides.py`.
    """
    run_dir = consensus_path.parent
    try:
        data = load_overrides(run_dir, consensus_path=consensus_path)
    except Exception as e:  # noqa: BLE001
        st.error(f"load_overrides failed: {e}")
        return

    overrides = data.get("overrides") or []
    global_block = data.get("global") or {}
    sha_match = data.get("_consensus_sha256_match")

    # ---- Stale-binding warning (ADR §2.10.6) ------------------------
    if sha_match is False:
        st.error(
            "**Stale binding** — `consensus_sha256` does NOT match the "
            "live consensus. Existing overrides are kept on disk but "
            "are NOT applied until you re-confirm them. Save any new "
            "override below to refresh the binding."
        )

    # ---- Global block toggle (top of tab) ---------------------------
    block_now = bool(global_block.get("block_skp_export") or False)
    if block_now:
        reason_text = global_block.get("block_reason") or "(no reason given)"
        st.error(f"⛔ **SKP export blocked**: {reason_text}")

    with st.expander("⛔ Block SKP export (master toggle)",
                       expanded=block_now):
        new_blocked = st.checkbox(
            "Block SKP export for this run",
            value=block_now,
            help=("When ON, the cockpit refuses to greenlight the "
                  "SKP export step. This sets `global.block_skp_export "
                  "= true` in `review_overrides.json`. The pipeline "
                  "still ignores this file at Slice 2 — Slice 3 wires "
                  "it into the smoke harness via the F0 gate."),
        )
        new_reason = st.text_input(
            "Block reason",
            value=global_block.get("block_reason") or "",
            help="Free-text. Recorded in the audit trail.",
        )
        if st.button("Apply block toggle", key="apply_block_skp"):
            try:
                set_block_skp_export(
                    run_dir,
                    blocked=bool(new_blocked),
                    reason=(new_reason or None),
                    audit_actor="human",
                    consensus_path=consensus_path,
                )
                st.success(
                    "Block toggle saved → "
                    "`review_overrides.json`. Reload the tab to "
                    "see the updated audit trail."
                )
            except Exception as e:  # noqa: BLE001
                st.error(f"set_block_skp_export failed: {e}")

    # ---- Slice 4 — proposed_actions chips ---------------------------
    # Loaded once per render so each row helper reads from the same
    # snapshot. Audit trail is the existing on-disk one (post any
    # writes from this render's earlier interactions).
    proposed_doc = load_proposed_actions(
        run_dir,
        expected_consensus_sha=data.get("consensus_sha256"),
    )
    proposed_actions_list = proposed_doc.get("actions") or []
    audit_trail = data.get("audit_trail") or []
    pa_load_error = proposed_doc.get("_load_error")
    pa_sha_match = proposed_doc.get("_consensus_sha256_match", True)
    if pa_load_error:
        st.warning(
            f"`proposed_actions.json` failed to parse: {pa_load_error}. "
            "Suggestion chips disabled."
        )
    elif proposed_actions_list and pa_sha_match is False:
        st.warning(
            "`proposed_actions.json` was generated against a different "
            "consensus_sha256. Chips are still rendered but flagged as "
            "STALE — re-run `python -m tools.propose_skp_actions "
            f"--run-dir {run_dir.name}` to refresh."
        )
    elif proposed_actions_list:
        st.caption(
            f"📎 {len(proposed_actions_list)} agent suggestion(s) loaded "
            "from `proposed_actions.json`. Chips appear inline next to "
            "each affected opening / room. Click `Apply suggestion` to "
            "promote a chip into a real override (audit-tracked)."
        )

    # ---- Per-opening rows -------------------------------------------
    st.divider()
    st.markdown("### Per-opening review")
    openings = list(consensus.get("openings") or [])
    if not openings:
        st.info("No openings in this consensus.")
    else:
        st.caption(
            f"{len(openings)} opening(s). For each row: pick a "
            "kind override, mark suspect, or reject/approve. "
            "Each click writes to `review_overrides.json`."
        )
        for op in openings:
            _render_opening_review_row(
                op=op, run_dir=run_dir, consensus_path=consensus_path,
                consensus=consensus, overrides=overrides,
                proposed_actions=proposed_actions_list,
                audit_trail=audit_trail,
            )

    # ---- Per-room rows ----------------------------------------------
    st.divider()
    st.markdown("### Per-room review")
    rooms = list(consensus.get("rooms") or [])
    if not rooms:
        st.info("No rooms in this consensus.")
    else:
        st.caption(
            f"{len(rooms)} room(s). Override label, mark suspect, "
            "or reject/approve."
        )
        for r in rooms:
            _render_room_review_row(
                room=r, run_dir=run_dir, consensus_path=consensus_path,
                consensus=consensus, overrides=overrides,
                pt_to_m=pt_to_m,
                proposed_actions=proposed_actions_list,
                audit_trail=audit_trail,
            )

    # ---- Audit trail (bottom) ----------------------------------------
    st.divider()
    audit = list(data.get("audit_trail") or [])
    if not audit:
        st.caption("Audit trail is empty — no overrides recorded yet.")
    else:
        with st.expander(
                f"Audit trail ({len(audit)} event(s))",
                expanded=False):
            # Reverse chronological — newest first
            for entry in reversed(audit):
                ts = entry.get("timestamp") or "?"
                actor = entry.get("actor") or "?"
                event = entry.get("event") or "?"
                tag = entry.get("tag") or ""
                ovid = entry.get("override_id") or "(global)"
                head = (f"`{ts}` · **{event}** · actor=`{actor}` · "
                        f"override_id=`{ovid}`"
                        + (f" · tag=`{tag}`" if tag else ""))
                st.markdown(head)
                cols = st.columns(2)
                with cols[0]:
                    st.caption("before")
                    st.json(entry.get("before") or {})
                with cols[1]:
                    st.caption("after")
                    st.json(entry.get("after") or {})

    # ---- Active overrides summary ------------------------------------
    if overrides:
        with st.expander(
                f"Active overrides ({len(overrides)})", expanded=False):
            view_rows: list[dict] = []
            for ov in overrides:
                tgt = ov.get("target") or {}
                pl = ov.get("payload") or {}
                view_rows.append({
                    "id": (ov.get("id") or "?")[:8],
                    "type": ov.get("type"),
                    "target": f"{tgt.get('kind')}:{tgt.get('id')}",
                    "payload": json.dumps(pl, ensure_ascii=False),
                    "author": ov.get("author"),
                    "created_at": ov.get("created_at"),
                    "reason": ov.get("reason"),
                })
            st.dataframe(view_rows, use_container_width=True,
                          hide_index=True)

            # Cycle 12h — inline override removal. Per ADR-001 §2.7
            # the audit_trail is append-only: clicking "× remove"
            # pops the override from `overrides[]` and appends a
            # NEW `event: delete` audit entry; the original `create`
            # entry stays untouched.
            st.caption(
                "Click `× remove` to delete an override. The "
                "audit trail keeps the original `create` entry "
                "and gains a new `delete` entry — full history "
                "is preserved (ADR-001 §2.7)."
            )
            for ov in overrides:
                ov_id = ov.get("id") or ""
                tgt = ov.get("target") or {}
                tgt_str = f"{tgt.get('kind')}:{tgt.get('id')}"
                cols = st.columns([5, 1])
                with cols[0]:
                    st.markdown(
                        f"`{ov_id[:8]}` · **{ov.get('type')}** · "
                        f"target=`{tgt_str}` · "
                        f"author=`{ov.get('author')}`"
                    )
                with cols[1]:
                    if st.button(
                            "× remove",
                            key=f"rm_ov_{ov_id}",
                            help=("Delete this override. The "
                                  "original `create` audit entry "
                                  "stays; a new `delete` entry is "
                                  "appended."),
                    ):
                        try:
                            remove_override(
                                run_dir,
                                override_id=ov_id,
                                audit_actor="human",
                                consensus_path=consensus_path,
                            )
                            st.success(
                                f"Removed override `{ov_id[:8]}`. "
                                "Reload the tab to see the updated "
                                "audit trail."
                            )
                        except Exception as e:  # noqa: BLE001
                            st.error(f"remove_override failed: {e}")


def _render_opening_review_row(*,
                                op: dict,
                                run_dir: Path,
                                consensus_path: Path,
                                consensus: dict,
                                overrides: list[dict],
                                proposed_actions: list[dict] | None = None,
                                audit_trail: list[dict] | None = None) -> None:
    """One opening row in the Review tab.

    Layout: id+kind on the left; kind dropdown + suspect radio +
    reject/approve toggles on the right. Slice 4 (Cycle 14): when
    ``proposed_actions`` is non-empty and contains entries targeting
    this opening, suggestion chips render below the controls with a
    one-click `Apply suggestion` button.
    """
    eid = op.get("id") or "?"
    kind = op.get("kind_v5") or op.get("kind") or "?"
    decision = op.get("decision") or "?"
    active = overrides_for_element(overrides, "opening", eid)
    active_summary = ", ".join(o.get("type") or "?" for o in active) \
        if active else "(none)"

    with st.container(border=True):
        cols = st.columns([2, 3])
        with cols[0]:
            st.markdown(f"**id=`{eid}`** · kind=`{kind}` · "
                        f"decision=`{decision}`")
            st.caption(f"active overrides: {active_summary}")

        with cols[1]:
            kind_options = ["(none)", *OPENING_KIND_VALUES]
            new_kind = st.selectbox(
                f"kind override · `{eid}`",
                kind_options,
                index=0,
                key=f"opn_kind_{eid}",
                label_visibility="collapsed",
            )
            sev = st.radio(
                f"mark suspect · `{eid}`",
                options=["(off)", *SUSPECT_SEVERITIES],
                index=0,
                horizontal=True,
                key=f"opn_susp_{eid}",
                label_visibility="collapsed",
            )
            r_cols = st.columns(3)
            with r_cols[0]:
                do_reject = st.checkbox(
                    "reject", key=f"opn_rej_{eid}", value=False)
            with r_cols[1]:
                do_approve = st.checkbox(
                    "approve", key=f"opn_app_{eid}", value=False)
            with r_cols[2]:
                if st.button("Apply", key=f"opn_apply_{eid}"):
                    _apply_element_overrides(
                        run_dir=run_dir,
                        consensus_path=consensus_path,
                        consensus=consensus,
                        kind="opening", eid=eid,
                        new_kind=(None if new_kind == "(none)" else new_kind),
                        new_label=None,
                        severity=(None if sev == "(off)" else sev),
                        do_reject=bool(do_reject),
                        do_approve=bool(do_approve),
                    )

        _render_proposed_action_chips(
            target_kind="opening", target_id=eid,
            proposed_actions=proposed_actions,
            audit_trail=audit_trail,
            run_dir=run_dir,
            consensus_path=consensus_path,
            consensus=consensus,
        )


def _render_room_review_row(*,
                             room: dict,
                             run_dir: Path,
                             consensus_path: Path,
                             consensus: dict,
                             overrides: list[dict],
                             pt_to_m: float,
                             proposed_actions: list[dict] | None = None,
                             audit_trail: list[dict] | None = None) -> None:
    """One room row in the Review tab.

    Slice 4 (Cycle 14): proposed_actions chips render below the
    controls, same shape as the opening helper.
    """
    eid = room.get("id") or "?"
    name = room.get("name") or "?"
    poly = room.get("polygon_pts") or []
    area_pts2 = float(room.get("area_pts2") or 0.0)
    area_m2 = area_pts2 * pt_to_m * pt_to_m
    active = overrides_for_element(overrides, "room", eid)
    active_summary = ", ".join(o.get("type") or "?" for o in active) \
        if active else "(none)"

    with st.container(border=True):
        cols = st.columns([2, 3])
        with cols[0]:
            st.markdown(
                f"**id=`{eid}`** · name=`{name}` · "
                f"area={area_m2:.2f} m² · verts={len(poly)}"
            )
            st.caption(f"active overrides: {active_summary}")

        with cols[1]:
            new_label = st.text_input(
                f"label override · `{eid}`",
                value="",
                placeholder=f"new name (current: {name})",
                key=f"room_lbl_{eid}",
                label_visibility="collapsed",
            )
            sev = st.radio(
                f"mark suspect · `{eid}`",
                options=["(off)", *SUSPECT_SEVERITIES],
                index=0,
                horizontal=True,
                key=f"room_susp_{eid}",
                label_visibility="collapsed",
            )
            r_cols = st.columns(3)
            with r_cols[0]:
                do_reject = st.checkbox(
                    "reject", key=f"room_rej_{eid}", value=False)
            with r_cols[1]:
                do_approve = st.checkbox(
                    "approve", key=f"room_app_{eid}", value=False)
            with r_cols[2]:
                if st.button("Apply", key=f"room_apply_{eid}"):
                    _apply_element_overrides(
                        run_dir=run_dir,
                        consensus_path=consensus_path,
                        consensus=consensus,
                        kind="room", eid=eid,
                        new_kind=None,
                        new_label=(new_label.strip() or None),
                        severity=(None if sev == "(off)" else sev),
                        do_reject=bool(do_reject),
                        do_approve=bool(do_approve),
                    )

        _render_proposed_action_chips(
            target_kind="room", target_id=eid,
            proposed_actions=proposed_actions,
            audit_trail=audit_trail,
            run_dir=run_dir,
            consensus_path=consensus_path,
            consensus=consensus,
        )


def _render_proposed_action_chips(*,
                                    target_kind: str,
                                    target_id: str,
                                    proposed_actions: list[dict] | None,
                                    audit_trail: list[dict] | None,
                                    run_dir: Path,
                                    consensus_path: Path,
                                    consensus: dict) -> None:
    """Slice 4 — render proposed_actions as `Apply suggestion` chips.

    No-op when no proposals target this element. Already-applied
    proposals (audit_trail has a `source_proposed_action_id` link)
    render greyed out as "✓ applied".
    """
    if not proposed_actions:
        return
    matches = actions_for_target(
        proposed_actions, target_kind, str(target_id),
    )
    if not matches:
        return
    audit = audit_trail or []
    st.caption("📎 agent suggestions")
    for action in matches:
        applied = action_already_applied(action, audit)
        a_type = action.get("type") or "?"
        a_id = action.get("id") or "?"
        payload = action.get("payload") or {}
        rationale = (action.get("rationale") or "")[:160]
        # Build a one-line chip summary
        if a_type == "classify_opening":
            chip_summary = (
                f"`classify_opening` → {payload.get('suggested_kind', '?')}"
            )
        elif a_type == "mark_low_confidence":
            chip_summary = (
                f"`mark_low_confidence` "
                f"(conf={payload.get('current_confidence', '?')})"
            )
        elif a_type == "request_human_review":
            codes = payload.get("reason_codes") or []
            chip_summary = (
                "`request_human_review` "
                f"({', '.join(str(c) for c in codes) or 'no codes'})"
            )
        else:
            chip_summary = f"`{a_type}` (no Slice 4 mapping)"
        c1, c2 = st.columns([5, 2])
        with c1:
            if applied:
                st.markdown(
                    f"~~{chip_summary}~~ ✓ applied · "
                    f"<span style='opacity:0.6'>{rationale}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"{chip_summary} · "
                    f"<span style='opacity:0.7'>{rationale}</span>",
                    unsafe_allow_html=True,
                )
        with c2:
            if applied:
                st.button(
                    "applied",
                    key=f"chip_apply_{target_kind}_{target_id}_{a_id}",
                    disabled=True,
                )
            else:
                if st.button(
                    "Apply suggestion",
                    key=f"chip_apply_{target_kind}_{target_id}_{a_id}",
                ):
                    try:
                        apply_proposed_action(
                            run_dir=run_dir,
                            action=action,
                            audit_actor="human",
                            consensus_path=consensus_path,
                            consensus=consensus,
                        )
                        st.success(
                            f"Promoted suggestion `{a_id}` → override. "
                            "Reload the tab to see the updated audit "
                            "trail."
                        )
                    except ValueError as e:
                        st.error(f"apply_proposed_action failed: {e}")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"unexpected error: {e}")


def _apply_element_overrides(*,
                              run_dir: Path,
                              consensus_path: Path,
                              consensus: dict,
                              kind: str,
                              eid: str,
                              new_kind: str | None,
                              new_label: str | None,
                              severity: str | None,
                              do_reject: bool,
                              do_approve: bool) -> None:
    """Helper that fans the `Apply` click out into one or more
    `save_override` calls — one per non-default UI control.

    Each call is its own audit-trailed override (per ADR §2.10.3).
    """
    saved_count = 0
    errors: list[str] = []

    if do_reject and do_approve:
        st.error("`reject` and `approve` are mutually exclusive — "
                  "uncheck one and try again.")
        return

    pending: list[dict] = []
    if new_kind and kind == "opening":
        pending.append({
            "type": "opening_kind_override",
            "target": {"kind": "opening", "id": eid},
            "payload": {"new_kind_v5": new_kind},
            "reason": "set via cockpit Review tab",
        })
    if new_label and kind == "room":
        pending.append({
            "type": "room_label_override",
            "target": {"kind": "room", "id": eid},
            "payload": {"new_name": new_label},
            "reason": "set via cockpit Review tab",
        })
    if severity:
        pending.append({
            "type": "mark_suspect",
            "target": {"kind": kind, "id": eid},
            "payload": {"severity": severity, "tag": "review"},
            "reason": "set via cockpit Review tab",
        })
    if do_reject:
        pending.append({
            "type": "reject_element",
            "target": {"kind": kind, "id": eid},
            "payload": {},
            "reason": "set via cockpit Review tab",
        })
    if do_approve:
        pending.append({
            "type": "approve_element",
            "target": {"kind": kind, "id": eid},
            "payload": {},
            "reason": "set via cockpit Review tab",
        })

    if not pending:
        st.info("Nothing to save — pick at least one override.")
        return

    for p in pending:
        try:
            save_override(
                run_dir, p, audit_actor="human",
                consensus_path=consensus_path, consensus=consensus,
            )
            saved_count += 1
        except Exception as e:  # noqa: BLE001
            errors.append(f"{p['type']}: {e}")

    if saved_count:
        st.success(
            f"Saved {saved_count} override(s) for `{kind}:{eid}`. "
            "Reload the page to see the updated audit trail."
        )
    if errors:
        for er in errors:
            st.error(er)


def _render_expected_panel(consensus: dict,
                            expected: dict | None,
                            pt_to_m: float) -> None:
    """Cycle 12d — show the per-room match table between observed
    consensus and expected_model. Pairs with the SVG outline
    re-coloring driven by the `Ground truth overlay` toggle."""
    if expected is None:
        st.info(
            "No ground truth selected — pick a "
            "`ground_truth/<plant>/expected_model.json` in the sidebar "
            "to see the per-room match table."
        )
        return
    rows = expected_match_summary(consensus, expected, pt_to_m)
    if not rows:
        st.info("Expected model has no `rooms` entries to match.")
        return
    # Pretty-print the status with an emoji + color hint so the
    # table reads at a glance even without GT-toggle on the SVG
    status_label = {
        "in_range": "✅ in range",
        "out_of_range_low": "🟧 below min",
        "out_of_range_high": "🟧 above max",
        "missing_polygon": "❌ missing",
        "unmatched_observed": "⬜ unmatched",
    }
    pretty = []
    for r in rows:
        rng = r.get("expected_area_m2_range") or [None, None]
        pretty.append({
            "label": (r.get("expected_label")
                      or r.get("observed_name") or "?"),
            "status": status_label.get(
                r.get("status") or "", r.get("status") or "?"),
            "observed_m2": r.get("observed_area_m2"),
            "expected_min": rng[0] if rng else None,
            "expected_max": rng[1] if rng else None,
        })
    st.dataframe(pretty, use_container_width=True, hide_index=True)
    from collections import Counter
    by_status = Counter(r.get("status") for r in rows)
    st.caption(f"by_status: {dict(by_status)}")
    st.caption(
        "Toggle `Ground truth overlay` in the sidebar to color the "
        "observed room outlines on the SVG by these statuses."
    )


def _render_fidelity_panel(consensus: dict,
                            expected: dict | None,
                            pt_to_m: float) -> None:
    if expected is None:
        st.info(
            "No ground truth selected — pick a `ground_truth/<plant>/"
            "expected_model.json` in the sidebar to see the fidelity "
            "report."
        )
        return
    try:
        from tools.fidelity.compare_generated_to_expected import compare
    except ImportError as e:
        st.error(f"Fidelity engine not importable: {e}")
        return
    try:
        report = compare(
            observed=consensus, expected=expected, pt_to_m=pt_to_m,
        )
    except Exception as e:  # noqa: BLE001
        st.error(f"Fidelity engine error: {e}")
        return
    g = report["global_fidelity"]
    color = "green" if g >= 0.85 else ("orange" if g >= 0.69 else "red")
    st.markdown(
        f"**global_fidelity = "
        f"<span style='color:{color}'>{g}</span>**",
        unsafe_allow_html=True,
    )
    st.write(report.get("sub_scores", {}))
    if report.get("hard_fails"):
        st.error("hard_fails (would block in --strict):")
        for hf in report["hard_fails"]:
            st.code(hf, language="text")
    if report.get("warnings"):
        st.warning("warnings:")
        for w in report["warnings"]:
            st.code(w, language="text")
    if report.get("suggested_fixes"):
        st.info("Suggested fixes:")
        for s in report["suggested_fixes"]:
            st.write(f"- {s}")


if __name__ == "__main__":
    main()
