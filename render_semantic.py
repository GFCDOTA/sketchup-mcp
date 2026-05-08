"""DEPRECATED — moved to ``renderers.semantic``.

This thin wrapper preserves backward compatibility for callers still
running ``python render_semantic.py <run_dir>``. It will be removed in
a future release. Migrate to ``python -m renderers.semantic <run_dir>``
or ``import renderers.semantic``.

Migrated 2026-05-08 per ``docs/architecture/target_repo_architecture.md``
step 5.
"""
import runpy
import warnings

warnings.warn(
    "render_semantic.py at repo root is deprecated; "
    "use 'python -m renderers.semantic' or 'import renderers.semantic' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from renderers.semantic import *  # noqa: E402, F401, F403

if __name__ == "__main__":
    runpy.run_module("renderers.semantic", run_name="__main__", alter_sys=True)
