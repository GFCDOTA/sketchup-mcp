"""FP-046/P3 — driver da materializacao Shaker (SEM SketchUp): guardas, fiacao, verificador e travas do Ruby.

NAO e prova de geometria: a prova no SketchUp real e a bateria L2 em artifacts/review/fp046/p3_shaker_l2/. Um dublê de
SketchUp aqui so prova que o driver nao sobe o SketchUp quando nao deve, e que `verify_shaker` reprova cada defeito.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from tools.rooms.shared.cabinet import plan_cabinet
from tools.rooms.shared.cabinet import sketchup as cabinet_su
from tools.rooms.shared.cabinet.shaker import ShakerPlanRefused, plan_shaker_door
from tools.rooms.shared.cabinet.shaker import sketchup as ss
from tools.sketchup import paths
from tools.sketchup.process import Locations, SketchUp

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures/synthetic_cabinets"
EXE = Path("C:/SU/SketchUp.exe")
RUBY = ROOT / "tools/rooms/shared/cabinet/ruby"


def load(name):
    return json.loads((FIX / name).read_text("utf-8"))


def parent_plan(rot=0, fronts=1):
    r = load("valid_a_base_600.json")
    r["pose"]["rotation_deg"]["value"] = rot
    r["fronts"] = {"count": fronts}
    plan = plan_cabinet(r)
    assert plan["status"] == "OK"
    return plan


def shaker_plan(par, **over):
    req = load("fp046_shaker_valid_a.json")
    req.update(over)
    plan = plan_shaker_door(req, par)
    assert plan["status"] == "OK", plan["findings"]
    return plan


class Boom:
    def __getattr__(self, name):
        raise AssertionError(f"SketchUp nao deveria ser usado ({name})")


def fake_su(job=None):
    from tests.test_sketchup_specialist import FakeSystem
    sys_ = FakeSystem(job=job, virtual=(EXE,))
    return SketchUp(sys_, Locations(exe=EXE, plugins_dir=Path("C:/SU/Plugins"), vray_exe=Path("C:/SU/vray.exe"))), sys_


@pytest.fixture(autouse=True)
def repo_falso(tmp_path, monkeypatch):
    fake = tmp_path / "repo"
    (fake / "artifacts").mkdir(parents=True)
    (fake / "fixtures").mkdir()
    monkeypatch.setattr(paths, "REPO_ROOT", fake)
    return fake


# --- guardas antes de subir o SketchUp -----------------------------------------------------------------------------------

def test_plano_adulterado_nao_sobe_o_sketchup(tmp_path):
    par = parent_plan()
    plan = shaker_plan(par)
    plan["parts"][4]["max_m"][1] += 0.004
    with pytest.raises(ShakerPlanRefused) as exc:
        ss.materialize_shaker(plan, par, tmp_path / "o.skp", base_skp=tmp_path / "b.skp", su=Boom())
    assert exc.value.findings[0]["code"] == "SIGNATURE_MISMATCH"


def test_pai_alterado_depois_do_plano_nao_sobe_o_sketchup(tmp_path):
    par = parent_plan()
    plan = shaker_plan(par)
    other = parent_plan(rot=30)
    with pytest.raises(ShakerPlanRefused) as exc:
        ss.materialize_shaker(plan, other, tmp_path / "o.skp", base_skp=tmp_path / "b.skp", su=Boom())
    assert exc.value.findings[0]["code"] == "PARENT_PLAN_CHANGED"


def test_plano_do_gabinete_legado_nao_e_aceito_pelo_materializador_shaker(tmp_path):
    par = parent_plan()
    with pytest.raises(ShakerPlanRefused):
        ss.materialize_shaker(par, par, tmp_path / "o.skp", base_skp=tmp_path / "b.skp", su=Boom())


@pytest.mark.parametrize("sub", ["artifacts/x/out.skp", "fixtures/out.skp"])
def test_destino_em_artifacts_ou_fixtures_e_recusado(repo_falso, tmp_path, sub):
    base = tmp_path / "b.skp"
    base.write_bytes(b"SKP")
    par = parent_plan()
    assert ss.materialize_shaker(shaker_plan(par), par, repo_falso / sub, base_skp=base, su=Boom())["status"] == "REFUSED"


def test_base_inexistente_destino_existente_e_extensao_errada(tmp_path):
    par = parent_plan()
    plan = shaker_plan(par)
    assert ss.materialize_shaker(plan, par, tmp_path / "o.skp", base_skp=tmp_path / "nao.skp", su=Boom())["status"] == "ERROR"
    base = tmp_path / "b.skp"
    base.write_bytes(b"SKP")
    ja = tmp_path / "ja.skp"
    ja.write_bytes(b"X")
    assert ss.materialize_shaker(plan, par, ja, base_skp=base, su=Boom())["status"] == "REFUSED"
    assert ss.materialize_shaker(plan, par, tmp_path / "o.txt", base_skp=base, su=Boom())["status"] == "ERROR"


# --- fiacao Python -> job Ruby -------------------------------------------------------------------------------------------

def test_comando_usa_o_job_shaker_numa_copia_e_nao_altera_a_base(tmp_path):
    base = tmp_path / "base.skp"
    base.write_bytes(b"SKP-PAI")
    par = parent_plan()
    plan = shaker_plan(par)
    seen = {}

    def job(cmd, env, handle):
        seen["cmd"] = cmd
        seen["params"] = json.loads(Path(env["SKMCP_PARAMS"]).read_text("utf-8"))
        Path(cmd[1]).write_bytes(b"SKP-SHAKER")
        Path(env["SKMCP_RESULT"]).write_text(json.dumps({"ok": True, "saved": True, "built": True}), "utf-8")

    su, _ = fake_su(job)
    out = tmp_path / "res" / "cab.skp"
    res = ss.materialize_shaker(plan, par, out, base_skp=base, mode="interactive", su=su)
    assert res["status"] == "OK", res
    cmd = seen["cmd"]
    assert cmd[1] == str(out.resolve()) and cmd[2] == "-RubyStartup" and cmd[3].endswith("shaker_build.rb")
    assert seen["params"]["plan"]["signature"] == plan["signature"] and seen["params"]["edits"] is None
    assert base.read_bytes() == b"SKP-PAI" and out.read_bytes() == b"SKP-SHAKER"


def test_job_que_diz_ok_sem_gravar_ou_que_morre_nao_deixa_copia_com_cara_de_resultado(tmp_path):
    base = tmp_path / "b.skp"
    base.write_bytes(b"SKP")
    par = parent_plan()
    plan = shaker_plan(par)

    def no_save(cmd, env, handle):
        Path(env["SKMCP_RESULT"]).write_text(json.dumps({"ok": True, "saved": False}), "utf-8")

    su, _ = fake_su(no_save)
    res = ss.materialize_shaker(plan, par, tmp_path / "o1.skp", base_skp=base, mode="interactive", su=su)
    assert res["status"] == "FAILED" and not (tmp_path / "o1.skp").exists()

    def dies(cmd, env, handle):
        handle.returncode = 1

    su, _ = fake_su(dies)
    res = ss.materialize_shaker(plan, par, tmp_path / "o2.skp", base_skp=base, mode="interactive", su=su)
    assert res["status"] == "SU_EXITED" and not (tmp_path / "o2.skp").exists() and base.read_bytes() == b"SKP"


# --- verificador plano x modelo -----------------------------------------------------------------------------------------

def inspected_from(par, plan, *, fp="fp0"):
    def part(p, plan_, dict_sig, defs):
        d = defs.get(p["id"])
        return {"name": p["id"], "part_id": p["id"], "role": p["role"], "definition": d[0] if d else "Def_" + p["id"],
                "definition_instances": d[1] if d else 1, "manifold": True, "tag": f"Cabinet_{p['role']}",
                "material": p["material"], "attr_material": p["material"], "attr_grain": p["grain"], "attr_signature": dict_sig,
                "geometry": {"faces": 6, "edges": 12, "vertices": 8, "area_m2": 1.0},
                "world_corners_m": [list(c) for c in cabinet_su.expected_corners(plan_, p)], "pid": 1}

    def defs_of(pl):
        return {i: ("Def_" + d["key"], len(d["instances"])) for d in pl["definitions"] for i in d["instances"]}

    remaining = [part(p, par, par["signature"], defs_of(par)) for p in par["parts"] if p["id"] != plan["replaces_part"]]
    shaker = {"name": f"Shaker_{plan['request_id']}", "request_id": plan["request_id"], "parent_request_id": par["request_id"],
              "capability": plan["capability"]["id"], "capability_version": plan["capability"]["version"],
              "signature": plan["signature"], "parent_plan_signature": plan["parent_plan_signature"],
              "replaces_part": plan["replaces_part"], "source_verified": plan["origin_context"]["source_verified"],
              "tag": "Cabinet", "loose_faces": 0, "loose_edges": 0,
              "parts": [part(p, plan, plan["signature"], defs_of(plan)) for p in plan["parts"]]}
    cab = {"name": f"Cabinet_{par['request_id']}", "request_id": par["request_id"], "signature": par["signature"], "tag": "Cabinet",
           "loose_faces": 0, "loose_edges": 0, "parts": remaining, "shakers": [shaker]}
    return {"cabinets": [cab], "non_cabinet": {"count": 1, "fingerprint": fp, "items": 1}}


def _failed(par, plan, insp, **kw):
    rep = ss.verify_shaker(plan, par, insp, **kw)
    return {c["check"].split(":")[0] for c in rep["checks"] if not c["ok"]}


def test_verificador_aceita_modelo_igual_ao_plano_em_varias_poses():
    for rot in (0, 90, 30):
        par = parent_plan(rot)
        plan = shaker_plan(par)
        rep = ss.verify_shaker(plan, par, inspected_from(par, plan), baseline={"non_cabinet": {"count": 1, "fingerprint": "fp0"}})
        assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
        measured = next(c for c in rep["checks"] if c["check"] == "panel_recess_measured_in_model")
        assert measured["ok"] and "0.0040000" in measured["detail"]


def test_verificador_reprova_cada_defeito():
    par = parent_plan(30)
    plan = shaker_plan(par)

    def with_(fn, **kw):
        insp = inspected_from(par, plan)
        fn(insp)
        return _failed(par, plan, insp, **kw)

    sh = lambda i: i["cabinets"][0]["shakers"][0]  # noqa: E731
    assert "replaced_front_is_gone" in with_(lambda i: i["cabinets"][0]["parts"].append(
        {**copy.deepcopy(i["cabinets"][0]["parts"][0]), "part_id": plan["replaces_part"], "name": plan["replaces_part"]}))
    assert "other_parent_parts_untouched" in with_(lambda i: i["cabinets"][0]["parts"].pop())
    assert any(f.startswith("parent_part_corners") for f in with_(lambda i: i["cabinets"][0]["parts"][0]["world_corners_m"][0].__setitem__(0, 9.0)))
    assert "parent_signature_unchanged" in with_(lambda i: i["cabinets"][0].__setitem__("signature", "0" * 64))
    assert "exactly_one_shaker_group" in with_(lambda i: i["cabinets"][0]["shakers"].append(copy.deepcopy(sh(i))))
    assert "exactly_one_shaker_group" in with_(lambda i: i["cabinets"][0]["shakers"].clear())
    assert "part_ids_match_plan" in with_(lambda i: sh(i)["parts"].pop())
    assert "corners" in with_(lambda i: sh(i)["parts"][4]["world_corners_m"][0].__setitem__(0, sh(i)["parts"][4]["world_corners_m"][0][0] + 2e-5))
    assert "solid" in with_(lambda i: sh(i)["parts"][0].__setitem__("manifold", False))
    assert "material" in with_(lambda i: sh(i)["parts"][1].__setitem__("material", "outro"))
    assert "tag" in with_(lambda i: sh(i)["parts"][2].__setitem__("tag", "Layer0"))
    assert "name" in with_(lambda i: sh(i)["parts"][2].__setitem__("name", "x"))
    assert "signature_attribute" in with_(lambda i: sh(i).__setitem__("signature", "0" * 64))
    assert "capability_attributes" in with_(lambda i: sh(i).__setitem__("capability", "outra"))
    assert "parent_link_attributes" in with_(lambda i: sh(i).__setitem__("parent_plan_signature", "0" * 64))
    assert "source_verified_carried_not_flipped" in with_(lambda i: sh(i).__setitem__("source_verified", True))
    assert "no_loose_geometry" in with_(lambda i: sh(i).__setitem__("loose_faces", 1))
    assert "group_tag" in with_(lambda i: sh(i).__setitem__("tag", "Layer0"))
    base = {"non_cabinet": {"count": 1, "fingerprint": "fp0"}}
    assert "non_cabinet_unchanged" in with_(lambda i: i["non_cabinet"].__setitem__("fingerprint", "fpX"), baseline=base)


def test_recuo_e_medido_nas_coordenadas_do_modelo_nao_copiado_do_plano():
    """Painel faceando a moldura (recuo 0 no modelo) com um plano que pede 4 mm tem que reprovar, mesmo com os outros checks ok."""
    par = parent_plan(90)
    plan = shaker_plan(par)
    insp = inspected_from(par, plan)
    flush_plan = shaker_plan(par, panel={**load("fp046_shaker_valid_a.json")["panel"],
                                         "recess_from_frame_front": {"value": 0, "unit": "mm", "origin": "user_request"}})
    flush = inspected_from(par, flush_plan)
    insp["cabinets"][0]["shakers"][0]["parts"][4] = copy.deepcopy(flush["cabinets"][0]["shakers"][0]["parts"][4])
    failed = _failed(par, plan, insp)
    assert "panel_recess_measured_in_model" in failed and "panel_face_behind_frame_face" in failed


def test_verificador_reprova_definicao_compartilhada_que_nao_e():
    par = parent_plan()
    plan = shaker_plan(par)
    insp = inspected_from(par, plan)
    left = next(p for p in insp["cabinets"][0]["shakers"][0]["parts"] if p["name"].endswith("stile_left"))
    left["definition"] = "ShakerDef_isolada"
    assert any(c.startswith("definition_sharing") for c in _failed(par, plan, insp))


def test_local_y_desfaz_pose():
    pose = {"x": 2.0, "y": 1.0, "z": 0.0, "rotation_deg": 90.0}
    th = math.radians(90)
    world = [2.0 + math.cos(th) * 0.3 - math.sin(th) * 0.5, 1.0 + math.sin(th) * 0.3 + math.cos(th) * 0.5, 0.0]
    assert ss._local_y(pose, world) == pytest.approx(0.5)


# --- travas do Ruby (texto) ----------------------------------------------------------------------------------------------

def _code(text: str) -> str:
    return chr(10).join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def test_shaker_ruby_so_materializa_plano_ok_da_capacidade_shaker_sem_executar_nada_arbitrario():
    src = _code((RUBY / "shaker_build.rb").read_text("utf-8"))
    assert "shaker_door_plan.v1" in src and "shared.cabinet.front.shaker" in src and "plan['status'] == 'OK'" in src
    assert "plan['execution_authorized'] == false" in src and "parent_plan_signature" in src
    assert "start_operation" in src and "abort_operation" in src and "commit_operation" in src
    for forbidden in ("eval(", "system(", "`", "exec(", "File.delete", "FileUtils.rm", "Dir.rm", "IO.popen", "open-uri", "Net::HTTP",
                      "purge_unused", "model.entities.clear"):
        assert forbidden not in src, forbidden
    assert "NOT_SUPPORTED" in src and "make_unique" in src


def test_shaker_ruby_so_apaga_a_frente_substituida_e_o_proprio_subgrupo():
    src = _code((RUBY / "shaker_build.rb").read_text("utf-8"))
    assert src.count("erase!") == 2                                  # (1) subgrupo Shaker anterior do MESMO request_id; (2) a frente lisa
    assert "get_attribute(DICT, 'root') == true" in src and "plan['replaces_part']" in src
    assert "PlanShell" not in src and "Window_" not in src and "Floor_Group" not in src


def test_cabinet_ruby_legado_continua_protegido():
    src = _code((RUBY / "cabinet_build.rb").read_text("utf-8"))
    assert "shared.cabinet.parametric" in src and "shaker" not in src.lower()


def test_shaker_inspector_nao_modifica_nada():
    ins = _code((RUBY / "shaker_inspect.rb").read_text("utf-8"))
    for forbidden in ("erase!", "transform!", "start_operation", ".save", "entities.add", "make_unique", "clear!"):
        assert forbidden not in ins, f"o inspetor nao pode modificar: {forbidden}"


def test_shaker_ruby_remove_definicoes_orfas_da_execucao_anterior_antes_de_recriar():
    """Achado do L2 (s3): sem isso a reexecucao deixa 3 definicoes orfas e a nova leva vira '#1'."""
    src = _code((RUBY / "shaker_build.rb").read_text("utf-8"))
    assert 'start_with?("ShakerDef_#{request_id}_")' in src and "shk_drop_definition_if_unused" in src
    assert src.index("old.each(&:erase!)") < src.index('start_with?("ShakerDef_#{request_id}_")') < src.index("model.definitions.add(")
