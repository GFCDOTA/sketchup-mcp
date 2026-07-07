"""variant_axes.py — FP-034: declaracao TIPADA dos 3 eixos do variant sweep
(estilo x tema x layout) + a celula `Variant` com id deterministico.

Fontes dos eixos sao o codigo/dados VIVOS (nada duplicado a mao):
  - estilo: style_spec.STYLE_TOKENS (+ None = baseline neutro);
  - tema:   presets em artifacts/reference_lab/themes/*.json, com o vocabulario
    de tokens KITCHEN_THEME do consumidor real (batch_theme_render.THEMES) como
    fallback — hoje so 1 dos 4 presets carrega `kitchen_theme_env` machine-
    readable (ver theme_axis);
  - layout: layout_seed inteiro (0 = brain default; k>=1 = k-esimo template
    VALIDO do layout_candidates — a mecanica vive em tools/variant_sweep.py).

Modulo leve: stdlib + style_spec/batch_theme_render em import lazy. Sem clock,
sem random — mesmo input => mesmos eixos, mesmos ids.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEMES_DIR = ROOT / "artifacts/reference_lab/themes"

# token de env valido (KITCHEN_THEME): identificador minusculo, sem espaco/acento
_TOKEN_RE = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class Variant:
    """Uma celula do sweep. variant_id e' funcao pura dos params (estavel)."""
    plant: str
    style: str | None
    theme: str
    layout_seed: int

    @property
    def variant_id(self) -> str:
        return (f"{self.plant}__{self.style or 'baseline'}__"
                f"{self.theme or 'warm_compact'}__L{self.layout_seed}")


def style_axis() -> list[str | None]:
    """[None] + STYLE_TOKENS ordenados. None = baseline (FURNISH_STYLE vazio)."""
    from tools.style_spec import STYLE_TOKENS
    return [None] + sorted(STYLE_TOKENS)


def theme_axis(themes_dir: Path = THEMES_DIR) -> list[str]:
    """Tokens KITCHEN_THEME dos presets, '' (warm_compact default) primeiro.

    DESVIO documentado da spec: dos 4 presets em themes/*.json, so o
    BLACK_WOOD_GOLD carrega `kitchen_theme_env` como token valido; o
    WARM_COMPACT traz texto descritivo ("(vazio ...)") e os outros 2 nao tem a
    chave. Preset sem token cai no vocabulario do consumidor real
    (batch_theme_render.THEMES, os valores que o path V-Ray de fato le) via
    match do theme_id; sem match -> '' (default). Nenhum valor e' inventado.
    """
    from tools.batch_theme_render import THEMES as _consumer_themes
    vocab = [t["theme"] for t in _consumer_themes if t.get("theme")]
    tokens: set[str] = set()
    for p in sorted(Path(themes_dir).glob("*.json")):
        try:
            d = json.loads(p.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        env = d.get("kitchen_theme_env")
        if isinstance(env, str) and _TOKEN_RE.match(env):
            tokens.add(env)
            continue
        tid = str(d.get("theme_id") or p.stem).lower()
        tokens.add(next((v for v in vocab if v in tid), ""))
    return [""] + sorted(t for t in tokens if t)


def layout_axis() -> list[int]:
    """Seeds de layout: 0 = brain default (plan_living via collect_boxes);
    k>=1 = substitui o living pelo k-esimo template VALIDO do
    layout_candidates.run (ranking deterministico; placeholders chapados —
    perturbacao real suportada hoje, nao os moveis golden compostos)."""
    return [0, 1, 2]


def default_axes() -> dict:
    """Eixos default na ordem canonica do grid (style, theme, layout).
    Funcao (nao constante congelada) pra permitir injecao em teste."""
    return {"style": style_axis(), "theme": theme_axis(), "layout": layout_axis()}
