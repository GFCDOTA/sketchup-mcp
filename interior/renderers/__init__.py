"""Fachada FP-042/R6: o RenderProvider vive em `tools.rendering.providers` (mesmos simbolos, mesma identidade)."""
from tools.rendering.providers import (  # noqa: F401
    RENDER_TYPES,
    RenderProvider,
    RenderRequest,
    RenderResult,
    available_providers,
    get_provider,
)
