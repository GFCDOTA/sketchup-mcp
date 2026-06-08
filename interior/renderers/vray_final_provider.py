"""vray_final_provider.py — V-Ray FINAL/premium (stub com API MAPEADA; Fase 8 implementa).

SPIKE Fase 5 CONFIRMOU VIABILIDADE (empirico, .claude/scratch/probe_vray*.rb em SU 2026):
  - Extensao "V-Ray for SketchUp" CARREGA no SU 2026 (loaded=true) + binario vray4sketchup2026.so.
  - API Ruby `module VRay` totalmente alcancavel (176 constants) a partir de -RubyStartup.
  - Fluxo render->save MAPEADO:
      * VRay::RenderSessionProduction.new(context:).start        -> render in-SU
      * VRay::RenderSessionExport.new(context:, path: '..vrscene').start -> exporta .vrscene
        (depois `vray.exe -sceneFile=x.vrscene -imgFile=y.png` renderiza HEADLESS, offline)
      * VRayRenderer#image -> VRay::VRayImage#save(path) -> PNG
      * VRay.configure_renderer(...) / VRay::Settings.load_defaults -> settings
      * VRay::ModelExporter#update_camera / export_model -> camera/geom
  - vray.exe standalone: C:\\Program Files\\Chaos\\V-Ray\\V-Ray for SketchUp\\extension\\vray\\bin\\vray.exe

REMANESCENTE (Fase 8, empirico — NAO inventar): obter o `context` (source crypt-protegido,
sem call-sites em texto) + nailar os 3 args de VRay.start_render. Caminho mais deterministico:
RenderSessionExport -> .vrscene -> vray.exe headless (desacopla do GUI do SU). Pre-req: licenca
V-Ray ativa (ja instalada). Riscos: render lento (min), VFB window, compat. Implementar em ciclo
focado com tentativa cuidadosa (base copia + timeout + kill) OU snippet de referencia do AppSDK.
"""
from __future__ import annotations

from pathlib import Path

from interior.renderers.render_provider import RenderProvider, RenderRequest, RenderResult

VRAY_SO = Path(r"C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\extension\vray4sketchup2026.so")
VRAY_EXE = Path(r"C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp\extension\vray\bin\vray.exe")


class VRayFinalProvider(RenderProvider):
    name = "vray_final"

    def available(self) -> bool:
        # extensao p/ SU 2026 + vray.exe presentes (viabilidade confirmada pela spike);
        # a orquestracao render->save e Fase 8.
        return VRAY_SO.exists() and VRAY_EXE.exists()

    def render(self, req: RenderRequest) -> RenderResult:
        raise NotImplementedError(
            "VRayFinalProvider: API mapeada (spike Fase 5), implementacao = Fase 8 "
            "(RenderSessionExport -> .vrscene -> vray.exe headless). Ver docstring + "
            "docs/spikes/render_and_asset_providers.md. Falta nailar context/start_render.")
