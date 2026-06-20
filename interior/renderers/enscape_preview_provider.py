"""enscape_preview_provider.py — STUB documentado (Fase 4). Enscape e candidato a PREVIEW
visual rapido (layout/escala/composicao/iluminacao basica — "parece um quarto real?"),
NAO acabamento premium (isso e V-Ray, Fase 8).

NAO IMPLEMENTADO: a viabilidade de automacao depende da SPIKE da Fase 5. Perguntas abertas
(a spike responde honestamente, sem inventar API):
  - Enscape tem CLI / Ruby command confiavel p/ renderizar SEM UI?
  - da p/ escolher camera/preset e salvar PNG automaticamente (batch)?
  - onde ficam os outputs? quais limitacoes (licenca, foco de janela, GPU)?
Recomendacao provavel ate a spike: PREVIEW manual OU adapter via Ruby se houver comando.
"""
from __future__ import annotations

from interior.renderers.render_provider import RenderProvider, RenderRequest, RenderResult


class EnscapePreviewProvider(RenderProvider):
    name = "enscape_preview"

    def available(self) -> bool:
        return False   # ate a spike da Fase 5 provar automacao

    def render(self, req: RenderRequest) -> RenderResult:
        raise NotImplementedError(
            "EnscapePreviewProvider e stub — automacao depende da spike da Fase 5 "
            "(docs/spikes/render_and_asset_providers.md). Nao inventar API.")
