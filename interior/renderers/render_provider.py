"""render_provider.py — Interior RenderProvider abstraction (Fase 4). Interface comum
p/ renderizar um layout/movel num .skp + PNGs, SEM acoplar o codigo a um renderizador
especifico. Hoje so o SketchUpBasicProvider e funcional; Enscape/V-Ray sao stubs
documentados (Fase 5 spike decide se/como automatizar).

Contrato: RenderRequest (boxes/skp + camera/render_type + saidas) -> RenderResult
(status success/fail/skipped + paths + timing + base_intact + log). Determinismo do
artefato canonico: a base .skp NUNCA e mutada (build numa COPIA; hash conferido)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# tipos de render suportados (camera preset)
RENDER_TYPES = ("top", "iso", "front", "closeup", "perspective")


@dataclass
class RenderRequest:
    """Pedido de render. `boxes` = layout (lista de boxes do place_layout/build_furniture);
    se None, usa um .skp ja pronto em `in_skp`. `renderer` escolhe o .rb: 'layout' (shell
    da planta, place_layout_skp.rb) ou 'furniture' (movel standalone, build_furniture_skp.rb)."""
    boxes: list | None
    out_skp: str                       # onde salvar o .skp gerado
    renders: dict = field(default_factory=dict)   # render_type -> output PNG path
    renderer: str = "layout"           # 'layout' | 'furniture'
    zoom_group: bool = False           # enquadrar so o grupo de moveis (LAYOUT_ZOOM_GROUP)
    base_skp: str | None = None        # shell a copiar (nunca mutado); default = planta_74 base
    in_skp: str | None = None          # .skp pronto (quando boxes=None) — futuro
    label: str = "render"


@dataclass
class RenderResult:
    status: str                        # success | fail | skipped
    provider: str
    skp: str | None = None
    renders: dict = field(default_factory=dict)   # render_type -> path (existente)
    timing_s: float = 0.0
    base_intact: bool = True
    log: str = ""
    error: str = ""

    def ok(self):
        return self.status == "success"


class RenderProvider(ABC):
    """Interface de renderizador. Implementacoes: SketchUpBasic (funcional), Enscape/V-Ray (stubs)."""

    name: str = "abstract"

    @abstractmethod
    def available(self) -> bool:
        """O renderizador esta instalado/automatizavel neste ambiente?"""

    @abstractmethod
    def render(self, req: RenderRequest) -> RenderResult:
        """Materializa o .skp + PNGs. NUNCA muta a base (build numa copia, confere hash)."""

    def skipped(self, req: RenderRequest, why: str) -> RenderResult:
        return RenderResult(status="skipped", provider=self.name, error=why)
