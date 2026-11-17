"""FP-060 MT-03 (lado da BASE: politica, coletor do CI e verificacao da evidencia; a integracao no revisor vem com a pilha #630/#670): delegacao sandbox->CI por node id EXATO, com politica da BASE e evidencia individual ligada ao HEAD exato. Cenarios adversariais: PR que altera a propria
politica, SHA velho, relatorio adulterado, teste ausente/ignorado, workflow nao autorizado, evidencia incompleta, GitHub fora do ar, tentativa de ampliar a lista."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

from tools.orchestration import delegated_results as dr
from tools.orchestration import delegated_tests as dt

REPO = "GFCDOTA/sketchup-mcp"
HEAD = "a" * 40
IDS = ["tests/test_git_thing.py::test_alpha", "tests/test_git_thing.py::test_beta[x]", "tests/test_git_thing.py::test_gamma"]
WORKFLOW_TEXT = "name: delegated-tests\n"
POLICY_FILE = dt.POLICY_PATH


def sh(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True, env={**__import__("os").environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                                                                                     "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return r.stdout.strip()


def run_git(args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def policy_json(ids=IDS, pin="0" * 40, **over):
    body = {"schema": 1, "ci": {"workflow_path": dt.WORKFLOW_PATH, "workflow_blob_sha": pin, "artifact_name": dt.ARTIFACT_NAME},
            "delegated": [{"node_id": i, "reason": "git_unavailable_in_appcontainer", "sandbox_proof": {"outcome": "error", "first_error": "FileNotFoundError: git"}} for i in ids]}
    body.update(over)
    return body


@pytest.fixture()
def base(tmp_path):
    """Repositorio do COORDENADOR com a politica, o workflow e o coletor na base (origin/develop faz o papel do `develop`)."""
    root = tmp_path / "coord"
    root.mkdir()
    sh(root, "init", "-q", "-b", "develop")
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/delegated-tests.yml").write_text(WORKFLOW_TEXT, encoding="utf-8", newline="\n")
    (root / dt.COLLECTOR_PATH).parent.mkdir(parents=True)
    (root / dt.COLLECTOR_PATH).write_text("# coletor\n", encoding="utf-8", newline="\n")
    (root / "docs/governance").mkdir(parents=True)
    pin = sh(root, "hash-object", ".github/workflows/delegated-tests.yml")
    (root / POLICY_FILE).write_text(json.dumps(policy_json(pin=pin), indent=1) + "\n", encoding="utf-8", newline="\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "base")
    sha = sh(root, "rev-parse", "HEAD")
    sh(root, "update-ref", "refs/remotes/origin/develop", sha)
    return root, sha, pin


def no_fetch_git(args, cwd):
    if args[:1] == ["fetch"]:
        return 0, ""
    return run_git(args, cwd)


# ------------------------------------------------------------------------------------------------------------------------ politica
def test_a_valid_policy_loads_from_the_base_commit(base):
    root, sha, pin = base
    pol = dt.load_policy(root, run_git, sha)
    assert pol is not None and list(pol.ids) == IDS and pol.workflow_blob_sha == pin and pol.base_sha == sha


def test_a_pr_that_edits_its_own_policy_in_the_worktree_gets_nothing_extra(base):
    root, sha, _pin = base
    widened = policy_json(IDS + ["tests/test_other.py::test_zzz"], pin=sh(root, "hash-object", ".github/workflows/delegated-tests.yml"))
    (root / POLICY_FILE).write_text(json.dumps(widened), encoding="utf-8")                 # a worktree/PR tenta ampliar
    pol = dt.load_policy(root, run_git, sha)
    assert list(pol.ids) == IDS                                                             # vale so o commit da base


def test_when_the_base_has_no_policy_nothing_is_delegated(tmp_path):
    root = tmp_path / "vazio"
    root.mkdir()
    sh(root, "init", "-q", "-b", "develop")
    (root / "x").write_text("x", encoding="utf-8")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "c")
    sha = sh(root, "rev-parse", "HEAD")
    assert dt.load_policy(root, run_git, sha) is None
    assert dt.eligible(None, ["tools/a.py"])[0] is False


@pytest.mark.parametrize("changed", [[dt.POLICY_PATH], [dt.WORKFLOW_PATH], [dt.COLLECTOR_PATH], [".github/workflows/ci.yml"], ["tools/a.py", dt.POLICY_PATH]])
def test_a_pr_that_touches_the_policy_the_workflow_the_collector_or_github_loses_the_delegation(base, changed):
    root, sha, _ = base
    pol = dt.load_policy(root, run_git, sha)
    ok, why = dt.eligible(pol, changed)
    assert ok is False and "propria regra" in why
    assert dt.eligible(pol, ["tools/a.py", "tests/test_x.py"]) == (True, "")


@pytest.mark.parametrize("bad", [
    {"node_id": "tests/test_git_thing.py", "case": "arquivo inteiro"},
    {"node_id": "tests/test_git_thing.py::test_*", "case": "curinga"},
    {"node_id": "tests/*.py::test_a", "case": "curinga no caminho"},
    {"node_id": "tests/test_git_thing.py::test_a?", "case": "curinga ?"},
    {"node_id": "tests/", "case": "diretorio"},
    {"node_id": "tools/x.py::test_a", "case": "fora de tests/"},
    {"node_id": "../tests/x.py::test_a", "case": "travessia"},
    {"node_id": "tests/../tools/x.py::test_a", "case": "travessia depois de tests/"},
    {"node_id": "tests/./x.py::test_a", "case": "segmento ."},
    {"node_id": "tests//x.py::test_a", "case": "segmento vazio"},
    {"node_id": "tests/sub/../../x.py::test_a", "case": "travessia aninhada"},
    {"node_id": "tests/x.py::A::B::test_a", "case": "classe aninhada"},
    {"node_id": "tests/x.py::TestClass::", "case": "metodo vazio"},
    {"node_id": "tests/x.py::TestClass::test_*", "case": "curinga no metodo"},
    {"node_id": "tests/x.py::test_a[", "case": "param malformado"},
    {"node_id": "", "case": "vazio"},
    {"node_id": 5, "case": "tipo"},
])
def test_the_policy_refuses_wildcards_whole_files_categories_and_malformed_ids(bad):
    raw = policy_json()
    raw["delegated"] = [{"node_id": bad["node_id"], "reason": "r", "sandbox_proof": {"first_error": "e"}}]
    with pytest.raises(dt.DelegationError, match="node id invalido"):
        dt.validate_policy(raw, "b" * 40)


@pytest.mark.parametrize("nid", ["tests/x.py::TestClass::test_a", "tests/x.py::TestClass::test_p[event]"])
def test_an_exact_class_method_id_is_accepted(nid):
    raw = policy_json([nid])
    assert dt.validate_policy(raw, "b" * 40).ids == (nid,)


def test_a_class_only_id_never_deselects_its_methods_so_they_still_run_in_the_sandbox(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_c.py").write_text(textwrap.dedent('''
        class TestReal:
            def test_a(self): pass
            def test_b(self): pass
    '''), encoding="utf-8")
    report = tmp_path / "rep.json"
    (tmp_path / f"{dt.PLUGIN_NAME}.py").write_text(dt.plugin_source(["tests/test_c.py::TestReal", "tests/test_c.py::TestReal::test_b"], str(report)), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-p", dt.PLUGIN_NAME, "-v", "-p", "no:cacheprovider"], cwd=tmp_path, capture_output=True, text=True,
                       env={**__import__("os").environ, "PYTHONPATH": str(tmp_path)})
    assert r.returncode == 0, r.stdout[-800:]
    assert "test_a PASSED" in r.stdout and "test_b PASSED" not in r.stdout                        # so o metodo exato saiu
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["deselected"] == ["tests/test_c.py::TestReal::test_b"] and data["not_collected"] == ["tests/test_c.py::TestReal"]


@pytest.mark.parametrize("mutate,match", [
    (lambda r: r["delegated"].append(copy.deepcopy(r["delegated"][0])), "duplicado"),
    (lambda r: r["delegated"].reverse(), "fora de ordem"),
    (lambda r: r["delegated"][0].pop("sandbox_proof"), "prova individual"),
    (lambda r: r["delegated"][0].update(reason=""), "prova individual"),
    (lambda r: r["delegated"][0]["sandbox_proof"].update(first_error=""), "prova individual"),
    (lambda r: r.update(delegated=[]), "sem testes"),
    (lambda r: r.update(schema=2), "schema"),
    (lambda r: r["ci"].update(workflow_path=".github/workflows/outro.yml"), "fora do autorizado"),
    (lambda r: r["ci"].update(artifact_name="outro"), "fora do autorizado"),
    (lambda r: r["ci"].update(workflow_blob_sha="xyz"), "workflow_blob_sha"),
])
def test_the_policy_validator_is_strict(mutate, match):
    raw = policy_json()
    mutate(raw)
    with pytest.raises(dt.DelegationError, match=match):
        dt.validate_policy(raw, "b" * 40)


def test_widening_the_exception_list_beyond_the_hard_ceiling_is_refused():
    ids = sorted(f"tests/test_big.py::test_{n:03d}" for n in range(dt.MAX_DELEGATED + 1))
    with pytest.raises(dt.DelegationError, match="teto"):
        dt.validate_policy(policy_json(ids), "b" * 40)


def test_only_delegated_ids_whose_file_was_selected_are_delegated(base):
    root, sha, _ = base
    pol = dt.load_policy(root, run_git, sha)
    assert dt.delegated_in_selection(pol, ["tests/test_other.py"]) == []
    assert dt.delegated_in_selection(pol, ["tests/test_other.py", "tests/test_git_thing.py"]) == IDS


# ------------------------------------------------------------------------------------------------------------------------ plugin (pytest real)
def test_the_plugin_deselects_exactly_the_requested_ids_never_by_prefix_or_file(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_t.py").write_text(textwrap.dedent('''
        import pytest
        def test_a(): pass
        def test_ab(): pass
        @pytest.mark.parametrize("v", ["1", "2"])
        def test_p(v): pass
    '''), encoding="utf-8")
    report = tmp_path / "rep.json"
    (tmp_path / f"{dt.PLUGIN_NAME}.py").write_text(dt.plugin_source(["tests/test_t.py::test_a", "tests/test_t.py::test_p[1]", "tests/test_t.py::test_ausente"], str(report)), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-p", dt.PLUGIN_NAME, "-v", "-p", "no:cacheprovider"], cwd=tmp_path, capture_output=True, text=True,
                       env={**__import__("os").environ, "PYTHONPATH": str(tmp_path)})
    assert r.returncode == 0, r.stdout[-800:]
    out = r.stdout
    assert "test_ab PASSED" in out and "test_p[2] PASSED" in out                                   # prefixo/irmao NAO foram deselecionados
    assert "test_a PASSED" not in out and "test_p[1] PASSED" not in out
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["deselected"] == ["tests/test_t.py::test_a", "tests/test_t.py::test_p[1]"] and data["not_collected"] == ["tests/test_t.py::test_ausente"]


# ------------------------------------------------------------------------------------------------------------------------ evidencia do CI
class Ci:
    """GitHub falso com uma execucao do workflow autorizado e seu artefato; cada teste adultera UM aspecto."""
    def __init__(self, base_sha: str, head: str = HEAD, attempt: int = 1, run_id: int = 900):
        self.head, self.attempt, self.run_id, self.base_sha = head, attempt, run_id, base_sha
        # semantica real do `workflow_run`: head_sha/head_branch da execucao = ponta da branch padrao no disparo; o HEAD do PR so aparece no titulo (`run-name`); `path` sem sufixo
        self.run = {"id": run_id, "run_number": 5, "run_attempt": attempt, "head_sha": base_sha, "head_branch": "develop", "display_title": f"delegated-tests {head}",
                    "event": "workflow_run", "conclusion": "success", "path": ".github/workflows/delegated-tests.yml",
                    "repository": {"full_name": REPO}, "head_repository": {"full_name": REPO}}
        self.report = {"schema": 1, "repository": REPO, "head_sha": head, "run_id": run_id, "run_attempt": attempt, "workflow_path": dt.WORKFLOW_PATH,
                       "policy_base_sha": base_sha, "results": [{"node_id": i, "outcome": "passed"} for i in IDS]}
        self.files = None
        self.artifacts = None
        self.boom = None
        self.digest_override = None
        self.download_boom = False

    def zip_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, data in (self.files if self.files is not None else {dt.RESULT_FILE: json.dumps(self.report)}).items():
                z.writestr(name, data)
        return buf.getvalue()

    def gh(self, path: str):
        if self.boom:
            raise self.boom
        if "/workflows/" in path and path.endswith("per_page=100"):
            assert "head_sha=" not in path and "event=workflow_run" in path and "branch=develop" in path   # filtrar pelo HEAD do PR nunca acharia a execucao
            return {"workflow_runs": [self.run]}
        if path.endswith(f"actions/runs/{self.run_id}/artifacts?per_page=100"):
            if self.artifacts is not None:
                return {"artifacts": self.artifacts}
            data = self.zip_bytes()
            return {"artifacts": [{"id": 77, "name": dt.ARTIFACT_NAME, "expired": False, "digest": self.digest_override or "sha256:" + hashlib.sha256(data).hexdigest(),
                                   "workflow_run": {"id": self.run_id, "head_sha": self.base_sha}}]}
        raise AssertionError(path)

    def download(self, path: str) -> bytes:
        if self.download_boom:
            raise OSError("rede")
        assert path.endswith("/actions/artifacts/77/zip")
        return self.zip_bytes()


def verify(base, ci: Ci, head: str = HEAD):
    root, sha, _ = base
    pol = dt.load_policy(root, run_git, sha)
    return dt.verify_ci_evidence(ci.gh, ci.download, REPO, head, pol, run_git, root)


def test_good_evidence_for_the_exact_head_is_accepted(base):
    ev = verify(base, Ci(base[1]))
    assert ev["run_id"] == 900 and ev["run_attempt"] == 1 and ev["head_sha"] == HEAD and ev["tests"] == 3 and ev["artifact_digest"].startswith("sha256:")


def test_evidence_of_an_old_sha_is_refused(base):
    ci = Ci(base[1], head="b" * 40)                                                         # a execucao existe, mas o titulo e de OUTRO commit do PR
    with pytest.raises(dt.DelegationError, match="HEAD exato"):
        verify(base, ci)


def test_a_run_whose_own_head_sha_is_the_pr_head_is_not_how_workflow_run_works_and_is_refused(base):
    ci = Ci(base[1])
    ci.run["head_sha"] = HEAD                                                               # HEAD do PR nao e commit da base: nao esta na historia
    with pytest.raises(dt.DelegationError, match="historia da base"):
        verify(base, ci)


@pytest.mark.parametrize("field,value", [("event", "pull_request"), ("conclusion", "failure"), ("conclusion", None), ("path", ".github/workflows/ci.yml"),
                                         ("path", ".github/workflows/delegated-tests.yml@refs/pull/9/merge"), ("path", ".github/workflows/delegated-tests.yml@refs/heads/feat/x"),
                                         ("head_branch", "feat/x"), ("head_branch", None), ("display_title", "delegated-tests " + "c" * 40), ("display_title", HEAD),
                                         ("display_title", "outro titulo"), ("head_sha", "zz"), ("head_sha", None),
                                         ("run_number", "5"), ("run_number", None), ("run_number", 5.0), ("run_attempt", "x"), ("run_attempt", True), ("run_attempt", 0),
                                         ("id", "900"), ("id", None), ("repository", "GFCDOTA/sketchup-mcp"), ("head_repository", ["x"]),
                                         ("repository", {"full_name": "outro/repo"}), ("head_repository", {"full_name": "fork/sketchup-mcp"})])
def test_a_run_of_an_unauthorized_workflow_event_branch_fork_title_or_conclusion_is_refused(base, field, value):
    ci = Ci(base[1])
    ci.run[field] = value
    with pytest.raises(dt.DelegationError, match="nenhuma execucao"):
        verify(base, ci)


@pytest.mark.parametrize("path", [".github/workflows/delegated-tests.yml@refs/heads/develop", ".github/workflows/delegated-tests.yml@develop"])
def test_a_path_with_the_base_branch_suffix_is_still_accepted(base, path):
    ci = Ci(base[1])
    ci.run["path"] = path
    assert verify(base, ci)["run_id"] == 900


def test_a_run_that_executed_a_workflow_other_than_the_pinned_blob_is_refused(base):
    root, sha, pin = base
    (root / ".github/workflows/delegated-tests.yml").write_text(WORKFLOW_TEXT + "# versao intermediaria\n", encoding="utf-8", newline="\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "workflow intermediario")
    mid = sh(root, "rev-parse", "HEAD")
    (root / ".github/workflows/delegated-tests.yml").write_text(WORKFLOW_TEXT, encoding="utf-8", newline="\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "workflow restaurado")
    new = sh(root, "rev-parse", "HEAD")
    pol = dt.load_policy(root, run_git, new)
    assert pol.workflow_blob_sha == pin
    ci = Ci(mid)                                                                            # a execucao rodou na base intermediaria, com outra definicao
    with pytest.raises(dt.DelegationError, match="que executou"):
        dt.verify_ci_evidence(ci.gh, ci.download, REPO, HEAD, pol, run_git, root)


def test_a_report_claiming_a_base_other_than_the_one_the_run_executed_on_is_refused(base):
    ci = Ci(base[1])
    ci.report["policy_base_sha"] = "a" * 40
    with pytest.raises(dt.DelegationError, match="rodou em"):
        verify(base, ci)


def test_a_workflow_that_no_longer_matches_the_pinned_blob_is_refused(base):
    root, sha, _ = base
    (root / ".github/workflows/delegated-tests.yml").write_text(WORKFLOW_TEXT + "# alterado\n", encoding="utf-8", newline="\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "workflow alterado sem atualizar a politica")
    new = sh(root, "rev-parse", "HEAD")
    sh(root, "update-ref", "refs/remotes/origin/develop", new)
    pol = dt.load_policy(root, run_git, new)
    ci = Ci(new)
    with pytest.raises(dt.DelegationError, match="blob fixado"):
        dt.verify_ci_evidence(ci.gh, ci.download, REPO, HEAD, pol, run_git, root)


def test_an_artifact_tampered_after_upload_fails_the_digest_check(base):
    ci = Ci(base[1])
    ci.digest_override = "sha256:" + "0" * 64
    with pytest.raises(dt.DelegationError, match="digest"):
        verify(base, ci)


@pytest.mark.parametrize("mutate,match", [
    (lambda r: r.update(head_sha="d" * 40), "head_sha"),
    (lambda r: r.update(run_id=1), "run_id"),
    (lambda r: r.update(run_attempt=9), "run_attempt"),
    (lambda r: r.update(repository="outro/repo"), "repository"),
    (lambda r: r.update(workflow_path=".github/workflows/ci.yml"), "workflow_path"),
    (lambda r: r.update(schema=2), "schema"),
    (lambda r: r.update(policy_base_sha="zz"), "policy_base_sha"),
    (lambda r: r.pop("results"), "results"),
    (lambda r: r["results"].pop(), "ausentes"),
    (lambda r: r["results"].append({"node_id": "tests/test_extra.py::test_x", "outcome": "passed"}), "extras"),
    (lambda r: r["results"].append(dict(r["results"][0])), "duplicado"),
    (lambda r: r["results"][0].update(outcome="skipped"), "nao passaram"),
    (lambda r: r["results"][1].update(outcome="xfail"), "nao passaram"),
    (lambda r: r["results"][2].update(outcome="failed"), "nao passaram"),
    (lambda r: r["results"][0].update(outcome="missing"), "nao passaram"),
    (lambda r: r["results"][0].update(node_id=None), "invalido"),
])
def test_a_tampered_incomplete_skipped_or_inconsistent_report_is_refused(base, mutate, match):
    ci = Ci(base[1])
    mutate(ci.report)
    with pytest.raises(dt.DelegationError, match=match):
        verify(base, ci)


def test_a_report_made_under_a_different_rule_set_is_refused(base):
    root, sha, _ = base
    (root / dt.COLLECTOR_PATH).write_text("# outro coletor\n", encoding="utf-8", newline="\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "coletor mudou depois da execucao do CI")
    new = sh(root, "rev-parse", "HEAD")
    sh(root, "update-ref", "refs/remotes/origin/develop", new)
    pol = dt.load_policy(root, run_git, new)
    ci = Ci(sha)                                                                            # o CI rodou com o coletor ANTIGO (base `sha`)
    with pytest.raises(dt.DelegationError, match="outra regra"):
        dt.verify_ci_evidence(ci.gh, ci.download, REPO, HEAD, pol, run_git, root)


@pytest.mark.parametrize("setup,match", [
    (lambda ci: setattr(ci, "artifacts", []), "exatamente 1"),
    (lambda ci: setattr(ci, "artifacts", [{"id": 77, "name": dt.ARTIFACT_NAME, "expired": True, "digest": "sha256:x", "workflow_run": {"id": 900, "head_sha": HEAD}}]), "exatamente 1"),
    (lambda ci: setattr(ci, "artifacts", [{"id": 77, "name": "outro", "expired": False, "digest": "sha256:x", "workflow_run": {"id": 900, "head_sha": HEAD}}]), "exatamente 1"),
    (lambda ci: setattr(ci, "artifacts", [{"id": 77, "name": dt.ARTIFACT_NAME, "expired": False, "digest": "sha256:x", "workflow_run": {"id": 901, "head_sha": HEAD}}]), "nao pertence"),
    (lambda ci: setattr(ci, "artifacts", [{"id": 77, "name": dt.ARTIFACT_NAME, "expired": False, "digest": "sha256:x", "workflow_run": {"id": 900, "head_sha": "e" * 40}}]), "nao pertence"),
    (lambda ci: setattr(ci, "artifacts", [{"id": 77, "name": dt.ARTIFACT_NAME, "expired": False, "digest": "sha256:x", "workflow_run": {"id": "900", "head_sha": ci.base_sha}}]),
     "nao pertence"),
    (lambda ci: setattr(ci, "artifacts", [{"id": 77, "name": dt.ARTIFACT_NAME, "expired": False, "digest": "sha256:x", "workflow_run": "900"}]), "nao pertence"),
    (lambda ci: setattr(ci, "artifacts", [{"id": "77", "name": dt.ARTIFACT_NAME, "expired": False, "digest": "sha256:x", "workflow_run": {"id": 900, "head_sha": ci.base_sha}}]),
     "nao pertence"),
    (lambda ci: setattr(ci, "files", {}), "inesperado"),
    (lambda ci: setattr(ci, "files", {dt.RESULT_FILE: "{}", "extra.txt": "x"}), "inesperado"),
    (lambda ci: setattr(ci, "files", {dt.RESULT_FILE: "isto nao e json"}), "ilegivel"),
    (lambda ci: setattr(ci, "files", {dt.RESULT_FILE: "[]"}), "nao e um objeto"),
    (lambda ci: setattr(ci, "files", {dt.RESULT_FILE: '"texto"'}), "nao e um objeto"),
    (lambda ci: setattr(ci, "files", {dt.RESULT_FILE: "3"}), "nao e um objeto"),
    (lambda ci: setattr(ci, "files", {"results.txt": "{}"}), "inesperado"),
    (lambda ci: setattr(ci, "download_boom", True), "download"),
])
def test_incomplete_missing_or_foreign_evidence_is_refused(base, setup, match):
    ci = Ci(base[1])
    setup(ci)
    with pytest.raises(dt.DelegationError, match=match):
        verify(base, ci)


@pytest.mark.parametrize("boom", [RuntimeError("HTTP 502"), TimeoutError("sem resposta"), OSError("rede caiu"), ValueError("json invalido")])
def test_github_being_down_is_fail_closed(base, boom):
    ci = Ci(base[1])
    ci.boom = boom
    with pytest.raises(dt.DelegationError, match="GitHub indisponivel"):
        verify(base, ci)


def test_a_zip_that_is_not_a_zip_is_refused(base):
    ci = Ci(base[1])
    ci.zip_bytes = lambda: b"nao e zip"                                                     # type: ignore[method-assign]
    with pytest.raises(dt.DelegationError, match="ilegivel"):
        verify(base, ci)


# ------------------------------------------------------------------------------------------------------------------------ plano + conclusao
def delegation(base, ci, changed=("tools/a.py",), head=HEAD):
    root, _sha, _ = base
    return dt.Delegation(gh=ci.gh, repo=REPO, head_sha=head, changed_files=list(changed), root=root, run_git=no_fetch_git, download=ci.download)


def test_the_plan_is_active_only_with_a_valid_base_policy_and_an_eligible_pr(base):
    ci = Ci(base[1])
    planned = dt.plan(delegation(base, ci), ["tests/test_git_thing.py", "tests/test_other.py"])
    assert planned["active"] and planned["ids"] == IDS
    off = dt.plan(delegation(base, ci, changed=[dt.POLICY_PATH]), ["tests/test_git_thing.py"])
    assert off["active"] is False and off["ids"] == [] and "propria regra" in off["note"]


def test_a_broken_base_policy_delegates_nothing_and_says_why(base):
    root, sha, _ = base
    (root / POLICY_FILE).write_text("{ quebrado", encoding="utf-8", newline="\n")
    sh(root, "add", "-A")
    sh(root, "commit", "-q", "-m", "politica quebrada")
    new = sh(root, "rev-parse", "HEAD")
    sh(root, "update-ref", "refs/remotes/origin/develop", new)
    planned = dt.plan(delegation(base, Ci(sha)), ["tests/test_git_thing.py"])
    assert planned["active"] is False and planned["ids"] == [] and "nao e JSON" in planned["error"]


def test_settle_demands_the_plugin_report_to_match_the_request_exactly(base):
    ci = Ci(base[1])
    d = delegation(base, ci)
    planned = dt.plan(d, ["tests/test_git_thing.py"])
    good = {"requested": IDS, "deselected": IDS, "not_collected": []}
    assert dt.settle(d, planned, {"delegation": good})["ok"] is True
    for facts, text in (({}, "ausente"), ({"delegation": None}, "ausente"), ({"delegation": {**good, "requested": IDS[:1]}}, "diferente do pedido"),
                        ({"delegation": {**good, "not_collected": [IDS[0]]}}, "nao coletado"), ({"delegation": {**good, "deselected": IDS[:2]}}, "diferentes")):
        res = dt.settle(d, planned, facts)
        assert res["ok"] is False and text in res["reasons"][0]


def test_settle_fails_closed_when_the_ci_evidence_is_missing(base):
    ci = Ci(base[1])
    ci.artifacts = []
    d = delegation(base, ci)
    planned = dt.plan(d, ["tests/test_git_thing.py"])
    res = dt.settle(d, planned, {"delegation": {"requested": IDS, "deselected": IDS, "not_collected": []}})
    assert res["ok"] is False and "exatamente 1" in res["reasons"][0] and res["evidence"] is None


# ------------------------------------------------------------------------------------------------------------------------ integracao com o revisor
class FakeRun:
    def __init__(self, code=0, facts=None):
        self.exit_code, self.timed_out, self.output, self.facts = code, False, "ok", facts or {}












# ------------------------------------------------------------------------------------------------------------------------ coletor do CI
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


def git_blob_sha(data: bytes) -> str:
    """Blob que o git GUARDA para o arquivo (o repositorio normaliza texto para LF), independente do checkout CRLF do Windows e sem precisar do binario `git`."""
    data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def test_the_pinned_blob_check_is_the_same_in_lf_and_crlf_checkouts():
    lf = b"name: x\non: push\n"
    assert git_blob_sha(lf) == git_blob_sha(lf.replace(b"\n", b"\r\n")) == hashlib.sha1(b"blob 17\0" + lf).hexdigest()


def test_a_failed_fetch_never_falls_back_to_a_stale_local_base(base):
    root, sha, _ = base
    def git(args, cwd):
        if args[:1] == ["fetch"]:
            return 128, "fatal: unable to access origin"
        return run_git(args, cwd)
    with pytest.raises(dt.DelegationError, match="fetch"):
        dt.trusted_base_sha(root, git)                                                       # origin/develop local existe e resolveria; mesmo assim nada vale


def test_the_repository_policy_matches_the_workflow_it_pins_and_names_only_exact_ids():
    root = Path(__file__).resolve().parents[1]
    pol = dt.validate_policy(json.loads((root / POLICY_FILE).read_text(encoding="utf-8")), "b" * 40)
    assert pol.workflow_blob_sha == git_blob_sha((root / dt.WORKFLOW_PATH).read_bytes())    # workflow e politica andam juntos (blob do COMMIT, nao da worktree)
    # 28 do executor + 53 do laboratorio (git) + 7 TestRealProcesses do event_store (pipe nomeado do multiprocessing negado no AppContainer) — 2026-11-16
    files = {"tests/test_event_executor_deliver.py": 28, "tests/test_closed_loop_lab.py": 53, "tests/test_event_store.py": 7}
    assert len(pol.ids) == sum(files.values()) <= dt.MAX_DELEGATED
    assert {f: sum(1 for i in pol.ids if i.startswith(f + "::")) for f in files} == files
    raw = json.loads((root / POLICY_FILE).read_text(encoding="utf-8"))["delegated"]
    reasons = {"tests/test_event_store.py": "multiprocessing_pipe_denied_in_appcontainer"}
    assert all(d["reason"] == reasons.get(d["node_id"].split("::")[0], "git_unavailable_in_appcontainer") and d["sandbox_proof"]["run_alone"] is True
               for d in raw)                                                                                   # prova individual de cada um
    assert all(i.startswith("tests/test_event_store.py::TestRealProcesses::") for i in pol.ids if i.startswith("tests/test_event_store.py"))
    assert not any("real_appcontainer" in i for i in pol.ids)                                                 # o teste @windows_only seria PULADO no CI Linux
