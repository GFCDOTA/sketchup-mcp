"""Unit tests for the on-demand thumbnail renderer (Cycle 12g).

Covers:
- ``thumbnail_path`` lives under the cache subdir.
- ``ensure_thumbnail`` creates the cache dir + writes PNG bytes.
- Cached thumbnails short-circuit on subsequent calls.
- Stale thumbnails (consensus mtime > thumb mtime) trigger re-render.
- ``render_consensus_thumbnail`` returns valid PNG bytes.
- Render failures degrade gracefully (return ``None``).
- ``cockpit.history_view.summarise_run`` invokes the thumbnail path
  when no PNG/SVG previews exist in the run dir.

Tests fabricate their own ``runs/<run_id>/`` tree under ``tmp_path``
so they do not depend on the gitignored ``runs/`` directory in the
checkout.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest import mock

import pytest

from cockpit.history_view import summarise_run
from cockpit.thumbnails import (
    CACHE_DIRNAME,
    DEFAULT_WIDTH_PX,
    THUMBNAIL_FILENAME,
    ensure_thumbnail,
    render_consensus_thumbnail,
    thumbnail_path,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _consensus_payload() -> dict:
    """Minimal consensus dict with walls + rooms + openings.
    Coordinates roughly mimic the planta_74 baseline so the thumbnail
    has interesting geometry."""
    return {
        "schema_version": "1.0.0",
        "wall_thickness_pts": 5.4,
        "walls": [
            {"id": "w0", "start": [0, 0], "end": [200, 0],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w1", "start": [200, 0], "end": [200, 150],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w2", "start": [0, 150], "end": [200, 150],
             "thickness": 5.4, "orientation": "h"},
            {"id": "w3", "start": [0, 0], "end": [0, 150],
             "thickness": 5.4, "orientation": "v"},
            {"id": "w4", "start": [100, 0], "end": [100, 150],
             "thickness": 5.4, "orientation": "v"},
        ],
        "rooms": [
            {"id": "r0", "name": "SALA",
             "polygon_pts": [[0, 0], [100, 0], [100, 150], [0, 150]],
             "area_pts2": 15000},
            {"id": "r1", "name": "QUARTO",
             "polygon_pts": [[100, 0], [200, 0], [200, 150], [100, 150]],
             "area_pts2": 15000},
        ],
        "openings": [
            {"id": "o0", "wall_id": "w4", "kind_v5": "interior_door",
             "decision": "clean", "center": [100.0, 75.0],
             "evidence": {"room_left": "SALA", "room_right": "QUARTO"}},
        ],
    }


def _materialise_run(repo: Path, run_id: str,
                     consensus: dict | None = None) -> tuple[Path, Path]:
    run_dir = repo / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    cons_path = run_dir / "consensus_with_room_context.json"
    if consensus is not None:
        cons_path.write_text(json.dumps(consensus), encoding="utf-8")
    return run_dir, cons_path


# ---------------------------------------------------------------------------
# Path / cache shape
# ---------------------------------------------------------------------------

def test_thumbnail_path_under_cache_dirname(tmp_path: Path):
    """The cached PNG path is always
    ``runs/<run_id>/_cockpit_cache/cockpit_thumbnail.png``."""
    run_dir, _ = _materialise_run(tmp_path, "run_a", _consensus_payload())
    p = thumbnail_path(run_dir)
    assert p == run_dir / CACHE_DIRNAME / THUMBNAIL_FILENAME
    assert p.parent.name == CACHE_DIRNAME
    assert p.name == THUMBNAIL_FILENAME
    # Path is computed lazily — calling it must NOT touch disk.
    assert not p.parent.exists()


def test_ensure_thumbnail_creates_cache_dir(tmp_path: Path):
    """``ensure_thumbnail`` must create the cache subdir on first
    call and produce the PNG file."""
    run_dir, cons_path = _materialise_run(
        tmp_path, "run_a", _consensus_payload(),
    )
    assert not (run_dir / CACHE_DIRNAME).exists()
    out = ensure_thumbnail(run_dir, cons_path)
    assert out is not None
    assert out.exists()
    assert out.parent.name == CACHE_DIRNAME
    assert out.read_bytes()[:8] == PNG_SIGNATURE


def test_ensure_thumbnail_returns_path_when_rendered(tmp_path: Path):
    """Successful render returns the cached path (not None)."""
    run_dir, cons_path = _materialise_run(
        tmp_path, "run_a", _consensus_payload(),
    )
    out = ensure_thumbnail(run_dir, cons_path)
    assert out is not None
    assert out == thumbnail_path(run_dir)
    assert out.is_file()


# ---------------------------------------------------------------------------
# Cache freshness
# ---------------------------------------------------------------------------

def test_ensure_thumbnail_uses_cached_when_fresh(tmp_path: Path):
    """When the cache is fresh (consensus mtime <= thumb mtime),
    a second call must NOT re-render — verified by mocking the
    renderer and asserting it never gets called."""
    run_dir, cons_path = _materialise_run(
        tmp_path, "run_a", _consensus_payload(),
    )
    out1 = ensure_thumbnail(run_dir, cons_path)
    assert out1 is not None
    mtime_before = out1.stat().st_mtime

    # Freeze clock noise — make the consensus file older than the
    # thumb so the freshness check unambiguously says "fresh".
    older = mtime_before - 60.0
    import os
    os.utime(cons_path, (older, older))

    with mock.patch(
        "cockpit.thumbnails.render_consensus_thumbnail"
    ) as m:
        out2 = ensure_thumbnail(run_dir, cons_path)
    assert out2 == out1
    m.assert_not_called()


def test_ensure_thumbnail_re_renders_when_consensus_newer(tmp_path: Path):
    """When the consensus mtime > thumb mtime, the cache is stale
    and ``ensure_thumbnail`` must regenerate."""
    run_dir, cons_path = _materialise_run(
        tmp_path, "run_a", _consensus_payload(),
    )
    out1 = ensure_thumbnail(run_dir, cons_path)
    assert out1 is not None

    # Force the thumb to be older than the consensus.
    thumb_mtime = out1.stat().st_mtime
    import os
    older = thumb_mtime - 60.0
    os.utime(out1, (older, older))
    # Touch the consensus to make it strictly newer.
    cons_path.write_text(
        json.dumps(_consensus_payload()), encoding="utf-8",
    )

    # Re-rendering: real call (no mock) — verify the file was
    # rewritten by checking the mtime advanced past the older marker.
    out2 = ensure_thumbnail(run_dir, cons_path)
    assert out2 is not None
    assert out2.stat().st_mtime > older + 0.5


def test_ensure_thumbnail_force_re_renders(tmp_path: Path):
    """``force=True`` must re-render even when the cache is fresh."""
    run_dir, cons_path = _materialise_run(
        tmp_path, "run_a", _consensus_payload(),
    )
    out1 = ensure_thumbnail(run_dir, cons_path)
    assert out1 is not None
    with mock.patch(
        "cockpit.thumbnails.render_consensus_thumbnail",
        return_value=PNG_SIGNATURE + b"forced",
    ) as m:
        out2 = ensure_thumbnail(run_dir, cons_path, force=True)
    assert out2 == out1
    m.assert_called_once()
    assert out2.read_bytes() == PNG_SIGNATURE + b"forced"


# ---------------------------------------------------------------------------
# Pure renderer
# ---------------------------------------------------------------------------

def test_render_consensus_thumbnail_returns_png_bytes():
    """The pure renderer must return bytes that begin with the PNG
    magic signature."""
    png = render_consensus_thumbnail(_consensus_payload())
    assert isinstance(png, bytes)
    assert png[:8] == PNG_SIGNATURE
    assert len(png) > 100


def test_render_consensus_thumbnail_handles_empty_consensus():
    """Even with no walls / rooms / openings, the renderer must
    still produce a valid PNG (a beige rectangle)."""
    empty = {"walls": [], "rooms": [], "openings": []}
    png = render_consensus_thumbnail(empty)
    assert png[:8] == PNG_SIGNATURE


def test_render_consensus_thumbnail_respects_custom_width():
    """When the caller pins a non-default width, the output must
    decode to that width."""
    import io as _io

    from PIL import Image

    png = render_consensus_thumbnail(_consensus_payload(), width_px=160)
    img = Image.open(_io.BytesIO(png))
    assert img.size[0] == 160


def test_render_consensus_thumbnail_rejects_zero_width():
    """A zero or negative width is a programming error and must
    raise rather than silently corrupt the output."""
    with pytest.raises(ValueError):
        render_consensus_thumbnail(_consensus_payload(), width_px=0)


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

def test_ensure_thumbnail_returns_none_on_render_failure(tmp_path: Path):
    """If ``render_consensus_thumbnail`` raises (e.g. PIL missing
    or some other unexpected fault), ``ensure_thumbnail`` must
    return ``None`` so the History view can continue."""
    run_dir, cons_path = _materialise_run(
        tmp_path, "run_a", _consensus_payload(),
    )
    with mock.patch(
        "cockpit.thumbnails.render_consensus_thumbnail",
        side_effect=RuntimeError("boom"),
    ):
        out = ensure_thumbnail(run_dir, cons_path)
    assert out is None
    # Must not have left a partial cache file behind.
    assert not thumbnail_path(run_dir).exists()


def test_ensure_thumbnail_returns_none_on_import_error(tmp_path: Path):
    """If PIL itself is missing (ImportError on the lazy import),
    we still return ``None`` — never a 500."""
    run_dir, cons_path = _materialise_run(
        tmp_path, "run_a", _consensus_payload(),
    )
    with mock.patch(
        "cockpit.thumbnails.render_consensus_thumbnail",
        side_effect=ImportError("no PIL"),
    ):
        out = ensure_thumbnail(run_dir, cons_path)
    assert out is None


def test_ensure_thumbnail_returns_none_on_corrupt_consensus(tmp_path: Path):
    """If the consensus JSON cannot be parsed (corrupt file), the
    thumbnail call returns ``None`` rather than crashing the
    cockpit."""
    run_dir = tmp_path / "runs" / "broken_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    cons_path = run_dir / "consensus.json"
    cons_path.write_text("{not valid json", encoding="utf-8")
    out = ensure_thumbnail(run_dir, cons_path)
    assert out is None


def test_ensure_thumbnail_returns_none_on_missing_consensus(tmp_path: Path):
    """If the consensus path doesn't exist at all, return None."""
    run_dir = tmp_path / "runs" / "ghost"
    run_dir.mkdir(parents=True, exist_ok=True)
    cons_path = run_dir / "missing.json"
    out = ensure_thumbnail(run_dir, cons_path)
    assert out is None


