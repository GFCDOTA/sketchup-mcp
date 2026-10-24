"""layout_preflight.py — pre-voo OBRIGATORIO do layout antes de materializar (FP-054 F1-03, R-04 / #381).

`collect_boxes` junta o que cada brain de comodo devolve; so a sala chama o gate de circulacao e ninguem roda a sobreposicao
antes do SketchUp. Este pre-voo roda, para cada comodo que recebeu movel:

  - `circulation_gate.gate` (corredor entre portais + cadeiras), com o contrato tipado da F1-01;
  - a sobreposicao movel-sobre-movel do comodo (`furniture_overlap_gate.pairwise_overlap`, mesmo nucleo do gate MCP);
  - interpenetracao ENTRE MODULOS no gemeo em caixas (`box_geometry`), baseline-aware: o limiar por modulo do `furniture_overlap`
    nao ve 3 cm de papeleira dentro do gabinete; aqui defeito OBJECTS NOVO ou PIOR que o registro (FP-055 P4) reprova (#502);
  - movel dentro de parede, sobre guarda-corpo/peitoril (FP-056 #434), no giro de porta e na VARREDURA REAL da folha (#500;
    o que ja esta em `docs/governance/known_gaps.json: door_sweep` e baseline conhecido, nao reprova de novo) (`room_collisions.audit`, o mesmo da regressao FP-047) — acrescentado depois que
    uma variante da Suite 01 (#381) punha o criado-mudo 1,8 dm2 dentro da parede e passava;

e agrega por `core.constraint_result.combine`. Quem materializa so segue com PASS ou NOT_APPLICABLE. Gate que quebra (excecao)
vira BLOCKED_MISSING_INPUT com o erro — achado, nunca omissao. Nenhum limiar e definido aqui.

Complexidade: O(R * (G + M^2)) por apartamento — R comodos mobiliados, G custo do gate de circulacao, M modulos do comodo
(o par-a-par da sobreposicao; ver R-12 da F0). Na planta_74: 8 comodos, <= 76 caixas por comodo.
"""
from __future__ import annotations

from core.constraint_result import combine

GATES = ("circulation", "furniture_overlap", "module_interpenetration", "room_collisions")


def planta74_twin(consensus_path) -> dict | None:
    """Contexto do gemeo para a planta_74 (unica com baseline registrado); None para outro consensus: nada medido, NOT_APPLICABLE."""
    import json
    from pathlib import Path

    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    if Path(consensus_path).resolve() != Path(PLANTA_74_CONSENSUS).resolve():
        return None
    root = Path(__file__).resolve().parents[2]
    base = json.loads((root / "artifacts/review/fp055/p4/defect_baseline.json").read_text("utf-8"))["defects"]
    from tools.validation import known_gaps
    return {"consensus_path": Path(PLANTA_74_CONSENSUS), "baseline": base, "borderline": set(known_gaps.load().get("twin_borderline", {}))}


def _interpenetration(twin_regression: dict, room_id: str) -> tuple[str, dict]:
    prefix = f"{room_id}|OBJECTS|"
    new = [d["key"] for d in twin_regression["new"] if d["key"].startswith(prefix)]
    worse = [d["key"] for d in twin_regression["worse"] if d["key"].startswith(prefix)]
    return ("FAIL", {"new": new, "worse": worse}) if new or worse else ("PASS", {})


def _circulation(con: dict, boxes: list[dict], room_id: str) -> tuple[str, dict]:
    from tools.validation import circulation_gate
    res = circulation_gate.gate(con, boxes, room_id)
    checks = sorted(res["checks"].items())
    blocking = {k: v.get("reason_code") for k, v in checks if v.get("result") in ("FAIL", "BLOCKED_MISSING_INPUT")}
    return res["result"], blocking or {k: v.get("reason_code") for k, v in checks if v.get("result") != "PASS"}


def _overlap(room_boxes: list[dict]) -> tuple[str, dict]:
    from tools.validation.furniture_overlap_gate import _module_geom, pairwise_overlap
    fails, warns, n_modules = pairwise_overlap(_module_geom(room_boxes))
    if n_modules < 2:                                  # sem par para comparar: nada medido nao e PASS
        return "NOT_APPLICABLE", {"modules": n_modules}
    if fails:
        return "FAIL", {"fails": fails}
    return ("WARN", {"warns": warns}) if warns else ("PASS", {})


