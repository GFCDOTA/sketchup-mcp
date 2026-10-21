"""Plano da porta Shaker (`shaker_door_plan.v1`): puro, deterministico, assinado, sem autorizar execucao.

A submontagem substitui UMA frente lisa do gabinete pai (o envelope W x H x espessura dessa frente permanece):
2 montantes (altura toda), 2 travessas (entre os montantes) e 1 painel central cuja face visivel fica recuada
`recess` da face frontal da moldura. Contato de face e permitido; volume em comum nao.
Quadro local = o do gabinete pai (+x largura, +y traseira->frente, +z altura, metros).
"""
from __future__ import annotations

import hashlib
import json

from ..assembly import definitions
from ..model import CabinetInputError
from ..plan import PlanRefused, require_valid
from ..plan import _canonical as _canon
from ..plan import signature_of_plan as parent_signature
from .model import GRAIN_SUPPORT, ShakerParams, parse_shaker_request
from .validation import validate_shaker

CAPABILITY_ID = "shared.cabinet.front.shaker"
CAPABILITY_VERSION = "1.0.0"
SCHEMA_PLAN = "shaker_door_plan.v1"
EPS = 1e-9


class ShakerPlanRefused(Exception):
    """Plano Shaker nao validado, adulterado ou desatualizado em relacao ao pai: nao materializa."""

    def __init__(self, findings: list[dict]):
        super().__init__("; ".join(f"{f['code']}: {f['detail']}" for f in findings))
        self.findings = findings


def _refused(stage: str, code: str, detail: str, request_id=None) -> dict:
    return {"schema_version": SCHEMA_PLAN, "status": "REFUSED", "stage": stage, "request_id": request_id,
            "findings": [{"code": code, "detail": detail}], "execution_authorized": False}


def _params_dict(p: ShakerParams) -> dict:
    return json.loads(_canon({k: getattr(p, k) for k in p.__dataclass_fields__}))


def signature(params: dict, parts: list[dict], parent_sig: str) -> str:
    body = {"capability": CAPABILITY_ID, "version": CAPABILITY_VERSION, "params": params, "parent_plan_signature": parent_sig,
            "parts": [{"id": x["id"], "min": x["min_m"], "max": x["max_m"], "material": x["material"], "grain": x["grain"]}
                      for x in parts]}
    return hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()


def build_shaker_parts(p: ShakerParams, front: dict) -> list[dict]:
    (x0, y0, z0), (x1, y1, z1) = front["min_m"], front["max_m"]
    sw, rh = p.stile_width, p.rail_height
    py1 = y1 - p.recess
    py0 = py1 - p.panel_thickness
    parts: list[dict] = []

    def add(name: str, role: str, lo: tuple, hi: tuple) -> None:
        parts.append({"id": f"{p.request_id}/{name}", "name": name, "role": role, "min_m": list(lo), "max_m": list(hi),
                      "size_m": [hi[k] - lo[k] for k in range(3)], "material": p.materials[role], "grain": p.grain[role]})

    add("stile_left", "frame", (x0, y0, z0), (x0 + sw, y1, z1))
    add("stile_right", "frame", (x1 - sw, y0, z0), (x1, y1, z1))
    add("rail_top", "frame", (x0 + sw, y0, z1 - rh), (x1 - sw, y1, z1))
    add("rail_bottom", "frame", (x0 + sw, y0, z0), (x1 - sw, y1, z0 + rh))
    add("recessed_panel", "panel", (x0 + sw, py0, z0 + rh), (x1 - sw, py1, z1 - rh))
    return parts


