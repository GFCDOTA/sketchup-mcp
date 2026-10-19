"""Gabinete parametrico compartilhado (FP-043/P6a): plano L1 de caixaria retangular + frentes lisas separadas.

API publica: `plan_cabinet`, `require_valid`, `PlanRefused`, `CabinetInputError`, `footprint_world`. Nao ha
ferragem, gaveta, porta Shaker, recorte de bancada, lista de corte nem certificacao de fabricacao (nao incluidos).
"""
from .model import CabinetInputError, parse_request  # noqa: F401
from .plan import (CAPABILITY_ID, CAPABILITY_VERSION, PlanRefused, footprint_world, plan_cabinet,  # noqa: F401
                   require_valid, signature_of_plan, to_world_xy)