def _collisions(audit: dict, room_name: str, n_boxes: int) -> tuple[str, dict]:
    if not n_boxes:                                    # nada no comodo para colidir: nada medido nao e PASS
        return "NOT_APPLICABLE", {"boxes": 0}
    data = audit.get(room_name) or {}
    walls = [f"{x['module']}/{x['label']} {x['area_cm2']} cm2" for x in data.get("wall_penetration", [])]
    swings = [f"{x['door']}:{x['module']}/{x['label']} {x['area_cm2']} cm2" for x in data.get("door_swing_hits", [])]
    barriers = [f"{x['barrier']}:{x['module']}/{x['label']} {x['area_cm2']} cm2" for x in data.get("barrier_penetration", [])]
    from tools.validation import known_gaps
    known = set(known_gaps.load().get("door_sweep", {}))
    sweeps = [x for x in data.get("door_sweep_hits", []) if f"{x['door']}|{x['module']}" not in known]
    sweep_txt = [f"{x['door']}:{x['module']}/{x['label']} {x['area_cm2']} cm2" for x in sweeps]
    if walls or swings or barriers or sweep_txt:
        return "FAIL", {"wall_penetration": walls, "door_swing_hits": swings, "barrier_penetration": barriers,
                        "door_sweep_hits": sweep_txt}
    return "PASS", {}


def preflight(con: dict, boxes: list[dict], rooms, twin: dict | None = None) -> dict:
    """rooms = resumo do `collect_boxes`: (room_id, nome, tipo, resultado, n_caixas). So comodos com caixas entram.
    `twin` (opcional, `planta74_twin`): liga a interpenetracao entre modulos contra o baseline; sem ele o gate e NOT_APPLICABLE."""
    import copy

    from tools.validation import room_collisions
    rows, blocking = [], []
    try:
        audit, audit_error = room_collisions.audit(con, copy.deepcopy(boxes)), None
    except Exception as exc:  # noqa: BLE001 — vira BLOCKED por comodo abaixo
        audit, audit_error = None, f"{type(exc).__name__}: {str(exc)[:160]}"
    twin_reg, twin_error = None, None
    if twin is not None:
        try:
            from tools.validation import box_geometry, defect_baseline
            reports = box_geometry.validate_boxes(con, copy.deepcopy(boxes), twin["consensus_path"])
            twin_reg = defect_baseline.regression(reports, twin["baseline"])
            twin_reg["new"] = [d for d in twin_reg["new"] if d["key"] not in twin.get("borderline", ())]
        except Exception as exc:  # noqa: BLE001 — gemeo quebrado e achado: BLOCKED por comodo
            twin_error = f"{type(exc).__name__}: {str(exc)[:160]}"
    for room_id, name, _type, _result, n_boxes in rooms:
        if not n_boxes:
            continue
        room_boxes = [b for b in boxes if b.get("room") == str(name or room_id)]
        def collisions(name=str(name or room_id)):
            if audit_error:
                raise RuntimeError(audit_error)
            return _collisions(audit, name, len(room_boxes))
        def interpenetration(room_id=room_id):
            if twin is None:
                return "NOT_APPLICABLE", {"twin": "sem baseline para este consensus"}
            if twin_error:
                raise RuntimeError(twin_error)
            return _interpenetration(twin_reg, room_id)
        for gate, run in (("circulation", lambda: _circulation(con, boxes, room_id)),
                          ("furniture_overlap", lambda: _overlap(room_boxes)),
                          ("module_interpenetration", interpenetration),
                          ("room_collisions", collisions)):
            try:
                status, reasons = run()
            except Exception as exc:  # noqa: BLE001 — gate quebrado e achado: bloqueia, nao some
                status, reasons = "BLOCKED_MISSING_INPUT", {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
            row = {"room_id": room_id, "gate": gate, "status": status, "reasons": reasons}
            rows.append(row)
            if status in ("FAIL", "BLOCKED_MISSING_INPUT"):
                blocking.append(row)
    return {"status": combine(r["status"] for r in rows), "rooms": rows, "blocking": blocking}


def allows_materialization(report: dict) -> bool:
    return report["status"] in ("PASS", "NOT_APPLICABLE")
