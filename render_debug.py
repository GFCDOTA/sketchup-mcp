"""DEPRECATED — moved to ``renderers.debug``.

This thin wrapper preserves backward compatibility for callers still
running ``python render_debug.py <run_dir>``. It will be removed in a
future release. Migrate to ``python -m renderers.debug <run_dir>`` or
``import renderers.debug``.

Migrated 2026-05-08 per ``docs/architecture/target_repo_architecture.md``
step 5.
"""
import runpy
import warnings

warnings.warn(
    "render_debug.py at repo root is deprecated; "
    "use 'python -m renderers.debug' or 'import renderers.debug' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export public attributes for ``from render_debug import ...`` callers.
from renderers.debug import *  # noqa: E402, F401, F403

if __name__ == "__main__":
    runpy.run_module("renderers.debug", run_name="__main__", alter_sys=True)
