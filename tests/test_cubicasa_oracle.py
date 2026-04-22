"""Tests for the CubiCasa5K dev-time oracle.

These tests intentionally do NOT require the weights to run. They verify:
  * the script raises a clear setup error if weights are missing,
  * the OracleOpening.to_dict() matches the pipeline's `openings[*]` shape,
  * if weights happen to exist locally, an end-to-end inference test runs
    on the `minimal_room.svg` fixture.

Weights-heavy tests are marked `@pytest.mark.skipif` so CI without
CubiCasa5K set up still passes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# Make scripts/ importable for the oracle module.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import run_cubicasa_oracle as oracle  # noqa: E402  (path insertion above)


DEFAULT_WEIGHTS = oracle.DEFAULT_WEIGHTS
MINIMAL_SVG = PROJECT_ROOT / "tests" / "fixtures" / "svg" / "minimal_room.svg"

WEIGHTS_PRESENT = DEFAULT_WEIGHTS.exists()
TORCH_AVAILABLE = True
try:
    import torch  # noqa: F401
except ImportError:
    TORCH_AVAILABLE = False


# ---------- always-on: setup-error path ----------


def test_run_cubicasa_skips_if_no_weights(tmp_path: Path) -> None:
    """Script emits a clear, pointing-to-README error if weights are absent.

    Runs against a fabricated missing path so it works regardless of
    whether the real weights exist or not.
    """
    missing = tmp_path / "no_such_weights.pkl"
    out = tmp_path / "oracle.json"

    with pytest.raises(RuntimeError) as err:
        oracle.run(
            svg_path=MINIMAL_SVG,
            out_path=out,
            weights_path=missing,
            raster_size=64,
            device="cpu",
        )

    message = str(err.value)
    # Must mention the README so the operator knows where to go.
    assert "vendor/CubiCasa5k/README.md" in message
    # Must mention the missing path so the operator can double-check.
    assert str(missing) in message
    # And must mention the Google Drive ID so the user can grab the file.
    assert "1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK" in message


def test_output_schema_matches_observed_openings() -> None:
    """OracleOpening.to_dict() must shape-match pipeline's openings[*].

    The pipeline's opening dict has exactly these keys:
        opening_id, page_index, orientation, center, width,
        wall_a, wall_b, kind

    (See `openings/service.py::Opening.to_dict`.) Oracle sets wall_a/wall_b
    to None because CubiCasa doesn't link openings to specific walls.
    """
    op = oracle.OracleOpening(
        opening_id="oracle-1",
        page_index=0,
        orientation="horizontal",
        center=(200.0, 215.0),
        width=46.0,
        kind="door",
    )
    d = op.to_dict()

    expected_keys = {
        "opening_id", "page_index", "orientation", "center",
        "width", "wall_a", "wall_b", "kind",
    }
    assert set(d.keys()) == expected_keys
    assert d["opening_id"] == "oracle-1"
    assert d["page_index"] == 0
    assert d["orientation"] == "horizontal"
    assert d["center"] == [200.0, 215.0]
    assert d["width"] == 46.0
    assert d["wall_a"] is None
    assert d["wall_b"] is None
    assert d["kind"] == "door"


def test_channel_layout_constants_match_cubicasa_spec() -> None:
    """Guards against accidental edits to the channel layout constants.

    The published CubiCasa5K checkpoint has exactly 21 + 12 + 11 = 44
    channels. Door=2, Window=1 inside the icon block. Changing any of
    these without also updating the inference code would silently produce
    wrong openings.
    """
    assert oracle.HEATMAP_COUNT == 21
    assert oracle.ROOM_COUNT == 12
    assert oracle.ICON_COUNT == 11
    assert oracle.HEATMAP_COUNT + oracle.ROOM_COUNT + oracle.ICON_COUNT == 44

    assert oracle.HEATMAPS_OFFSET == 0
    assert oracle.ROOMS_OFFSET == 21
    assert oracle.ICONS_OFFSET == 33

    # Door and Window have specific local-icon indices in the upstream
    # class list; swap them and the "kind" label flips. See samples.ipynb.
    assert oracle.ICON_WINDOW == 1
    assert oracle.ICON_DOOR == 2


# ---------- weights-heavy: skipped by default ----------


@pytest.mark.skipif(
    not WEIGHTS_PRESENT or not TORCH_AVAILABLE,
    reason=(
        "CubiCasa5K weights and/or torch not available. "
        "See vendor/CubiCasa5k/README.md for manual setup."
    ),
)
def test_end_to_end_minimal_room(tmp_path: Path) -> None:
    """If the operator has set up CubiCasa5K, verify a full run produces
    a valid JSON file with the expected top-level keys.
    """
    out = tmp_path / "oracle.json"

    payload = oracle.run(
        svg_path=MINIMAL_SVG,
        out_path=out,
        weights_path=DEFAULT_WEIGHTS,
        raster_size=256,  # small for test speed
        device="cpu",
    )

    assert out.exists()
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == payload

    # Top-level schema
    assert payload["source"] == "CubiCasa5K oracle"
    assert payload["weights_path"].endswith("model_best_val_loss_var.pkl")
    assert len(payload["weights_sha256"]) == 64  # sha256 hex digest
    assert payload["input"]["svg"].endswith("minimal_room.svg")
    assert payload["input"]["raster_size"] == [256, 256]

    # openings is a list; each entry has the pipeline schema
    assert isinstance(payload["openings"], list)
    for op in payload["openings"]:
        assert {
            "opening_id", "page_index", "orientation", "center",
            "width", "wall_a", "wall_b", "kind",
        } == set(op.keys())
        assert op["kind"] in ("door", "window")
        assert op["orientation"] in ("horizontal", "vertical")
        assert op["wall_a"] is None
        assert op["wall_b"] is None
