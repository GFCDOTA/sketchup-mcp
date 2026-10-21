"""FP-047/F1: contrato e estado final do gate de regressao geometrica e visual por comodo.

Esta fatia NAO compara geometria (isso e a F2): valida o contrato da mudanca (`room_regression_request.v1`) de forma
fail-closed e calcula o estado final de um relatorio (`room_regression_report.v1`) sem nunca promover prova incompleta.

- `change_mode` nunca tem default: ausente/desconhecido = BLOCKED_CHANGE_MODE (R-01); `scoped_change` sem
  `allowed_changes` = BLOCKED (R-04); `strict_identity` nao admite `allowed_changes`.
- `room_key` e `control_rooms` sao resolvidos contra os comodos reais (registry da planta_74 ou nome exato do snapshot);
  alias desconhecido nunca faz o check "pular" um comodo (INVALID_CONTRACT).
- Estado final: FAIL > REJECTED > BLOCKED > PENDING_SKETCHUP > PENDING_HUMAN > PASS; PASS exige L1 PASS, canonicos
  intactos e L2/L3 resolvidos quando exigidos (R-20, R-24, R-30, R-31).

uso: python -m tools.validation.room_regression validate-contract <contrato.json>   (exit 0 OK, 1 INVALID, 3 BLOCKED)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from core.schemas import load

REQUEST_SCHEMA = "room_regression_request.v1.schema.json"
REPORT_SCHEMA = "room_regression_report.v1.schema.json"
MODES = ("strict_identity", "scoped_change")

OK = "OK"
BLOCKED_CHANGE_MODE = "BLOCKED_CHANGE_MODE"
BLOCKED = "BLOCKED"
INVALID_CONTRACT = "INVALID_CONTRACT"


class RoomUnresolved(KeyError):
    """room_key desconhecido ou ambiguo; carrega o motivo."""


def registry_rooms(project_id: str = "planta_74") -> set[str]:
    """Nomes de exibicao dos comodos do registry (= `box["room"]` produzido por `collect_boxes`)."""
    from core.domain.room_registry import rooms_for_project
    return {r.display_name for r in rooms_for_project(project_id)}


def resolve_room(key: str, known_rooms: set[str], project_id: str | None = "planta_74") -> str:
    """`room_id` (r003), alias (suite_02) ou nome exato -> o nome presente em `known_rooms`.

    Nome exato tem prioridade, mas se o mesmo texto for tambem alias de OUTRO comodo e a ambiguidade mudar o resultado,
    recusa. Fora do registry (fixtures sinteticas) so vale nome exato do snapshot.
    """
    exact = key if key in known_rooms else None
    via_registry = None
    if project_id:
        from core.domain.room_registry import room_info
        try:
            via_registry = room_info(key, project_id=project_id).display_name
        except KeyError:
            via_registry = None
    if exact and via_registry and exact != via_registry:
        raise RoomUnresolved(f"{key!r} e ambiguo: nome exato {exact!r} x alias {via_registry!r}")
    found = exact or via_registry
    if found is None:
        raise RoomUnresolved(f"{key!r} nao e comodo conhecido (nem room_id/alias do registry, nem nome do snapshot)")
    if found not in known_rooms:
        raise RoomUnresolved(f"{key!r} resolve para {found!r}, ausente do snapshot")
    return found


def _err(code: str, path: str, detail: str) -> dict:
    return {"code": code, "path": path, "detail": detail}


def validate_contract(contract: object, known_rooms: set[str] | None = None,
                      project_id: str | None = "planta_74") -> dict:
    """{"state": OK|BLOCKED_CHANGE_MODE|BLOCKED|INVALID_CONTRACT, "errors": [...], "rooms": {chave: nome}}."""
    from jsonschema import Draft202012Validator

    if not isinstance(contract, dict):
        return {"state": INVALID_CONTRACT, "errors": [_err("NOT_AN_OBJECT", "", "contrato deve ser objeto JSON")], "rooms": {}}
    if contract.get("change_mode") not in MODES:
        return {"state": BLOCKED_CHANGE_MODE, "rooms": {},
                "errors": [_err("CHANGE_MODE_MISSING_OR_UNKNOWN", "change_mode",
                                f"deve ser um de {list(MODES)}; nunca inferido do diff (valor: {contract.get('change_mode')!r})")]}
    schema = load(REQUEST_SCHEMA)
    checked = {k: v for k, v in contract.items() if not (k == "allowed_changes" and v is None)}   # null = ausente
    errors = [_err("SCHEMA", "/".join(str(p) for p in e.path), e.message[:160])
              for e in sorted(Draft202012Validator(schema).iter_errors(checked), key=lambda e: list(e.path))]
    if errors:
        return {"state": INVALID_CONTRACT, "errors": errors, "rooms": {}}

    allowed = contract.get("allowed_changes") or []
    if contract["change_mode"] == "strict_identity":
        if allowed:
            return {"state": INVALID_CONTRACT, "rooms": {},
                    "errors": [_err("STRICT_IDENTITY_FORBIDS_ALLOWED_CHANGES", "allowed_changes",
                                    "strict_identity nao tem mudanca autorizada; use scoped_change com justificativa")]}
    elif not allowed:
        return {"state": BLOCKED, "rooms": {},
                "errors": [_err("SCOPED_CHANGE_WITHOUT_ALLOWED_CHANGES", "allowed_changes",
                                "scoped_change exige ao menos uma mudanca autorizada com comodo, pecas e justificativa")]}

    rooms: dict[str, str] = {}
    if known_rooms is not None:
        keys = [(f"allowed_changes/{i}/room_key", a["room_key"]) for i, a in enumerate(allowed)]
        keys += [(f"control_rooms/{i}", k) for i, k in enumerate(contract["control_rooms"])]
        for path, key in keys:
            try:
                rooms[key] = resolve_room(key, known_rooms, project_id)
            except RoomUnresolved as exc:
                errors.append(_err("UNRESOLVED_ROOM", path, str(exc)))
        allowed_rooms = {rooms[a["room_key"]] for a in allowed if a["room_key"] in rooms}
        for i, key in enumerate(contract["control_rooms"]):
            if rooms.get(key) in allowed_rooms:
                errors.append(_err("CONTROL_ROOM_ALSO_ALLOWED", f"control_rooms/{i}",
                                   f"{key!r} e controle e ao mesmo tempo autorizado a mudar"))
    if errors:
        return {"state": INVALID_CONTRACT, "errors": errors, "rooms": rooms}
    return {"state": OK, "errors": [], "rooms": rooms}


def aggregate_state(report: dict) -> tuple[str, list[str]]:
    """Estado final do relatorio a partir das provas; nunca PASS por default nem por prova parcial.

    Espera `report["tests"]` {l1,l2,l3}, `canonical_hashes_unchanged`, `room_results`, e opcionalmente
    `blocked` (lista de motivos), `require_l2`, `visual_changed`, `require_l3_if_visual_changed`.
    """
    tests = report.get("tests") or {}
    l1, l2, l3 = tests.get("l1", "NOT_RUN"), tests.get("l2", "NOT_RUN"), tests.get("l3", "NOT_REVIEWED")
    reasons: list[str] = []
    fail: list[str] = []
    if report.get("canonical_hashes_unchanged") is False:
        fail.append("CANONICAL_CHANGED")                                    # R-31: absoluto, sem excecao de allowed_changes
    if l1 == "FAIL":
        fail.append("L1_FAIL")
    if l2 == "FAIL":
        fail.append("FAILED_L2")
    fail += [f"ROOM_FAIL:{r.get('room_key')}" for r in report.get("room_results", []) if r.get("state") == "FAIL"
             or int(r.get("unexpected_delta_count", 0)) > 0]
    if fail:
        return "FAIL", fail
    if l3 == "REJECTED":
        return "REJECTED", ["VISUAL_REJECTED"]                               # R-32
    if report.get("blocked"):
        return "BLOCKED", list(report["blocked"])
    if l1 != "PASS":
        return "BLOCKED", ["L1_NOT_RUN"]
    if report.get("canonical_hashes_unchanged") is not True:
        return "BLOCKED", ["CANONICAL_HASHES_NOT_VERIFIED"]
    if any(r.get("state") == "NOT_RUN" for r in report.get("room_results", [])) or not report.get("room_results"):
        return "BLOCKED", ["ROOM_RESULTS_INCOMPLETE"]
    if report.get("require_l2", True) and l2 != "PASS":
        return "PENDING_SKETCHUP", ["L2_NOT_PROVEN"]                         # R-20
    if report.get("visual_changed") and report.get("require_l3_if_visual_changed", True) and l3 != "APPROVED":
        return "PENDING_HUMAN", ["L3_NOT_APPROVED"]                          # R-24
    return "PASS", reasons


def validate_report(report: dict) -> list[str]:
    """Erros de schema do relatorio e de coerencia entre `state` declarado e o recalculado."""
    from jsonschema import Draft202012Validator

    errors = [f"{'/'.join(str(p) for p in e.path)}: {e.message[:120]}"
              for e in Draft202012Validator(load(REPORT_SCHEMA)).iter_errors(report)]
    if not errors:
        recomputed, _ = aggregate_state(report)
        if report["state"] == "PASS" and recomputed != "PASS":
            errors.append(f"state PASS declarado, mas as provas dao {recomputed}")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "validate-contract":
        print(__doc__)
        return 2
    contract = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    project = "planta_74" if isinstance(contract, dict) and contract.get("fixture") == "planta_74" else None
    result = validate_contract(contract, registry_rooms() if project else None, project)
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return {OK: 0, INVALID_CONTRACT: 1}.get(result["state"], 3)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
