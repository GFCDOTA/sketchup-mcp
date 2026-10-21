"""Porta Shaker parametrica (FP-046/P1-P2): moldura (2 montantes + 2 travessas) e painel central realmente recuado.

Plano PURO (L1): `plan_shaker_door(request, parent_plan)` -> `shaker_door_plan.v1` ou recusa tipada. Nunca abre
SketchUp, nunca escreve arquivo e nao autoriza execucao. O plano do gabinete pai (`cabinet_assembly_plan.v1`) e o
materializador de frentes lisas NAO mudam (ADR-046-01: esquema proprio, sem converter o plano antigo).
Fora do escopo: gaveta, ferragem, corredica, veneziana, UV/veio (permanece NOT_SUPPORTED), plano de corte.
"""
from .model import GRAIN_SUPPORT, SCHEMA_REQUEST, ShakerParams, parse_shaker_request  # noqa: F401
from .plan import (  # noqa: F401
                   CAPABILITY_ID,
                   CAPABILITY_VERSION,
                   SCHEMA_PLAN,
                   ShakerPlanRefused,
                   plan_shaker_door,
                   require_valid_shaker,
)
