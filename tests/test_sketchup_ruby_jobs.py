"""Jobs Ruby do especialista (tools/sketchup/ruby) — sintaxe + lógica pura.

A API do SketchUp não existe fora dele; o que dá para provar com ruby comum é
(1) todo job compila e (2) a lógica pura (skmcp_core.rb) faz o que promete.
Sem `ruby` no PATH os testes pulam — o CI Linux do GitHub tem ruby.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

RUBY = shutil.which("ruby")
RUBY_DIR = Path("tools/sketchup/ruby")
pytestmark = pytest.mark.skipif(RUBY is None, reason="ruby não instalado")


@pytest.mark.parametrize("rb", sorted(RUBY_DIR.glob("*.rb")), ids=lambda p: p.name)
def test_job_ruby_compila(rb):
    r = subprocess.run([RUBY, "-c", str(rb)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_logica_pura_do_core_ruby():
    r = subprocess.run([RUBY, "tests/ruby/test_skmcp_core.rb"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_todo_job_usa_o_runtime_comum():
    """Sem o runtime, o job não escreve o JSON de resultado e o Python espera até o timeout."""
    for rb in RUBY_DIR.glob("*.rb"):
        if rb.stem.startswith("skmcp_"):
            continue
        src = rb.read_text("utf-8")
        assert "require_relative 'skmcp_runtime'" in src and "SkmcpRuntime.run(" in src, rb.name


def test_jobs_usam_a_logica_testada_do_core():
    """A lógica pura só protege se os jobs a chamarem: proteção completa e
    referencial de mundo no apply_edits, bbox de mundo no inspect."""
    apply_src = (RUBY_DIR / "apply_edits.rb").read_text("utf-8")
    for needle in ("SkmcpCore.guard_violation", "SkmcpCore.dedupe",
                   "SkmcpCore.world_to_local_vector", "SkmcpCore.world_to_local_point",
                   "SkmcpCore.uniform_frame?"):
        assert needle in apply_src, needle
    inspect_src = (RUBY_DIR / "inspect_model.rb").read_text("utf-8")
    assert "bbox_world_m" in inspect_src and "SkmcpCore.dedupe" in inspect_src
