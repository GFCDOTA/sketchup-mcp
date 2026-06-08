"""vray_final_provider.py — STUB documentado (Fase 4). V-Ray e o renderizador FINAL/premium
(tecido convincente, madeira, luz indireta, sombras realistas, camera de apresentacao) —
so quando layout + anatomia + preview ja passaram (Fase 8).

NAO IMPLEMENTADO: viabilidade depende da SPIKE da Fase 5. Perguntas abertas (a spike
responde sem inventar API):
  - V-Ray p/ SketchUp tem render command / headless / Ruby API?
  - da p/ aplicar materials + render settings via script e renderizar em lote?
  - da p/ exportar a cena? quais limitacoes (licenca, GPU, tempo, UI obrigatoria)?
Recomendacao provavel ate a spike: render FINAL manual; integracao so se a spike provar headless.
"""
from __future__ import annotations

from interior.renderers.render_provider import RenderProvider, RenderRequest, RenderResult


class VRayFinalProvider(RenderProvider):
    name = "vray_final"

    def available(self) -> bool:
        return False   # ate a spike da Fase 5 provar automacao

    def render(self, req: RenderRequest) -> RenderResult:
        raise NotImplementedError(
            "VRayFinalProvider e stub — automacao depende da spike da Fase 5 "
            "(docs/spikes/render_and_asset_providers.md). Nao inventar API.")
