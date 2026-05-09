"""DEPRECATED — moved to ``renderers.proto_overlays``.

This thin wrapper preserves backward compatibility for callers still
running ``python render_proto_overlays.py``. It will be removed in a
future release. Migrate to ``python -m renderers.proto_overlays`` or
``import renderers.proto_overlays``.

Migrated 2026-05-08 per ``docs/architecture/target_repo_architecture.md``
step 5.
"""
import runpy
import warnings

warnings.warn(
    "render_proto_overlays.py at repo root is deprecated; "
    "use 'python -m renderers.proto_overlays' or "
    "'import renderers.proto_overlays' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from renderers.proto_overlays import *  # noqa: E402, F401, F403

if __name__ == "__main__":
    runpy.run_module("renderers.proto_overlays", run_name="__main__", alter_sys=True)
