"""Registro de defeitos do apartamento construido e gate de NAO REGRESSAO (FP-055 P4 -> FP-056).

O registro (baseline) vem da geometria BRUTA do apartamento ORIGINAL (inspect_geometry) validada por
`built_geometry.validate_room` (v2). Cada defeito tem chave estavel (comodo, cheque, peca/porta), medida e causa-raiz:
  R1  peca dentro da massa de parede, sobre a laje que entra sob a parede (D-007, FP-043 P3a-03)
  R2a peca atravessa barreira de varanda / guarda-corpo (SoftBarrier) que nao limita a area de mobiliar
  R2b peca sobre regiao sem laje e sem parede construida
  R2  fora do poligono efetivo do comodo, sem outra causa identificada (investigar)
  R3  peca dentro de outra peca (composicao sem contrato de vizinhanca)
  R5  porta: a folha construida nao abre 90 graus (obstaculo na faixa de Z da folha)
As causas sao atribuidas por regras geometricas explicitas sobre o construido, nunca por nome de peca.

Gate (`regression`): defeito NOVO (chave fora do registro) ou PIOR (medida > registrada + 2 x RES_M) = FAIL; defeito que
sumiu = resolvido. O registro nunca e editado para aceitar defeito novo: muda so por correcao comprovada (FP-056).
"""
from __future__ import annotations

from typing import Any

from tools.validation import built_geometry as bg
from tools.validation.penetration import RES_M

WORSE_TOL_M = 2 * RES_M


def key(room_id: str, f: dict) -> str:
    who = f.get("door") or "+".join(f.get("modules") or []) or f.get("module") or "?"
    return f"{room_id}|{f['check']}|{who}"


def measure(f: dict) -> float:
    if f["check"] == "DOOR":
        return round(f.get("required_deg", 90.0) - f.get("max_open_deg", 0.0), 3)       # graus que faltam
    return float(f.get("outside_depth_m") or f.get("depth_m") or 0.0)


def _root_cause(idx: dict, room_id: str, room: str, f: dict) -> dict:
    if f["check"] == "OBJECTS":
        return {"cause": "R3"}
    if f["check"] == "DOOR":
        return {"cause": "R5", "blocked_by": f.get("blocked_by")}
    walls, floor, slab = bg.built_walls(idx), bg.room_floor(idx, room_id), bg.room_slab(idx, room_id)
    soft = {n: bg.footprint(g, zmax_m=None) for n, g in idx.items() if n.startswith("SoftBarrier")}
    g = bg.module_groups(idx, room).get(f["module"])
    fps = [p[0] for p in bg.parts(g)] if g else []
    out = None
    for fp in fps:
        o = fp.difference(floor) if floor is not None else fp
        out = o if out is None else out.union(o)
    if out is None or out.is_empty:
        return {"cause": "R2"}
    crossed = sorted(n for n, s in soft.items() if s is not None and any(fp.intersects(s) and fp.intersection(s).area > 1e-6
                                                                            for fp in fps))
    if crossed:
        return {"cause": "R2a", "barriers": crossed}
    in_wall = walls is not None and out.intersection(walls).area > 0.5 * out.area
    on_slab = slab is not None and out.intersection(slab).area > 0.5 * out.area
    if in_wall and on_slab:
        return {"cause": "R1"}
    others = [rid for rid in (n[len("Floor_Group_"):] for n in idx if n.startswith("Floor_Group_")) if rid != room_id]
    covered = (walls.intersection(out).area if walls is not None else 0.0) + sum(
        (bg.room_slab(idx, r).intersection(out).area if bg.room_slab(idx, r) is not None else 0.0) for r in [room_id, *others])
    if covered < 0.5 * out.area:
        return {"cause": "R2b"}
    return {"cause": "R2"}


def build_baseline(idx: dict, rooms: dict[str, str], doors: dict) -> list[dict]:
    rows = []
    for rid, name in rooms.items():
        rep = bg.validate_room(idx, rid, name, doors=doors)
        for f in rep["findings"]:
            if f.get("check") in ("CONTAINMENT", "WALL", "OBJECTS", "DOOR") and (f.get("module") or f.get("modules")
                                                                                or f.get("door")):
                rows.append({"key": key(rid, f), "room_id": rid, "room": name, "check": f["check"], "measure": measure(f),
                             "unit": "deg" if f["check"] == "DOOR" else "m", **_root_cause(idx, rid, name, f),
                             "finding": {k: v for k, v in f.items() if k not in ("regions",)}})
    return sorted(rows, key=lambda r: r["key"])


def program_baseline(idx: dict, rooms: dict[str, str]) -> dict[str, list[str]]:
    """Modulos construidos por comodo no apartamento ORIGINAL (o programa que uma geracao nova nao pode perder calada)."""
    return {rid: sorted(bg.module_groups(idx, name)) for rid, name in rooms.items()}


def regression(reports: dict[str, dict], baseline: list[dict], program: dict[str, list[str]] | None = None,
               accepted_omissions: dict[str, str] | None = None) -> dict[str, Any]:
    """`reports`: {room_id: validate_room(...)} da geracao nova. So os comodos presentes em `reports` sao comparados.
    `program`: modulos do original por comodo; modulo que SUMIU reprova (comodo esvaziado nao conta como "resolvido"),
    salvo se estiver em `accepted_omissions` ({"rid|PROGRAM|modulo": motivo}) - omissao so por decisao registrada."""
    base = {b["key"]: b for b in baseline}
    rooms = set(reports)
    new, worse, seen = [], [], set()
    for rid, rep in reports.items():
        for f in rep["findings"]:
            if f.get("check") not in ("CONTAINMENT", "WALL", "OBJECTS", "DOOR") or not (f.get("module") or f.get("modules")
                                                                                      or f.get("door")):
                continue
            k, m = key(rid, f), measure(f)
            seen.add(k)
            b = base.get(k)
            if b is None:
                new.append({"key": k, "measure": m})
            elif m > b["measure"] + (0.5 if b["unit"] == "deg" else WORSE_TOL_M):
                worse.append({"key": k, "measure": m, "baseline": b["measure"]})
    missing, accepted = [], []
    for rid in rooms:
        have = set(reports[rid].get("modules") or [])
        for m in (program or {}).get(rid, []):
            if m not in have:
                k = f"{rid}|PROGRAM|{m}"
                (accepted if k in (accepted_omissions or {}) else missing).append(k)
    present = {rid: set(reports[rid].get("modules") or []) for rid in rooms}

    def _still_there(b):            # defeito "resolvido" so se as pecas dele continuam no comodo (nao por sumico)
        f = b.get("finding", {})
        mods = f.get("modules") or ([f["module"]] if f.get("module") else [])
        return all(m in present[b["room_id"]] for m in mods)
    resolved = sorted(k for k, b in base.items() if b["room_id"] in rooms and k not in seen and _still_there(b))
    vanished = sorted(k for k, b in base.items() if b["room_id"] in rooms and k not in seen and not _still_there(b))
    return {"status": "FAIL" if new or worse or missing else "PASS", "new": new, "worse": worse, "resolved": resolved,
            "vanished_with_piece": vanished, "missing_program": missing, "accepted_omissions": accepted,
            "compared_rooms": sorted(rooms), "worse_tol_m": WORSE_TOL_M}
