"""Renderers package — overlays and debug visualisations for observed_model.

Migrated from root-level ``render_*.py`` scripts in 2026-05-08 per
``docs/architecture/target_repo_architecture.md`` step 5. The original
root-level entry points (``render_debug.py``, ``render_native.py``,
``render_semantic.py``, ``render_proto_overlays.py``,
``render_with_openings.py``) remain as deprecation wrappers; new code
should ``import renderers.<name>`` instead.

Submodules:
- ``renderers.debug`` — full overlay (rooms shaded + walls + junctions)
- ``renderers.native`` — minimal walls + junctions PNGs (replicates the
  repo SVG output)
- ``renderers.semantic`` — colour-coded overlay (walls/bridges/openings/peitoris)
- ``renderers.proto_overlays`` — multi-prototype overlay batch
- ``renderers.with_openings`` — walls + bridges + openings overlay
"""
