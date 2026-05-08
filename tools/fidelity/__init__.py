"""Fidelity engine — compare a generated/observed pipeline output
against a manual ground-truth ``expected_model.json``.

Stage 1 / Ground Truth v1. Distinct from:
- ``tools.coherence_audit`` (uncertainty audit, no ground truth)
- ``tools.micro_truth_gate`` (per-room subset, < whole plant)
- ``tests/test_planta_74_truth_gate.py`` (deterministic count baseline,
  pinned against itself)

Public API: ``tools.fidelity.compare_generated_to_expected.compare(...)``
+ CLI entry point in the same submodule.

NOTE: this package intentionally does NOT re-export the submodule's
symbols at top level. That avoids the ``RuntimeWarning: ... found in
sys.modules after import of package`` triggered when the submodule is
also invoked via ``python -m``.
"""