def plan_shaker_door(request: dict, parent_plan: dict) -> dict:
    """Recusa (status REFUSED + codigo) em vez de excecao: entrada, pai invalido, frente inexistente ou geometria inviavel."""
    try:
        p = parse_shaker_request(request)
    except CabinetInputError as exc:
        rid = request.get("request_id") if isinstance(request, dict) else None
        return _refused("input", exc.code, f"{exc.field}: {exc.message}", rid)
    try:
        require_valid(parent_plan)
    except PlanRefused as exc:
        return _refused("parent", "PARENT_PLAN_INVALID", str(exc), p.request_id)
    if parent_plan["request_id"] != p.parent_request_id:
        return _refused("parent", "PARENT_MISMATCH",
                        f"pedido cita {p.parent_request_id!r}, plano pai e {parent_plan['request_id']!r}", p.request_id)
    front = next((x for x in parent_plan["parts"] if x["name"] == p.target_front and x["role"] == "front"), None)
    if front is None:
        return _refused("parent", "TARGET_FRONT_NOT_FOUND",
                        f"{p.target_front!r} nao e frente do gabinete {p.parent_request_id!r}", p.request_id)
    fw, ft, fh = front["size_m"]                 # x largura, y espessura (profundidade), z altura
    if abs(p.frame_thickness - ft) > EPS:
        return _refused("geometry", "FRAME_THICKNESS_MISMATCH",
                        f"moldura {p.frame_thickness} m != espessura da frente do pai {ft} m", p.request_id)
    if p.recess + p.panel_thickness > p.frame_thickness + EPS:
        return _refused("geometry", "PANEL_OUTSIDE_FRAME_DEPTH",
                        f"recuo {p.recess} + painel {p.panel_thickness} excede a moldura {p.frame_thickness}", p.request_id)
    if fw - 2 * p.stile_width <= EPS or fh - 2 * p.rail_height <= EPS:
        return _refused("geometry", "INFEASIBLE_PANEL_OPENING",
                        f"vao do painel {fw - 2 * p.stile_width:.6f} x {fh - 2 * p.rail_height:.6f} m nao e positivo", p.request_id)
    parts = build_shaker_parts(p, front)
    report = validate_shaker(parts, p, front)
    params = _params_dict(p)
    parent_sig = parent_signature(parent_plan)
    return {
        "schema_version": SCHEMA_PLAN,
        "status": "OK" if report["ok"] else "REFUSED",
        "stage": "plan" if report["ok"] else "validation",
        "capability": {"id": CAPABILITY_ID, "version": CAPABILITY_VERSION},
        "request_id": p.request_id,
        "parent_cabinet_request_id": p.parent_request_id,
        "parent_plan_signature": parent_sig,
        "target_front": p.target_front,
        "replaces_part": front["id"],
        "units": "m",
        "convention": parent_plan["convention"],
        "pose": dict(parent_plan["pose"]),
        "parameters": params,
        "parts": parts,
        "definitions": definitions(parts),
        "edit_policy": {"local_change": "make_unique", "definition_edit_propagates": "only_when_explicit"},
        "origin_context": dict(p.origin_context),
        "grain_support": GRAIN_SUPPORT,
        "findings": report["findings"],
        "rollback": "descartar a copia de trabalho; o plano nao altera arquivo nem o original",
        "execution_authorized": False,
        "visual": "NOT_REVIEWED",
        "signature": signature(params, parts, parent_sig),
    }


def _namespace(params: dict) -> ShakerParams:
    return ShakerParams(**{k: params[k] for k in ShakerParams.__dataclass_fields__})


def require_valid_shaker(plan: dict, parent_plan: dict) -> dict:
    """Porta unica para materializar a Shaker: plano nao OK, adulterado ou de um pai que mudou NAO passa (R-12, R-18)."""
    if plan.get("schema_version") != SCHEMA_PLAN or plan.get("status") != "OK" or plan.get("findings"):
        raise ShakerPlanRefused(plan.get("findings") or [{"code": "PLAN_NOT_OK", "detail": str(plan.get("status"))}])
    if plan.get("capability", {}).get("id") != CAPABILITY_ID:
        raise ShakerPlanRefused([{"code": "WRONG_CAPABILITY", "detail": str(plan.get("capability"))}])
    if plan.get("execution_authorized") is not False:
        raise ShakerPlanRefused([{"code": "EXECUTION_FLAG_TAMPERED", "detail": "o plano nao pode autorizar execucao"}])
    try:
        require_valid(parent_plan)
    except PlanRefused as exc:
        raise ShakerPlanRefused([{"code": "PARENT_PLAN_INVALID", "detail": str(exc)}]) from exc
    if plan.get("parent_plan_signature") != parent_signature(parent_plan):
        raise ShakerPlanRefused([{"code": "PARENT_PLAN_CHANGED", "detail": "o gabinete pai mudou depois deste plano"}])
    if plan.get("signature") != signature(plan["parameters"], plan["parts"], plan["parent_plan_signature"]):
        raise ShakerPlanRefused([{"code": "SIGNATURE_MISMATCH", "detail": "plano alterado depois de assinado"}])
    front = next((x for x in parent_plan["parts"] if x["id"] == plan.get("replaces_part")), None)
    if front is None:
        raise ShakerPlanRefused([{"code": "TARGET_FRONT_NOT_FOUND", "detail": str(plan.get("replaces_part"))}])
    rebuilt = validate_shaker(plan["parts"], _namespace(plan["parameters"]), front)     # geometria revalidada, nao confiada
    if not rebuilt["ok"]:
        raise ShakerPlanRefused(rebuilt["findings"])
    return plan
