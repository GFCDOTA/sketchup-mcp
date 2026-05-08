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

from cockpit.render_overlay import (
    PT_TO_M_DEFAULT,
    OverlayToggles,
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
    st.title("Validation Cockpit — Cycle 12 MVP")
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
         tab_meta) = st.tabs(
            ["Rooms", "Openings", "Fidelity", "Expected", "Meta"]
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