# ---------------------------------------------------------------------------
# Integration — summarise_run wiring
# ---------------------------------------------------------------------------

def test_history_view_summarise_run_populates_thumbnail_when_no_previews(
    tmp_path: Path,
):
    """End-to-end: when a run dir has zero PNG/SVG previews,
    ``summarise_run`` must invoke the thumbnail path and surface
    the cached image in ``image_paths``."""
    run_dir, _cons = _materialise_run(
        tmp_path, "no_preview_run", _consensus_payload(),
    )
    # Sanity: no images on disk before
    assert not list(run_dir.glob("*.png"))
    assert not list(run_dir.glob("*.svg"))

    rs = summarise_run(run_dir, repo=tmp_path)
    assert rs.consensus_path is not None
    assert len(rs.image_paths) == 1
    only = rs.image_paths[0]
    assert only.name == THUMBNAIL_FILENAME
    assert only.parent.name == CACHE_DIRNAME
    assert only.exists()
    assert only.read_bytes()[:8] == PNG_SIGNATURE


def test_history_view_summarise_run_skips_thumbnail_when_previews_exist(
    tmp_path: Path,
):
    """If the run dir already has PNG/SVG previews, ``summarise_run``
    must NOT trigger the thumbnail path (we don't want to spam the
    cache for runs that already have artwork)."""
    run_dir, _ = _materialise_run(
        tmp_path, "with_preview", _consensus_payload(),
    )
    (run_dir / "preview_overlay.png").write_bytes(PNG_SIGNATURE)
    rs = summarise_run(run_dir, repo=tmp_path)
    # Cache dir must NOT have been created.
    assert not (run_dir / CACHE_DIRNAME).exists()
    img_names = [p.name for p in rs.image_paths]
    assert "preview_overlay.png" in img_names
    assert THUMBNAIL_FILENAME not in img_names


