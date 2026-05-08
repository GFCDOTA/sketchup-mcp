"""DEPRECATED — moved to ``renderers.with_openings``.

This thin wrapper preserves backward compatibility for callers still
running ``python render_with_openings.py <run_dir>``. It will be
removed in a future release. Migrate to
``python -m renderers.with_openings <run_dir>`` or
``import renderers.with_openings``.

Migrated 2026-05-08 per ``docs/architecture/target_repo_architecture.md``
step 5.
"""
import runpy
import warnings

warnings.warn(
    "render_with_openings.py at repo root is deprecated; "
    "use 'python -m renderers.with_openings' or "
    "'import renderers.with_openings' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from renderers.with_openings import *  # noqa: E402, F401, F403

if __name__ == "__main__":
    runpy.run_module("renderers.with_openings", run_name="__main__", alter_sys=True)
