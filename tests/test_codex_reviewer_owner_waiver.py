"""FP-060 MT-03: dispensa do PROPRIETARIO para testes que o PR ACRESCENTA e que o AppContainer do revisor nao executa (a politica da base ainda nao os conhece).

Decisao do proprietario (chat, 2026-11-16, #618): aceitar, para node ids EXATOS de um PR, os checks obrigatorios do CI verdes no HEAD exato. A dispensa fica no
diretorio do coordenador (fora do repositorio), vale para um PR, e a evidencia e exigida a cada revisao: sem CI verde no HEAD, os testes NAO contam como aprovados."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.orchestration import codex_reviewer as cr
from tools.orchestration import delegated_tests as dt
from tools.orchestration import lifecycle

REPO, PR, HEAD = "GFCDOTA/sketchup-mcp", 618, "a" * 40
IDS = ["tests/test_lab.py::test_alpha", "tests/test_lab.py::test_beta[x]"]


class FakeRun:
    def __init__(self, facts):
        self.exit_code, self.timed_out, self.output, self.facts = 0, False, "ok", facts


def runs(state="success", drop=None):
    return [{"name": n, "status": "completed", "conclusion": state, "head_sha": HEAD} for n in sorted(lifecycle.MANDATORY_CHECKS) if n != drop]


class Gh:
    def __init__(self, check_runs=None, boom=None):
        self.check_runs, self.boom, self.calls = runs() if check_runs is None else check_runs, boom, []

    def __call__(self, path):
        self.calls.append(path)
        if self.boom:
            raise self.boom
        assert path == f"repos/{REPO}/commits/{HEAD}/check-runs?per_page=100", path
        return {"check_runs": self.check_runs}


@pytest.fixture()
def env(monkeypatch, tmp_path):
    (tmp_path / "wt/tests").mkdir(parents=True)
    (tmp_path / "wt/tests/test_lab.py").write_text("def test_alpha(): pass\n", encoding="utf-8")
    monkeypatch.setattr(cr, "codex_dir", lambda: tmp_path / "codex")
    monkeypatch.setattr(cr.sb, "project_distributions", lambda p: ("pytest",))
    monkeypatch.setattr(cr.sb, "proves_isolation", lambda facts: True)
    seen = {}

    def fake_run_pytest(tree, tests, **kw):
        seen["delegated"] = kw.get("delegated")
        d = list(kw.get("delegated") or [])
        return FakeRun({"delegation": {"requested": d, "deselected": d, "not_collected": []}, "is_appcontainer": True})
    monkeypatch.setattr(cr.sb, "run_pytest", fake_run_pytest)
    return tmp_path, seen


def waivers(tmp_path, *entries) -> Path:
    p = tmp_path / "codex" / cr.OWNER_WAIVERS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema": 1, "waivers": list(entries)}), encoding="utf-8")
    return p


def entry(**over):
    return {"repo": REPO, "pr": PR, "node_ids": IDS, "decided_by": "proprietario", "decided_at": "2026-11-16", "decision": "chat: aceitar o CI no HEAD", **over}


def delegation(gh):
    # sem politica na base (fetch falha): so a dispensa do proprietario esta em jogo
    return dt.Delegation(gh=gh, repo=REPO, head_sha=HEAD, changed_files=["tests/test_lab.py"], root=Path("."), run_git=lambda args, cwd: (1, "sem rede"))


def run(tmp_path, gh, pr=PR, files=("tests/test_lab.py",)):
    return cr.run_coordinator_tests(tmp_path / "wt", list(files), delegation=delegation(gh), pr=pr)


def test_waived_ids_are_deselected_and_count_only_with_every_mandatory_check_green_at_the_exact_head(env):
    tmp_path, seen = env
    waivers(tmp_path, entry())
    out = run(tmp_path, Gh())
    assert out["tests_passed"] is True and seen["delegated"] == tuple(IDS)
    ev = out["delegated"]["evidence"]["owner_waiver"]
    assert ev["ids"] == IDS and ev["decided_by"] == "proprietario" and "passed" in ev["ci"]


@pytest.mark.parametrize("check_runs", [runs("failure"), runs(drop="pytest (py3.12)"), [], [{**r, "head_sha": "b" * 40} for r in runs()]])
def test_without_every_mandatory_check_green_on_this_head_the_waived_tests_do_not_count(env, check_runs):
    tmp_path, _ = env
    waivers(tmp_path, entry())
    out = run(tmp_path, Gh(check_runs=check_runs))
    assert out["tests_passed"] is False and "NAO comprovada" in out["summary"] and out["delegated"]["evidence"] is None


def test_an_unreadable_check_list_is_fail_closed(env):
    tmp_path, _ = env
    waivers(tmp_path, entry())
    out = run(tmp_path, Gh(boom=RuntimeError("502")))
    assert out["tests_passed"] is False and "ilegiveis" in out["summary"]


def test_a_waiver_for_another_pr_or_repo_waives_nothing(env):
    tmp_path, seen = env
    waivers(tmp_path, entry(pr=619), entry(repo="outro/repo"))
    out = run(tmp_path, Gh())
    assert not seen["delegated"] and out["tests_passed"] is True and out["delegated"]["owner_waived"] == []


def test_without_a_pr_number_nothing_is_waived(env):
    tmp_path, seen = env
    waivers(tmp_path, entry())
    run(tmp_path, Gh(), pr=None)
    assert not seen["delegated"]


def test_only_waived_ids_whose_file_was_selected_are_deselected(env):
    tmp_path, seen = env
    waivers(tmp_path, entry(node_ids=[*IDS, "tests/test_other.py::test_z"]))
    run(tmp_path, Gh())
    assert seen["delegated"] == tuple(IDS)


@pytest.mark.parametrize("bad", [entry(node_ids=["tests/test_lab.py::test_*"]), entry(node_ids=["tests/test_lab.py"]), entry(node_ids=["tests/../x.py::t"]),
                                 entry(node_ids=[]), entry(node_ids=IDS + IDS[:1]), entry(decided_by=""), entry(node_ids=[f"tests/test_lab.py::t{i}" for i in range(33)])])
def test_a_malformed_waiver_waives_nothing_and_says_why(env, bad):
    tmp_path, seen = env
    waivers(tmp_path, bad)
    out = run(tmp_path, Gh())
    assert not seen["delegated"] and any("dispensa do proprietario ilegivel" in r for r in out["delegated"]["reasons"])


def test_two_waivers_for_the_same_pr_are_ambiguous_and_waive_nothing(env):
    tmp_path, seen = env
    waivers(tmp_path, entry(), entry(node_ids=IDS[:1]))
    out = run(tmp_path, Gh())
    assert not seen["delegated"] and any("mais de uma" in r for r in out["delegated"]["reasons"])


def test_a_corrupt_waiver_file_waives_nothing(env):
    tmp_path, seen = env
    p = tmp_path / "codex" / cr.OWNER_WAIVERS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ quebrado", encoding="utf-8")
    out = run(tmp_path, Gh())
    assert not seen["delegated"] and any("ilegivel" in r for r in out["delegated"]["reasons"])


def test_the_waiver_lives_outside_the_repository_under_review():
    src = Path(cr.__file__).read_text(encoding="utf-8")
    assert 'codex_dir() / OWNER_WAIVERS_FILE' in src                                            # diretorio do coordenador, nunca a arvore do PR
