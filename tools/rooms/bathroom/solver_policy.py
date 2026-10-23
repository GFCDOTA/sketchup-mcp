"""Politica do solver para o banheiro (FP-054 F2): ancoras e graus de liberdade que o ESPECIALISTA do banheiro permite.

O solver compartilhado so enumera o que esta declarado aqui. Valores sao decisao de projeto PROPOSTA (nao norma): deslizar a
louca ao longo da parede em que o builder a apoiou (mantem a parede de apoio e, portanto, o ponto de esgoto/agua daquela parede)
e girar o box em torno do proprio centro (0/90/180/270 graus) para a porta dar para um lado livre (a frente que o builder escolhe
pela coordenada da porta do comodo pode cair contra a parede — Banho 02). Trocar de parede ou mover o box exige decisao do
Felipe — fora.
"""
from __future__ import annotations

from tools.rooms.shared.spatial_solver.contracts import DegreesOfFreedom

_SRC = "FP-054 F2 — proposta de graus de liberdade do banheiro (2026-10-23), PENDING_FELIPE"

POLICY_VERSION = "bathroom.solver_policy.v1"
ANCHOR_AND_DOF = {
    "toilet": ("WALL_BACKED", DegreesOfFreedom((-0.40, 0.40), 0.02, False, "PROJECT_POLICY", _SRC)),
    "lavatory": ("WALL_BACKED", DegreesOfFreedom((-0.40, 0.40), 0.02, False, "PROJECT_POLICY", _SRC)),
    "shower": ("CORNER", DegreesOfFreedom((0.0, 0.0), 0.02, False, "PROJECT_POLICY", _SRC, (0, 90, 180, 270))),
}
