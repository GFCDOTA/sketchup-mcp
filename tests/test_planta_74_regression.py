"""End-to-end regression snapshot for the planta_74 hardening chain.

Locks the metrics observed AFTER the F1+F2+F3 hardening commits
(`e0973ed`, `53bc0f7`, `2a268fe`) in `fix/dedup-colinear-planta74`.
This supersedes the earlier snapshot that pinned walls=42 / rooms=16 /
components=3: those numbers came from the pre-hardening union-find
dedup which produced super-clusters with perp_spread up to 151 px
(effectively erasing unrelated walls). The representative-anchored
algorithm (commit `2a268fe`) bounds perp_spread by the tolerance, so
walls and rooms now reflect the real raster geometry.

Snapshot freezes the *connectivity* invariants that matter semantically
(1 component, orphans <= 1, connectivity ratio == 1.0) and uses wide
ranges for wall / room counts because those will tighten later when a
topology-level short-polygon filter (WP-NEW in the plan) attacks the
residual over-polygonization.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from model.pipeline import run_pdf_pipeline

PLANTA_74_PDF = Path(__file__).resolve().parent.parent / "planta_74.pdf"


@pytest.fixture(scope="module")
def planta_74_run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    if not PLANTA_74_PDF.exists():
        pytest.skip(f"{PLANTA_74_PDF.name} is missing from the repo root")
    pdf_bytes = PLANTA_74_PDF.read_bytes()
    output_dir = tmp_path_factory.mktemp("planta_74_regression")
    result = run_pdf_pipeline(
        pdf_bytes=pdf_bytes,
        filename=PLANTA_74_PDF.name,
        output_dir=output_dir,
    )
    return result.observed_model


def test_planta_74_wall_count_within_post_hardening_range(planta_74_run: dict) -> None:
    # Pre-hardening (commit a11724a, union-find): 42 walls (artificially
    # low, super-cluster pathology). Post-hardening (2a268fe,
    # representative-anchored): 230 walls. An eventual topology-level
    # short-polygon filter will bring this back down toward 70-100.
    # The wide range here exists to catch regressions in either
    # direction while the follow-up work is in flight.
    walls = planta_74_run["walls"]
    assert 150 <= len(walls) <= 260, f"walls={len(walls)}"


def test_planta_74_connectivity_is_single_component(planta_74_run: dict) -> None:
    # The hardest semantic invariant to preserve: one connected
    # component, no orphan fragments. Pre-hardening this was 3
    # components with largest ratio 0.93; post-hardening it is 1 with
    # ratio 1.0.
    connectivity = planta_74_run["metadata"]["connectivity"]
    assert connectivity["component_count"] == 1
    assert connectivity["largest_component_ratio"] == pytest.approx(1.0, abs=0.01)
    assert connectivity["max_components_within_page"] == 1
    assert connectivity["orphan_component_count"] <= 1
    assert connectivity["orphan_node_count"] <= 2


def test_planta_74_room_count_within_post_hardening_range(planta_74_run: dict) -> None:
    # Pre-hardening: 16 rooms, many semantically fragmented.
    # Mid-hardening (sliver only): 23, with horizontal floor-hachura
    # strips in SUITE 01 / SUITE 02 / TERRAÇO surviving as "rooms".
    # Post-floor-hachura filter (is_wall_interior with floor_hachura=True):
    # 11, matching the 11 named spaces of the 74 m² apartment
    # (COZINHA, AS, SALA JANTAR/ESTAR, LAVABO, BANHO 02, SUITE 01,
    # BANHO 01, SUITE 02, TERRAÇO TÉCNICO, TERRAÇO SOCIAL, plus the
    # connecting hallway). Lower bound 8 catches regressions that
    # over-merge rooms; upper bound 16 catches regressions that re-
    # admit hachura strips.
    rooms = planta_74_run["rooms"]
    assert 8 <= len(rooms) <= 16, f"rooms={len(rooms)}"


def test_planta_74_no_disconnected_warning(planta_74_run: dict) -> None:
    # Pre-hardening always raised ``walls_disconnected``. Post-
    # hardening the single-component graph drops that warning. Any
    # regression that reintroduces it means the dedup or re-extract
    # changed enough to fragment the graph again.
    warnings = planta_74_run.get("warnings") or []
    assert "walls_disconnected" not in warnings, warnings


def test_planta_74_topology_snapshot_hash_present(planta_74_run: dict) -> None:
    # The F2 hardening commit (53bc0f7) adds a canonical SHA256 of the
    # (walls, junctions) tuple so downstream baselines can catch
    # accidental topology drift. The hash itself is not pinned here
    # because walls/rooms counts still fluctuate; just assert it is
    # emitted.
    metadata = planta_74_run.get("metadata", {})
    assert "topology_snapshot_sha256" in metadata
    assert isinstance(metadata["topology_snapshot_sha256"], str)
    assert len(metadata["topology_snapshot_sha256"]) == 64
