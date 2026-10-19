"""Plano do gabinete parametrico compartilhado (caixaria retangular + frentes lisas separadas). L1: so dados.

`plan_cabinet(request)` -> `cabinet_assembly_plan.v1` ou recusa tipada. Nunca abre SketchUp, nunca escreve arquivo.
O plano nao autoriza execucao: `require_valid` e a unica porta para a etapa de materializacao (P6b) e falha
fechada quando a validacao nao passa. O plano consultivo `tools.sketchup.knowledge.cabinet_plan` continua separado.
"""
from __future__ import annotations

import hashlib
import json
import math

from .assembly import build_parts, definitions
from .model import CabinetInputError, Params, parse_request
from .validation import validate_plan

CAPABILITY_ID = "shared.cabinet.parametric"
CAPABILITY_VERSION = "1.0.0"
SCHEMA_PLAN = "cabinet_assembly_plan.v1"
CONVENTION = ("local: origem no canto traseiro-esquerdo-inferior; +x largura, +y profundidade (frente em +y), +z altura; "
              "pose: rotacao anti-horaria em torno de +z (graus) e depois translacao da origem local; unidades em metros")


class PlanRefused(Exception):
    """Plano nao validado: a materializacao nao pode seguir."""

    def __init__(self, findings: list[dict]):
        super().__init__("; ".join(f"{f['code']}: {f['detail']}" for f in findings))
        self.findings = findings


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _params_dict(p: Params) -> dict:
    d = {k: getattr(p, k) for k in p.__dataclass_fields__}
    return json.loads(_canonical(d))


def signature(params: dict, parts: list[dict]) -> str:
    """Liga capacidade+versao+parametros+pecas: mudou qualquer um, a assinatura muda."""
    body = {"capability": CAPABILITY_ID, "version": CAPABILITY_VERSION, "params": params,
            "parts": [{"id": x["id"], "min": x["min_m"], "max": x["max_m"], "material": x["material"], "grain": x["grain"]}
                      for x in parts]}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def plan_cabinet(request: dict) -> dict:
    """Recusa (status REFUSED + codigo) em vez de excecao para entrada invalida; geometria inviavel tambem recusa."""
    try:
        p = parse_request(request)
    except CabinetInputError as exc:
        return {"schema_version": SCHEMA_PLAN, "status": "REFUSED", "stage": "input",
                "findings": [{"code": exc.code, "detail": f"{exc.field}: {exc.message}"}],
                "execution_authorized": False}
    parts = build_parts(p)
    report = validate_plan(parts, p)
    params = _params_dict(p)
    plan = {
        "schema_version": SCHEMA_PLAN,
        "status": "OK" if report["ok"] else "REFUSED",
        "stage": "validation" if not report["ok"] else "plan",
        "capability": {"id": CAPABILITY_ID, "version": CAPABILITY_VERSION},
        "request_id": p.request_id,
        "units": "m",
        "convention": CONVENTION,
        "envelope_m": [p.width, p.depth, p.height],
        "pose": dict(p.pose),
        "parameters": params,
        "parts": parts,
        "definitions": definitions(parts),
        "edit_policy": {"local_change": "make_unique", "definition_edit_propagates": "only_when_explicit"},
        "findings": report["findings"],
        "rollback": "descartar a copia de trabalho; o plano nao altera arquivo nem o original",
        "execution_authorized": False,
        "signature": signature(params, parts),
    }
    return plan


def require_valid(plan: dict) -> dict:
    """Porta unica para materializar: plano nao validado, adulterado ou sem assinatura coerente NAO passa."""
    if plan.get("schema_version") != SCHEMA_PLAN or plan.get("status") != "OK" or plan.get("findings"):
        raise PlanRefused(plan.get("findings") or [{"code": "PLAN_NOT_OK", "detail": str(plan.get("status"))}])
    if plan.get("capability", {}).get("id") != CAPABILITY_ID:
        raise PlanRefused([{"code": "WRONG_CAPABILITY", "detail": str(plan.get("capability"))}])
    expected = signature_of_plan(plan)
    if plan.get("signature") != expected:
        raise PlanRefused([{"code": "SIGNATURE_MISMATCH", "detail": "plano alterado depois de assinado"}])
    return plan


def signature_of_plan(plan: dict) -> str:
    return signature(plan["parameters"], plan["parts"])


def world_transform(plan: dict):
    """(rotacao_rad, tx, ty, tz) do quadro local ao do projeto."""
    pose = plan["pose"]
    return math.radians(pose["rotation_deg"]), pose["x"], pose["y"], pose["z"]


def to_world_xy(plan: dict, x: float, y: float) -> tuple[float, float]:
    th, tx, ty, _ = world_transform(plan)
    c, s = math.cos(th), math.sin(th)
    return tx + c * x - s * y, ty + s * x + c * y


def footprint_world(plan: dict) -> list[tuple[float, float]]:
    """Pegada (poligono) da caixaria+frentes no quadro do projeto, metros, em torno do envelope local."""
    W, D, _ = plan["envelope_m"]
    return [to_world_xy(plan, x, y) for x, y in ((0, 0), (W, 0), (W, D), (0, D))]
