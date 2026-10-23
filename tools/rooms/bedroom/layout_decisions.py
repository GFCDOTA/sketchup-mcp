"""Decisoes de layout de quarto tomadas pelo Felipe (origem `user_request`), aplicadas sobre o plano do `bedroom_designer`.

Medida que o pedido nao trouxe nao vira geometria: o designer propoe; quando a proposta reprova um gate e a saida muda o
programa do comodo, a escolha e do Felipe e fica registrada AQUI, com a medida, a unidade, a origem e a issue — nunca como
ajuste solto dentro do algoritmo. Cada decisao vale para UMA planta (`consensus.source`) e UM comodo.

Decisoes:
  suite01-circulation-2026-10-23 (#381): na Suite 01 da planta_74 a cadeira da escrivaninha fechava a passagem entre a porta
  do quarto e a da suite (corredor mobiliado 0,00 m; sem a cadeira 0,89 m para alvo 0,90). A 1a escolha (cama + criados-mudos
  2 in para cima) invadia a parede norte (o criado-mudo de cima ja encosta nela) e foi recusada com as medidas; a escolha final
  do Felipe no chat: tirar a cadeira e subir SO o criado-mudo de baixo (`criado_mudo_dir`, modulo "Criado-mudo 1") 1 in na
  planta (-y) -> corredor 0,91 m, 1,5 cm da cama, nada na parede.
"""
from __future__ import annotations

from shapely import affinity

DECISIONS: tuple[dict, ...] = (
    {"id": "suite01-circulation-2026-10-23", "plant": "planta_74", "room_id": "r000", "issue": "#381",
     "origin": "user_request", "decided": "2026-10-23",
     "drop_types": ["desk_chair"],
     "shift": {"names": ["criado_mudo_dir"], "dy": {"value": -1.0, "unit": "in", "origin": "user_request"}}},
)
_GEOMETRY_KEYS = ("box", "visual_footprint")


def _plant(con: dict) -> str:
    return str(con.get("source") or "").rsplit(".", 1)[0]


def decisions_for(con: dict, room_id: str) -> list[dict]:
    plant = _plant(con)
    return [d for d in DECISIONS if d["plant"] == plant and d["room_id"] == room_id]


def apply(con: dict, room_id: str, items: list[dict]) -> tuple[list[dict], list[dict]]:
    """(itens com as decisoes aplicadas, decisoes aplicadas). Nao muta a lista nem os itens de entrada."""
    from core.scale import PT_TO_IN
    applied = []
    for d in decisions_for(con, room_id):
        shift = d["shift"]
        if shift["dy"]["unit"] != "in":
            raise ValueError(f"{d['id']}: unidade nao suportada {shift['dy']['unit']!r}")
        dy_pt = shift["dy"]["value"] / PT_TO_IN
        out = []
        for it in items:
            if it.get("type") in d["drop_types"]:
                continue
            if it.get("name") in shift["names"]:
                it = {**it, **{k: affinity.translate(it[k], 0.0, dy_pt) for k in _GEOMETRY_KEYS if k in it}}
            out.append(it)
        items = out
        applied.append({"id": d["id"], "issue": d["issue"], "origin": d["origin"]})
    return items, applied
