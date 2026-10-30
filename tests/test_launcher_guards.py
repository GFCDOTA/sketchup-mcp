"""FP-043 P3b (#457): launchers recusam entrada inexistente com o motivo, em vez de traceback ou de um "OK" vazio.

Achados do smoke de 2026-10-25 (SketchUp 26, janela humana aberta): `--room zzz` morria num KeyError cru dentro do cerebro do
comodo, e `KITCHEN_THEME=tema_inexistente` terminava com "OK ... recolored=0 saved=true" e gravava um .skp que nao muda nada.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.sketchup import launcher_guards as lg

REPO = Path(__file__).resolve().parents[1]
CON = {"rooms": [{"id": "r000", "name": "SUITE 01"}, {"id": "r003", "name": "SUITE 02"}]}


def test_room_ids_come_from_the_consensus_in_order():
    assert lg.room_ids(CON) == ["r000", "r003"]
    assert lg.room_ids({}) == []


def test_a_known_room_passes_silently(capsys):
    lg.require_known_room(CON, "r003", "place")
    assert capsys.readouterr().out == ""


def test_an_unknown_room_is_refused_with_exit_2_naming_the_valid_ids(capsys):
    with pytest.raises(SystemExit) as exc:
        lg.require_known_room(CON, "zzz", "place")
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "REFUSED" in out and "'zzz'" in out and "r000" in out and "r003" in out


def test_a_consensus_without_rooms_refuses_everything():
    with pytest.raises(SystemExit):
        lg.require_known_room({}, "r000", "place")


OK_LOG = "OK theme=black_wood_gold recolored=16 saved=true -> E:/x/y.skp"


def test_bake_log_with_recolored_parts_and_saved_is_accepted():
    assert lg.verify_bake_log(OK_LOG) == (True, "recolored=16")


@pytest.mark.parametrize("log,why", [
    ("OK theme=tema_inexistente recolored=0 saved=true -> E:/x/y.skp", "recolored=0"),
    ("OK theme=black_wood_gold recolored=16 saved=false -> E:/x/y.skp", "saved=false"),
    ("", "sem log"),
    ("(no log)", "sem log"),
    ("saved=true", "recolored"),
])
def test_bake_log_that_changed_nothing_or_did_not_save_is_rejected(log, why):
    ok, reason = lg.verify_bake_log(log)
    assert not ok and why in reason


@pytest.mark.planta74_scale
@pytest.mark.parametrize("module_args", [
    ["-m", "tools.rooms.bedroom.capabilities.place_bedroom_skp"],
    ["tools/sketchup/furnish/place_layout_skp.py"],
])
def test_place_scripts_refuse_an_unknown_room_without_traceback_or_launching_sketchup(module_args):
    done = subprocess.run([sys.executable, *module_args, "--room", "zzz", "--dry-run"], cwd=REPO, capture_output=True, text=True,
                          env={**__import__("os").environ, "PT_TO_M": "0.0259", "PYTHONPATH": str(REPO)}, timeout=120)
    assert done.returncode == 2 and "Traceback" not in done.stderr and "REFUSED" in done.stdout
