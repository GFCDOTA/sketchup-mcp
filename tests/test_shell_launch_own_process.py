"""O build do shell roda no PRÓPRIO processo do SketchUp — sem control file no Plugins global (FP-043 §8).

Antes: `autorun_control.txt` + plugin `autorun_consume.rb` na pasta Plugins do USUÁRIO. Qualquer SketchUp aberto depois
(inclusive o do Felipe, com duplo clique num .skp) executava o build contra caminhos velhos; em 2026-05-20 isso apagou
e salvou por cima do arquivo aberto. Agora: `SketchUp.exe <modelo> -RubyStartup skmcp_launch.rb`, com as entradas no
env DAQUELE processo. Aqui: comando, env, ausência de escrita no Plugins e o contrato do launcher Ruby (sem SketchUp).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools import build_plan_shell_skp as bps
from tools.sketchup.batch import LAUNCHER, launch_env

ROOT = Path(__file__).resolve().parents[1]
QUADRADO = ROOT / "fixtures" / "quadrado" / "consensus_with_window.json"


@pytest.fixture
def launched(monkeypatch, tmp_path):
    seen = {}

    class FakePopen:
        pid = 4242
        returncode = None

        def __init__(self, cmd, env=None, **kw):
            seen["cmd"], seen["env"], seen["kw"] = cmd, env or {}, kw
            seen["out"].write_bytes(b"SKP")

        def poll(self):
            return None

        def terminate(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    monkeypatch.setattr(bps.time, "sleep", lambda s: None)
    return seen


def _run(seen, tmp_path, plugins):
    out = tmp_path / "out" / "model.skp"
    out.parent.mkdir()
    seen["out"] = out
    res = bps.run(QUADRADO, out, sketchup_exe=Path("SketchUp.exe"), plugins_dir=plugins, mode="interactive",
                  force_skp=True, plant_scale_only=True)
    assert res["ok"], res
    return out


def test_comando_usa_rubystartup_com_o_launcher_versionado_e_entradas_no_env(launched, tmp_path):
    plugins = tmp_path / "Plugins"
    out = _run(launched, tmp_path, plugins)
    cmd, env = launched["cmd"], launched["env"]
    assert cmd[0] == "SketchUp.exe" and "-RubyStartup" in cmd
    assert Path(cmd[cmd.index("-RubyStartup") + 1]) == LAUNCHER
    if len(cmd) > 3:
        assert cmd.index("-RubyStartup") > 1                    # modelo posicional ANTES de -RubyStartup
    assert Path(env["SKMCP_LAUNCH_SCRIPT"]) == bps.RUBY_TEMPLATE.resolve()
    assert env["CONSENSUS_JSON"].endswith("quadrado/consensus_with_window.json")
    assert env["SKP_OUT"] == str(out.resolve()).replace("\\", "/")
    assert env["SKMCP_LAUNCH_ERROR"].endswith("_launch_error.txt")
    assert launched["kw"]["stdin"] is subprocess.DEVNULL


def test_nada_e_escrito_no_plugins_do_usuario(launched, tmp_path):
    plugins = tmp_path / "Plugins"
    _run(launched, tmp_path, plugins)
    assert not plugins.exists(), "o build não pode tocar a pasta Plugins (control file global)"


def test_api_antiga_do_control_file_saiu_do_modulo():
    assert not hasattr(bps, "write_control") and not hasattr(bps, "CONTROL_FILE")
    assert not hasattr(bps, "disarm_autoruns")


def test_launch_env_so_define_o_que_foi_pedido(tmp_path):
    assert set(launch_env(tmp_path / "x.rb")) == {"SKMCP_LAUNCH_SCRIPT"}
    full = launch_env(tmp_path / "x.rb", tmp_path / "e.txt", 3.5)
    assert full["SKMCP_LAUNCH_DEFER"] == "3.5" and full["SKMCP_LAUNCH_ERROR"].endswith("e.txt")


def test_launcher_ruby_carrega_o_script_depois_da_janela_e_registra_falha():
    src = LAUNCHER.read_text(encoding="utf-8")
    assert "UI.start_timer" in src and "load script" in src
    assert "SKMCP_LAUNCH_SCRIPT" in src and "SKMCP_LAUNCH_ERROR" in src
    assert "Sketchup.quit" not in src and "model.save" not in src       # o launcher só carrega; o script decide


def test_quadrado_render_view_tambem_nao_usa_o_control_file():
    src = (ROOT / "tools/quadrado/render_view.py").read_text(encoding="utf-8")
    assert "autorun_control.txt\"" not in src and "-RubyStartup" in src and "spawn_detached" in src
