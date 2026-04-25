"""Invariants for runs/<run>/consensus_model.json.

Validates schema_version, coordinate_space, diagnostics consistency,
opening geometry_origin whitelist, wall sources/confidence, optional
walls_consolidated geometry, and furniture shape.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CONSENSUS_PATH = Path(
    "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json"
)

ALLOWED_DOOR_ORIGINS = {"svg_arc", "pipeline_gap"}
ALLOWED_WINDOW_ORIGINS = {"svg_window_pair"}


@pytest.fixture(scope="module")
def consensus() -> dict:
    assert CONSENSUS_PATH.exists(), (
        f"consensus_model.json not found at {CONSENSUS_PATH}"
    )
    return json.loads(CONSENSUS_PATH.read_text(encoding="utf-8"))


def test_consensus_file_exists() -> None:
    assert CONSENSUS_PATH.exists(), (
        f"consensus_model.json missing at {CONSENSUS_PATH}"
    )
    assert CONSENSUS_PATH.is_file()
    assert CONSENSUS_PATH.stat().st_size > 0, "consensus_model.json is empty"


def test_metadata_schema_version(consensus: dict) -> None:
    md = consensus.get("metadata")
    assert isinstance(md, dict), "metadata block missing or not a dict"
    assert md.get("schema_version") == "1.0.0", (
        f"expected schema_version '1.0.0', got {md.get('schema_version')!r}"
    )


def test_metadata_coordinate_space(consensus: dict) -> None:
    md = consensus.get("metadata", {})
    assert md.get("coordinate_space") == "pdf_points", (
        f"expected coordinate_space 'pdf_points', got "
        f"{md.get('coordinate_space')!r}"
    )


def test_walls_not_empty(consensus: dict) -> None:
    walls = consensus.get("walls")
    assert isinstance(walls, list), "walls must be a list"
    assert len(walls) > 0, "walls list is empty"


def test_diagnostics_walls_total_matches(consensus: dict) -> None:
    diag = consensus.get("diagnostics")
    assert isinstance(diag, dict), "diagnostics block missing"
    assert "walls_total" in diag, "diagnostics.walls_total missing"
    walls = consensus.get("walls", [])
    assert diag["walls_total"] == len(walls), (
        f"diagnostics.walls_total={diag['walls_total']} != len(walls)={len(walls)}"
    )


def test_diagnostics_openings_total_matches(consensus: dict) -> None:
    diag = consensus.get("diagnostics", {})
    assert "openings_total" in diag, "diagnostics.openings_total missing"
    openings = consensus.get("openings", [])
    assert diag["openings_total"] == len(openings), (
        f"diagnostics.openings_total={diag['openings_total']} "
        f"!= len(openings)={len(openings)}"
    )


def test_every_opening_has_allowed_geometry_origin(consensus: dict) -> None:
    """Door openings must be {svg_arc, pipeline_gap}; window openings
    must be {svg_window_pair}. Per spec, doors get the strict whitelist."""
    openings = consensus.get("openings", [])
    bad: list[tuple[str, str | None, str | None]] = []
    for op in openings:
        origin = op.get("geometry_origin")
        kind = op.get("kind", "door")
        if kind == "window":
            allowed = ALLOWED_WINDOW_ORIGINS
        else:
            allowed = ALLOWED_DOOR_ORIGINS
        if origin not in allowed:
            bad.append((op.get("opening_id", "<no-id>"), kind, origin))
    assert not bad, (
        f"{len(bad)} opening(s) have geometry_origin outside the allowed "
        f"set per kind (door->{sorted(ALLOWED_DOOR_ORIGINS)}, "
        f"window->{sorted(ALLOWED_WINDOW_ORIGINS)}): {bad[:10]}"
    )


def test_every_wall_has_sources_and_confidence(consensus: dict) -> None:
    walls = consensus.get("walls", [])
    failures: list[str] = []
    for w in walls:
        wid = w.get("wall_id", "<no-id>")
        sources = w.get("sources")
        if not isinstance(sources, list):
            failures.append(f"{wid}: sources missing or not a list")
            continue
        conf = w.get("confidence")
        if not isinstance(conf, (int, float)):
            failures.append(f"{wid}: confidence missing or not numeric")
            continue
        if float(conf) < 0.5:
            failures.append(f"{wid}: confidence {conf} < 0.5")
    assert not failures, (
        f"{len(failures)} wall(s) failed sources/confidence invariants: "
        f"{failures[:10]}"
    )


def test_walls_consolidated_geometry_when_present(consensus: dict) -> None:
    if "walls_consolidated" not in consensus:
        pytest.skip("walls_consolidated not present in this consensus")
    items = consensus["walls_consolidated"]
    assert isinstance(items, list), "walls_consolidated must be a list"
    failures: list[str] = []
    for w in items:
        wid = w.get("wall_id", "<no-id>")
        cs = w.get("centerline_start")
        ce = w.get("centerline_end")
        thk = w.get("thickness_pt")
        if not (isinstance(cs, list) and len(cs) == 2):
            failures.append(f"{wid}: centerline_start missing or malformed")
            continue
        if not (isinstance(ce, list) and len(ce) == 2):
            failures.append(f"{wid}: centerline_end missing or malformed")
            continue
        if not isinstance(thk, (int, float)):
            failures.append(f"{wid}: thickness_pt missing or not numeric")
    assert not failures, (
        f"{len(failures)} consolidated wall(s) failed geometry invariants: "
        f"{failures[:10]}"
    )


def test_furniture_shape_when_present(consensus: dict) -> None:
    if "furniture" not in consensus:
        pytest.skip("furniture not present in this consensus")
    items = consensus["furniture"]
    assert isinstance(items, list), "furniture must be a list"
    failures: list[str] = []
    for i, f in enumerate(items):
        if not f.get("type"):
            failures.append(f"furniture[{i}]: missing 'type'")
            continue
        srcs = f.get("sources")
        if not isinstance(srcs, list) or not srcs:
            failures.append(
                f"furniture[{i}] (type={f.get('type')!r}): "
                "sources missing or empty"
            )
    assert not failures, (
        f"{len(failures)} furniture item(s) failed shape invariants: "
        f"{failures[:10]}"
    )
