"""Especialista em SketchUp (tools/sketchup) — contrato sem SketchUp.

`FakeSystem` faz o papel do Windows + SketchUp.exe: lista processos, registra
taskkill por PID e, no `popen`, faz o que o job Ruby faria (escrever o JSON
de resultado). Assim a fiação Python → lote → resultado é provada aqui; o
lado Ruby que depende da API do SketchUp só se prova numa máquina com SU.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools.sketchup import batch, jobs, ops, paths
from tools.sketchup.process import Locations, SketchUp, parse_tasklist

EXE = Path("C:/SU/SketchUp.exe")
PLUGINS = Path("C:/SU/Plugins")
VRAY = Path("C:/SU/vray.exe")

TASKLIST_TWO = (
    '"SketchUp.exe","4242","Console","1","812.344 K"\n'
    '"SketchUp.exe","5150","Console","1","1.024 K"\n'
)


class FakeHandle:
    def __init__(self, pid: int, on_wait=None):
        self.pid = pid
        self.returncode = None
        self.terminated = False
        self._on_wait = on_wait

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15


class FakeSystem:
    def __init__(self, *, platform="win32", tasklist="", virtual=(EXE, PLUGINS / "autorun_consume.rb", VRAY),
                 job=None):
        self._platform = platform
        self._tasklist = tasklist
        self.virtual = {str(p) for p in virtual}
        self.killed: list[tuple[int, bool]] = []
        self.launched: list[tuple[list[str], dict]] = []
        self.handles: list[FakeHandle] = []
        self.clock = 0.0
        # job(cmd, env, handle) roda "dentro do SketchUp" no primeiro sleep
        self.job = job
        self._pending = None

    def platform(self):
        return self._platform

    def exists(self, path):
        return str(path) in self.virtual or Path(path).exists()

    def tasklist(self):
        return self._tasklist

    def taskkill_pid(self, pid, *, force):
        self.killed.append((pid, force))
        self._tasklist = "\n".join(ln for ln in self._tasklist.splitlines() if f'"{pid}"' not in ln)
        return 0

    def popen(self, cmd, env=None):
        h = FakeHandle(9000 + len(self.handles))
        self.launched.append((cmd, env or {}))
        self.handles.append(h)
        self._pending = (cmd, env or {}, h)
        return h

    def now(self):
        return self.clock

    def sleep(self, s):
        self.clock += s
        if self._pending and self.job:
            cmd, env, h = self._pending
            self._pending = None
            self.job(cmd, env, h)


def su_with(system: FakeSystem) -> SketchUp:
    return SketchUp(system, Locations(exe=EXE, plugins_dir=PLUGINS, vray_exe=VRAY))


def ruby_writes(result: dict, *, then_exit=False):
    """Simula o job Ruby: lê os params e escreve o resultado no SKMCP_RESULT."""
    seen = {}

    def job(cmd, env, handle):
        seen["params"] = json.loads(Path(env["SKMCP_PARAMS"]).read_text("utf-8"))
        seen["env"] = env
        seen["cmd"] = cmd
        Path(env["SKMCP_RESULT"]).write_text(json.dumps(result), "utf-8")
        if then_exit:
            handle.returncode = 0

    return job, seen


@pytest.fixture(autouse=True)
def repo_temporario(tmp_path, monkeypatch):
    """Todo caminho relativo cai num repo FALSO. Se uma regra de destino
    quebrar, o estrago fica no tmp — não em artifacts/ de verdade (já aconteceu
    numa sabotagem de teste antes desta fixture existir)."""
    fake = tmp_path / "repo"
    (fake / "artifacts" / "planta_74").mkdir(parents=True)
    (fake / "fixtures").mkdir()
    monkeypatch.setattr(paths, "REPO_ROOT", fake)
    return fake


@pytest.fixture
def skp(tmp_path):
    p = tmp_path / "in.skp"
    p.write_bytes(b"SKP")
    return p


# -- processo -----------------------------------------------------------------

def test_tasklist_parse_ignora_linha_info_e_le_memoria():
    rows = parse_tasklist("INFO: No tasks are running which match the specified criteria.\n")
    assert rows == []
    rows = parse_tasklist(TASKLIST_TWO)
    assert rows == [{"pid": 4242, "mem_kb": 812344}, {"pid": 5150, "mem_kb": 1024}]


def test_fora_do_windows_status_diz_unavailable_sem_fingir():
    su = su_with(FakeSystem(platform="linux"))
    st = su.status()
    assert st["platform_supported"] is False and st["instances"] == []
    assert "Windows" in su.unavailable()
    assert su.open(Path("x.skp"))["status"] == "UNAVAILABLE"


def test_close_sem_confirm_so_diz_o_que_fecharia():
    sys_ = FakeSystem(tasklist=TASKLIST_TWO)
    r = su_with(sys_).close(all_instances=True)
    assert r["status"] == "CONFIRMATION_REQUIRED" and r["would_close"] == [4242, 5150]
    assert sys_.killed == []


def test_close_confirmado_fecha_por_pid_gracioso():
    sys_ = FakeSystem(tasklist=TASKLIST_TWO)
    r = su_with(sys_).close(pid=4242, confirm=True)
    assert r["status"] == "CLOSED" and r["closed"] == [4242]
    assert sys_.killed == [(4242, False)]  # sem /F


def test_close_pid_que_nao_e_sketchup_recusa():
    sys_ = FakeSystem(tasklist=TASKLIST_TWO)
    r = su_with(sys_).close(pid=1, confirm=True)
    assert r["status"] == "ERROR" and sys_.killed == []


def test_close_exige_alvo_explicito():
    r = su_with(FakeSystem(tasklist=TASKLIST_TWO)).close(confirm=True)
    assert r["status"] == "ERROR"


def test_nenhum_codigo_do_especialista_mata_por_nome_de_imagem():
    for f in Path("tools/sketchup").rglob("*.py"):
        assert '"/IM"' not in f.read_text("utf-8"), f


# -- caminhos -----------------------------------------------------------------

def test_destino_em_fixtures_ou_artifacts_e_recusado(tmp_path):
    for bad in ("fixtures/x/out.skp", "artifacts/planta_74/planta_74.skp", "artifacts"):
        with pytest.raises(paths.OutputPathRefused):
            paths.check_output(bad)
    assert paths.check_output("runs/x/out.skp").name == "out.skp"


def test_destino_igual_a_entrada_e_recusado(skp):
    with pytest.raises(paths.OutputPathRefused):
        paths.check_output(skp, inputs=(skp,))


# -- schema de edição -----------------------------------------------------------

def test_ops_validas_normalizam(tmp_path):
    comp = tmp_path / "chair.skp"
    comp.write_bytes(b"x")
    norm = ops.validate([
        {"op": "set_material", "target": {"name": "Cama"}, "color": [0, 0, 0]},
        {"op": "move", "target": {"persistent_id": 77}, "by_m": [0.3, 0, 0]},
        {"op": "insert_component", "skp_path": str(comp), "position_m": [1, 2, 0]},
    ])
    assert norm[0]["target"] == {"name": "Cama", "expect": "one"}
    assert norm[2]["rotation_deg"] == 0


def test_ops_coletam_todos_os_erros_de_uma_vez():
    with pytest.raises(ops.OpsInvalid) as e:
        ops.validate([
            {"op": "move", "target": {"name": "Cama"}},                       # sem medida
            {"op": "set_material", "target": {"name": "x"}, "color": [300, 0, 0]},
            {"op": "teleport", "target": {"name": "x"}},
            {"op": "rename", "target": {"name": "x"}, "name": "PlanShell_fake"},
        ])
    assert len(e.value.errors) == 4


def test_arquitetura_do_pdf_nao_aceita_edicao_geometrica():
    for kind, extra in (("move", {"by_m": [1, 0, 0]}), ("rotate", {"degrees": 90}), ("delete", {})):
        with pytest.raises(ops.OpsInvalid, match="Hard Rule #1"):
            ops.validate([{"op": kind, "target": {"name": "PlanShell_Group"}, **extra}])
    # aparência é permitida
    assert ops.validate([{"op": "set_material", "target": {"name": "PlanShell_Group"},
                          "color": [200, 200, 200]}])


# -- lote ---------------------------------------------------------------------

def test_modo_ci_e_headless_e_explicito_vence():
    assert batch.resolve_mode(env={"CI": "true"}) == "headless"
    assert batch.resolve_mode(env={}) == "interactive"
    assert batch.resolve_mode("headless", env={}) == "headless"
    with pytest.raises(ValueError):
        batch.resolve_mode("turbo", env={})


def test_job_ok_le_o_resultado_e_monta_o_comando_na_ordem_certa(tmp_path, skp):
    job, seen = ruby_writes({"ok": True, "nodes": []})
    sys_ = FakeSystem(job=job)
    r = batch.run_job(su_with(sys_), "inspect_model", out_dir=tmp_path / "o", skp_in=skp,
                      params={"max_depth": 2}, mode="interactive")
    assert r["status"] == "OK" and r["result"]["nodes"] == []
    cmd = seen["cmd"]
    assert cmd[0] == str(EXE) and cmd[1] == str(skp.resolve()) and cmd[2] == "-RubyStartup"
    assert cmd[3].endswith("inspect_model.rb")
    assert seen["params"]["max_depth"] == 2 and "out_dir" in seen["params"]
    assert seen["env"]["SKMCP_QUIT"] == "0"
    assert r["su_left_running"] is True and not sys_.handles[0].terminated


def test_headless_pede_quit_e_fecha_so_o_proprio_filho(tmp_path, skp):
    job, seen = ruby_writes({"ok": True})
    sys_ = FakeSystem(job=job, tasklist=TASKLIST_TWO)
    r = batch.run_job(su_with(sys_), "inspect_model", out_dir=tmp_path, skp_in=skp,
                      params={}, mode="headless")
    assert seen["env"]["SKMCP_QUIT"] == "1"
    assert sys_.handles[0].terminated and sys_.killed == []  # as janelas 4242/5150 intactas
    assert r["su_left_running"] is False


def test_job_que_falha_no_ruby_vira_failed_com_erro(tmp_path, skp):
    job, _ = ruby_writes({"ok": False, "error": "RuntimeError: nenhuma entidade casa"})
    r = batch.run_job(su_with(FakeSystem(job=job)), "apply_edits", out_dir=tmp_path, skp_in=skp,
                      params={}, mode="interactive")
    assert r["status"] == "FAILED" and "casa" in r["result"]["error"]


def test_sketchup_que_fecha_sem_resultado_e_su_exited(tmp_path, skp):
    def job(cmd, env, handle):
        handle.returncode = 1

    r = batch.run_job(su_with(FakeSystem(job=job)), "inspect_model", out_dir=tmp_path, skp_in=skp,
                      params={}, mode="interactive")
    assert r["status"] == "SU_EXITED"


def test_timeout_em_interactive_nao_mata_nada(tmp_path, skp):
    sys_ = FakeSystem()
    r = batch.run_job(su_with(sys_), "inspect_model", out_dir=tmp_path, skp_in=skp, params={},
                      mode="interactive", timeout_s=5)
    assert r["status"] == "TIMEOUT" and not sys_.handles[0].terminated


def test_resultado_velho_nao_conta_como_desta_execucao(tmp_path, skp):
    (tmp_path / "inspect_model_result.json").write_text('{"ok": true}', "utf-8")
    r = batch.run_job(su_with(FakeSystem()), "inspect_model", out_dir=tmp_path, skp_in=skp,
                      params={}, mode="interactive", timeout_s=3)
    assert r["status"] == "TIMEOUT"


def test_attach_nao_sobe_sketchup(tmp_path, skp):
    sys_ = FakeSystem()
    r = batch.run_job(su_with(sys_), "inspect_model", out_dir=tmp_path, skp_in=skp, params={},
                      mode="attach")
    assert r["status"] == "UNAVAILABLE" and sys_.launched == []


# -- verbos -------------------------------------------------------------------

def _salva_no_modelo_aberto(result=None, check=None):
    """Simula o apply_edits.rb: grava no .skp ABERTO (cmd[1]) e responde."""
    def job(cmd, env, handle):
        params = json.loads(Path(env["SKMCP_PARAMS"]).read_text("utf-8"))
        if check:
            check(cmd, params)
        aberto = Path(cmd[1])
        aberto.write_bytes(b"NEW")
        st = aberto.stat()
        os.utime(aberto, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))  # o save vem depois da cópia
        Path(env["SKMCP_RESULT"]).write_text(json.dumps(result or {"ok": True, "saved": True}), "utf-8")
    return job


def test_apply_edits_edita_a_copia_e_o_original_nunca_e_aberto(tmp_path, skp):
    out = tmp_path / "out" / "edited.skp"

    def check(cmd, params):
        assert Path(cmd[1]) == out.resolve()          # o SketchUp abriu a CÓPIA
        assert params["ops"][0]["target"]["expect"] == "one"
        assert "PlanShell_" in params["protected_prefixes"]

    r = jobs.apply_edits(str(skp), [{"op": "set_hidden", "target": {"name": "Cama"}, "hidden": True}],
                         out_path=str(out), mode="interactive",
                         su=su_with(FakeSystem(job=_salva_no_modelo_aberto(check=check))))
    assert r["status"] == "OK" and out.read_bytes() == b"NEW"
    assert skp.read_bytes() == b"SKP"                   # original intacto


def test_apply_edits_sem_save_nao_e_sucesso(tmp_path, skp):
    job, _ = ruby_writes({"ok": True})  # disse ok, mas não regravou a cópia
    r = jobs.apply_edits(str(skp), [{"op": "set_hidden", "target": {"name": "Cama"}, "hidden": True}],
                         out_path=str(tmp_path / "x.skp"), mode="interactive",
                         su=su_with(FakeSystem(job=job)))
    assert r["status"] == "FAILED"


def test_apply_edits_que_falha_nao_deixa_copia_parecendo_resultado(tmp_path, skp):
    job, _ = ruby_writes({"ok": False, "error": "nenhuma entidade casa"})
    out = tmp_path / "x.skp"
    r = jobs.apply_edits(str(skp), [{"op": "set_hidden", "target": {"name": "Cama"}, "hidden": True}],
                         out_path=str(out), mode="interactive", su=su_with(FakeSystem(job=job)))
    assert r["status"] == "FAILED" and not out.exists()


def test_rename_de_arquitetura_e_recusado_porque_furaria_a_protecao():
    with pytest.raises(ops.OpsInvalid, match="Hard Rule #1"):
        ops.validate([{"op": "rename", "target": {"name": "Window_Group_w1"}, "name": "janela"}])


def test_apply_edits_recusa_antes_de_subir_o_sketchup(skp):
    sys_ = FakeSystem()
    r = jobs.apply_edits(str(skp), [{"op": "move", "target": {"name": "Cama"}}], su=su_with(sys_))
    assert r["status"] == "ERROR" and r["errors"] and sys_.launched == []
    r = jobs.apply_edits(str(skp), [{"op": "set_hidden", "target": {"name": "Cama"}, "hidden": True}],
                         out_path="artifacts/planta_74/planta_74.skp", su=su_with(sys_))
    assert r["status"] == "REFUSED" and sys_.launched == []
    assert not any(paths.REPO_ROOT.joinpath("artifacts").rglob("*.json"))


def test_render_recusa_preset_desconhecido(skp):
    r = jobs.render_views(str(skp), views=[{"name": "a", "preset": "diagonal"}],
                          su=su_with(FakeSystem()))
    assert r["status"] == "ERROR" and "preset" in r["reason"]


def test_render_aceita_camera_em_metros_e_abre_copia(tmp_path, skp):
    job, seen = ruby_writes({"ok": True, "views": [], "all_ok": True})
    r = jobs.render_views(str(skp), views=[{"name": "sala", "eye_m": [1, 2, 1.6], "target_m": [3, 2, 1]}],
                          out_dir=str(tmp_path / "r"), mode="interactive", su=su_with(FakeSystem(job=job)))
    assert r["status"] == "OK" and seen["params"]["views"][0]["name"] == "sala"
    assert Path(seen["cmd"][1]) != skp.resolve()  # esconder grupos não suja o original


def test_render_com_vista_falha_e_partial(tmp_path, skp):
    job, _ = ruby_writes({"ok": True, "views": [{"name": "top", "ok": False}], "all_ok": False})
    r = jobs.render_views(str(skp), out_dir=str(tmp_path / "r"), mode="interactive",
                          su=su_with(FakeSystem(job=job)))
    assert r["status"] == "PARTIAL"


def test_build_shell_sem_plugin_de_autorun_e_unavailable():
    sys_ = FakeSystem(virtual=(EXE,))
    r = jobs.build_shell(su=su_with(sys_))
    assert r["status"] == "UNAVAILABLE" and "autorun_consume.rb" in r["reason"]


def test_build_shell_nao_escreve_em_artifacts(monkeypatch, repo_temporario, tmp_path):
    from tools import build_plan_shell_skp as bps

    def nunca(*a, **k):
        raise AssertionError("build real chamado com destino proibido")

    monkeypatch.setattr(bps, "run", nunca)
    con = tmp_path / "consensus.json"
    con.write_text("{}", "utf-8")
    r = jobs.build_shell(str(con), out_path="artifacts/planta_74/model.skp", su=su_with(FakeSystem()))
    assert r["status"] == "REFUSED"
    assert list((repo_temporario / "artifacts").rglob("*")) == [repo_temporario / "artifacts" / "planta_74"]


def test_furnish_recusa_escala_errada(monkeypatch):
    from core import scale

    monkeypatch.setattr(scale, "PT_TO_M", 0.0352)
    r = jobs.furnish(su=su_with(FakeSystem()))
    assert r["status"] == "ERROR" and "0.0259" in r["reason"]


def test_furnish_abre_copia_e_nunca_o_shell_base(monkeypatch, tmp_path):
    """Defeito achado na revisão do #249: o furnish abria o .skp canônico direto.
    Em modo interactive a janela fica aberta — um Ctrl+S gravaria por cima dele."""
    import sys
    import types

    from core import scale

    monkeypatch.setattr(scale, "PT_TO_M", 0.0259)
    fake = types.ModuleType("tools.furnish_apartment")
    fake.collect_boxes = lambda con: ([{"kind": "bed", "x0": 0, "y0": 0, "x1": 1, "y1": 1}],
                                      [("r1", "Quarto", "BEDROOM", "PASS", 1)])
    monkeypatch.setitem(sys.modules, "tools.furnish_apartment", fake)
    base = tmp_path / "planta_74.skp"
    base.write_bytes(b"CANONICO")
    con = tmp_path / "consensus.json"
    con.write_text("{}", "utf-8")
    seen = {}

    def job(cmd, env, handle):
        seen["cmd"] = cmd
        Path(env["LAYOUT_OUT"]).write_bytes(b"MOBILIADO")
        Path(env["LAYOUT_LOG"]).write_text("ok", "utf-8")

    r = jobs.furnish(consensus_path=str(con), base_skp=str(base), out_dir=str(tmp_path / "out"),
                     mode="interactive", su=su_with(FakeSystem(job=job)))
    assert r["status"] == "OK"
    aberto = Path(seen["cmd"][1])
    assert aberto != base.resolve() and aberto.parent == (tmp_path / "out").resolve()
    assert base.read_bytes() == b"CANONICO"


def test_inspect_abre_copia_e_nunca_o_original(tmp_path, skp):
    job, seen = ruby_writes({"ok": True, "nodes": []})
    r = jobs.inspect_model(str(skp), out_dir=str(tmp_path / "i"), mode="interactive",
                           su=su_with(FakeSystem(job=job)))
    assert r["status"] == "OK" and r["input_skp"] == str(skp.resolve())
    assert Path(seen["cmd"][1]) != skp.resolve()


def test_su_marcadas_como_nao_provadas_no_sketchup():
    st = jobs.status(su=su_with(FakeSystem()))
    assert st["proof_state"] == "UNVERIFIED_ON_SKETCHUP"


def test_render_vray_recusa_enquanto_o_launcher_mata_por_imagem(tmp_path):
    """O launcher legado roda `taskkill /F /IM SketchUp.exe` após a exportação:
    a tool recusa com o motivo, mesmo com SketchUp e V-Ray presentes, e nunca
    chega a importá-lo."""
    sys_ = FakeSystem()
    r = jobs.render_vray(str(tmp_path), su=su_with(sys_))
    assert r["status"] == "REFUSED" and "taskkill" in r["reason"]
    assert sys_.launched == []


def test_apply_edits_recusa_destino_que_ja_existe(tmp_path, skp):
    """Antes: a cópia sobrescrevia o destino e uma falha depois o APAGAVA —
    destruindo um arquivo que o job nunca criou."""
    out = tmp_path / "ja_existe.skp"
    out.write_bytes(b"TRABALHO DO FELIPE")
    sys_ = FakeSystem()
    r = jobs.apply_edits(str(skp), [{"op": "set_hidden", "target": {"name": "Cama"}, "hidden": True}],
                         out_path=str(out), su=su_with(sys_))
    assert r["status"] == "REFUSED" and sys_.launched == []
    assert out.read_bytes() == b"TRABALHO DO FELIPE"


def test_insert_component_com_nome_de_arquitetura_e_recusado(tmp_path):
    comp = tmp_path / "Window_Group_w9.skp"
    comp.write_bytes(b"x")
    with pytest.raises(ops.OpsInvalid, match="reservado para arquitetura"):
        ops.validate([{"op": "insert_component", "skp_path": str(comp), "position_m": [0, 0, 0]}])


def test_status_lista_os_jobs_ruby_versionados():
    st = jobs.status(su=su_with(FakeSystem(tasklist=TASKLIST_TWO)))
    assert {"inspect_model", "render_views", "apply_edits"} <= set(st["ruby_jobs"])
    assert [i["pid"] for i in st["instances"]] == [4242, 5150]


# -- revisão adversarial, rodada 2 ---------------------------------------------

def test_laje_do_banho_e_protegida_com_o_nome_que_o_place_layout_da():
    """O prefixo 'PeleTeto' nunca casava: o grupo se chama '<cômodo> · PeleTeto'."""
    layout = Path("tools/place_layout_skp.rb").read_text("utf-8")
    assert '"#{room} · #{mod}"' in layout                 # o nome que o grupo recebe
    assert '"PeleTeto")' in Path("tools/bathroom_layout.py").read_text("utf-8")  # módulo da laje
    for room in ("BANHO 01", "BANHO 02", "LAVABO"):
        assert ops.is_protected(f"{room} · PeleTeto")
        with pytest.raises(ops.OpsInvalid, match="Hard Rule #1"):
            ops.validate([{"op": "move", "target": {"name": f"{room} · PeleTeto"}, "by_m": [0, 0, -1]}])
    assert not ops.is_protected("BANHO 01 · Vaso")


def test_jobs_mandam_a_mesma_regra_de_protecao_ao_ruby(tmp_path, skp):
    seen = {}
    out = tmp_path / "o" / "e.skp"
    jobs.apply_edits(str(skp), [{"op": "set_hidden", "target": {"name": "Cama"}, "hidden": True}],
                     out_path=str(out), mode="interactive",
                     su=su_with(FakeSystem(job=_salva_no_modelo_aberto(check=lambda c, p: seen.update(p)))))
    assert seen["protected_substrings"] == ["PeleTeto"]
    assert seen["protected_prefixes"] == list(ops.PROTECTED_PREFIXES)


def test_caminho_relativo_de_textura_e_componente_e_do_repo_nao_do_cwd(repo_temporario, tmp_path,
                                                                     monkeypatch):
    (repo_temporario / "assets").mkdir()
    (repo_temporario / "assets" / "wood.png").write_bytes(b"png")
    (repo_temporario / "assets" / "chair.skp").write_bytes(b"skp")
    cwd = tmp_path / "outro_cwd"
    (cwd / "assets").mkdir(parents=True)
    (cwd / "assets" / "chair.skp").write_bytes(b"OUTRO")    # homônimo que NÃO deve ser usado
    monkeypatch.chdir(cwd)
    norm = ops.validate([
        {"op": "set_material", "target": {"name": "Cama"}, "texture": "assets/wood.png"},
        {"op": "insert_component", "skp_path": "assets/chair.skp", "position_m": [0, 0, 0]},
    ])
    assert norm[0]["texture"] == str((repo_temporario / "assets" / "wood.png").resolve())
    assert norm[1]["skp_path"] == str((repo_temporario / "assets" / "chair.skp").resolve())
