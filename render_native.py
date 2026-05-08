"""DEPRECATED — moved to ``renderers.native``.

This thin wrapper preserves backward compatibility for callers still
running ``python render_native.py <run_dir>``. It will be removed in a
future release. Migrate to ``python -m renderers.native <run_dir>`` or
``import renderers.native``.

Migrated 2026-05-08 per ``docs/architecture/target_repo_architecture.md``
step 5.
"""
import runpy
import warnings

warnings.warn(
    "render_native.py at repo root is deprecated; "
    "use 'python -m renderers.native' or 'import renderers.native' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from renderers.native import *  # noqa: E402, F401, F403

if __name__ == "__main__":
    runpy.run_module("renderers.native", run_name="__main__", alter_sys=True)
