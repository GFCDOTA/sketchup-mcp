"""FP-060: plugin do coordenador que mede quais arquivos vigiados os testes ABREM (cobertura comportamental de arquivos nao-.py).

Roda o plugin num pytest REAL (subprocesso, fora do AppContainer): citar o caminho nao conta; so a leitura registrada pelo audit hook `open`."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

from tools.orchestration import sandboxed_tests as sb

WF = ".github/workflows/x.yml"


def run_plugin(tmp_path, test_body: str, watch=(WF,)):
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / WF).write_text("name: x\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_t.py").write_text(textwrap.dedent(test_body), encoding="utf-8")
    plugdir = tmp_path / "coord"
    plugdir.mkdir()
    report = plugdir / "watched.json"
    (plugdir / f"{sb.WATCH_PLUGIN}.py").write_text(sb.watch_plugin_source(list(watch), str(report)), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "-p", sb.WATCH_PLUGIN, "-p", "no:cacheprovider"], cwd=tmp_path, capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(plugdir)})
    assert r.returncode == 0, r.stdout[-600:]
    return json.loads(report.read_text(encoding="utf-8"))


def test_a_test_that_reads_the_file_marks_it_opened(tmp_path):
    rep = run_plugin(tmp_path, f'''
        from pathlib import Path
        def test_reads():
            assert Path("{WF}").read_text().startswith("name")
    ''')
    assert rep == {"watched": [WF], "opened": [WF]}


def test_a_test_that_only_cites_the_path_does_not_mark_it_opened(tmp_path):
    rep = run_plugin(tmp_path, f'''
        P = "{WF}"
        def test_cites():
            assert P.endswith(".yml")
    ''')
    assert rep["opened"] == []


def test_writing_a_fake_copy_elsewhere_does_not_count_as_reading_the_real_file(tmp_path):
    rep = run_plugin(tmp_path, f'''
        def test_fake(tmp_path):
            f = tmp_path / "{WF}"
            f.parent.mkdir(parents=True)
            f.write_text("name: falso")
            assert f.read_text() == "name: falso"
    ''')
    assert rep["opened"] == []


def test_an_absolute_or_dotted_path_to_the_same_file_counts(tmp_path):
    rep = run_plugin(tmp_path, '''
        import os
        def test_abs():
            with open(os.path.join(os.getcwd(), ".github", "workflows", ".", "x.yml"), "rb") as fh:
                assert fh.read()
    ''')
    assert rep["opened"] == [WF]
