"""Validacao da submontagem Shaker: viabilidade, recuo REAL por coordenada, contato sem volume e envelope. Pura."""
from __future__ import annotations

import itertools
import math

from ..validation import EPS, _overlap_volume
from .model import ShakerParams


def validate_shaker(parts: list[dict], p: ShakerParams, front: dict) -> dict:
    """`front` e a peca de frente lisa do gabinete pai que a Shaker substitui (define o envelope)."""
    findings: list[dict] = []

    def flag(code: str, detail: str) -> None:
        findings.append({"code": code, "detail": detail})

    for part in parts:
        if any(not math.isfinite(v) for v in part["min_m"] + part["max_m"] + part["size_m"]):
            flag("NON_FINITE_GEOMETRY", part["id"])
        elif any(s <= EPS for s in part["size_m"]):
            flag("NON_POSITIVE_PART", f"{part['id']} size={part['size_m']}")
    ids = [x["id"] for x in parts]
    if len(set(ids)) != len(ids):
        flag("DUPLICATE_PART_ID", "ids de peca repetidos")
    if len(parts) != 5:
        flag("WRONG_PART_COUNT", f"esperado 2 montantes + 2 travessas + 1 painel, veio {len(parts)}")
    lo, hi = front["min_m"], front["max_m"]
    for part in parts:
        if any(part["min_m"][k] < lo[k] - EPS or part["max_m"][k] > hi[k] + EPS for k in range(3)):
            flag("PART_OUTSIDE_FRONT_ENVELOPE", part["id"])
    for a, b in itertools.combinations(parts, 2):
        v = _overlap_volume(a, b)
        if v > EPS:
            flag("PART_COLLISION", f"{a['id']} x {b['id']} volume={v:.9f} m3")
    panel = next((x for x in parts if x["name"] == "recessed_panel"), None)
    frame_fronts = [x["max_m"][1] for x in parts if x["role"] == "frame"]
    if panel is not None and frame_fronts:
        if abs((hi[1] - panel["max_m"][1]) - p.recess) > EPS:
            flag("PANEL_RECESS_MISMATCH", f"recuo medido {hi[1] - panel['max_m'][1]:.9f} m != pedido {p.recess:.9f} m")
        if p.recess > EPS and not panel["max_m"][1] < min(frame_fronts) - EPS:
            flag("PANEL_NOT_BEHIND_FRAME", "face visivel do painel nao esta atras da face frontal da moldura")
        if panel["min_m"][1] < lo[1] - EPS:
            flag("PANEL_BEHIND_FRAME_BACK", "painel ultrapassa a face traseira da moldura")
    return {"ok": not findings, "findings": findings}
