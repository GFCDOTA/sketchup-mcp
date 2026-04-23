"""GATE test: p12_red.pdf rodado pelo run_pdf_pipeline precisa bater exatamente
os snapshots canonicos congelados. Qualquer divergencia = regressao.

Asserts:
  - walls == 33
  - juncs == 65
  - rooms == 19
  - openings == 6
  - peitoris == 2
  - topology_snapshot_sha256 == "39b4138f4fd5613ed897824657b0329445d2eb332a6a1d810da75933ba4b5ce3"
  - scores: topology==1.0, geometry~=0.3226, rooms~=0.7346

Se o teste falhar: investigar o que mudou antes de atualizar o snapshot.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
P12_PDF = REPO_ROOT / "runs" / "proto" / "p12_red.pdf"
P12_PEITORIS = REPO_ROOT / "runs" / "proto" / "p12_peitoris.json"

EXPECTED_SHA = "39b4138f4fd5613ed897824657b0329445d2eb332a6a1d810da75933ba4b5ce3"
EXPECTED_WALLS = 33
EXPECTED_JUNCS = 65
# F6 dedup absorbs room-17 (a 3-vertex sliver between room-16 and
# room-18) into room-16. Walls/junctions are unchanged — the topology
# snapshot hash remains byte-identical to the Wave 1 baseline.
EXPECTED_ROOMS = 18
EXPECTED_OPENINGS = 6
EXPECTED_PEITORIS = 2
EXPECTED_TOPOLOGY_SCORE = 1.0
EXPECTED_GEOMETRY_SCORE = 0.3226
# Rooms score depends on room count (density over edge count); drops
# from 0.7346 to 0.7222 when a single room is absorbed.
EXPECTED_ROOMS_SCORE = 0.7222


def _require_inputs():
    if not P12_PDF.exists():
        pytest.skip(f"p12_red.pdf ausente: {P12_PDF}")
    if not P12_PEITORIS.exists():
        pytest.skip(f"p12_peitoris.json ausente: {P12_PEITORIS}")


@pytest.fixture(scope="module")
def p12_observed(tmp_path_factory):
    _require_inputs()
    from model.pipeline import run_pdf_pipeline

    out = tmp_path_factory.mktemp("p12_snapshot")
    peitoris = json.loads(P12_PEITORIS.read_text(encoding="utf-8"))
    result = run_pdf_pipeline(
        pdf_bytes=P12_PDF.read_bytes(),
        filename=P12_PDF.name,
        output_dir=out,
        peitoris=peitoris,
    )
    return result.observed_model


def test_p12_walls_count_gate(p12_observed):
    assert len(p12_observed["walls"]) == EXPECTED_WALLS, (
        f"walls={len(p12_observed['walls'])} != {EXPECTED_WALLS} (regressao canonical)"
    )


def test_p12_junctions_count_gate(p12_observed):
    assert len(p12_observed["junctions"]) == EXPECTED_JUNCS, (
        f"juncs={len(p12_observed['junctions'])} != {EXPECTED_JUNCS}"
    )


def test_p12_rooms_count_gate(p12_observed):
    assert len(p12_observed["rooms"]) == EXPECTED_ROOMS, (
        f"rooms={len(p12_observed['rooms'])} != {EXPECTED_ROOMS}"
    )


def test_p12_openings_count_gate(p12_observed):
    assert len(p12_observed.get("openings", [])) == EXPECTED_OPENINGS, (
        f"openings={len(p12_observed.get('openings', []))} != {EXPECTED_OPENINGS}"
    )


def test_p12_peitoris_count_gate(p12_observed):
    assert len(p12_observed.get("peitoris", [])) == EXPECTED_PEITORIS, (
        f"peitoris={len(p12_observed.get('peitoris', []))} != {EXPECTED_PEITORIS}"
    )


def test_p12_topology_snapshot_sha_gate(p12_observed):
    sha = p12_observed.get("metadata", {}).get("topology_snapshot_sha256")
    assert sha == EXPECTED_SHA, (
        f"topology_snapshot_sha256 mudou: {sha!r} != {EXPECTED_SHA!r}"
    )


def test_p12_topology_score_gate(p12_observed):
    assert p12_observed["scores"]["topology"] == EXPECTED_TOPOLOGY_SCORE, (
        f"topology score={p12_observed['scores']['topology']} != {EXPECTED_TOPOLOGY_SCORE}"
    )


def test_p12_geometry_score_gate(p12_observed):
    got = p12_observed["scores"]["geometry"]
    assert math.isclose(got, EXPECTED_GEOMETRY_SCORE, abs_tol=1e-4), (
        f"geometry score={got} != {EXPECTED_GEOMETRY_SCORE}"
    )


def test_p12_rooms_score_gate(p12_observed):
    got = p12_observed["scores"].get("rooms")
    assert got is not None, "scores.rooms ausente no observed_model"
    assert math.isclose(got, EXPECTED_ROOMS_SCORE, abs_tol=1e-4), (
        f"rooms score={got} != {EXPECTED_ROOMS_SCORE}"
    )
