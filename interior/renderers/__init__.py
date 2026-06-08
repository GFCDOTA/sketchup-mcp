"""interior.renderers — RenderProvider abstraction (Fase 4).

get_provider(name) devolve o provider por nome. Hoje so 'sketchup_basic' e funcional;
'enscape_preview' e 'vray_final' sao stubs (available()=False) ate a spike da Fase 5.
"""
from interior.renderers.render_provider import (  # noqa: F401
    RENDER_TYPES, RenderProvider, RenderRequest, RenderResult)


def get_provider(name: str = "sketchup_basic"):
    if name == "sketchup_basic":
        from interior.renderers.sketchup_basic_provider import SketchUpBasicProvider
        return SketchUpBasicProvider()
    if name == "enscape_preview":
        from interior.renderers.enscape_preview_provider import EnscapePreviewProvider
        return EnscapePreviewProvider()
    if name == "vray_final":
        from interior.renderers.vray_final_provider import VRayFinalProvider
        return VRayFinalProvider()
    raise ValueError(f"provider desconhecido: {name}")


def available_providers():
    """Quais providers estao automatizaveis neste ambiente."""
    out = {}
    for n in ("sketchup_basic", "enscape_preview", "vray_final"):
        try:
            out[n] = get_provider(n).available()
        except Exception:  # noqa: BLE001
            out[n] = False
    return out
