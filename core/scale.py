"""core/scale.py — FONTE ÚNICA de escala PDF↔mundo do app.

Regra (Felipe 2026-06-08): **ninguém mais define `PT_TO_M` / `PT_TO_IN` localmente.**
Toda conversão de escala vem daqui. O `repo_health_gate` proíbe novas definições
fora deste arquivo.

Eixos:
- `pdf-points` (pt): unidade do consensus/PDF.
- `metros` (m): mundo real.
- `polegadas` (in): unidade interna do SketchUp.

Constantes:
- `PT_TO_M`  pt → m. **Override por env `PT_TO_M`** (anchor do PDF; planta_74 = 0.0259).
             Default = ancoragem por wall-thickness `0.19/5.4` (≈0.0352) — NÃO mudar o default
             cegamente; o 0.0259 entra via env/config, não hardcoded espalhado.
- `M_TO_IN`  m → in (constante FÍSICA, scale-independente; nunca muda).
- `PT_TO_IN` pt → in = `PT_TO_M * M_TO_IN`.

Helpers: `M(m)`/`to_pt(m)` (m→pt), `to_m(pt)` (pt→m), `to_in(pt)` (pt→in), `m_to_in(m)` (m→in).

Nota de ordem-de-import: `PT_TO_M` é lido do env no IMPORT deste módulo. Quem precisa de
0.0259 deve setar `PT_TO_M=0.0259` ANTES do primeiro import de `core.scale` (convenção do
build planta_74). Mesma semântica que o código já usava — drop-in.
"""
from __future__ import annotations

import os

# constante física m→in (nunca muda com a escala)
M_TO_IN: float = 39.3700787402

# default = ancoragem por espessura de parede (wall_thickness 0.19 m / 5.4 pt)
_DEFAULT_PT_TO_M: float = 0.19 / 5.4

# pt → m (ÚNICO ponto de leitura do env; default não muda sem env/config)
PT_TO_M: float = float(os.environ.get("PT_TO_M") or _DEFAULT_PT_TO_M)

# pt → in (derivado; não definir em lugar nenhum além daqui)
PT_TO_IN: float = PT_TO_M * M_TO_IN


# ---- verified per-plant scale (cota-anchored) ------------------------
# Some plants have a real-world scale verified against the PDF's printed
# cotas, which beats the wall-thickness default above. planta_74: SUITE 01's
# cota is 5.45 x 4.00 m and its consensus room polygon is 210.70 x 154.43 pt
# (5.45/210.70=0.02587, 4.00/154.43=0.02590 — two axes agreeing to 0.14%);
# the wall-thickness default inflated the flat ~1.36x (bbox 186 m² for a
# 74 m² unit). Builders call resolve_plant_pt_to_m() and set the PT_TO_M env
# BEFORE the (sub)process that imports core.scale, so the value still flows
# through the single PT_TO_M above — no second source of truth. Explicit env
# always wins; plants absent here keep the default.
PLANT_PT_TO_M: dict[str, float] = {
    "planta_74": 0.0259,
}


def plant_from_fixture_path(consensus_path) -> str | None:
    """Plant name iff the path lives under ``fixtures/<plant>/``, else None."""
    from pathlib import Path
    parts = Path(consensus_path).resolve().parts
    if "fixtures" in parts:
        i = parts.index("fixtures")
        if i + 1 < len(parts):
            return parts[i + 1]
    return None


def resolve_plant_pt_to_m(consensus_path, env: dict | None = None) -> str | None:
    """PT_TO_M string to inject for a plant build, or None to keep the default.

    An explicit ``env['PT_TO_M']`` is never overridden (caller intent wins).
    Otherwise, if the plant inferred from the fixtures path has a verified
    scale in ``PLANT_PT_TO_M``, return it as a string for the consumer (Ruby
    exporter / furnish subprocess) to set as ``ENV['PT_TO_M']`` before it
    imports core.scale.
    """
    env = os.environ if env is None else env
    if env.get("PT_TO_M"):
        return None
    plant = plant_from_fixture_path(consensus_path)
    val = PLANT_PT_TO_M.get(plant) if plant else None
    return None if val is None else str(val)


def to_pt(m: float) -> float:
    """metros → pdf-points."""
    return m / PT_TO_M


def M(m: float) -> float:
    """metros → pdf-points (alias histórico de to_pt; usado pelos layouts)."""
    return m / PT_TO_M


def to_m(pt: float) -> float:
    """pdf-points → metros."""
    return pt * PT_TO_M


def to_in(pt: float) -> float:
    """pdf-points → polegadas (SketchUp)."""
    return pt * PT_TO_IN


def m_to_in(m: float) -> float:
    """metros → polegadas (constante física; independe da escala do PDF)."""
    return m * M_TO_IN
