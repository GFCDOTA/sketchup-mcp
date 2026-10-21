"""FP-043/P7 — fluxo vertical da cozinha (pedido -> gabinete) com SketchUp DUBLE: trace, bloqueios e negativos.

Prova a ORDEM, os bloqueios e a ausencia de autorizacao implicita. A prova real (SKP salvo/reaberto) e o L2 da P7
(artifacts/review/fp043/p7_kitchen_cabinet/). Escala da planta_74 -> marcador `planta74_scale`.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tests.test_cabinet_sketchup_driver import inspected_from
from tests.test_sketchup_specialist import FakeSystem
from tools.sketchup.process import Locations, SketchUp

pytestmark = pytest.mark.planta74_scale

ROOT = Path(__file__).resolve().parents[1]
EXE = Path("C:/SU/SketchUp.exe")


def _inputs(**over):
    def q(v, u, o="user_request"):
        return {"value": v, "unit": u, "origin": o}
    base = {
        "dimensions.width": q(600, "mm"), "dimensions.depth": q(560, "mm"), "dimensions.height": q(720, "mm"),
        "panels.side": q(18, "mm"), "panels.top_bottom": q(18, "mm"), "panels.back": q(6, "mm"), "panels.front": q(18, "mm"),
        "gaps.front_clearance": q(2, "mm"), "gaps.front_reveal": q(3, "mm"), "fronts.count": q(1, "count"), "shelf.count": q(0, "count"),
        "materials.carcass": q("mdf_branco", "text"), "materials.back": q("hdf_branco", "text"), "materials.front": q("mdf_carvalho", "text"),
        "pose.x": q(2.22, "m"), "pose.y": q(15.88, "m"), "pose.z": q(0.0, "m"), "pose.rotation_deg": q(0, "deg"),
    }
    base.update(over)
    return base


def _request(**kw):
    inputs = kw.pop("inputs", None) or _inputs()
    return {"request_id": "flow-test", "text": "gabinete de cozinha com frentes lisas", "room": "kitchen", "inputs": inputs,
            "materials": {"carcass": "mdf_branco", "back": "hdf_branco", "front": "mdf_carvalho"}, **kw}


class World:
    """SketchUp dublê: constroi/le o 'modelo' a partir do plano que o job recebeu."""

    def __init__(self, tmp_path, *, tamper=False, die_on_build=False):
        self.state = {"plan": None, "launches": []}
        self.tamper, self.die = tamper, die_on_build
        st = self.state

        def job(cmd, env, handle):
            st["launches"].append(Path(cmd[3]).name)
            params = json.loads(Path(env["SKMCP_PARAMS"]).read_text("utf-8"))
            if cmd[3].endswith("cabinet_build.rb"):
                if self.die:
                    handle.returncode = 1
                    return
                st["plan"] = params["plan"]
                Path(cmd[1]).write_bytes(b"SKP-WITH-CABINET")
                res = {"ok": True, "saved": True, "built": True, "sketchup_version": "26.0.429", "replaced_previous": 0}
            else:
                if st["plan"] is None:
                    res = {"ok": True, "cabinets": [], "non_cabinet": {"count": 3, "fingerprint": "fp0", "items": 3}}
                else:
                    res = {"ok": True, **inspected_from(st["plan"], baseline_fp="fp0")}
                    res["non_cabinet"]["count"] = 3
                    if self.tamper:
                        res["cabinets"][0]["parts"][0]["world_corners_m"][0][0] += 0.01
            Path(env["SKMCP_RESULT"]).write_text(json.dumps(res), "utf-8")
        sys_ = FakeSystem(job=job, virtual=(EXE,))
        self.su = SketchUp(sys_, Locations(exe=EXE, plugins_dir=Path("C:/SU/Plugins"), vray_exe=Path("C:/SU/vray.exe")))
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.base = tmp_path / "base.skp"
        self.base.write_bytes(b"SKP-SHELL-FURNISHED")
        self.out = tmp_path / "out"


def _run(world, req, **kw):
    from tools.rooms.kitchen.capabilities.cabinet_flow import run_request
    return run_request(req, out_dir=world.out, base_skp=world.base, su=world.su, mode="interactive", close_pids=False, **kw)


def _states(trace):
    return [(s["step"], s["status"]) for s in trace["steps"]]


# ------------------------------------------------------------------ positivo
def test_percurso_completo_gera_trace_na_ordem_e_evidencia_com_hashes(tmp_path):
    w = World(tmp_path)
    req = _request()
    snap = copy.deepcopy(req)
    t = _run(w, req)
    assert t["state"] == "DONE_L2_VERIFIED", t["steps"][-3:]
    assert [s["step"] for s in t["steps"]] == ["request", "project_room", "consensus_requirements", "knowledge", "specialist_plan",
                                                "capability", "parameters", "plan_validation", "allowlist", "baseline_inspect",
                                                "job", "reopen_inspection", "kitchen_anchor_after", "evidence"]
    assert t["execution_authorized"] is False and t["input_unchanged"] is True and req == snap
    ev = t["evidence"]
    assert ev["capability"]["id"] == "shared.cabinet.parametric" and len(ev["skp_sha256"]) == 64 and len(ev["consensus_sha256"]) == 64
    assert ev["non_cabinet_fingerprint_before"] == ev["non_cabinet_fingerprint_after"] == "fp0"
    assert [g["result"] for g in ev["gates"]] == ["PASS"] * 4 and "NOT_REVIEWED" in ev["visual_review"]
    k = next(s for s in t["steps"] if s["step"] == "knowledge")
    assert k["binding"] == "bind.kitchen.cabinet" and "cabinet.reusable-components" in k["recipe_ids"]
    assert all(v == "KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP" for v in k["recipe_states"].values())
    assert set(t["tools_used"]) <= set(json.loads((ROOT / "tools/rooms/kitchen/specialist.v1.json").read_text("utf-8"))["tool_allowlist"])
    assert (w.out / t["idempotency_key"][:12] / "manifest.json").is_file()
    assert w.base.read_bytes() == b"SKP-SHELL-FURNISHED"
    assert w.state["launches"] == ["cabinet_inspect.rb", "cabinet_build.rb", "cabinet_inspect.rb"]


def test_mesma_chave_de_idempotencia_nao_refaz_o_job(tmp_path):
    w = World(tmp_path)
    first = _run(w, _request())
    n = len(w.state["launches"])
    again = _run(w, _request())
    assert first["state"] == "DONE_L2_VERIFIED" and again["state"] == "ALREADY_DONE"
    assert len(w.state["launches"]) == n and again["skp_sha256"] == first["evidence"]["skp_sha256"]


def test_pedido_diferente_tem_chave_diferente(tmp_path):
    w = World(tmp_path)
    a = _run(w, _request())
    b = _run(w, _request(inputs=_inputs(**{"pose.x": {"value": 2.3, "unit": "m", "origin": "user_request"}})))
    assert a["idempotency_key"] != b["idempotency_key"] and b["state"] == "DONE_L2_VERIFIED"


# ------------------------------------------------------------------ negativos obrigatorios (nenhum sobe o SketchUp)
def _blocked(world, req, state):
    snap_req, base_before = copy.deepcopy(req), world.base.read_bytes()
    t = _run(world, req)
    assert t["state"] == state, t["steps"][-2:]
    assert world.state["launches"] == [] and not world.out.exists()                      # nada subiu, nada foi escrito
    assert req == snap_req and world.base.read_bytes() == base_before and t["input_unchanged"] is True
    assert "evidence" not in t and t["execution_authorized"] is False                  # rejeicao nao marca prova positiva
    return t


def test_shaker_no_fluxo_de_frentes_lisas_nao_vira_gabinete_liso_em_silencio(tmp_path):
    """FP-046/P5: a Shaker foi promovida, mas ESTE fluxo so materializa frente lisa."""
    # so com os insumos do gabinete liso: o especialista pede as medidas da porta (nada sobe)
    _blocked(World(tmp_path / "a"), _request(text="armario de cozinha com porta Shaker"), "BLOCKED_INPUT_INCOMPLETE")
    # com os insumos da Shaker tambem: o fluxo liso RECUSA em vez de construir a peca errada
    full = _inputs(**{f"shaker.{k}": {"value": v, "unit": "mm", "origin": "user_request"}
                      for k, v in (("frame.stile_width", 50), ("frame.rail_height", 50), ("frame.frame_thickness", 18),
                                   ("panel.thickness", 6), ("panel.recess_from_frame_front", 4))},
                    **{f"shaker.materials.{r}": {"value": "mdf_branco", "unit": "text", "origin": "user_request"} for r in ("frame", "panel")})
    t = _blocked(World(tmp_path / "b"), _request(text="armario de cozinha com porta Shaker", inputs=full), "BLOCKED_CAPABILITY_MISMATCH")
    assert "frentes lisas" in t["reason"] and "shaker_flow" in t["next_step"]


def test_ferramenta_fora_da_allowlist_e_bloqueada(tmp_path):
    _blocked(World(tmp_path), _request(tool="mcp:su_apply_edits"), "BLOCKED_TOOL_NOT_ALLOWED")


def test_allowlist_do_perfil_incompleta_bloqueia_antes_do_job(tmp_path, monkeypatch):
    from tools.rooms import specialists as sp
    real = sp.load_profile

    def trimmed(room, root=ROOT):
        p = real(room, root)
        p["tool_allowlist"] = [t for t in p["tool_allowlist"] if "sketchup.materialize" not in t]
        return p
    monkeypatch.setattr(sp, "load_profile", trimmed)
    _blocked(World(tmp_path), _request(), "BLOCKED_TOOL_NOT_ALLOWED")


def test_geometria_impossivel_e_bloqueada_pelo_plano(tmp_path):
    t = _blocked(World(tmp_path), _request(inputs=_inputs(**{"dimensions.width": {"value": 30, "unit": "mm", "origin": "user_request"}})),
                 "BLOCKED_PLAN_REFUSED")
    assert any(f["code"] == "INFEASIBLE_INNER_WIDTH" for f in t["findings"])


def test_entrada_sem_unidade_ou_origem_vira_pergunta_nao_execucao(tmp_path):
    bad = _inputs()
    del bad["dimensions.depth"]["unit"]
    t = _blocked(World(tmp_path), _request(inputs=bad), "BLOCKED_INPUT_INCOMPLETE")
    assert "dimensions.depth" in str(t["steps"][-1]["missing"]) and "unidade" in t["reason"]
    bad2 = _inputs()
    del bad2["dimensions.height"]["origin"]
    _blocked(World(tmp_path / "b"), _request(inputs=bad2), "BLOCKED_INPUT_INCOMPLETE")


def test_tentativa_de_alterar_arquitetura_e_bloqueada(tmp_path):
    _blocked(World(tmp_path), _request(text="gabinete de cozinha e remover a parede oeste"), "BLOCKED_ARCHITECTURE_CHANGE")
    _blocked(World(tmp_path / "b"), _request(touches=["walls"]), "BLOCKED_ARCHITECTURE_CHANGE")


def test_gabinete_na_zona_de_porta_ou_fora_da_cozinha_e_bloqueado_pelos_gates(tmp_path):
    t = _blocked(World(tmp_path), _request(inputs=_inputs(**{"pose.x": {"value": 0.5, "unit": "m", "origin": "user_request"},
                                                              "pose.y": {"value": 0.5, "unit": "m", "origin": "user_request"}})),
                 "BLOCKED_PLAN_REFUSED")
    assert any("architecture" in f["detail"] for f in t["findings"])


def test_pedido_de_outro_comodo_nao_chama_a_cozinha(tmp_path):
    _blocked(World(tmp_path), _request(text="gabinete do quarto com cama"), "BLOCKED_ROOM_MISMATCH")


# ------------------------------------------------------------------ job interrompido / verificacao reprovada
def test_job_interrompido_nao_deixa_resultado_nem_prova_positiva(tmp_path):
    w = World(tmp_path, die_on_build=True)
    t = _run(w, _request())
    assert t["state"] == "JOB_FAILED" and "evidence" not in t
    job = next(s for s in t["steps"] if s["step"] == "job")
    assert job["status"] == "FAILED" and job["unedited_copy_removed"] is True
    key_dir = w.out / t["idempotency_key"][:12]
    assert not (key_dir / "cabinet.skp").exists() and not (key_dir / "manifest.json").exists()
    assert w.base.read_bytes() == b"SKP-SHELL-FURNISHED"


def test_modelo_que_nao_bate_com_o_plano_reprova_e_nao_escreve_manifest(tmp_path):
    w = World(tmp_path, tamper=True)
    t = _run(w, _request())
    assert t["state"] == "VERIFY_FAILED"
    assert not (w.out / t["idempotency_key"][:12] / "manifest.json").exists()
    assert next(s for s in t["steps"] if s["step"] == "reopen_inspection")["failed"]


def test_cada_pid_subido_e_fechado_so_pelo_pid(tmp_path, monkeypatch):
    from tools.sketchup import jobs
    closed = []
    monkeypatch.setattr(jobs, "close", lambda **kw: closed.append(kw) or {"status": "CLOSED"})
    w = World(tmp_path)
    from tools.rooms.kitchen.capabilities.cabinet_flow import run_request
    t = run_request(_request(), out_dir=w.out, base_skp=w.base, su=w.su, mode="interactive", close_pids=True)
    assert t["state"] == "DONE_L2_VERIFIED" and len(closed) == len(t["pids"]) == 3
    assert all(set(c) == {"pid", "force", "confirm"} for c in closed)           # sempre por PID, nunca por nome


def test_base_ou_consensus_ausentes_bloqueiam(tmp_path):
    from tools.rooms.kitchen.capabilities.cabinet_flow import run_request
    t = run_request(_request(), out_dir=tmp_path / "o", base_skp=tmp_path / "nao.skp", su=World(tmp_path).su, close_pids=False)
    assert t["state"] == "BLOCKED_INPUT_MISSING"


def test_inputs_para_requisicao_do_gabinete_nao_inventa_campo():
    from tools.rooms.kitchen.capabilities.cabinet_flow import inputs_to_cabinet_request
    inputs = _inputs()
    del inputs["gaps.front_reveal"]
    out = inputs_to_cabinet_request("x", inputs, {"carcass": "a", "back": "b", "front": "c"})
    assert "front_reveal" not in out["gaps"] and out["fronts"] == {"count": 1}
    from tools.rooms.shared.cabinet import plan_cabinet
    assert plan_cabinet(out)["status"] == "REFUSED"                                # o plano recusa a falta, nao completa
