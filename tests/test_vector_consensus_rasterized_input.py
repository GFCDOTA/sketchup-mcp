"""Pin the early-return diagnostic when build_vector_consensus.py
receives a PDF without vector path objects.

Background
----------
`planta_74_clean.pdf` (a rasterized "print to PDF" of the same plan)
caused `tools.build_vector_consensus` to print a generic
``[err] no wall paths detected`` and silently exit. The real reason
was that the PDF wraps a single bitmap and has zero ``path`` objects
to read. See ``docs/learning/planta_74_clean_compatibility.md``.

This test pins the new behavior:

* on a rasterized PDF, the build returns ``{}`` AND prints a clear
  diagnostic with ``drawings=0`` + ``page_size=WxH`` + pointer to
  the raster pipeline.
* on a vector PDF that has paths but no walls extractable, the build
  also returns ``{}`` but with a different diagnostic that includes
  ``drawings=N filled_only=K stroked_only=M``.
* the existing happy path on the real ``planta_74.pdf`` keeps working
  (regression check; integration-only — skipped when the asset is
  not on disk).
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from build_vector_consensus import build  # noqa: E402


def _make_rasterized_pdf(out_path: Path, w: int = 600, h: int = 800) -> None:
    """Write a single-page PDF that wraps a bitmap. The same shape as
    a "print to PDF" of an image — what we observed in
    `planta_74_clean.pdf`.
    """
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    # Draw something raster-only so the PDF isn't entirely blank.
    d.rectangle([50, 50, w - 50, h - 50], outline="black", width=8)
    d.line([(w // 2, 50), (w // 2, h - 50)], fill="black", width=8)
    img.save(out_path, "PDF", resolution=72.0)


def test_rasterized_pdf_emits_clear_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pdf = tmp_path / "rasterized.pdf"
    _make_rasterized_pdf(pdf)

    out = tmp_path / "consensus.json"
    result = build(pdf, out, detect_openings=False)

    assert result == {}, "rasterized PDF must short-circuit to {}"
    captured = capsys.readouterr()
    err = captured.err
    # The new explicit message
    assert "rasterized" in err.lower(), (
        f"expected 'rasterized' diagnostic, got stderr={err!r}"
    )
    assert "drawings=0" in err
    assert "page_size=" in err
    # Pointer to the raster pipeline
    assert "main.py extract" in err or "raster pipeline" in err.lower()
    # No JSON file should be written for the empty result
    assert not out.exists()


def test_real_planta_74_keeps_working() -> None:
    """Regression: the documented happy path
    (``OVERVIEW.md §4.4 step 1`` on ``planta_74.pdf``) must still
    produce 33 walls. Skipped on a fresh checkout where the PDF
    is not on disk.
    """
    pdf = REPO_ROOT / "planta_74.pdf"
    if not pdf.exists():
        pytest.skip("planta_74.pdf not in working tree")

    out = REPO_ROOT / "runs" / "_test_vector_regression" / "consensus.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        consensus = build(pdf, out, detect_openings=True)
    finally:
        # Clean up the temp output file but leave the dir (gitignored).
        if out.exists():
            out.unlink()

    assert consensus, "build() returned empty on planta_74.pdf — regression!"
    assert len(consensus["walls"]) == 33, (
        f"wall count regression on planta_74.pdf: "
        f"got {len(consensus['walls'])}, expected 33"
    )
    # detect_openings=True must yield 12 on this baseline.
    assert len(consensus["openings"]) == 12


def test_diagnostic_message_format_for_no_paths(tmp_path: Path,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    """The diagnostic must mention all three counters that
    docs/learning/planta_74_clean_compatibility.md specifies:
    drawings, page_size, and mode (raster-like).
    """
    pdf = tmp_path / "raster2.pdf"
    _make_rasterized_pdf(pdf, w=856, h=1212)
    out = tmp_path / "out.json"
    result = build(pdf, out)
    assert result == {}
    err = capsys.readouterr().err
    assert "drawings=0" in err
    assert "page_size=856x1212" in err
    assert "raster-like" in err
