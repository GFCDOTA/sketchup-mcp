"""Contract test: detect_wall_gaps emits every field the SU exporter
reads for passage markers.

The Ruby exporter (``tools/consume_consensus.rb``) consumes openings
whose ``geometry_origin == "wall_gap"`` and renders a floor-level
passage marker. It reads exactly these fields from each such opening:

* ``geometry_origin`` (the discriminator)
* ``wall_id`` — must point to a wall whose ``id`` exists in
  ``consensus["walls"]``; the marker uses the wall's ``orientation``
  to orient the rectangle
* ``center`` — [x_pdf_pts, y_pdf_pts], the marker centroid
* ``opening_width_pts`` — the marker's long-side length
* ``id`` — used for the SU group name (``passage_<id>``)

This test does NOT invoke SketchUp. It validates the Python producer
emits every field the Ruby consumer reads, and that the values are in
the shapes the Ruby code assumes (numeric, list of two numbers, etc.).
If a future refactor of ``detect_wall_gaps`` drops or renames any of
these fields, this test fails before the change ships, preventing a
silent break of the SU render.

The Ruby side is asserted indirectly via grepping the exporter source
for the field names — same file referenced above. If the exporter
stops reading one of these fields, the corresponding source-grep
assertion fails, signalling that the contract has shifted on the SU
side and either the producer must follow OR this test must be updated.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.detect_wall_gaps import detect_wall_gaps

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSUMER_RB = REPO_ROOT / "tools" / "consume_consensus.rb"


REQUIRED_FIELDS = (
    "geometry_origin",
    "wall_id",
    "center",
    "opening_width_pts",
    "id",
)


def _consensus_with_one_wall_gap() -> dict:
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 4.0,
        "walls": [
            {
                "id": "w000",
                "start": [0.0, 100.0],
                "end": [100.0, 100.0],
                "thickness": 4.0,
                "orientation": "h",
            },
            {
                "id": "w001",
                "start": [175.0, 100.0],
                "end": [300.0, 100.0],
                "thickness": 4.0,
                "orientation": "h",
            },
        ],
        "openings": [],
        "rooms": [],
        "soft_barriers": [],
    }


@pytest.fixture(scope="module")
def consumer_source() -> str:
    return CONSUMER_RB.read_text(encoding="utf-8")


def test_consumer_reads_geometry_origin_wall_gap(consumer_source: str):
    """The Ruby exporter must branch on the wall_gap discriminator."""
    assert re.search(r"geometry_origin'?\s*\]\s*==\s*'wall_gap'",
                     consumer_source) or "wall_gap" in consumer_source, (
        "consume_consensus.rb does not appear to branch on "
        "geometry_origin == 'wall_gap'; this contract test exists to "
        "catch silent removals of that branch."
    )


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_consumer_reads_each_required_field(consumer_source: str, field: str):
    """Each field the producer emits must still be referenced by the
    consumer. If the consumer stops reading a field, either the producer
    can drop it (update this list) or the consumer regressed."""
    assert f"'{field}'" in consumer_source or f"\"{field}\"" in consumer_source, (
        f"consume_consensus.rb no longer references opening field "
        f"`{field}`; the producer-consumer contract has shifted."
    )


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_producer_emits_each_required_field(field: str):
    """detect_wall_gaps must populate every field the consumer reads."""
    consensus = _consensus_with_one_wall_gap()
    detect_wall_gaps(consensus)
    assert len(consensus["openings"]) == 1
    op = consensus["openings"][0]
    assert field in op, (
        f"detect_wall_gaps does not emit `{field}` on wall_gap "
        f"openings; the SU exporter expects to read it."
    )


def test_producer_field_shapes_match_consumer_assumptions():
    consensus = _consensus_with_one_wall_gap()
    detect_wall_gaps(consensus)
    op = consensus["openings"][0]

    assert op["geometry_origin"] == "wall_gap"
    assert isinstance(op["wall_id"], str) and op["wall_id"]
    assert isinstance(op["center"], list) and len(op["center"]) == 2
    assert all(isinstance(c, (int, float)) for c in op["center"])
    assert isinstance(op["opening_width_pts"], (int, float))
    assert op["opening_width_pts"] > 0
    assert isinstance(op["id"], str) and op["id"]


def test_consumer_resolves_wall_id_to_a_real_wall():
    """The Ruby exporter uses ``walls_by_id[wall_id]`` to look up the
    host wall. The producer must always emit a wall_id that exists in
    the consensus walls list."""
    consensus = _consensus_with_one_wall_gap()
    detect_wall_gaps(consensus)
    wall_ids = {w["id"] for w in consensus["walls"]}
    for op in consensus["openings"]:
        if op.get("geometry_origin") != "wall_gap":
            continue
        assert op["wall_id"] in wall_ids, (
            f"wall_gap opening references unknown wall_id "
            f"{op['wall_id']!r}; SU exporter's walls_by_id lookup "
            f"would silently skip this marker."
        )


def test_consumer_uses_passages_layer(consumer_source: str):
    """The exporter must place markers on a dedicated `passages` layer
    so a human inspecting the SKP can isolate them from walls /
    parapets / rooms."""
    assert "'passages'" in consumer_source or "\"passages\"" in consumer_source, (
        "consume_consensus.rb no longer references a 'passages' layer; "
        "passage markers would land on the default layer and become "
        "unidentifiable."
    )
