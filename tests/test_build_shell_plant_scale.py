"""Escala que chega ao Ruby do shell — regressão do L2 de 2026-10-19.

O servidor MCP exporta PT_TO_M=0.0259 (é a escala da planta_74) e
build_plan_shell_skp.run trata env explícito como intenção do usuário: via
su_build_shell o quadrado saiu com a escala da planta_74 (PlanShell 3,08 m em vez
de 4,19 m) e os gates deram PASS. Com plant_scale_only, só a escala da PRÓPRIA
planta vale. Sem SketchUp: o Popen é dublado e o .skp "aparece".
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools import build_plan_shell_skp as bps

ROOT = Path(__file__).resolve().parents[1]
QUADRADO = ROOT / "fixtures" / "quadrado" / "consensus_with_window.json"
PLANTA = ROOT / "fixtures" / "planta_74" / "consensus_with_human_walls_and_soft_barriers.json"


@pytest.fixture
def launched(monkeypatch, tmp_path):
    seen = {}

    class FakePopen:
        pid = 4242
        returncode = None

        def __init__(self, cmd, env=None, **kw):
            seen["env"] = env or {}
            seen["out"].write_bytes(b"SKP")

        def poll(self):
            return None

        def terminate(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    monkeypatch.setattr(bps.time, "sleep", lambda s: None)
    monkeypatch.setattr(bps, "disarm_autoruns", lambda d: [])
    monkeypatch.setattr(bps, "write_control", lambda *a, **k: None)
    monkeypatch.setenv("PT_TO_M", "0.0259")  # o que o servidor MCP exporta
    return seen


def _run(seen, tmp_path, con, **kw):
    out = tmp_path / "model.skp"
    seen["out"] = out
    res = bps.run(con, out, sketchup_exe=Path("SketchUp.exe"), plugins_dir=tmp_path,
                  mode="interactive", force_skp=True, **kw)
    assert res["ok"], res
    return seen["env"]


def test_su_build_shell_ignora_a_escala_herdada_de_outra_planta(launched, tmp_path):
    env = _run(launched, tmp_path, QUADRADO, plant_scale_only=True)
    assert "PT_TO_M" not in env  # quadrado não tem escala verificada: default do Ruby


def test_planta_com_escala_verificada_continua_recebendo_a_sua(launched, tmp_path):
    env = _run(launched, tmp_path, PLANTA, plant_scale_only=True)
    assert env["PT_TO_M"] == "0.0259"


def test_consensus_fora_de_fixtures_usa_o_source_da_planta(launched, tmp_path):
    con = tmp_path / "amended.json"
    data = json.loads(PLANTA.read_text("utf-8"))
    assert str(data.get("source", "")).startswith("planta_74")
    con.write_text(json.dumps(data), "utf-8")
    env = _run(launched, tmp_path, con, plant_scale_only=True)
    assert env["PT_TO_M"] == "0.0259"


def test_cli_continua_respeitando_pt_to_m_explicito(launched, tmp_path):
    """Sem a flag (CLI), env explícito ainda vence — comportamento documentado."""
    env = _run(launched, tmp_path, QUADRADO)
    assert env["PT_TO_M"] == "0.0259"


def test_su_build_shell_liga_a_flag():
    src = (ROOT / "tools" / "sketchup" / "jobs.py").read_text("utf-8")
    assert "plant_scale_only=True" in src
