"""FP-047/F2: snapshot e diff semantico de caixas por comodo/peca (L1 puro, sem SketchUp, sem gerar geometria).

`fp044_baseline` compara SAIDA IDENTICA (hash por comodo): serve para refatoracao, nao diz O QUE mudou. Aqui cada caixa
de `collect_boxes` vira uma peca com identidade estavel e o diff diz quais EFEITOS ocorreram (position/size/material/
intent/tag/added/removed). `compare` cruza o diff com o contrato (`room_regression_request.v1`):

- strict_identity: qualquer delta = FAIL (BASELINE_MISMATCH, R-02);
- scoped_change: todo delta precisa casar comodo + peca (`module`) + efeito da allowlist. Comodo fora = UNAUTHORIZED_ROOM_DELTA
  (R-05), peca fora = UNAUTHORIZED_PART_DELTA (R-06), efeito fora = UNAUTHORIZED_EFFECT_DELTA. Comodo de controle nunca muda.

Identidade: `(room, module, label|kind)` NAO e unica (planta_74: 402 caixas, 254 chaves), entao pecas do mesmo grupo
primeiro se pareiam por digest identico (reordenar e inofensivo) e so o resto pareia por ordem de ocorrencia.

Tolerancia: `COORD_EPS_IN` e ruido de ponto flutuante (1e-6 pol = 2,5e-8 m), ordens de grandeza abaixo de qualquer mudanca
real (o D-007 e ~1,8 pol). NAO e tolerancia de aceite; a politica definitiva e a ADR-047-02.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from tools.validation import room_regression as rr

SNAPSHOT_SCHEMA = "room_snapshot.v1"
COORD_EPS_IN = 1e-6
APPEARANCE_EFFECTS = frozenset({"position", "size", "material", "intent", "added", "removed"})
PLACEMENT = ("x0", "y0", "x1", "y1", "corners", "z0_in", "h_in")
MATERIAL = ("rgb", "mat_name", "tex_png", "tile_in", "alpha")
SHAPE = ("profile_world", "extrude_vec", "smooth")
INTENT = ("geometry_intent", "interaction_policy", "shape_policy", "host")
IDENTITY = ("room", "module", "label", "kind")

# codigos de delta nao autorizado (PROPOSTOS na SPEC ate o schema; aqui sao os valores do relatorio)
BASELINE_MISMATCH = "BASELINE_MISMATCH"
UNAUTHORIZED_ROOM_DELTA = "UNAUTHORIZED_ROOM_DELTA"
UNAUTHORIZED_PART_DELTA = "UNAUTHORIZED_PART_DELTA"
UNAUTHORIZED_EFFECT_DELTA = "UNAUTHORIZED_EFFECT_DELTA"


def _norm(v: Any) -> Any:
    """JSON canonico: floats viram str(float) estavel; listas/dicts recursivos; nada de arredondar mudanca real."""
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in sorted(v.items())}
    return v


def _digest(box: dict) -> str:
    return hashlib.sha256(json.dumps(_norm(box), sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


def part_group(box: dict) -> tuple[str, str, str]:
    return (str(box.get("room")), str(box.get("module")), str(box.get("label") or box.get("kind")))


def snapshot(boxes: list[dict], *, fixture: str, pt_to_m: float, source_digests: dict | None = None) -> dict:
    """Snapshot deterministico: pecas em ordem de entrada, com grupo, ocorrencia e digest; nunca depende de PID/data."""
    seen: dict[tuple, int] = defaultdict(int)
    parts = []
    for box in boxes:
        group = part_group(box)
        occ = seen[group]
        seen[group] += 1
        parts.append({"id": "|".join(group) + f"#{occ}", "group": list(group), "occurrence": occ,
                      "digest": _digest(box), "box": json.loads(json.dumps(box, default=str))})
    ambiguous = sum(1 for n in seen.values() if n > 1)
    body = {"schema_version": SNAPSHOT_SCHEMA, "fixture": fixture, "pt_to_m": pt_to_m,
            "rooms": sorted({g[0] for g in seen}), "part_count": len(parts), "ambiguous_groups": ambiguous,
            "source_digests": dict(sorted((source_digests or {}).items())), "parts": parts}
    body["snapshot_sha256"] = hashlib.sha256(
        json.dumps(_norm({k: v for k, v in body.items() if k != "parts"}) | {"digests": [p["digest"] for p in parts]},
                   sort_keys=True).encode("utf-8")).hexdigest()
    return body


def _close(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) <= COORD_EPS_IN
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    return a == b


def _dims(box: dict) -> tuple[float, float, float]:
    return (float(box["x1"]) - float(box["x0"]), float(box["y1"]) - float(box["y0"]), float(box.get("h_in") or 0.0))


def _center(box: dict) -> tuple[float, float, float]:
    return ((float(box["x0"]) + float(box["x1"])) / 2, (float(box["y0"]) + float(box["y1"])) / 2, float(box.get("z0_in") or 0.0))


def classify(before: dict, after: dict) -> tuple[list[str], list[str]]:
    """(efeitos, campos) de uma peca modificada. Mesma bbox com material/intent/tag diferentes AINDA e delta (R-15)."""
    before, after = {"z0_in": 0.0, **before}, {"z0_in": 0.0, **after}     # ausente == 0.0 (400 de 402 caixas trazem z0_in)
    keys = sorted(set(before) | set(after))
    changed = [k for k in keys if not _close(before.get(k), after.get(k))]
    effects: set[str] = set()
    if all(k in before and k in after for k in ("x0", "y0", "x1", "y1")):
        if not _close(_center(before), _center(after)):
            effects.add("position")
        if not _close(_dims(before), _dims(after)):
            effects.add("size")
    elif any(k in changed for k in ("x0", "y0", "x1", "y1")):
        effects.update({"position", "size"})
    if "z0_in" in changed and "position" not in effects:
        effects.add("position")
    for k in changed:
        if k in MATERIAL:
            effects.add("material")
        elif k in INTENT:
            effects.add("intent")
        elif k in SHAPE or (k in ("corners", "h_in") and "size" not in effects and "position" not in effects):
            effects.add("size")
        elif k in PLACEMENT:
            pass                                      # ja coberto por centro/dimensao acima
        else:
            effects.add("tag")                        # label/kind/decorative/ambiguous/product/desconhecido: conservador
    return sorted(effects), changed


def diff(before: dict, after: dict) -> list[dict]:
    """Deltas ordenados e deterministicos entre dois snapshots (mesmo `fixture` e `pt_to_m`, senao ValueError)."""
    for k in ("schema_version", "fixture", "pt_to_m"):
        if before.get(k) != after.get(k):
            raise ValueError(f"snapshots incomparaveis: {k} {before.get(k)!r} != {after.get(k)!r} (escalas nao se misturam, R-29)")
    groups: dict[tuple, dict[str, list]] = defaultdict(lambda: {"b": [], "a": []})
    for p in before["parts"]:
        groups[tuple(p["group"])]["b"].append(p)
    for p in after["parts"]:
        groups[tuple(p["group"])]["a"].append(p)
    deltas: list[dict] = []
    for group in sorted(groups):
        b, a = list(groups[group]["b"]), list(groups[group]["a"])
        for pb in list(b):                                                  # pares identicos saem primeiro (reorder inofensivo)
            match = next((pa for pa in a if pa["digest"] == pb["digest"]), None)
            if match is not None:
                b.remove(pb)
                a.remove(match)
        for pb, pa in zip(b, a):
            effects, fields = classify(pb["box"], pa["box"])
            if not fields:
                continue                                                    # difere so abaixo da tolerancia de float
            deltas.append(_delta(group, pb["occurrence"], "modified", effects or ["tag"], fields, pb["box"], pa["box"]))
        for pb in b[len(a):]:
            deltas.append(_delta(group, pb["occurrence"], "removed", ["removed"], [], pb["box"], None))
        for pa in a[len(b):]:
            deltas.append(_delta(group, pa["occurrence"], "added", ["added"], [], None, pa["box"]))
    return deltas


def _delta(group: tuple, occ: int, kind: str, effects: list[str], fields: list[str], b: dict | None, a: dict | None) -> dict:
    return {"id": "|".join(group) + f"#{occ}", "room": group[0], "module": group[1], "label": group[2], "occurrence": occ,
            "kind": kind, "effects": effects, "fields_changed": fields,
            "before": {k: b[k] for k in fields if b and k in b} if kind == "modified" else b,
            "after": {k: a[k] for k in fields if a and k in a} if kind == "modified" else a}


def _allowed_index(contract: dict, rooms: dict[str, str]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    for item in contract.get("allowed_changes") or []:
        index[rooms[item["room_key"]]].append(item)
    return index


def authorize(deltas: list[dict], contract: dict, rooms: dict[str, str]) -> list[dict]:
    """Anota cada delta com `authorization` (None = autorizado | codigo do bloqueio) conforme o modo do contrato."""
    allowed = _allowed_index(contract, rooms) if contract["change_mode"] == "scoped_change" else {}
    out = []
    for d in deltas:
        d = dict(d)
        if contract["change_mode"] == "strict_identity":
            d["authorization"] = BASELINE_MISMATCH
        elif d["room"] not in allowed:
            d["authorization"] = UNAUTHORIZED_ROOM_DELTA
        else:
            rules = [r for r in allowed[d["room"]] if d["module"] in r["part_keys"]]
            if not rules:
                d["authorization"] = UNAUTHORIZED_PART_DELTA
            elif not all(any(e in r["allowed_effects"] for r in rules) for e in d["effects"]):
                d["authorization"] = UNAUTHORIZED_EFFECT_DELTA
            else:
                d["authorization"] = None
                d["visual_review_required"] = any(r["visual_review_required"] for r in rules)
        out.append(d)
    return out


def _in_room(rows: list[dict], room: str) -> list[dict]:
    return [r for r in rows if r["room"] == room]


def compare(before: dict, after: dict, contract: dict, *, canonical_before: dict | None = None,
            canonical_after: dict | None = None, l1_gates: str | None = None, gates_before: dict | None = None,
            gates_after: dict | None = None, l2: str | None = None, l3: str | None = None) -> dict:
    """`room_regression_report.v1`. Contrato invalido/bloqueado => relatorio BLOCKED sem comparar nada (fail-closed).

    L1 de parede/giro/circulacao (F3): `gates_before`/`gates_after` = `room_regression_gates.run(...)` dos dois commits;
    o que a mudanca INTRODUZ reprova, o que ja existia na base e listado como preexistente. So um dos dois lados = BLOCKED
    (nunca comparar contra o nada). `l1_gates` ("PASS"/"FAIL") e o atalho antigo da F2. Sem nenhum, L1 fica NOT_RUN.
    """
    known = set(before["rooms"]) | set(after["rooms"])
    check = rr.validate_contract(contract, known, "planta_74" if contract.get("fixture") == "planta_74" else None)
    base = {"schema_version": "room_regression_report.v1", "change_id": contract.get("change_id", "unknown"),
            "mode": contract.get("change_mode") if contract.get("change_mode") in rr.MODES else "scoped_change",
            "base_commit": contract.get("base_commit"), "candidate_commit": contract.get("candidate_commit"),
            "input_sha256": after.get("snapshot_sha256"), "evidence": {"before_snapshot_sha256": before.get("snapshot_sha256")},
            "require_l2": bool(contract.get("require_l2", True)),
            "require_l3_if_visual_changed": bool(contract.get("require_l3_if_visual_changed", True))}
    if check["state"] != rr.OK:
        report = {**base, "canonical_hashes_unchanged": None, "room_results": [], "visual_changed": False,
                  "tests": {"l1": "NOT_RUN", "l2": "NOT_RUN", "l3": "NOT_REVIEWED"},
                  "blocked": [f"{check['state']}:{e['code']}" for e in check["errors"]]}
        report["state"], report["reasons"] = rr.aggregate_state(report)
        if check["state"] == rr.INVALID_CONTRACT:
            report["state"] = "BLOCKED"
        return report

    deltas = authorize(diff(before, after), contract, check["rooms"])
    controls = {check["rooms"][k] for k in contract["control_rooms"]}
    allowed_rooms = {check["rooms"][a["room_key"]] for a in contract.get("allowed_changes") or []}
    room_results = []
    for room in sorted(known):
        mine = [d for d in deltas if d["room"] == room]
        bad = [d for d in mine if d["authorization"]]
        room_results.append({"room_key": room, "state": "FAIL" if bad else "PASS",
                             "role": "control" if room in controls else ("allowed" if room in allowed_rooms else "unlisted"),
                             "allowed_delta_count": len(mine) - len(bad), "unexpected_delta_count": len(bad),
                             "deltas": mine})
    gate_delta = None
    incomplete = []
    if (gates_before is None) != (gates_after is None):
        incomplete.append("GATES_INCOMPLETE")
    elif gates_before is not None:
        from tools.validation import room_regression_gates as gates
        gate_delta = gates.delta(gates_before, gates_after)
        for entry in room_results:
            entry["gate_findings"] = {"introduced": _in_room(gate_delta["introduced"], entry["room_key"]),
                                      "preexisting": _in_room(gate_delta["preexisting"], entry["room_key"])}
            if entry["gate_findings"]["introduced"]:
                entry["state"] = "FAIL"
    canonical = None
    if canonical_before is not None and canonical_after is not None:
        canonical = canonical_before == canonical_after                      # R-31: vale em qualquer modo
    visual = any(d["authorization"] is None and set(d["effects"]) & APPEARANCE_EFFECTS for d in deltas)
    base["evidence"]["delta_count"] = len(deltas)
    base["evidence"]["unauthorized_delta_count"] = sum(1 for d in deltas if d["authorization"])
    base["evidence"]["ambiguous_groups"] = {"before": before.get("ambiguous_groups"), "after": after.get("ambiguous_groups")}
    if gate_delta is not None:
        base["evidence"]["l1_gates"] = {k: (v if k == "rooms_checked" else len(v) if isinstance(v, list) else v)
                                        for k, v in gate_delta.items() if k != "state"}
        base["evidence"]["preexisting_gate_findings"] = [f["key"] for f in gate_delta["preexisting"]]
        base["evidence"]["introduced_gate_findings"] = [f["key"] for f in gate_delta["introduced"]]
        base["evidence"]["resolved_gate_findings"] = [f["key"] for f in gate_delta["resolved"]]
    l1 = gate_delta["state"] if gate_delta is not None else (l1_gates or "NOT_RUN")
    if incomplete:
        base["blocked"] = incomplete
    report = {**base, "canonical_hashes_unchanged": canonical, "room_results": room_results, "visual_changed": visual,
              "tests": {"l1": l1, "l2": l2 or ("NOT_RUN" if base["require_l2"] else "NOT_APPLICABLE"),
                        "l3": l3 or ("NOT_REVIEWED" if visual else "NOT_APPLICABLE")}}
    report["state"], report["reasons"] = rr.aggregate_state(report)
    return report


PLANTA_74_PT_TO_M = 0.0259


def capture(fixture: str = "planta_74") -> dict:
    """Snapshot das caixas reais da planta_74 no commit atual. Exige o processo na escala dela (R-21, R-29): o
    `PT_TO_M` e lido uma vez por processo em `core.scale`, entao outra escala nunca e misturada aqui."""
    import json as _json
    from pathlib import Path

    from core.scale import PT_TO_M
    from tools.orchestration.furnish_apartment import CONSENSUS, collect_boxes
    from tools.validation.fp044_baseline import CANONICAL, ROOT, _sha

    if fixture != "planta_74":
        raise NotImplementedError("so planta_74 tem captura automatica; fixtures sinteticas montam o snapshot das proprias caixas")
    if abs(PT_TO_M - PLANTA_74_PT_TO_M) > 1e-12:
        raise RuntimeError(f"processo em PT_TO_M={PT_TO_M}; a planta_74 exige PT_TO_M={PLANTA_74_PT_TO_M} (processo isolado)")
    boxes, _ = collect_boxes(_json.loads(Path(CONSENSUS).read_text("utf-8")))
    digests = {p: _sha(ROOT / p) for p in CANONICAL}
    return snapshot(boxes, fixture=fixture, pt_to_m=PT_TO_M, source_digests=digests)


def main(argv: list[str]) -> int:
    import sys
    from pathlib import Path

    if len(argv) == 3 and argv[1] == "capture":
        Path(argv[2]).write_text(json.dumps(capture(), indent=1, ensure_ascii=False), encoding="utf-8")
        return 0
    if len(argv) == 5 and argv[1] == "compare":
        contract, before, after = (json.loads(Path(p).read_text("utf-8")) for p in argv[2:5])
        report = compare(before, after, contract, canonical_before=before.get("source_digests"),
                         canonical_after=after.get("source_digests"))
        print(json.dumps({k: v for k, v in report.items() if k != "room_results"}, indent=1, ensure_ascii=False))
        for r in report["room_results"]:
            for d in r.get("deltas", []):
                if d["authorization"]:
                    print(f"{d['authorization']}: {d['room']} / {d['module']} / {d['label']} #{d['occurrence']} {d['effects']}", file=sys.stderr)
        return {"PASS": 0, "FAIL": 1, "REJECTED": 1}.get(report["state"], 3)
    print("uso: capture <saida.json> | compare <contrato.json> <antes.json> <depois.json>   (exit 0 PASS, 1 FAIL, 3 pendente/bloqueado)")
    return 2


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main(_sys.argv))