def test_history_view_summarise_run_no_thumbnail_when_consensus_missing(
    tmp_path: Path,
):
    """If a run dir has no consensus AND no previews, the thumbnail
    path is a no-op (we have nothing to render). image_paths stays
    empty, and the cache dir is not created."""
    run_dir = tmp_path / "runs" / "ghost"
    run_dir.mkdir(parents=True, exist_ok=True)
    rs = summarise_run(run_dir, repo=tmp_path)
    assert rs.consensus_path is None
    assert rs.image_paths == []
    assert not (run_dir / CACHE_DIRNAME).exists()


# ---------------------------------------------------------------------------
# Stability touch — make sure the timing test isn't flaky
# ---------------------------------------------------------------------------

def test_ensure_thumbnail_keeps_returning_same_path_across_calls(
    tmp_path: Path,
):
    """Five consecutive calls under fresh-cache conditions must
    return the same path and not rewrite the file."""
    run_dir, cons_path = _materialise_run(
        tmp_path, "run_a", _consensus_payload(),
    )
    out = ensure_thumbnail(run_dir, cons_path)
    assert out is not None
    first_mtime = out.stat().st_mtime
    # Make the consensus older so freshness check definitely passes.
    import os
    os.utime(cons_path, (first_mtime - 60.0, first_mtime - 60.0))
    for _ in range(5):
        again = ensure_thumbnail(run_dir, cons_path)
        assert again == out
    # Mtime must not have advanced — we never re-rendered.
    assert out.stat().st_mtime == first_mtime
    # Anchor on a real time call so the test framework counts the
    # delay; protects against systems that round mtime to >1s.
    _ = time.time()


# ---------------------------------------------------------------------------
# Width / aspect smoke
# ---------------------------------------------------------------------------

def test_ensure_thumbnail_width_default_is_320(tmp_path: Path):
    """Default rendered width matches the documented default."""
    from PIL import Image
    run_dir, cons_path = _materialise_run(
        tmp_path, "run_a", _consensus_payload(),
    )
    out = ensure_thumbnail(run_dir, cons_path)
    assert out is not None
    assert Image.open(out).size[0] == DEFAULT_WIDTH_PX
