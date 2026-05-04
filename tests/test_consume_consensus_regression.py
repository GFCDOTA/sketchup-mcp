"""Regression tests for `tools/consume_consensus.rb` source-level invariants.

These tests pin source-level fixes for known SKP fidelity defects so that
future edits cannot silently revert them. They do NOT launch SketchUp
(per CLAUDE.md §3, SU is the last gate). They grep the Ruby source.

Defects guarded
---------------

D1 — Triplication / Sree template figure
    Symptom: re-running consume on the same SKP produces ``wall_dark1`` /
    ``wall_dark2`` material duplicates, 3x wall groups at the same bbox,
    and a leftover ``Sree`` ComponentInstance from the SU 2026
    Architectural template. Documented in
    ``runs/vector/inspect_report_summary.md`` (2026-05-02).
    Fix in source: ``reset_model(model)`` is called from ``main`` BEFORE
    ``model.start_operation`` and clears entities + purges defs/mats.

D2 — Parapets without material
    Symptom: ``add_parapet`` extrudes faces but doesn't paint them, so
    994 default-white faces ride on top of every parapet.
    Fix in source: after ``pushpull``, every face in the parapet group
    gets ``material`` and ``back_material`` assigned.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSUME = REPO_ROOT / "tools" / "consume_consensus.rb"


@pytest.fixture(scope="module")
def consume_source() -> str:
    assert CONSUME.exists(), f"consume_consensus.rb missing: {CONSUME}"
    return CONSUME.read_text(encoding="utf-8")


def test_reset_model_defined_and_clears_entities(consume_source: str) -> None:
    """D1 guard: reset_model must exist and call entities.clear!."""
    match = re.search(
        r"def\s+reset_model\b(.+?)(?=^def\s|\Z)",
        consume_source,
        re.DOTALL | re.MULTILINE,
    )
    assert match, "reset_model function not found in consume_consensus.rb"
    body = match.group(1)
    assert "model.entities.clear!" in body, (
        "reset_model must call model.entities.clear! to kill triplication"
    )
    assert "model.definitions.purge_unused" in body, (
        "reset_model must purge unused definitions to remove Sree figure"
    )
    assert "model.materials.purge_unused" in body, (
        "reset_model must purge unused materials to avoid wall_dark1/2 collisions"
    )


def test_main_calls_reset_before_start_operation(consume_source: str) -> None:
    """D1 guard: main must invoke reset_model(model) BEFORE start_operation."""
    main_match = re.search(
        r"def\s+main\b(.+?)(?=^def\s|\Z)",
        consume_source,
        re.DOTALL | re.MULTILINE,
    )
    assert main_match, "main function not found in consume_consensus.rb"
    body = main_match.group(1)
    reset_idx = body.find("reset_model(model)")
    start_idx = body.find("model.start_operation")
    assert reset_idx >= 0, "main must call reset_model(model)"
    assert start_idx >= 0, "main must call model.start_operation"
    assert reset_idx < start_idx, (
        "reset_model must run BEFORE start_operation; otherwise the wipe "
        "happens mid-undo-stack and triplication returns"
    )


def test_add_parapet_paints_faces(consume_source: str) -> None:
    """D2 guard: add_parapet must assign material AND back_material."""
    match = re.search(
        r"def\s+add_parapet\b(.+?)(?=^def\s|\Z)",
        consume_source,
        re.DOTALL | re.MULTILINE,
    )
    assert match, "add_parapet function not found in consume_consensus.rb"
    body = match.group(1)
    assert "pushpull" in body, "add_parapet must extrude (pushpull)"
    assert re.search(r"\.material\s*=\s*parapet_material", body), (
        "add_parapet must assign face.material = parapet_material to "
        "prevent 583 default-white side faces"
    )
    assert re.search(r"\.back_material\s*=\s*parapet_material", body), (
        "add_parapet must assign back_material to prevent 411 default-white "
        "tops visible from below"
    )
