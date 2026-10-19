"""FP-043/P6b — driver da materializacao do gabinete (SEM SketchUp): guardas, fiacao e verificador.

Prova que: plano nao validado nunca sobe o SketchUp; a saida respeita as regras de destino; o comando usa o job Ruby da
capacidade; `verify` reprova cada defeito geometrico; o Ruby tem as travas declaradas. A prova de GEOMETRIA no SketchUp
real e a bateria L2 (artifacts/review/fp043/...), nao este arquivo.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from tools.rooms.shared.cabinet import PlanRefused, plan_cabinet
from tools.rooms.shared.cabinet import sketchup as cs
from tools.sketchup import batch, paths
from tools.sketchup.process import Locations, SketchUp

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures/synthetic_cabinets"
EXE = Path("C:/SU/SketchUp.exe")
RUBY = ROOT / "tools/rooms/shared/cabinet/ruby"


def req(name="valid_b_tall_900", **kw):
    r = json.loads((FIX / f"{name}.json").read_text("utf-8"))
    r.update(kw)
    return r


class Boom:
    """Dublê de SketchUp: qualquer uso falha — prova que o driver nao tocou o SketchUp."""

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


# ------------------------------------------------------------------ guardas antes de subir o SketchUp
def test_plano_recusado_nao_sobe_o_sketchup(tmp_path):
    bad = plan_cabinet(req("invalid_impossible"))
    with pytest.raises(PlanRefused):
        cs.materialize(bad, tmp_path / "out.skp", su=Boom())


def test_plano_adulterado_nao_sobe_o_sketchup(tmp_path):
    plan = plan_cabinet(req())
    plan["parts"][0]["max_m"][0] += 0.01
    with pytest.raises(PlanRefused) as exc:
        cs.materialize(plan, tmp_path / "out.skp", su=Boom())
    assert exc.value.findings[0]["code"] == "SIGNATURE_MISMATCH"


@pytest.mark.parametrize("sub", ["artifacts/x/out.skp", "fixtures/out.skp"])
def test_destino_em_artifacts_ou_fixtures_e_recusado(repo_falso, sub):
    res = cs.materialize(plan_cabinet(req()), repo_falso / sub, su=Boom())
    assert res["status"] == "REFUSED"


def test_destino_existente_ou_sem_extensao_skp_e_recusado(tmp_path):
    exists = tmp_path / "ja.skp"
    exists.write_bytes(b"SKP")
    assert cs.materialize(plan_cabinet(req()), exists, su=Boom())["status"] == "REFUSED"
    assert cs.materialize(plan_cabinet(req()), tmp_path / "out.txt", su=Boom())["status"] == "ERROR"


def test_base_inexistente_e_erro_sem_subir_o_sketchup(tmp_path):
    assert cs.materialize(plan_cabinet(req()), tmp_path / "o.skp", base_skp=tmp_path / "nao.skp", su=Boom())["status"] == "ERROR"


# ------------------------------------------------------------------ fiacao Python -> job Ruby
def test_comando_usa_o_job_da_capacidade_na_ordem_certa_e_nao_altera_a_base(tmp_path):
    base = tmp_path / "base.skp"
    base.write_bytes(b"SKP-BASE")
    plan = plan_cabinet(req())
    seen = {}

    def job(cmd, env, handle):
        seen["cmd"], seen["env"] = cmd, env
        seen["params"] = json.loads(Path(env["SKMCP_PARAMS"]).read_text("utf-8"))
        Path(cmd[1]).write_bytes(b"SKP-SAVED")                   # o Ruby salvaria a copia
        Path(env["SKMCP_RESULT"]).write_text(json.dumps({"ok": True, "saved": True, "built": True}), "utf-8")

    su, _ = fake_su(job)
    out = tmp_path / "res" / "cab.skp"
    res = cs.materialize(plan, out, base_skp=base, mode="interactive", su=su)
    assert res["status"] == "OK", res
    cmd = seen["cmd"]
    assert cmd[0] == str(EXE) and cmd[1] == str(out.resolve()) and cmd[2] == "-RubyStartup" and cmd[3].endswith("cabinet_build.rb")
    assert seen["params"]["plan"]["signature"] == plan["signature"] and seen["params"]["edits"] is None
    assert base.read_bytes() == b"SKP-BASE"                      # a base nunca e aberta nem alterada
    assert out.read_bytes() == b"SKP-SAVED"


def test_ruby_que_diz_ok_sem_gravar_vira_failed(tmp_path):
    def job(cmd, env, handle):
        Path(env["SKMCP_RESULT"]).write_text(json.dumps({"ok": True, "saved": False}), "utf-8")
    su, _ = fake_su(job)
    base = tmp_path / "b.skp"
    base.write_bytes(b"SKP")
    res = cs.materialize(plan_cabinet(req()), tmp_path / "o.skp", base_skp=base, mode="interactive", su=su)
    assert res["status"] == "FAILED"


def test_run_job_aceita_script_fora_de_tools_sketchup_ruby(tmp_path):
    skp = tmp_path / "in.skp"
    skp.write_bytes(b"SKP")

    def job(cmd, env, handle):
        Path(env["SKMCP_RESULT"]).write_text(json.dumps({"ok": True}), "utf-8")
    su, _ = fake_su(job)
    custom = tmp_path / "meu_job.rb"
    custom.write_text("# job", encoding="utf-8")
    res = batch.run_job(su, "meu_job", out_dir=tmp_path / "o", skp_in=skp, params={}, mode="interactive", script=custom)
    assert res["status"] == "OK"
    default = batch.run_job(su, "inspect_model", out_dir=tmp_path / "o2", skp_in=skp, params={}, mode="interactive")
    assert default["status"] == "ERROR" or default["status"] in ("OK", "TIMEOUT", "DONE", "FAILED", "SU_EXITED")


# ------------------------------------------------------------------ verificador plano x modelo
def inspected_from(plan, *, baseline_fp="fp0"):
    parts = []
    for p in plan["parts"]:
        parts.append({"name": p["id"], "part_id": p["id"], "role": p["role"], "definition": "CabinetDef_x_" + p["role"],
                      "definition_instances": 2 if p["name"].startswith(("side", "front_")) else 1,
                      "manifold": True, "tag": f"Cabinet_{p['role']}", "material": p["material"], "attr_material": p["material"],
                      "attr_grain": p["grain"], "attr_signature": plan["signature"],
                      "geometry": {"faces": 6, "edges": 12, "vertices": 8, "area_m2": 1.0},
                      "world_corners_m": [list(c) for c in cs.expected_corners(plan, p)], "pid": 1})
    cab = {"name": f"Cabinet_{plan['request_id']}", "request_id": plan["request_id"], "capability": plan["capability"]["id"],
           "capability_version": plan["capability"]["version"], "signature": plan["signature"], "tag": "Cabinet",
           "loose_faces": 0, "loose_edges": 0, "parts": parts}
    # definicoes: pecas equivalentes compartilham o nome; as demais, nome proprio
    for d in plan["definitions"]:
        for i in d["instances"]:
            next(x for x in parts if x["part_id"] == i)["definition"] = "CabinetDef_" + d["key"]
            next(x for x in parts if x["part_id"] == i)["definition_instances"] = len(d["instances"])
    return {"cabinets": [cab], "non_cabinet": {"count": 1, "fingerprint": baseline_fp, "items": 1}}


def test_verificador_aceita_modelo_igual_ao_plano_em_varias_poses():
    for rot in (0, 90, 30):
        r = req("valid_b_tall_900")
        r["pose"]["rotation_deg"]["value"] = rot
        plan = plan_cabinet(r)
        rep = cs.verify(plan, inspected_from(plan), baseline={"non_cabinet": {"count": 1, "fingerprint": "fp0"}})
        assert rep["ok"], [c for c in rep["checks"] if not c["ok"]]
        assert rep["max_corner_error_m"] == pytest.approx(0, abs=1e-12)


def _fails(plan, insp, **kw):
    rep = cs.verify(plan, insp, **kw)
    return {c["check"].split(":")[0] for c in rep["checks"] if not c["ok"]}


def test_verificador_reprova_cada_defeito_geometrico_e_de_estado():
    plan = plan_cabinet(req())

    def with_(fn, **kw):
        insp = inspected_from(plan)
        fn(insp)
        return _fails(plan, insp, **kw)

    assert "corners" in with_(lambda i: i["cabinets"][0]["parts"][0]["world_corners_m"][0].__setitem__(0, 9.0))
    d = with_(lambda i: i["cabinets"][0]["parts"][0]["world_corners_m"][0].__setitem__(0, i["cabinets"][0]["parts"][0]["world_corners_m"][0][0] + 2e-5))
    assert "corners" in d                                                          # 0,02 mm ja reprova
    assert "part_ids_match_plan" in with_(lambda i: i["cabinets"][0]["parts"].pop())
    assert "part_ids_match_plan" in with_(lambda i: i["cabinets"][0]["parts"].append(copy.deepcopy(i["cabinets"][0]["parts"][0])))
    assert "solid" in with_(lambda i: i["cabinets"][0]["parts"][1].__setitem__("manifold", False))
    assert "solid" in with_(lambda i: i["cabinets"][0]["parts"][1]["geometry"].__setitem__("faces", 5))
    assert "material" in with_(lambda i: i["cabinets"][0]["parts"][2].__setitem__("material", "outro"))
    assert "tag" in with_(lambda i: i["cabinets"][0]["parts"][2].__setitem__("tag", "Layer0"))
    assert "name" in with_(lambda i: i["cabinets"][0]["parts"][2].__setitem__("name", "renomeado"))
    assert "signature_attribute" in with_(lambda i: i["cabinets"][0].__setitem__("signature", "0" * 64))
    assert "capability_attribute" in with_(lambda i: i["cabinets"][0].__setitem__("capability", "outra"))
    assert "no_loose_geometry_in_root" in with_(lambda i: i["cabinets"][0].__setitem__("loose_faces", 1))
    assert "exactly_one_cabinet_root" in with_(lambda i: i["cabinets"].append(copy.deepcopy(i["cabinets"][0])))
    assert "exactly_one_cabinet_root" in with_(lambda i: i["cabinets"].clear())
    base = {"non_cabinet": {"count": 1, "fingerprint": "fp0"}}
    assert "non_cabinet_unchanged" in with_(lambda i: i["non_cabinet"].__setitem__("fingerprint", "fpX"), baseline=base)
    assert "non_cabinet_unchanged" in with_(lambda i: i["non_cabinet"].__setitem__("count", 2), baseline=base)


def test_verificador_reprova_definicao_que_deveria_ser_compartilhada_e_nao_e():
    plan = plan_cabinet(req())
    insp = inspected_from(plan)
    parts = insp["cabinets"][0]["parts"]
    left = next(p for p in parts if p["name"].endswith("side_left"))
    left["definition"] = "CabinetDef_isolada"
    assert any(f.startswith("definition_sharing") for f in {c["check"] for c in cs.verify(plan, insp)["checks"] if not c["ok"]})


def test_gabarito_de_vertices_gira_pela_pose():
    plan = plan_cabinet(req())
    part = plan["parts"][0]
    pts = cs.expected_corners(plan, part)
    assert len(pts) == 8 and len({tuple(round(v, 9) for v in p) for p in pts}) == 8
    th = math.radians(plan["pose"]["rotation_deg"])
    x0 = part["min_m"]
    assert pts[0] == pytest.approx((plan["pose"]["x"] + math.cos(th) * x0[0] - math.sin(th) * x0[1],
                                    plan["pose"]["y"] + math.sin(th) * x0[0] + math.cos(th) * x0[1], plan["pose"]["z"] + x0[2]))


# ------------------------------------------------------------------ contrato do Ruby (texto): travas declaradas
def _code(text: str) -> str:
    """Ruby sem comentarios de linha inteira (os comentarios citam coisas como `eval` ao explicar)."""
    return chr(10).join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def test_ruby_so_materializa_plano_ok_da_capacidade_e_nao_executa_nada_arbitrario():
    src = _code((RUBY / "cabinet_build.rb").read_text("utf-8"))
    assert "plan['status'] == 'OK'" in src and "shared.cabinet.parametric" in src and "cabinet_assembly_plan.v1" in src
    assert "start_operation" in src and "abort_operation" in src and "commit_operation" in src
    for forbidden in ("eval(", "system(", "`", "exec(", "File.delete", "FileUtils.rm", "Dir.rm", "IO.popen", "open-uri", "Net::HTTP"):
        assert forbidden not in src, forbidden
    assert "NOT_SUPPORTED" in src                                                    # veio: nao declara PASS
    assert "erase!" in src and "get_attribute(DICT, 'root') == true" in src         # so apaga o que ELE criou (por atributo)
    ins = _code((RUBY / "cabinet_inspect.rb").read_text("utf-8"))
    for forbidden in ("erase!", "transform!", "start_operation", ".save", "entities.add", "make_unique"):
        assert forbidden not in ins, f"o inspetor nao pode modificar: {forbidden}"


def test_ruby_nao_toca_entidades_de_arquitetura():
    src = _code((RUBY / "cabinet_build.rb").read_text("utf-8"))
    assert "PlanShell" not in src and "Window_" not in src and "Floor_Group" not in src
    # unica remocao: grupos de gabinete com request_id igual (reexecucao controlada)
    assert src.count("erase!") == 1


# ------------------------------------------------------------------ job interrompido/falho nao deixa resultado
def test_job_que_sai_sem_resultado_nao_deixa_copia_que_pareca_resultado(tmp_path):
    base = tmp_path / "base.skp"
    base.write_bytes(b"SKP-BASE")

    def job(cmd, env, handle):          # o SketchUp morre no meio: nao escreve resultado
        handle.returncode = 1
    su, _ = fake_su(job)
    out = tmp_path / "res" / "cab.skp"
    res = cs.materialize(plan_cabinet(req()), out, base_skp=base, mode="interactive", su=su)
    assert res["status"] == "SU_EXITED" and not out.exists() and res["unedited_copy_removed"] is True
    assert base.read_bytes() == b"SKP-BASE"


def test_job_que_falha_no_ruby_tambem_descarta_a_copia(tmp_path):
    base = tmp_path / "base.skp"
    base.write_bytes(b"SKP-BASE")

    def job(cmd, env, handle):
        Path(env["SKMCP_RESULT"]).write_text(json.dumps({"ok": False, "error": "RuntimeError: x"}), "utf-8")
    su, _ = fake_su(job)
    out = tmp_path / "res" / "cab.skp"
    res = cs.materialize(plan_cabinet(req()), out, base_skp=base, mode="interactive", su=su)
    assert res["status"] == "FAILED" and not out.exists()


def test_copia_que_nao_da_para_apagar_ganha_marcador(tmp_path, monkeypatch):
    out = tmp_path / "cab.skp"
    out.write_bytes(b"SKP")
    monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: (_ for _ in ()).throw(PermissionError("aberta")))
    res = {"status": "SU_EXITED", "reason": "x", "pid": 7}
    cs._discard_unedited(out, res)
    assert res["unedited_copy_removed"] is False and Path(res["unedited_copy_marker"]).exists()
