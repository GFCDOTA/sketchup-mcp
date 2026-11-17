"""FP-060 MT-03: coletor da evidencia dos testes delegados (`tools/orchestration/delegated_results.py`), que o workflow `delegated-tests` roda a partir da BASE.

Mapeia cada node id da politica para o registro EXATO que o pytest grava no JUnit; nunca conta skip/xfail/falha/duplicado/ambiguo como aprovado."""
from __future__ import annotations

import json
import textwrap

from tests.test_delegated_tests import HEAD, IDS, REPO, policy_json
from tools.orchestration import delegated_results as dr

JUNIT = """<?xml version="1.0"?><testsuites><testsuite>
<testcase classname="tests.test_git_thing" name="test_alpha"/>
<testcase classname="tests.test_git_thing" name="test_beta[x]"><skipped type="pytest.xfail" message="x"/></testcase>
<testcase classname="tests.test_git_thing" name="test_gamma"><failure message="boom"/></testcase>
<testcase classname="tests.test_other" name="test_o"><error message="e"/></testcase>
<testcase classname="tests.test_dup" name="test_d"/><testcase classname="tests.test_dup" name="test_d"/>
</testsuite></testsuites>"""


def test_the_collector_maps_junit_to_exact_node_ids_and_never_counts_skip_xfail_failure_or_duplicates_as_passed(tmp_path):
    f = tmp_path / "j.xml"
    f.write_text(JUNIT, encoding="utf-8")
    ids = ["tests/test_git_thing.py::test_alpha", "tests/test_git_thing.py::test_beta[x]", "tests/test_git_thing.py::test_gamma", "tests/test_other.py::test_o",
           "tests/test_dup.py::test_d", "tests/test_git_thing.py::test_never_ran"]
    seen = dr.collect(f, ids)
    assert seen == {"tests/test_git_thing.py::test_alpha": "passed", "tests/test_git_thing.py::test_beta[x]": "skipped", "tests/test_git_thing.py::test_gamma": "failed",
                    "tests/test_other.py::test_o": "error", "tests/test_dup.py::test_d": "duplicate"}           # o que nao rodou fica fora (vira `missing` no relatorio)


def test_the_junit_key_of_a_class_method_matches_what_pytest_writes():
    assert dr.junit_key("tests/test_event_store.py::TestRealProcesses::test_x[event]") == ("tests.test_event_store.TestRealProcesses", "test_x[event]")
    assert dr.junit_key("tests/sub/test_a.py::test_y") == ("tests.sub.test_a", "test_y")


def test_two_policy_ids_with_the_same_junit_record_are_never_counted_as_passed(tmp_path):
    f = tmp_path / "j.xml"
    f.write_text('<testsuites><testsuite><testcase classname="tests.a.b" name="test_x"/></testsuite></testsuites>', encoding="utf-8")
    ids = ["tests/a/b.py::test_x", "tests/a.py::b::test_x"]                                     # arquivo `tests/a/b.py` x classe `b` de `tests/a.py`
    assert dr.collect(f, ids) == {ids[0]: "ambiguous", ids[1]: "ambiguous"}


def test_the_collector_maps_real_pytest_junit_for_parametrized_class_methods(tmp_path, monkeypatch):
    tree = tmp_path / "pr"
    (tree / "tests").mkdir(parents=True)
    (tree / "tests/test_procs.py").write_text(textwrap.dedent('''
        import pytest
        class TestRealProcesses:
            def test_one_owner(self): pass
            @pytest.mark.parametrize("kind", ["event", "outbox"])
            def test_fences(self, kind): pass
    '''), encoding="utf-8")
    ids = ["tests/test_procs.py::TestRealProcesses::test_fences[event]", "tests/test_procs.py::TestRealProcesses::test_fences[outbox]",
           "tests/test_procs.py::TestRealProcesses::test_one_owner"]
    pol = tmp_path / "policy.json"
    pol.write_text(json.dumps(policy_json(ids)), encoding="utf-8")
    for k, v in {"GITHUB_REPOSITORY": REPO, "DELEGATED_HEAD_SHA": HEAD, "GITHUB_RUN_ID": "900", "DELEGATED_POLICY_BASE_SHA": "b" * 40}.items():
        monkeypatch.setenv(k, v)
    out = tmp_path / "results.json"
    assert dr.main(["--policy", str(pol), "--tree", str(tree), "--out", str(out)]) == 0
    assert {r["node_id"]: r["outcome"] for r in json.loads(out.read_text(encoding="utf-8"))["results"]} == {i: "passed" for i in ids}


def test_the_collector_runs_exactly_the_policy_ids_and_fails_if_any_does_not_pass(tmp_path, monkeypatch):
    tree = tmp_path / "pr"
    (tree / "tests").mkdir(parents=True)
    (tree / "tests/test_git_thing.py").write_text("import pytest\ndef test_alpha(): pass\n@pytest.mark.parametrize('v', ['x'])\ndef test_beta(v): pass\n"
                                                  "@pytest.mark.skip\ndef test_gamma(): pass\n", encoding="utf-8")
    pol = tmp_path / "policy.json"
    pol.write_text(json.dumps(policy_json()), encoding="utf-8")
    for k, v in {"GITHUB_REPOSITORY": REPO, "DELEGATED_HEAD_SHA": HEAD, "GITHUB_RUN_ID": "900", "GITHUB_RUN_ATTEMPT": "2", "DELEGATED_POLICY_BASE_SHA": "b" * 40}.items():
        monkeypatch.setenv(k, v)
    out = tmp_path / "results.json"
    code = dr.main(["--policy", str(pol), "--tree", str(tree), "--out", str(out)])
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert code == 1                                                                         # test_gamma foi pulado: nenhum teste delegado pode ficar sem passar
    assert {r["node_id"]: r["outcome"] for r in rep["results"]} == {IDS[0]: "passed", IDS[1]: "passed", IDS[2]: "skipped"}
    assert rep["head_sha"] == HEAD and rep["run_id"] == 900 and rep["run_attempt"] == 2 and rep["policy_base_sha"] == "b" * 40


def test_the_collector_reports_a_missing_test_as_missing(tmp_path, monkeypatch):
    tree = tmp_path / "pr"
    (tree / "tests").mkdir(parents=True)
    (tree / "tests/test_git_thing.py").write_text("def test_alpha(): pass\n", encoding="utf-8")                   # beta e gamma sumiram
    pol = tmp_path / "policy.json"
    pol.write_text(json.dumps(policy_json()), encoding="utf-8")
    for k, v in {"GITHUB_REPOSITORY": REPO, "DELEGATED_HEAD_SHA": HEAD, "GITHUB_RUN_ID": "1", "DELEGATED_POLICY_BASE_SHA": "b" * 40}.items():
        monkeypatch.setenv(k, v)
    out = tmp_path / "r.json"
    assert dr.main(["--policy", str(pol), "--tree", str(tree), "--out", str(out)]) == 1
    assert {r["node_id"]: r["outcome"] for r in json.loads(out.read_text(encoding="utf-8"))["results"]}[IDS[1]] == "missing"
