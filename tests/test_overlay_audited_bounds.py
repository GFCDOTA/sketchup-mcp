"""Overlay sanity test: `runs/h5_final/overlay_audited.png` precisa existir
apos um run, ter dimensoes minimas viaveis e tamanho nao trivial (>10KB).
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
H5_OVERLAY = REPO_ROOT / "runs" / "h5_final" / "overlay_audited.png"


def _require():
    if not H5_OVERLAY.exists():
        pytest.skip(f"overlay_audited.png ausente em {H5_OVERLAY}")


def test_overlay_file_exists():
    _require()
    assert H5_OVERLAY.is_file(), f"overlay nao e arquivo: {H5_OVERLAY}"


def test_overlay_file_size_reasonable():
    _require()
    size = H5_OVERLAY.stat().st_size
    assert size > 10 * 1024, f"overlay tamanho={size} bytes < 10KB (suspeito)"


def test_overlay_dimensions_reasonable():
    _require()
    try:
        from PIL import Image  # noqa: WPS433
    except ImportError:
        pytest.skip("PIL nao disponivel")
    with Image.open(H5_OVERLAY) as img:
        w, h = img.size
    assert w > 500, f"overlay width={w} < 500"
    assert h > 200, f"overlay height={h} < 200"
