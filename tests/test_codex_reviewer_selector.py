"""FP-060: seletor de testes do revisor — arquivos que nao sao Python (workflow, .ps1, .sh) contam como cobertos pelos testes que citam o caminho EXATO.

Decisao do proprietario (chat, 2026-11-16, "Ensinar o seletor"): um workflow do GitHub nunca tem `test_<nome>.py`; sem esta regra todo PR que toca `.yml` fica
"descoberto" para sempre e nunca pode ser aprovado. Um modulo .py continua exigindo o teste com o NOME dele (mencao em teste de inventario nao cobre)."""
from __future__ import annotations

from pathlib import Path

from tools.orchestration import codex_reviewer as cr

WF = ".github/workflows/delegated-tests.yml"


def tree(tmp_path: Path, tests: dict[str, str]) -> Path:
    (tmp_path / "tests").mkdir()
    for name, body in tests.items():
        (tmp_path / "tests" / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_a_workflow_is_covered_by_the_tests_that_cite_its_exact_path(tmp_path):
    wt = tree(tmp_path, {"test_wf.py": f'P = "{WF}"\ndef test_pin(): pass\n', "test_other.py": "def test_x(): pass\n"})
    assert cr.select_tests(wt, [WF]) == (["tests/test_wf.py"], [])


def test_single_quotes_also_count_as_a_citation(tmp_path):
    wt = tree(tmp_path, {"test_wf.py": f"P = '{WF}'\n"})
    assert cr.select_tests(wt, [WF]) == (["tests/test_wf.py"], [])


def test_a_workflow_nobody_cites_stays_uncovered(tmp_path):
    wt = tree(tmp_path, {"test_other.py": "def test_x(): pass\n"})
    assert cr.select_tests(wt, [WF]) == ([], [WF])


def test_a_partial_or_different_path_is_not_a_citation(tmp_path):
    wt = tree(tmp_path, {"test_a.py": 'P = ".github/workflows/delegated-tests.yml.bak"\n', "test_b.py": 'P = "workflows/delegated-tests.yml"\n',
                         "test_c.py": "# .github/workflows/delegated-tests.yml citado em comentario sem aspas\n"})
    assert cr.select_tests(wt, [WF]) == ([], [WF])


def test_a_python_module_is_never_covered_by_a_mere_citation(tmp_path):
    mod = "tools/orchestration/novo_modulo.py"
    wt = tree(tmp_path, {"test_inventory.py": f'PATHS = ["{mod}"]\n'})
    assert cr.select_tests(wt, [mod]) == ([], [mod])                                            # .py so pelo teste com o NOME dele


def test_name_based_selection_is_unchanged_for_python_modules(tmp_path):
    wt = tree(tmp_path, {"test_novo_modulo.py": "def test_x(): pass\n"})
    assert cr.select_tests(wt, ["tools/orchestration/novo_modulo.py"]) == (["tests/test_novo_modulo.py"], [])


def test_a_powershell_script_is_covered_by_the_test_that_cites_it(tmp_path):
    ps = "tools/orchestration/run_pr_lifecycle.ps1"
    wt = tree(tmp_path, {"test_launcher.py": f'SCRIPT = "{ps}"\n'})
    assert cr.select_tests(wt, [ps]) == (["tests/test_launcher.py"], [])


def test_only_test_files_count_as_citations(tmp_path):
    wt = tree(tmp_path, {"helpers.py": f'P = "{WF}"\n', "conftest.py": f'P = "{WF}"\n'})
    assert cr.select_tests(wt, [WF]) == ([], [WF])


# -- cobertura COMPORTAMENTAL: citado escolhe o teste; so conta como coberto se o teste ABRIR o arquivo no sandbox ----------------------------------------
class _Run:
    def __init__(self, opened):
        self.exit_code, self.timed_out, self.output = 0, False, "ok"
        self.facts = {"is_appcontainer": True, "watched": {"watched": [WF], "opened": opened}}


def _reviewer(monkeypatch, tmp_path, opened):
    wt = tree(tmp_path, {"test_wf.py": f'P = "{WF}"\ndef test_pin(): pass\n'})
    monkeypatch.setattr(cr, "codex_dir", lambda: tmp_path / "codex")
    monkeypatch.setattr(cr.sb, "project_distributions", lambda p: ("pytest",))
    monkeypatch.setattr(cr.sb, "proves_isolation", lambda facts: True)
    seen = {}

    def fake_run_pytest(tree_, tests, **kw):
        seen["watch"] = kw.get("watch")
        return _Run(opened)
    monkeypatch.setattr(cr.sb, "run_pytest", fake_run_pytest)
    return wt, seen


def test_a_cited_file_that_the_tests_really_read_is_covered(monkeypatch, tmp_path):
    wt, seen = _reviewer(monkeypatch, tmp_path, [WF])
    out = cr.run_coordinator_tests(wt, [WF])
    assert seen["watch"] == (WF,) and out["uncovered"] == [] and out["cited_files"] == {"read_by_tests": [WF], "not_read": []}


def test_a_cited_file_that_no_test_reads_stays_uncovered(monkeypatch, tmp_path):
    wt, _ = _reviewer(monkeypatch, tmp_path, [])
    out = cr.run_coordinator_tests(wt, [WF])
    assert out["uncovered"] == [WF] and out["cited_files"]["not_read"] == [WF]


def test_a_missing_watch_report_counts_as_not_read(monkeypatch, tmp_path):
    wt, _ = _reviewer(monkeypatch, tmp_path, None)
    out = cr.run_coordinator_tests(wt, [WF])
    assert out["uncovered"] == [WF]


# -- evidencia em pastas que o sandbox nao copia (artifacts/...): fora da exigencia de cobertura, listada a parte ------------------------------------------
def test_an_evidence_script_under_artifacts_is_not_uncovered_code(tmp_path):
    script = "artifacts/review/fp060/x/collect_evidence.py"
    wt = tree(tmp_path, {"test_other.py": "def test_x(): pass\n"})
    assert cr.select_tests(wt, [script]) == ([], [])


def test_the_report_lists_evidence_code_the_sandbox_cannot_run(monkeypatch, tmp_path):
    wt, _ = _reviewer(monkeypatch, tmp_path, [])
    out = cr.run_coordinator_tests(wt, ["artifacts/review/x/e2e.py", WF])
    assert out["not_testable_in_sandbox"] == ["artifacts/review/x/e2e.py"] and "artifacts/review/x/e2e.py" not in out["uncovered"]


def test_operational_scripts_under_ops_still_require_a_test():
    import pathlib
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        wt = tree(pathlib.Path(d), {"test_other.py": "def test_x(): pass\n"})
        assert cr.select_tests(wt, ["ops/launchers/run.ps1"]) == ([], ["ops/launchers/run.ps1"])   # ops/ roda em producao: nunca isento
