"""Validacao do plano do gabinete: viabilidade, envelope, colisao indevida e pose. Pura (sem SketchUp, sem I/O).

`validate_plan` NAO corrige nada: devolve achados com codigo estavel. A materializacao so pode seguir se
`ok` for verdadeiro (ver `plan.require_valid`).
"""
from __future__ import annotations

import itertools
import math

from .assembly import carcass_depth
from .model import Params

EPS = 1e-9                  # tolerancia numerica de ponto flutuante (m / m3), nao tolerancia de projeto


def _overlap_volume(a: dict, b: dict) -> float:
    vol = 1.0
    for k in range(3):
        lo, hi = max(a["min_m"][k], b["min_m"][k]), min(a["max_m"][k], b["max_m"][k])
        if hi - lo <= EPS:
            return 0.0
        vol *= hi - lo
    return vol


def validate_plan(parts: list[dict], p: Params) -> dict:
    findings: list[dict] = []

    def flag(code: str, detail: str) -> None:
        findings.append({"code": code, "detail": detail})

    # --- numeros: finitos e dimensoes positivas ---
    for part in parts:
        for v in part["min_m"] + part["max_m"] + part["size_m"]:
            if not math.isfinite(v):
                flag("NON_FINITE_GEOMETRY", part["id"])
                break
        if any(s <= EPS for s in part["size_m"]):
            flag("NON_POSITIVE_PART", f"{part['id']} size={part['size_m']}")
    # --- viabilidade da montagem (fisica, nao estetica) ---
    inner_w = p.width - 2 * p.side
    inner_h = p.height - 2 * p.top_bottom
    if inner_w <= EPS:
        flag("INFEASIBLE_INNER_WIDTH", f"width={p.width} nao comporta 2 laterais de {p.side}")
    if inner_h <= EPS:
        flag("INFEASIBLE_INNER_HEIGHT", f"height={p.height} nao comporta base+topo de {p.top_bottom}")
    if carcass_depth(p) - p.back <= EPS:
        flag("INFEASIBLE_DEPTH", f"depth={p.depth} nao comporta frente {p.front} + folga {p.front_clearance} + fundo {p.back}")
    n, r = p.fronts, p.front_reveal
    if (p.width - 2 * r - (n - 1) * r) / n <= EPS or p.height - 2 * r <= EPS:
        flag("INFEASIBLE_FRONT", "reveals consomem toda a largura/altura da frente")
    if p.shelf_count == 1:
        if p.shelf_z < p.top_bottom - EPS or p.shelf_z + p.shelf_t > p.height - p.top_bottom + EPS:
            flag("SHELF_OUT_OF_SPAN", f"prateleira z=[{p.shelf_z}, {p.shelf_z + p.shelf_t}] fora do vao [{p.top_bottom}, {p.height - p.top_bottom}]")
    # --- peca dentro do envelope declarado ---
    env_min, env_max = [0.0, 0.0, 0.0], [p.width, p.depth, p.height]
    for part in parts:
        if any(part["min_m"][k] < env_min[k] - EPS or part["max_m"][k] > env_max[k] + EPS for k in range(3)):
            flag("PART_OUTSIDE_ENVELOPE", part["id"])
    # --- colisao indevida: contato de face e permitido; volume em comum, nao ---
    for a, b in itertools.combinations(parts, 2):
        v = _overlap_volume(a, b)
        if v > EPS:
            flag("PART_COLLISION", f"{a['id']} x {b['id']} volume={v:.9f} m3")
    # --- pose ---
    for k in ("x", "y", "z", "rotation_deg"):
        if not math.isfinite(p.pose[k]):
            flag("NON_FINITE_POSE", k)
    # --- ids estaveis e unicos ---
    ids = [part["id"] for part in parts]
    if len(set(ids)) != len(ids):
        flag("DUPLICATE_PART_ID", "ids de peca repetidos")
    return {"ok": not findings, "findings": findings}
