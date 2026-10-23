"""Politica do solver para a cozinha (FP-054 F2): a bancada e ANCORADA na parede da pia (ponto hidraulico do PDF). Nenhum grau
de liberdade — o solver so DIAGNOSTICA a cozinha (folga, alcance, gargalos). Mover a bancada mexeria no layout com prova L2
(`kitchen.layout.galley`) e na ancora do PDF: fora do escopo do solver.
"""
from __future__ import annotations

from tools.rooms.shared.spatial_solver.contracts import DegreesOfFreedom

POLICY_VERSION = "kitchen.solver_policy.v1"
ANCHOR_AND_DOF = {
    "kitchen_counter": ("HYDRAULIC_PDF", DegreesOfFreedom((0.0, 0.0), 0.02, False, "PROJECT_POLICY",
                                                          "ancora hidraulica do PDF (anchor_rules: PDF_WEST_WALL); L2 kitchen.layout.galley")),
}
