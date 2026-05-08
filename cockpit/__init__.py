"""Validation Cockpit — local Streamlit UI for visualizing what
the planta extraction pipeline understood from a PDF, BEFORE
SKP generation.

Cycle 12 (2026-05-08). Optional dependency: install via
``pip install -e ".[cockpit]"`` to get streamlit. The renderer
in ``cockpit.render_overlay`` has zero hard deps and is unit-
testable on its own.

Entry point: ``streamlit run cockpit/app.py`` from the repo root.
"""
