"""FP-043/P6a — gabinete parametrico compartilhado: plano L1 (sem SketchUp).

Prova contrato e geometria planejada. NAO prova materializacao: isso e a P6b (L2). Fixtures sinteticas novas;
nenhuma medida padrao e inventada para o apartamento.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import pytest

from tools.rooms.shared.cabinet import (CAPABILITY_ID, CabinetInputError, PlanRefused, footprint_world, parse_request,
                                        plan_cabinet, require_valid)
from tools.rooms.shared.cabinet.assembly import build_parts, definitions
from tools.rooms.shared.cabinet.validation import validate_plan

FIX = Path(__file__).resolve().parents[1] / "fixtures/synthetic_cabinets"
HOLDOUT_SHA256 = "13572644f6ad2a8c941adb3640daaf4fe4647b97c0ddbfd43db9f2d801479d83"   # fixado ANTES de existir o planner


def load(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text("utf-8"))


def mut(req: dict, path: str, value) -> dict:
    out = copy.deepcopy(req)
    node = out
    keys = path.split(".")
    for k in keys[:-1]:
        node = node[k]
    if value is _DROP:
        del node[keys[-1]]
    else:
        node[keys[-1]] = value
    return out


_DROP = object()
A, B, C = load("valid_a_base_600"), load("valid_b_tall_900"), load("holdout_c")


def codes(plan: dict) -> set[str]:
    return {f["code"] for f in plan["findings"]}


# ------------------------------------------------------------------ positivos (3 dimensoes diferentes + holdout)
@pytest.mark.parametrize("req", [A, B, C], ids=["base600", "tall900", "holdout"])
def test_dimensoes_validas_geram_plano_ok_e_pecas_dentro_do_envelope(req):
    plan = plan_cabinet(req)
    assert plan["status"] == "OK" and plan["findings"] == [] and plan["execution_authorized"] is False
    assert plan["capability"] == {"id": CAPABILITY_ID, "version": "1.0.0"} and plan["schema_version"] == "cabinet_assembly_plan.v1"
    W, D, H = plan["envelope_m"]
    for p in plan["parts"]:
        assert all(s > 0 and math.isfinite(s) for s in p["size_m"]), p["id"]
        assert all(-1e-9 <= p["min_m"][k] and p["max_m"][k] <= (W, D, H)[k] + 1e-9 for k in range(3)), p["id"]
    require_valid(plan)


def test_as_tres_dimensoes_sao_realmente_diferentes():
    envs = {tuple(plan_cabinet(r)["envelope_m"]) for r in (A, B, C)}
    assert len(envs) == 3


def test_caso_reservado_esta_fixado_por_hash_e_foi_planejado_sem_ajuste():
    raw = (FIX / "holdout_c.json").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == HOLDOUT_SHA256, "o caso reservado nao pode mudar para fazer o teste passar"
    plan = plan_cabinet(C)
    assert plan["status"] == "OK"
    # contas independentes do planner: laterais 15,5 mm; vao = 437 - 31 = 406 mm; caixaria = 523 - 18,7 - 1,9 = 502,4 mm
    sizes = {p["name"]: p["size_m"] for p in plan["parts"]}
    assert sizes["side_left"] == pytest.approx([0.0155, 0.5024, 1.033])
    assert sizes["bottom"][0] == pytest.approx(0.406)
    assert sizes["front"] == pytest.approx([0.437 - 2 * 0.0023, 0.0187, 1.033 - 2 * 0.0023])


def test_conta_de_pecas_e_convencao_de_montagem():
    plan = plan_cabinet(A)
    assert [p["name"] for p in plan["parts"]] == ["side_left", "side_right", "bottom", "top", "back", "front"]
    by = {p["name"]: p for p in plan["parts"]}
    assert by["back"]["min_m"][1] == 0.0                                    # fundo rente a face traseira
    assert by["front"]["max_m"][1] == pytest.approx(0.560)                  # frente na face frontal (+y)
    assert by["front"]["min_m"][1] - by["side_left"]["max_m"][1] == pytest.approx(0.002)   # front_clearance
    tall = {p["name"]: p for p in plan_cabinet(B)["parts"]}
    assert set(tall) >= {"shelf", "front_1", "front_2"}
    gap = tall["front_2"]["min_m"][0] - tall["front_1"]["max_m"][0]
    assert gap == pytest.approx(0.0025)                                      # front_reveal entre portas
    assert tall["shelf"]["min_m"][2] == pytest.approx(1.05)


def test_materiais_e_veio_por_peca():
    plan = plan_cabinet(A)
    mats = {p["name"]: (p["material"], p["grain"]) for p in plan["parts"]}
    assert mats["side_left"] == ("mdf_branco", "along_height") and mats["back"] == ("hdf_branco", "none")
    assert mats["front"] == ("mdf_carvalho", "along_height")


# ------------------------------------------------------------------ pose
@pytest.mark.parametrize("deg", [0, 90, 30])
def test_pegada_no_quadro_do_projeto_gira_em_torno_da_origem_local(deg):
    req = mut(A, "pose.rotation_deg.value", deg)
    plan = plan_cabinet(req)
    fp = footprint_world(plan)
    th = math.radians(deg)
    W, D, _ = plan["envelope_m"]
    assert fp[0] == pytest.approx((2.0, 1.0))                                # origem local = posicao da pose
    assert fp[1] == pytest.approx((2.0 + W * math.cos(th), 1.0 + W * math.sin(th)))
    assert fp[3] == pytest.approx((2.0 - D * math.sin(th), 1.0 + D * math.cos(th)))
    area = 0.5 * abs(sum(fp[i][0] * fp[(i + 1) % 4][1] - fp[(i + 1) % 4][0] * fp[i][1] for i in range(4)))
    assert area == pytest.approx(W * D)                                      # rotacao preserva a area


# ------------------------------------------------------------------ negativos: entrada
def test_entrada_incompleta_sem_unidade_ou_origem_e_recusada():
    inc = load("invalid_incomplete")
    plan = plan_cabinet(inc)
    assert plan["status"] == "REFUSED" and plan["stage"] == "input" and plan["execution_authorized"] is False
    assert "MISSING_UNIT" in codes(plan)
    assert plan_cabinet(mut(A, "dimensions.height.origin", _DROP))["findings"][0]["code"] == "MISSING_ORIGIN"


@pytest.mark.parametrize("path,value,code", [
    ("dimensions.width.value", float("nan"), "NON_FINITE"),
    ("dimensions.width.value", float("inf"), "NON_FINITE"),
    ("dimensions.width.value", -600, "NON_POSITIVE"),
    ("dimensions.width.value", 0, "NON_POSITIVE"),
    ("dimensions.width.value", "600", "MISSING_VALUE"),
    ("dimensions.width.value", True, "MISSING_VALUE"),
    ("dimensions.width.unit", "polegada", "INVALID_UNIT"),
    ("dimensions.width.origin", "default_declared", "INVALID_ORIGIN"),
    ("dimensions.width.origin", "chute", "INVALID_ORIGIN"),
    ("panels.side.value", 0, "NON_POSITIVE"),
    ("gaps.front_clearance.value", -1, "NON_POSITIVE"),
    ("pose.rotation_deg.unit", "rad", "INVALID_UNIT"),
    ("pose.x.value", float("nan"), "NON_FINITE"),
    ("fronts.count", 3, "INVALID_FRONT_COUNT"),
    ("shelf.count", 2, "INVALID_SHELF_COUNT"),
    ("materials.front", "", "MISSING_MATERIAL"),
    ("grain.carcass", "diagonal", "INVALID_GRAIN"),
    ("request_id", "tem espaco", "INVALID_REQUEST_ID"),
    ("schema_version", "cabinet_request.v0", "INVALID_SCHEMA"),
])
def test_entrada_invalida_e_recusada_com_codigo_estavel(path, value, code):
    plan = plan_cabinet(mut(A, path, value))
    assert plan["status"] == "REFUSED" and plan["stage"] == "input" and code in codes(plan), plan["findings"]


@pytest.mark.parametrize("path", ["dimensions", "panels.side", "gaps.front_reveal", "materials.back", "pose.z"])
def test_campo_obrigatorio_ausente_e_recusado_sem_inventar_padrao(path):
    plan = plan_cabinet(mut(A, path, _DROP))
    assert plan["status"] == "REFUSED" and plan["stage"] == "input"
    assert "parts" not in plan or plan.get("parts") in (None, [])


def test_prateleira_pedida_exige_espessura_e_altura():
    assert plan_cabinet(mut(B, "shelf.height_from_bottom", _DROP))["status"] == "REFUSED"
    assert plan_cabinet(mut(B, "panels.shelf", _DROP))["status"] == "REFUSED"


def test_entrada_com_tipo_errado_nao_explode():
    for bad in (None, [], "x", {"schema_version": "cabinet_request.v1"}):
        assert plan_cabinet(bad)["status"] == "REFUSED"
    with pytest.raises(CabinetInputError):
        parse_request({})


# ------------------------------------------------------------------ negativos: geometria
def test_geometria_impossivel_e_recusada_na_validacao():
    plan = plan_cabinet(load("invalid_impossible"))
    assert plan["status"] == "REFUSED" and plan["stage"] == "validation"
    assert {"INFEASIBLE_INNER_WIDTH", "NON_POSITIVE_PART"} <= codes(plan)
    with pytest.raises(PlanRefused):
        require_valid(plan)


@pytest.mark.parametrize("path,value,code", [
    ("dimensions.depth.value", 24, "INFEASIBLE_DEPTH"),
    ("dimensions.height.value", 30, "INFEASIBLE_INNER_HEIGHT"),
    ("gaps.front_reveal.value", 400, "INFEASIBLE_FRONT"),
])
def test_outras_inviabilidades_tem_codigo_proprio(path, value, code):
    assert code in codes(plan_cabinet(mut(A, path, value)))


def test_prateleira_fora_do_vao_e_recusada():
    assert "SHELF_OUT_OF_SPAN" in codes(plan_cabinet(mut(B, "shelf.height_from_bottom.value", 2.2)))
    assert "SHELF_OUT_OF_SPAN" in codes(plan_cabinet(mut(B, "shelf.height_from_bottom.value", 0.001)))


def test_colisao_indevida_e_peca_fora_do_envelope_sao_detectadas():
    from tools.rooms.shared.cabinet.model import parse_request as parse
    p = parse(A)
    parts = copy.deepcopy(build_parts(p))
    parts[2]["max_m"][0] += 0.05                                             # base invade a lateral direita
    parts[2]["size_m"][0] += 0.05
    rep = validate_plan(parts, p)
    assert not rep["ok"] and {"PART_COLLISION", "PART_OUTSIDE_ENVELOPE"} & {f["code"] for f in rep["findings"]}
    parts = copy.deepcopy(build_parts(p))
    parts[0]["min_m"][0] = -0.01
    assert "PART_OUTSIDE_ENVELOPE" in {f["code"] for f in validate_plan(parts, p)["findings"]}


def test_contato_de_face_nao_e_colisao():
    from tools.rooms.shared.cabinet.model import parse_request as parse
    p = parse(A)
    assert validate_plan(build_parts(p), p)["ok"]                            # base/laterais/fundo se tocam sem volume comum


# ------------------------------------------------------------------ porta unica de materializacao
def test_materializacao_so_depois_de_validar_e_com_assinatura_integra():
    plan = plan_cabinet(A)
    assert require_valid(plan) is plan
    tampered = copy.deepcopy(plan)
    tampered["parts"][0]["size_m"][0] += 0.001
    tampered["parts"][0]["max_m"][0] += 0.001
    with pytest.raises(PlanRefused) as exc:
        require_valid(tampered)
    assert exc.value.findings[0]["code"] == "SIGNATURE_MISMATCH"
    wrong = copy.deepcopy(plan)
    wrong["capability"]["id"] = "outra.capacidade"
    with pytest.raises(PlanRefused):
        require_valid(wrong)
    refused = plan_cabinet(mut(A, "dimensions.width.value", 10))
    with pytest.raises(PlanRefused):
        require_valid(refused)
    with pytest.raises(PlanRefused):
        require_valid({"schema_version": "x"})


def test_assinatura_liga_capacidade_versao_e_parametros():
    s1 = plan_cabinet(A)["signature"]
    assert s1 == plan_cabinet(copy.deepcopy(A))["signature"]                 # deterministico
    assert s1 != plan_cabinet(mut(A, "dimensions.width.value", 601))["signature"]
    assert s1 != plan_cabinet(mut(A, "materials.front", "mdf_outro"))["signature"]
    assert s1 != plan_cabinet(mut(A, "pose.x.value", 2.5))["signature"]


def test_ids_de_peca_sao_estaveis_ao_editar_parametros_e_nao_duplicam():
    before = [p["id"] for p in plan_cabinet(A)["parts"]]
    after = [p["id"] for p in plan_cabinet(mut(A, "dimensions.width.value", 800))["parts"]]
    assert before == after and len(set(before)) == len(before)
    assert all(i.startswith("synthetic-a/") for i in before)


# ------------------------------------------------------------------ componentes compartilhados / make_unique
def test_definicoes_so_se_compartilham_entre_pecas_equivalentes():
    plan = plan_cabinet(B)
    shared = {tuple(d["instances"]) for d in plan["definitions"] if d["shared"]}
    assert ("synthetic-b/side_left", "synthetic-b/side_right") in shared
    assert ("synthetic-b/front_1", "synthetic-b/front_2") in shared
    assert plan["edit_policy"] == {"local_change": "make_unique", "definition_edit_propagates": "only_when_explicit"}
    from tools.rooms.shared.cabinet.model import parse_request as parse
    parts = copy.deepcopy(build_parts(parse(B)))
    next(x for x in parts if x["name"] == "front_2")["material"] = "mdf_diferente"     # edicao local -> deixa de ser equivalente
    defs = definitions(parts)
    assert not any("synthetic-b/front_1" in d["instances"] and "synthetic-b/front_2" in d["instances"] for d in defs)


def test_plano_consultivo_continua_separado_e_nao_autorizado():
    from tools.sketchup import knowledge
    assert knowledge.PROOF_STATE == "KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP"
    assert plan_cabinet(A)["schema_version"] != "advisory_cabinet_plan.v1"
