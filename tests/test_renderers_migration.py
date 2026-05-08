"""Regression tests for the ``renderers/`` package migration (2026-05-08).

Asserts:
- the legacy root ``render_*.py`` modules still import (back-compat),
- the new ``renderers.*`` modules import cleanly,
- importing a legacy wrapper emits ``DeprecationWarning``.

See ``docs/architecture/target_repo_architecture.md`` step 5.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import warnings
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

LEGACY_NAMES = (
    "render_debug",
    "render_native",
    "render_semantic",
    "render_proto_overlays",
    "render_with_openings",
)
NEW_SUBMODULES = (
    "debug",
    "native",
    "semantic",
    "proto_overlays",
    "with_openings",
)


def _purge(name: str) -> None:
    """Drop a module and its sub-modules from ``sys.modules`` before import."""
    for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        sys.modules.pop(key, None)


def _ensure_repo_on_path() -> None:
    """The legacy root scripts live at the repo root and need that on
    ``sys.path`` to be importable. CI / dev shells that add the repo
    via ``pip install -e .`` get this for free; this guard makes the
    test work in environments without an editable install."""
    repo = str(REPO_ROOT)
    if repo not in sys.path:
        sys.path.insert(0, repo)


def test_legacy_imports_still_work():
    """Each legacy ``render_<name>`` module at the repo root must
    remain importable post-migration so old scripts and notebooks keep
    working until the wrappers are removed in a future release."""
    _ensure_repo_on_path()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for name in LEGACY_NAMES:
            _purge(name)
            mod = importlib.import_module(name)
            # The wrapper should have re-exported public names from the
            # underlying ``renderers.<name>`` package via ``import *``.
            assert hasattr(mod, "__doc__")
            assert "DEPRECATED" in (mod.__doc__ or "")


def test_new_package_imports_work():
    """The new ``renderers.<name>`` modules must import cleanly without
    requiring CLI args (the heavy lifting now lives inside ``main()`` /
    ``render()``)."""
    _ensure_repo_on_path()
    for sub in NEW_SUBMODULES:
        mod_name = f"renderers.{sub}"
        _purge(mod_name)
        mod = importlib.import_module(mod_name)
        # Each renderer exposes a ``main()`` callable (CLI entry point);
        # most also expose a ``render()`` function for library callers.
        assert callable(getattr(mod, "main", None)), \
            f"{mod_name}.main is missing or not callable"


def test_legacy_import_emits_deprecation_warning():
    """At least one legacy wrapper must emit ``DeprecationWarning`` on
    fresh import. We pick ``render_debug`` for the canonical assertion;
    the rest are checked structurally in ``test_legacy_imports_still_work``."""
    _ensure_repo_on_path()
    _purge("render_debug")
    _purge("renderers.debug")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        importlib.import_module("render_debug")
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations, "render_debug should emit a DeprecationWarning on import"
    msg = str(deprecations[0].message)
    assert "deprecated" in msg.lower()
    assert "renderers.debug" in msg


@pytest.mark.parametrize("legacy_name", LEGACY_NAMES)
def test_each_legacy_wrapper_has_expected_shape(legacy_name: str):
    """Defensive: each wrapper's source must contain the standard
    deprecation pattern so ``ruff`` can't accidentally simplify it
    away in a future cleanup PR."""
    src = (REPO_ROOT / f"{legacy_name}.py").read_text(encoding="utf-8")
    new_module = legacy_name.replace("render_", "renderers.")
    assert "DeprecationWarning" in src
    assert new_module in src
    assert "warnings.warn" in src
