"""Issue #589 fase 2: execucao do Claude local a partir da fila. Tudo com runner/gh/worktree injetados (nada real e executado)."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

import pytest

from tools.orchestration import event_bridge as eb
from tools.orchestration import event_executor as ex

NOW = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)
HEAD = "a" * 40
NEWHEAD = "d" * 40
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}
REPO = eb.REPO


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "bridge.json"))
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "exec.json"))
    monkeypatch.setenv("BRIDGE_WORKTREE_ROOT", str(tmp_path / "wt"))
    monkeypatch.setenv("GH_TOKEN", "ghp_" + "x" * 30)
    monkeypatch.setattr(ex, "CONFIRM_PAUSE_S", 0.0)                          # nao espera de verdade o GitHub atualizar o HEAD
    monkeypatch.setattr(ex, "deliver", fake_deliver)                         # a entrega tem testes proprios (test_event_executor_deliver)
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, NEWHEAD))   # `git ls-remote` real nao roda aqui: a ponta remota e o commit publicado
    monkeypatch.setattr(ex, "comment_pr", lambda *a, **k: None)


def fake_deliver(wt, branch, base, py, it, **kw):
    """Como o `deliver` real: registra em `item["published_sha"]` o commit que SERA publicado e devolve PUSHED."""
    it["published_sha"] = NEWHEAD
    return ("PUSHED", "fake")


def item(**kw):
    base = {"key": f"review:9:7:{HEAD}", "kind": "review", "event_id": "review:9", "pr": 7, "issue": 589, "head_sha": HEAD,
            "author": "fmmodesto", "url": "https://x", "state": "QUEUED", "queued_at": "2026-11-04T11:00:00Z"}
    return {**base, **kw}


def bstate(*items):
    return {**eb.default_bridge_state(), "queue": list(items), "seen": [i["key"] for i in items]}


class FakeGh:
    def __init__(self, head=HEAD, state="open", fork=False, ref="feat/589-x", login="fmodesto30", review_user="fmmodesto",
                 review_state="CHANGES_REQUESTED", review_commit=HEAD, body="Refs #589", labels=("executor-ok",)):
        self.head, self.state, self.fork, self.ref, self.login, self.body = head, state, fork, ref, login, body
        self.labels = list(labels)
        self.rev = {"id": 9, "user": {"login": review_user}, "state": review_state, "commit_id": review_commit,
                    "html_url": "https://x", "submitted_at": "t"}

    def __call__(self, path):
        if path == "user":
            return {"login": self.login}
        if path == f"repos/{REPO}/pulls/7":
            return {"number": 7, "body": self.body, "state": self.state, "labels": [{"name": n} for n in self.labels],
                    "head": {"sha": self.head, "ref": self.ref,
                                                  "repo": {"full_name": "outro/fork" if self.fork else REPO}}}
        if path == f"repos/{REPO}/pulls/7/reviews/9":
            return self.rev
        if path == f"repos/{REPO}/pulls/7/reviews/9/comments":
            return [{"path": "x.py", "line": 3, "body": "troque isto"}]
        raise AssertionError(path)


class Runner:
    """Simula o claude: opcionalmente 'empurra um commit' mudando o head do FakeGh."""
    def __init__(self, gh, push=True, rc=0, out="", err="", timed_out=False, boom=None):
        self.gh, self.push, self.rc, self.out, self.err, self.timed_out, self.boom = gh, push, rc, out, err, timed_out, boom
        self.calls = []

    def __call__(self, argv, cwd, env, stdin, timeout, cancel=None):
        self.calls.append({"argv": argv, "cwd": cwd, "env": env, "stdin": stdin, "timeout": timeout})
        if self.boom:
            raise self.boom
        if self.push:
            self.gh.head = NEWHEAD
        return self.rc, self.out, self.err, self.timed_out


def wt_ok(pr, branch, sha, root):
    return True, "", Path("wt") / f"bridge-pr{pr}"


def go(gh, b, runner=None, execute=True, wt=wt_ok, now=NOW, claude_bin="claude", **kw):
    """O estado vive no DISCO (como em producao): semeia `b`, roda um item e devolve `b` atualizado in-place."""
    eb.save(b)
    res = ex.process_one(gh, POLICY, REPO, execute, runner or Runner(gh), claude_bin, wt, now, **kw)
    b.clear()
    b.update(eb.load())
    return res


# ------------------------------------------------------------------------------------------------- fluxo feliz
def test_dry_run_never_launches_anything_and_leaves_the_item_queued():
    gh, r = FakeGh(), None
    r = Runner(gh)
    b = bstate(item())
    res = go(gh, b, r, execute=False)
    assert res["action"] == "DRY_RUN" and r.calls == [] and b["queue"][0]["state"] == "QUEUED"


def test_execute_runs_claude_once_in_the_pr_worktree_and_records_done_awaiting_rereview():
    gh = FakeGh()
    r = Runner(gh)
    b = bstate(item())
    res = go(gh, b, r)
    assert res == {"action": "DONE", "item": b["queue"][0]["key"], "new_head": NEWHEAD, "delivery": "PUSHED"}
    t = b["queue"][0]
    assert t["state"] == "DONE_AWAITING_REREVIEW" and t["new_head"] == NEWHEAD and t["attempts"] == 1 and len(r.calls) == 1
    assert r.calls[0]["cwd"].name == "bridge-pr7" and r.calls[0]["timeout"] == ex.RUN_TIMEOUT_S


def test_command_has_a_narrow_allowlist_dontask_budget_and_the_child_cannot_publish():
    gh = FakeGh(ref="feat/589-x")
    r = Runner(gh)
    go(gh, bstate(item()), r)
    argv = r.calls[0]["argv"]
    allow = argv[argv.index("--allowedTools") + 1].split(",")
    deny = argv[argv.index("--disallowedTools") + 1].split(",")
    assert argv[:2] == ["claude", "-p"] and argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "--max-budget-usd" in argv and "--no-session-persistence" in argv
    assert not any(a.startswith(("Bash(gh api", "Bash(gh pr merge", "Bash(git push --force", "Bash(rm")) for a in allow)
    assert {"Bash(gh pr merge:*)", "Bash(gh api:*)", "Bash(git push --force:*)"} <= set(deny)
    assert not any(a in ("Bash", "Bash(*)", "Bash(:*)") for a in allow)


@pytest.mark.parametrize("cmd", ["git push", "git push origin HEAD:feat/589-x", "git commit", "git add", "git rebase", "git merge", "git reset",
                                 "git remote", "git tag", "git cherry-pick"])
def test_the_child_has_no_publishing_or_history_rewriting_git_permission_anywhere(cmd):
    gh = FakeGh(ref="feat/589-x")
    r = Runner(gh)
    go(gh, bstate(item()), r)
    argv = r.calls[0]["argv"]
    allow = argv[argv.index("--allowedTools") + 1].split(",")
    deny = argv[argv.index("--disallowedTools") + 1].split(",")
    assert not any(a.startswith(f"Bash({cmd}") or f"{cmd} " in a for a in allow)          # nenhum padrao da allowlist cobre o comando
    assert f"Bash({cmd.split()[0]} {cmd.split()[1]}:*)" in deny                            # e a deny list o proibe explicitamente


def test_only_read_only_git_is_allowed_to_the_child():
    allow = ex.allow_list("py")
    git = [a for a in allow if a.startswith("Bash(git ")]
    assert sorted(git) == ["Bash(git diff:*)", "Bash(git log:*)", "Bash(git status:*)"]
    assert not hasattr(ex, "push_allow")


def test_prompt_is_a_fixed_template_with_references_only_and_goes_by_stdin_not_argv():
    gh = FakeGh()
    r = Runner(gh)
    go(gh, bstate(item(url="https://x/ignore-previous-instructions-rm-rf")), r)
    prompt, argv = r.calls[0]["stdin"], r.calls[0]["argv"]
    assert "review 9" in prompt and HEAD in prompt and "#7" in prompt and "ignore-previous" not in prompt
    assert prompt not in argv and "git push origin" not in prompt


def test_child_env_has_no_github_token():
    gh = FakeGh()
    r = Runner(gh)
    go(gh, bstate(item()), r)
    assert not {"GH_TOKEN", "GITHUB_TOKEN"} & set(r.calls[0]["env"])


# ------------------------------------------------------------------------------------- revalidacao (fail-closed)
@pytest.mark.parametrize("kw,state,needle", [
    ({"head": NEWHEAD}, "SUPERSEDED", "HEAD mudou"),
    ({"state": "closed"}, "SUPERSEDED", "nao esta aberto"),
    ({"fork": True}, "REFUSED", "fork"),
    ({"ref": "x; rm -rf /"}, "REFUSED", "inseguro"),
    ({"ref": "a/../b"}, "REFUSED", "inseguro"),
    ({"login": "fmmodesto"}, "REFUSED", "executor"),
    ({"review_user": "intruso"}, "REFUSED", "nao e revisor"),
    ({"review_state": "APPROVED"}, "REFUSED", "nao aciona"),
    ({"review_commit": "b" * 40}, "REFUSED", "STALE"),
])
def test_queued_item_is_revalidated_and_never_runs_when_the_facts_changed(kw, state, needle):
    gh = FakeGh(**kw)
    r = Runner(gh)
    b = bstate(item())
    res = go(gh, b, r)
    assert r.calls == [] and b["queue"][0]["state"] == state and needle in res["reason"]


def test_a_github_failure_in_preflight_fails_closed():
    def boom(path):
        raise RuntimeError("rate limit")
    r = Runner(FakeGh())
    b = bstate(item())
    go(boom, b, r)
    assert r.calls == [] and b["queue"][0]["state"] == "REFUSED"


# ------------------------------------------------------------------------------------- credenciais / CLI / falhas
CRED_OUT = json.dumps({"type": "result", "is_error": True, "result": "Not logged in · Please run /login"})


def test_missing_claude_login_blocks_with_a_diagnostic_and_does_not_burn_attempts_then_resumes():
    gh = FakeGh()
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False, out=CRED_OUT))
    t = b["queue"][0]
    assert res["action"] == "BLOCKED_CREDENTIALS" and t["state"] == "BLOCKED_CREDENTIALS" and t.get("attempts", 0) == 0
    assert "claude auth login" in t["last_error"] and t["retry_after"] > ex.es.now_iso(NOW)
    assert go(gh, b, Runner(gh), now=NOW)["action"] == "IDLE"                # ainda em espera (retry_after)
    later = NOW + dt.timedelta(seconds=ex.RETRY_S + 1)
    assert go(gh, b, Runner(gh), now=later)["action"] == "DONE"              # logou: retoma sem duplicar


def test_claude_cli_not_installed_is_blocked_cli_with_a_message():
    gh = FakeGh()
    b = bstate(item())
    res = go(gh, b, Runner(gh, boom=FileNotFoundError("claude")))
    assert res["action"] == "BLOCKED_CLI" and "nao encontrada" in b["queue"][0]["last_error"]


@pytest.mark.parametrize("kw,reason", [({"push": False}, "sem commit novo"), ({"push": False, "rc": 1}, "codigo 1"),
                                       ({"push": False, "rc": -1, "timed_out": True}, "timeout")])
def test_failed_runs_are_retried_with_a_cap_of_three_attempts(kw, reason, monkeypatch):
    if reason == "sem commit novo":
        monkeypatch.setattr(ex, "deliver", lambda *a, **k: ("NOOP", "nenhuma alteracao"))      # o filho terminou sem editar nada
    gh = FakeGh()
    b = bstate(item())
    clock = NOW
    for n in range(1, ex.MAX_ATTEMPTS + 1):
        res = go(gh, b, Runner(gh, **kw), now=clock)
        assert res["action"] == "FAILED" and reason in res["reason"] and b["queue"][0]["attempts"] == n
        clock += dt.timedelta(days=1)
        b["runs"] = []                                                       # isola do teto diario
        eb.save(b)
    assert go(gh, b, Runner(gh, **kw), now=clock)["action"] == "IDLE"        # 3 tentativas: para (anti-laco)


def test_daily_cap_stops_new_runs():
    gh = FakeGh()
    b = bstate(item())
    b["runs"] = [ex.es.now_iso(NOW - dt.timedelta(hours=1))] * ex.DAILY_CAP
    r = Runner(gh)
    assert go(gh, b, r)["action"] == "IDLE" and r.calls == []


def test_kill_switch_file_disables_execution(tmp_path):
    (tmp_path / "EXECUTOR_DISABLED").write_text("x", encoding="utf-8")
    gh = FakeGh()
    r = Runner(gh)
    assert go(gh, bstate(item()), r)["action"] == "DISABLED" and r.calls == []


# ------------------------------------------------------------------------- concorrencia 1 e recuperacao apos reinicio
def test_concurrency_is_one_a_running_item_with_a_valid_lease_blocks_the_next():
    gh = FakeGh()
    running = item(key="k1", state="RUNNING", lease_expires=ex.es.now_iso(NOW + dt.timedelta(hours=1)))
    r = Runner(gh)
    assert go(gh, bstate(running, item(key="k2")), r)["action"] == "IDLE" and r.calls == []


def test_restart_after_crash_requeues_an_expired_running_item_and_runs_it_once():
    gh = FakeGh()
    stuck = item(state="RUNNING", lease_expires=ex.es.now_iso(NOW - dt.timedelta(minutes=1)), attempts=0)
    b = bstate(stuck)
    r = Runner(gh)
    res = go(gh, b, r)
    assert res["action"] == "DONE" and len(r.calls) == 1
    assert go(gh, b, Runner(gh))["action"] == "IDLE"                         # concluido: nao roda de novo


def test_restart_after_the_claude_already_pushed_never_reruns_the_old_review():
    gh = FakeGh(head=NEWHEAD)                                                # crash depois do push: o HEAD ja mudou
    stuck = item(state="RUNNING", lease_expires=ex.es.now_iso(NOW - dt.timedelta(minutes=1)))
    b = bstate(stuck)
    r = Runner(gh)
    res = go(gh, b, r)
    assert res["action"] == "SUPERSEDED" and r.calls == []


def test_running_is_persisted_before_the_child_starts_so_a_crash_is_recoverable(tmp_path):
    gh = FakeGh()
    seen = {}

    def spy(argv, cwd, env, stdin, timeout, cancel=None):
        seen["disk"] = json.loads((tmp_path / "bridge.json").read_text(encoding="utf-8"))["queue"][0]["state"]
        gh.head = NEWHEAD
        return 0, "", "", False
    go(gh, bstate(item()), spy)
    assert seen["disk"] == "RUNNING"


# -------------------------------------------------------------------------------------------------- worktree e logs
def test_dirty_existing_worktree_is_preserved_and_blocks_the_run(tmp_path):
    wt = tmp_path / "wt" / "bridge-pr7"
    wt.mkdir(parents=True)
    calls = []

    def fake_git(args, cwd):
        calls.append(args)
        return (0, " M arquivo.py") if args[0] == "status" else (0, "")
    ok, msg, _ = ex.prepare_worktree(7, "b", HEAD, tmp_path, run=fake_git)
    assert not ok and "preservado" in msg and all(c[0] == "status" for c in calls)      # nada de checkout/clean/remove


def test_new_worktree_is_created_detached_at_the_sha(tmp_path):
    calls = []

    def fake_git(args, cwd):
        calls.append(args)
        return 0, ""
    ok, _, wt = ex.prepare_worktree(7, "feat/x", HEAD, tmp_path, run=fake_git)
    assert ok and calls[0] == ["fetch", "origin", "feat/x"] and calls[1][:3] == ["worktree", "add", "--detach"] and calls[1][-1] == HEAD
    assert wt.name == "bridge-pr7" and wt.parent.name == "wt"


def test_logs_redact_secrets_and_the_state_has_no_secret(tmp_path):
    gh = FakeGh()
    leak = "ghp_" + "A" * 30
    b = bstate(item())
    go(gh, b, Runner(gh, out=f"token {leak} Bearer {'z' * 30}", err=f"sk-ant-{'q' * 30}"))
    log = Path(b["queue"][0]["log"]).read_text(encoding="utf-8")
    assert leak not in log and "[REDACTED]" in log and "sk-ant-" not in log
    assert leak not in json.dumps(b)


def test_issue_lease_is_visible_to_the_scheduler_state_and_released_after(tmp_path):
    gh = FakeGh()
    seen = {}

    def spy(argv, cwd, env, stdin, timeout, cancel=None):
        seen["claims"] = sorted(ex.es.load(tmp_path / "exec.json")["claims"])
        gh.head = NEWHEAD
        return 0, "", "", False
    go(gh, bstate(item()), spy)
    assert seen["claims"] == ["589"] and ex.es.load(tmp_path / "exec.json")["claims"] == {}


def test_run_cycle_polls_then_executes_end_to_end_with_fakes(tmp_path):
    gh = FakeGh()

    def api(path):
        if path.startswith(f"repos/{REPO}/pulls?"):
            return [{"number": 7, "head": {"sha": gh.head}, "body": "Refs #589"}]
        if path.endswith("/pulls/7/reviews?per_page=100"):
            return [gh.rev]
        if "/issues/comments" in path:
            return []
        return gh(path)
    r = Runner(gh)
    res = ex.run_cycle(api, POLICY, REPO, True, r, "claude", wt_ok, NOW)
    assert res["poll"]["ACCEPT"] == 1 and res["action"] == "DONE" and len(r.calls) == 1
    res2 = ex.run_cycle(api, POLICY, REPO, True, Runner(gh), "claude", wt_ok, NOW)    # reinicio: nada novo, nada duplicado
    assert res2["poll"]["ACCEPT"] == 0 and res2["action"] == "IDLE"


# ------------------------------------------------- exclusao mutua: claim/lease duravel, SEM segurar a trava durante o Claude
def test_the_state_lock_is_not_held_while_claude_runs_and_a_second_process_never_runs_the_same_item(tmp_path):
    """O lockfile de es.locked e quebrado apos 60 s; segurar 45 min o tornaria inutil. Aqui o runner bloqueia: a trava tem de
    estar LIVRE, o item RUNNING com dono+lease no disco, e um segundo processo nao pode executar o mesmo item."""
    import threading
    gh = FakeGh()
    eb.save(bstate(item()))
    started, release = threading.Event(), threading.Event()
    first = Runner(gh)
    inside = {}

    def blocking(argv, cwd, env, stdin, timeout, cancel=None):
        started.set()
        assert release.wait(10)
        return first(argv, cwd, env, stdin, timeout)

    out = {}
    th = threading.Thread(target=lambda: out.update(ex.process_one(gh, POLICY, REPO, True, blocking, "claude", wt_ok, NOW)))
    th.start()
    assert started.wait(10)
    try:
        assert not (tmp_path / "bridge.lock").exists()                       # trava livre durante o trabalho longo
        disk = eb.load()["queue"][0]
        inside.update(state=disk["state"], owner=disk.get("owner"), lease=disk.get("lease_expires"))
        second = Runner(gh)
        # segundo "processo" (outra chamada independente, estado so no disco), inclusive com o relogio adiante mas dentro do lease
        res2 = ex.process_one(gh, POLICY, REPO, True, second, "claude", wt_ok, NOW + dt.timedelta(seconds=30))
        assert res2["action"] == "IDLE" and second.calls == []
    finally:
        release.set()
        th.join(15)
    assert inside["state"] == "RUNNING" and inside["owner"] and inside["lease"] > ex.es.now_iso(NOW)
    assert out["action"] == "DONE" and len(first.calls) == 1
    final = eb.load()["queue"][0]
    assert final["state"] == "DONE_AWAITING_REREVIEW" and "owner" not in final and "lease_expires" not in final


def test_heartbeat_renews_the_lease_while_the_child_runs(monkeypatch):
    import threading
    gh = FakeGh()
    eb.save(bstate(item()))
    started, release = threading.Event(), threading.Event()
    seen = {}

    def slow(argv, cwd, env, stdin, timeout, cancel=None):
        seen["before"] = eb.load()["queue"][0]["lease_expires"]
        started.set()
        release.wait(10)
        seen["after"] = eb.load()["queue"][0]["lease_expires"]
        gh.head = NEWHEAD
        return 0, "", "", False

    th = threading.Thread(target=lambda: ex.process_one(gh, POLICY, REPO, True, slow, "claude", wt_ok, NOW, None, 0.05))
    th.start()
    assert started.wait(10)
    import time
    deadline = time.time() + 8                                               # espera ATE o heartbeat renovar (nao um sleep fixo: carga na maquina atrasa a thread)
    while time.time() < deadline and eb.load()["queue"][0]["lease_expires"] <= seen["before"]:
        time.sleep(0.05)
    release.set()
    th.join(15)
    assert seen["after"] > seen["before"]                                    # renovado pelo relogio real (NOW fixo e antigo)


def test_a_process_that_lost_its_lease_never_overwrites_the_new_owner_state():
    gh = FakeGh()
    eb.save(bstate(item()))

    def runner(argv, cwd, env, stdin, timeout, cancel=None):                              # outro processo assume o item no meio da execucao
        b = eb.load()
        b["queue"][0].update(state="RUNNING", owner="outro-dono")
        eb.save(b)
        gh.head = NEWHEAD
        return 0, "", "", False

    ex.process_one(gh, POLICY, REPO, True, runner, "claude", wt_ok, NOW)
    t = eb.load()["queue"][0]
    assert t["state"] == "RUNNING" and t["owner"] == "outro-dono"            # nada sobrescrito
    assert any("lease perdido" in d["message"] for d in eb.load()["diagnostics"])


def test_restart_with_a_valid_lease_does_not_steal_the_item_but_an_expired_one_is_recovered_once():
    gh = FakeGh()
    live = item(state="RUNNING", owner="vivo", lease_expires=ex.es.now_iso(NOW + dt.timedelta(minutes=4)))
    b = bstate(live)
    r = Runner(gh)
    assert go(gh, b, r, now=NOW + dt.timedelta(minutes=1))["action"] == "IDLE" and r.calls == []
    assert go(gh, b, r, now=NOW + dt.timedelta(minutes=10))["action"] == "DONE" and len(r.calls) == 1     # dono morto: lease venceu
    assert b["queue"][0].get("owner") is None


def test_unexpected_executor_error_never_leaves_an_orphan_running_item():
    gh = FakeGh()
    b = bstate(item())

    def bad_wt(pr, branch, sha, root):
        raise ZeroDivisionError("boom")
    res = go(gh, b, Runner(gh), wt=bad_wt)
    t = b["queue"][0]
    assert res["action"] == "FAILED" and t["state"] == "FAILED" and "owner" not in t and t["attempts"] == 1


# ------------------------------------------------------------------------------------ escopo: Refs reais e eventos comment
def test_pr_that_no_longer_references_the_issue_is_refused_even_if_the_queue_says_otherwise():
    gh = FakeGh(body="agora sem referencia a Issue")
    r = Runner(gh)
    b = bstate(item())
    res = go(gh, b, r)
    assert r.calls == [] and b["queue"][0]["state"] == "REFUSED" and "fora de escopo" in res["reason"]
    gh2 = FakeGh(body="Refs #590")                                           # troca de Issue tambem sai do escopo
    b2 = bstate(item())
    assert go(gh2, b2, Runner(gh2))["action"] == "REFUSED"


def test_a_comment_event_is_parked_with_a_diagnostic_and_never_treated_as_a_review():
    gh = FakeGh()
    r = Runner(gh)
    c = item(key="comment:5:3:-", kind="comment", event_id="comment:5", pr=None, head_sha="", author="fmmodesto")
    b = bstate(c)
    res = go(gh, b, r)
    t = b["queue"][0]
    assert res["action"] == "UNSUPPORTED" and r.calls == [] and t["state"] == "PARKED_UNSUPPORTED"
    assert "nao e uma revisao" in t["last_error"]
    assert go(gh, b, Runner(gh))["action"] == "IDLE"                         # estacionado nao e reprocessado


# -------------------------------------------------------------------------------------- portabilidade (venv / allowlist)
def test_venv_python_is_derived_not_hardcoded_and_can_be_overridden(monkeypatch):
    monkeypatch.delenv("BRIDGE_PYTHON", raising=False)
    py = ex.venv_python()
    assert py.endswith((".venv/Scripts/python.exe", ".venv/bin/python")) and "\\" not in py
    assert py.startswith(ex.repo_root().as_posix())
    bs = chr(92)
    for given in (f"D:{bs}outra{bs}maquina{bs}py.exe", "D:/outra/maquina/py.exe", f"D:/outra{bs}maquina/py.exe",
                  "/opt/venv/bin/python"):                                   # Windows, Unix e misto: mesmo resultado em qualquer host
        monkeypatch.setenv("BRIDGE_PYTHON", given)
        assert ex.venv_python() == given.replace(bs, "/")
    monkeypatch.setenv("BRIDGE_PYTHON", "D:/outra/maquina/py.exe")
    assert "D:/outra/maquina/py.exe -m pytest" in " ".join(ex.build_command("claude", Path("wt"), "b"))
    src = Path(ex.__file__).read_text(encoding="utf-8")
    assert "E:/Claude" not in src and "E:\\Claude" not in src


def test_execution_is_never_the_default_in_main_and_the_launcher():
    import inspect
    assert "--execute" in inspect.getsource(ex.main) and 'action="store_true"' in inspect.getsource(ex.main)
    ps1 = (ex.repo_root() / "tools/orchestration/run_event_bridge.ps1").read_text(encoding="utf-8")
    assert "[switch]$Execute" in ps1 and "if ($Execute)" in ps1


# --------------------------------------------- achados medidos no Windows real (claude.cmd, hook do usuario, instalador)
def test_child_ignores_user_and_branch_settings_and_mcp_so_the_allowlist_is_the_only_permission_source():
    argv = ex.build_command("claude", Path("wt"), "feat/x")
    # `local` AINDA carrega .claude/settings.local.json do cwd (medido: hook hostil executou) => fonte VAZIA
    assert argv[argv.index("--setting-sources") + 1] == "" and "--strict-mcp-config" in argv and "local" not in argv


def test_resolve_claude_prefers_the_real_exe_next_to_the_npm_cmd_shim_and_never_runs_a_cmd(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_BIN", raising=False)
    shim = tmp_path / "claude.cmd"
    shim.write_text("@echo off", encoding="utf-8")
    exe = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("x", encoding="utf-8")
    monkeypatch.setattr(ex.shutil, "which", lambda name: str(shim))
    assert ex.resolve_claude() == str(exe)
    exe.unlink()
    assert ex.resolve_claude() == "claude"                                   # sem exe: nao devolve o .cmd (cmd.exe = injecao)
    monkeypatch.setenv("CLAUDE_BIN", "D:/x/claude.exe")
    assert ex.resolve_claude() == "D:/x/claude.exe"


def test_task_scheduler_installer_is_ascii_dry_run_by_default_and_has_a_remove_switch():
    raw = (ex.repo_root() / "tools/orchestration/install_event_bridge_task.ps1").read_bytes()
    assert all(b < 128 for b in raw)                                         # PS 5.1 sem BOM le ANSI: acento quebra
    ps1 = raw.decode("ascii")
    assert "[switch]$Execute" in ps1 and 'if ($Execute) { $argLine += " -Execute" }' in ps1
    assert "[switch]$Remove" in ps1 and "Unregister-ScheduledTask" in ps1 and "-MultipleInstances IgnoreNew" in ps1
    assert "-RunLevel Limited" in ps1 and "Start-ScheduledTask" not in ps1.replace("# Nada e iniciado aqui: use `Start-ScheduledTask", "")


# ------------------------------------------- perda de lease com o filho AINDA VIVO: ele e derrubado (fail-closed, 2o review)
def test_losing_the_lease_while_the_child_is_alive_cancels_the_child_and_discards_its_result():
    gh = FakeGh()
    eb.save(bstate(item()))
    seen = {}

    def live_child(argv, cwd, env, stdin, timeout, cancel=None):
        b = eb.load()                                                          # outro executor reivindica o item
        b["queue"][0].update(state="RUNNING", owner="outro-dono")
        eb.save(b)
        seen["cancelled"] = cancel.wait(5)                                     # o filho "vivo" so termina porque foi cancelado
        gh.head = NEWHEAD                                                      # se NAO fosse derrubado, ainda publicaria
        return -2, "", "", False

    ex.process_one(gh, POLICY, REPO, True, live_child, "claude", wt_ok, NOW, None, 0.05)
    t = eb.load()["queue"][0]
    assert seen["cancelled"] is True                                           # heartbeat acionou o cancelamento
    assert t["state"] == "RUNNING" and t["owner"] == "outro-dono"              # resultado do 1o processo descartado


def test_heartbeat_that_cannot_renew_before_the_lease_ends_cancels_the_child(monkeypatch):
    gh = FakeGh()
    eb.save(bstate(item()))
    monkeypatch.setattr(ex, "LEASE_S", 0.4)
    real_locked = ex.es.locked
    seen = {}

    def broken_locked(*a, **k):
        raise TimeoutError("disco/trava indisponivel")

    def child(argv, cwd, env, stdin, timeout, cancel=None):
        monkeypatch.setattr(ex.es, "locked", broken_locked)                    # renovacoes passam a falhar
        seen["cancelled"] = cancel.wait(5)
        monkeypatch.setattr(ex.es, "locked", real_locked)                      # restaura para a gravacao final
        return -2, "", "", False

    res = ex.process_one(gh, POLICY, REPO, True, child, "claude", wt_ok, NOW, None, 0.05)
    assert seen["cancelled"] is True and res["action"] == "FAILED" and "fail-closed" in res["reason"]


def test_default_runner_kills_a_live_process_tree_as_soon_as_cancel_is_set(tmp_path):
    import sys
    import threading
    import time
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    t0 = time.monotonic()
    rc, _, _, timed_out = ex.default_runner([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path, dict(ex.child_env()), "",
                                            120, cancel, poll_s=0.1)
    assert rc == -2 and not timed_out and time.monotonic() - t0 < 15


def test_isolation_probe_plants_hostile_settings_in_both_files(tmp_path):
    from tools.orchestration import isolation_probe as ip
    ip.plant(tmp_path)
    for name in ("settings.json", "settings.local.json"):
        blob = json.loads((tmp_path / ".claude" / name).read_text(encoding="utf-8"))
        assert "Bash(rm:*)" in blob["permissions"]["allow"] and blob["hooks"]["PreToolUse"]


# ------------------------------------------------------------------------- label de autorizacao + revalidacao (review #598)
def test_pr_without_the_executor_ok_label_is_refused_and_never_runs_claude():
    gh = FakeGh(labels=("bug",))
    r = Runner(gh)
    b = bstate(item())
    res = go(gh, b, r)
    assert res["action"] == "REFUSED" and "executor-ok" in res["reason"] and r.calls == []


def test_launch_hands_the_delivery_a_revalidation_that_rereads_github(monkeypatch):
    gh = FakeGh()
    captured = {}

    def fake_deliver(wt, branch, base, py, it, **kw):
        captured["revalidate"] = kw["revalidate"]
        return ("NOOP", "")
    monkeypatch.setattr(ex, "deliver", fake_deliver)
    go(gh, bstate(item()), Runner(gh, push=False))
    assert captured["revalidate"]() == (True, "ok")
    gh.head = NEWHEAD                                                          # alguem publicou depois do inicio
    ok, why = captured["revalidate"]()
    assert not ok and "HEAD mudou" in why
    gh.head, gh.labels = HEAD, []                                              # label removida depois do inicio
    assert not captured["revalidate"]()[0]


def test_a_stale_delivery_fails_the_item_with_the_reason_and_comments(monkeypatch):
    gh = FakeGh()
    comments = []
    monkeypatch.setattr(ex, "deliver", lambda *a, **k: ("STALE", "HEAD remoto mudou"))
    monkeypatch.setattr(ex, "comment_pr", lambda pr, repo, body: comments.append(body))
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))
    assert res["action"] == "FAILED" and "STALE" in res["reason"] and comments and "NAO publicada" in comments[0]


def test_prompt_never_tells_the_child_to_publish_and_says_the_executor_does():
    gh = FakeGh()
    r = Runner(gh)
    go(gh, bstate(item()), r)
    prompt = r.calls[0]["stdin"]
    assert "NAO faca git add, git commit nem git push" in prompt and "o executor valida" in prompt
    assert "e `git push origin HEAD" not in prompt and "commit (um por intencao)" not in prompt


# ------------------------------------------------------------------------------------------------- FP-060 §7.1 / D-060-04
@pytest.mark.parametrize("cmd", ["gh pr comment", "gh pr review", "gh pr merge", "gh pr edit", "gh pr close", "gh issue comment",
                                 "gh issue edit", "gh api", "gh label", "gh release"])
def test_the_child_has_no_github_mutation_in_its_allowlist(cmd):
    """O `gh` autentica pelo keyring: tirar GH_TOKEN do env NAO tira a credencial. So leitura do GitHub e permitida ao filho."""
    allow = ex.allow_list("py")
    assert not any(a.startswith(f"Bash({cmd}") for a in allow)
    assert not [a for a in allow if a.startswith("Bash(gh")]                  # nenhum gh: o review chega como arquivo


def test_the_prompt_never_tells_the_child_to_comment_or_publish():
    prompt = ex.build_prompt(item(), "feat/589-x", REPO)
    assert "gh pr comment" not in prompt and "DUVIDA:" in prompt


def _result(text, is_error=False):
    return json.dumps({"type": "result", "subtype": "success", "is_error": is_error, "result": text})


def test_is_error_with_exit_zero_and_subtype_success_is_a_failure_and_nothing_is_delivered(monkeypatch):
    calls = []
    monkeypatch.setattr(ex, "deliver", lambda *a, **k: calls.append(1) or ("PUSHED", "x"))
    gh = FakeGh()
    r = Runner(gh, push=False, out=_result("algo deu errado", is_error=True))
    b = bstate(item())
    res = go(gh, b, r)
    assert calls == [] and res["action"] != "DONE"
    assert "is_error" in b["queue"][0]["last_error"]


def test_a_question_from_the_child_is_posted_by_the_executor_not_by_the_child(monkeypatch):
    posted = []
    monkeypatch.setattr(ex, "comment_pr", lambda pr, repo, body: posted.append((pr, body)))
    gh = FakeGh()
    token = "ghp_" + "y" * 30
    monkeypatch.setattr(ex, "deliver", lambda *a, **k: ("NOOP", "nenhuma alteracao"))   # quem duvida nao edita
    r = Runner(gh, push=False, out=_result(f"Analisei.\nDUVIDA: o review pede A ou B? {token}"))
    go(gh, bstate(item()), r)
    assert len(posted) == 1 and posted[0][0] == 7
    assert "o review pede A ou B?" in posted[0][1] and token not in posted[0][1]


# ------------------------------------------------------------------------- review 2026-11-05: DONE so com PUSHED; env minimo
@pytest.mark.parametrize("delivery", ["STALE", "BLOCKED_GUARDS", "FAILED_CHECKS", "ERROR", "SKIPPED", "NOOP"])
def test_a_head_moved_by_someone_else_is_never_recorded_as_executor_done(monkeypatch, delivery):
    """Claude saiu 0 e o HEAD remoto mudou, mas a entrega NAO foi do executor: concorrencia externa, nao sucesso."""
    monkeypatch.setattr(ex, "deliver", lambda *a, **k: (delivery, "x"))
    gh = FakeGh()
    r = Runner(gh, push=True)                                                 # alguem mudou o HEAD durante a execucao
    b = bstate(item())
    res = go(gh, b, r)
    assert res["action"] != "DONE" and b["queue"][0]["state"] != "DONE_AWAITING_REREVIEW"


def test_pushed_delivery_is_the_only_path_to_done(monkeypatch):
    gh = FakeGh()
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=True))
    assert res["action"] == "DONE" and res["delivery"] == "PUSHED" and b["queue"][0]["state"] == "DONE_AWAITING_REREVIEW"


def test_an_external_head_change_is_superseded_not_retried(monkeypatch):
    monkeypatch.setattr(ex, "deliver", lambda *a, **k: ("STALE", "HEAD remoto mudou durante a validacao"))
    gh = FakeGh()
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=True))
    assert res["action"] == "SUPERSEDED" and b["queue"][0]["state"] == "SUPERSEDED"


def test_child_env_is_an_allowlist_without_credentials_or_cloud_secrets():
    base = {"PATH": "p", "SYSTEMROOT": "s", "USERPROFILE": "u", "TEMP": "t", "GH_TOKEN": "x", "GITHUB_TOKEN": "y",
            "AWS_SECRET_ACCESS_KEY": "z", "OPENAI_API_KEY": "k", "AZURE_CLIENT_SECRET": "a", "SSH_AUTH_SOCK": "s", "RANDOM_VAR": "r",
            "ANTHROPIC_API_KEY": "c"}
    env = ex.child_env(base)
    assert {"PATH", "SYSTEMROOT", "USERPROFILE", "TEMP"} <= set(env)
    assert not ({"GH_TOKEN", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY", "AZURE_CLIENT_SECRET", "SSH_AUTH_SOCK",
                 "RANDOM_VAR"} & set(env))
    assert env["GH_PROMPT_DISABLED"] == "1" and env["GIT_TERMINAL_PROMPT"] == "0"


def test_the_executor_hands_the_authorized_review_to_the_child_as_a_file(tmp_path):
    gh = FakeGh()
    gh.rev["body"] = "corrija x " + "ghp_" + "z" * 30
    r = Runner(gh)
    go(gh, bstate(item()), r)
    prompt = r.calls[0]["stdin"]
    path = Path(prompt.split("leia (ferramenta Read) o arquivo ")[1].split(":")[0] + ":" + prompt.split("leia (ferramenta Read) o arquivo ")[1].split(":")[1])         if ":" in prompt.split("leia (ferramenta Read) o arquivo ")[1][:3] else Path(prompt.split("leia (ferramenta Read) o arquivo ")[1].split(":")[0])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["untrusted_data"] is True and data["review_id"] == "9" and data["author"] == "fmmodesto"
    assert "corrija x" in data["body"] and "ghp_" not in data["body"] and data["comments"] == [{"path": "x.py", "line": 3, "body": "troque isto"}]
    assert "gh pr view" not in prompt and r.calls[0]["env"]["GH_CONFIG_DIR"]


def test_review_fetch_failure_blocks_without_launching_the_child():
    class Broken(FakeGh):
        def __call__(self, path):
            if path.endswith("/comments"):
                raise RuntimeError("gh 502")
            return super().__call__(path)
    gh = Broken()
    r = Runner(gh)
    b = bstate(item())
    res = go(gh, b, r)
    assert res["action"] == "BLOCKED_REVIEW_FETCH" and r.calls == [] and b["queue"][0]["state"] == "BLOCKED_REVIEW_FETCH"


# ------------------------------------------------------------- HEAD confirmado depois do push (visto no E2E real da MT-06)
import subprocess  # noqa: E402

PUBLISHED = "e" * 40


class StaleGh:
    """O GitHub devolve o HEAD antigo por `stale` leituras e so depois `new`."""
    def __init__(self, stale, new=PUBLISHED, boom=None):
        self.stale, self.new, self.boom, self.calls = stale, new, boom, 0

    def __call__(self, path):
        self.calls += 1
        if self.boom:
            raise self.boom
        return {"head": {"sha": HEAD if self.calls <= self.stale else self.new}}


def head_git(local=PUBLISHED, rc=0, boom=None):
    def run(args, cwd):
        assert args == ["rev-parse", "HEAD"], args
        if boom:
            raise boom
        return rc, local
    return run


def test_published_sha_is_the_local_head_the_push_left_on_the_remote():
    assert ex.published_sha(item(), Path("."), head_git()) == PUBLISHED


@pytest.mark.parametrize("run", [head_git(local=HEAD), head_git(local="nao-e-sha"), head_git(rc=1), head_git(boom=OSError("sem worktree")),
                                 head_git(boom=subprocess.TimeoutExpired("git", 1))])
def test_published_sha_is_empty_when_git_cannot_prove_a_new_commit(run):
    assert ex.published_sha(item(), Path("."), run) == ""


def test_confirm_head_does_not_wait_when_nothing_was_pushed(monkeypatch):
    slept = []
    monkeypatch.setattr(ex.time, "sleep", slept.append)
    gh = StaleGh(stale=99)
    assert ex.confirm_head(item(), gh, REPO, False) == HEAD and gh.calls == 1 and slept == []


def test_confirm_head_waits_for_github_to_show_the_pushed_commit(monkeypatch):
    slept = []
    monkeypatch.setattr(ex.time, "sleep", slept.append)
    gh = StaleGh(stale=2)
    assert ex.confirm_head(item(), gh, REPO, True, PUBLISHED, tries=6, pause=2.0) == PUBLISHED and gh.calls == 3 and slept == [2.0, 2.0]


def test_confirm_head_trusts_the_push_exit_status_when_the_api_stays_stale(monkeypatch):
    monkeypatch.setattr(ex.time, "sleep", lambda s: None)
    gh = StaleGh(stale=99)
    assert ex.confirm_head(item(), gh, REPO, True, PUBLISHED, tries=3) == PUBLISHED and gh.calls == 3     # sem ls-remote: nada mais na rede


def test_confirm_head_returns_an_external_advance_so_the_caller_can_tell_it_from_the_published_commit(monkeypatch):
    monkeypatch.setattr(ex.time, "sleep", lambda s: None)
    assert ex.confirm_head(item(), StaleGh(stale=0, new="f" * 40), REPO, True, PUBLISHED, tries=2) == "f" * 40


@pytest.mark.parametrize("boom", [RuntimeError("502"), OSError("rede"), ValueError("json"), subprocess.TimeoutExpired("gh", 120)])
def test_confirm_head_survives_any_github_error_including_a_timeout(monkeypatch, boom):
    monkeypatch.setattr(ex.time, "sleep", lambda s: None)
    assert ex.confirm_head(item(), StaleGh(stale=0, boom=boom), REPO, True, PUBLISHED, tries=2) == PUBLISHED
    assert ex.confirm_head(item(), StaleGh(stale=0, boom=boom), REPO, False) == ""


def test_a_push_that_github_shows_late_is_recorded_as_done_with_the_published_commit(monkeypatch):
    gh = FakeGh()                                                                 # a API segue mostrando o HEAD antigo
    monkeypatch.setattr(ex, "published_sha", lambda item, wt, run=None: PUBLISHED)
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, PUBLISHED))   # e o REMOTO confirma que a ponta e o commit do executor
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))
    assert res["action"] == "DONE" and res["new_head"] == PUBLISHED and b["queue"][0]["state"] == "DONE_AWAITING_REREVIEW"
    assert b["queue"][0]["new_head"] == PUBLISHED


def test_an_external_advance_right_after_the_push_is_superseded_not_credited_to_the_executor(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "published_sha", lambda item, wt, run=None: PUBLISHED)
    r = Runner(gh, push=False)

    def other_person_pushes(*a, **k):                                             # a API passa a mostrar um SHA que NAO e o publicado
        gh.head = "f" * 40
        return ("PUSHED", "fake")
    monkeypatch.setattr(ex, "deliver", other_person_pushes)
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, "f" * 40))                    # o avanco externo tambem aparece no REMOTO
    b = bstate(item())
    res = go(gh, b, r)
    assert res["action"] == "SUPERSEDED" and b["queue"][0]["state"] == "SUPERSEDED" and b["queue"][0]["new_head"] == "f" * 40


@pytest.mark.parametrize("api_moved", [True, False])
def test_a_push_whose_published_commit_cannot_be_proven_is_never_credited_to_the_executor(monkeypatch, api_moved):
    """Revisao independente do #652: sem o commit publicado nao ha como separar a entrega do executor de um avanco externo: SUPERSEDED, nunca DONE nem retry."""
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", lambda *a, **k: ("PUSHED", "fake"))                    # sem registrar published_sha
    monkeypatch.setattr(ex, "published_sha", lambda item, wt, run=None: "")                   # e o git nao responde
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=api_moved))
    assert res["action"] == "SUPERSEDED" and "nao confirmada" in res["reason"] and b["queue"][0]["state"] == "SUPERSEDED"


def test_published_sha_prefers_the_commit_the_delivery_recorded_before_pushing():
    it = item(published_sha=PUBLISHED)
    assert ex.published_sha(it, Path("."), lambda *a: (_ for _ in ()).throw(AssertionError("nao deveria ler o git"))) == PUBLISHED
    assert ex.published_sha(item(published_sha=HEAD), Path("."), head_git(local="nao-e-sha")) == ""      # registrado = HEAD revisado: nada de novo
    assert ex.published_sha(item(published_sha="xyz"), Path("."), head_git()) == PUBLISHED               # registro invalido: cai no git


def test_the_external_advance_message_says_the_executor_did_publish(monkeypatch):
    gh = FakeGh()
    r = Runner(gh, push=False)

    def other_person_pushes(wt, branch, base, py, it, **kw):
        it["published_sha"] = PUBLISHED
        gh.head = "f" * 40
        return ("PUSHED", "fake")
    monkeypatch.setattr(ex, "deliver", other_person_pushes)
    res = go(gh, bstate(item()), r)
    assert res["action"] == "SUPERSEDED" and "o executor publicou" in res["reason"] and "avanco externo" in res["reason"]


def test_git_has_a_deadline_and_never_prompts(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(kw)
        raise subprocess.TimeoutExpired(argv, kw["timeout"])
    monkeypatch.setattr(ex.subprocess, "run", fake_run)
    rc, msg = ex.git(["ls-remote", "origin"], Path("."))
    assert rc == 124 and "prazo" in msg and seen["timeout"] == ex.GIT_TIMEOUT_S
    assert seen["env"]["GIT_TERMINAL_PROMPT"] == "0" and seen["env"]["GCM_INTERACTIVE"] == "never"


# -- achados da 4a revisao do Codex (#652): publicacao pendente DURAVEL, reinicio e API velha ---------------------------------------------
def unconfirmed_deliver(wt, branch, base, py, it, **kw):
    """Como o `deliver` real num timeout do push: registra o commit (duravel) ANTES e devolve PUBLISH_UNCONFIRMED."""
    it["published_sha"] = NEWHEAD
    assert kw["record"](NEWHEAD) is True
    return ("PUBLISH_UNCONFIRMED", "git push sem confirmacao")


def test_a_push_timeout_leaves_a_durable_publish_pending_state_and_the_item_is_never_picked_again(monkeypatch):
    gh = FakeGh()                                                            # a API segue mostrando o HEAD ANTIGO
    runner = Runner(gh, push=False)
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    b = bstate(item())
    res = go(gh, b, runner)
    row = b["queue"][0]
    assert res["action"] == "PUBLISH_PENDING" and row["state"] == "PUBLISH_PENDING" and row["published_sha"] == NEWHEAD and "owner" not in row
    assert ex.pick(eb.load(), NOW + dt.timedelta(days=2)) is None            # nem depois do retry_after: nunca volta a ser escolhido
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (False, ""))   # remoto segue inalcancavel
    again = ex.process_one(gh, POLICY, REPO, True, runner, "claude", wt_ok, NOW + dt.timedelta(days=2))
    assert again["action"] == "IDLE" and len(runner.calls) == 1              # o claude NAO foi executado de novo, e o item segue pendente
    assert eb.load()["queue"][0]["state"] == "PUBLISH_PENDING"


def test_a_pending_publish_whose_remote_has_the_recorded_commit_becomes_done(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    go(gh, bstate(item()), Runner(gh, push=False))
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, NEWHEAD))
    out = ex.settle_pending(gh, REPO, NOW)
    row = eb.load()["queue"][0]
    assert out[0]["action"] == "SETTLED" and row["state"] == "DONE_AWAITING_REREVIEW" and row["new_head"] == NEWHEAD


def test_a_pending_publish_whose_remote_never_got_the_push_is_retried_not_marked_done(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    go(gh, bstate(item()), Runner(gh, push=False))
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, HEAD))     # a ponta remota ainda e o HEAD revisado
    ex.settle_pending(gh, REPO, NOW)
    assert eb.load()["queue"][0]["state"] == "PUBLISH_PENDING"                    # UMA leitura ainda no HEAD revisado nao prova que o push nao entrou (pode estar sendo aplicado)
    real = dt.datetime.now(dt.timezone.utc)                                           # `pending_since` e o instante REAL em que ficou pendente
    ex.settle_pending(gh, REPO, real + dt.timedelta(seconds=ex.PENDING_GRACE_S - 30))
    assert eb.load()["queue"][0]["state"] == "PUBLISH_PENDING"                    # ainda dentro da janela de graca
    ex.settle_pending(gh, REPO, real + dt.timedelta(seconds=ex.PENDING_GRACE_S + 30))
    row = eb.load()["queue"][0]
    assert row["state"] == "PUBLISH_MANUAL" and "MANUAL" in row["last_error"] and row["published_sha"] == NEWHEAD    # depois da graca: NUNCA volta sozinho a ser elegivel
    assert ex.pick(eb.load(), NOW + dt.timedelta(days=30)) is None


def test_a_pending_publish_with_another_remote_tip_is_superseded(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    go(gh, bstate(item()), Runner(gh, push=False))
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, "e" * 40))
    ex.settle_pending(gh, REPO, NOW)
    row = eb.load()["queue"][0]
    assert row["state"] == "SUPERSEDED" and row["new_head"] == "e" * 40 and "avanco externo" in row["last_error"]


def test_a_pending_publish_stays_pending_while_the_remote_cannot_be_consulted(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    go(gh, bstate(item()), Runner(gh, push=False))
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (False, ""))
    out = ex.settle_pending(gh, REPO, NOW)
    assert out[0]["action"] == "PUBLISH_PENDING" and eb.load()["queue"][0]["state"] == "PUBLISH_PENDING"


def test_a_restart_after_the_commit_was_recorded_goes_to_publish_pending_not_back_to_the_queue():
    expired = item(state="RUNNING", owner="morto", lease_expires="2026-11-04T11:00:00Z", published_sha=NEWHEAD)
    plain = item(key="review:10:7:" + HEAD, event_id="review:10", state="RUNNING", owner="morto2", lease_expires="2026-11-04T11:00:00Z")
    b = bstate(expired, plain)
    assert ex.recover(b, NOW) == 2
    assert b["queue"][0]["state"] == "PUBLISH_PENDING" and b["queue"][1]["state"] == "QUEUED"         # so quem registrou o commit vai para a reconciliacao
    assert ex.pick(b, NOW + dt.timedelta(days=1))["key"] == plain["key"]


def test_the_commit_is_recorded_durably_before_the_push_and_a_failed_record_blocks_it(monkeypatch):
    seen = {}

    def spy(wt, branch, base, py, it, **kw):
        seen["on_disk"] = eb.load()["queue"][0].get("published_sha")           # o que ja esta no DISCO quando a entrega comeca o push
        kw["record"](NEWHEAD)
        seen["after_record"] = eb.load()["queue"][0].get("published_sha")
        it["published_sha"] = NEWHEAD
        return ("PUSHED", "fake")
    monkeypatch.setattr(ex, "deliver", spy)
    gh = FakeGh()
    go(gh, bstate(item()), Runner(gh))
    assert seen["on_disk"] is None and seen["after_record"] == NEWHEAD


def test_a_stale_api_with_a_remote_that_holds_another_commit_is_superseded_not_done(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, "f" * 40))     # alguem reescreveu a branch depois do push
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))                                  # a API segue velha (HEAD antigo)
    assert res["action"] == "SUPERSEDED" and b["queue"][0]["state"] == "SUPERSEDED" and b["queue"][0]["new_head"] == "f" * 40


def test_a_stale_api_with_an_unreachable_remote_is_publish_pending_not_done(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (False, ""))
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))
    assert res["action"] == "PUBLISH_PENDING" and b["queue"][0]["state"] == "PUBLISH_PENDING"


def test_a_stale_api_with_a_remote_that_confirms_the_published_commit_is_done():
    gh = FakeGh()
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))                                  # fixture: remote_tip_of == NEWHEAD == commit publicado
    assert res["action"] == "DONE" and b["queue"][0]["state"] == "DONE_AWAITING_REREVIEW" and b["queue"][0]["new_head"] == NEWHEAD


def test_the_dry_run_never_reconciles_pending_items(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    go(gh, bstate(item()), Runner(gh, push=False))
    called = []
    monkeypatch.setattr(ex, "settle_pending", lambda *a, **k: called.append(1) or [])
    ex.process_one(gh, POLICY, REPO, False, Runner(gh), "claude", wt_ok, NOW)
    assert called == []


def test_the_next_executor_cycle_reconciles_a_pending_publish_before_picking_new_work(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    runner = Runner(gh, push=False)
    go(gh, bstate(item()), runner)
    assert eb.load()["queue"][0]["state"] == "PUBLISH_PENDING"
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, NEWHEAD))     # o push TINHA entrado
    res = ex.process_one(gh, POLICY, REPO, True, runner, "claude", wt_ok, NOW)
    assert eb.load()["queue"][0]["state"] == "DONE_AWAITING_REREVIEW" and res["action"] == "IDLE" and len(runner.calls) == 1


# -- 5a revisao do Codex (#652) ---------------------------------------------------------------------------------------------------------------------------
def test_a_remote_restored_to_the_reviewed_sha_after_the_push_is_superseded_not_rerun(monkeypatch):
    gh = FakeGh()                                                                          # a API segue velha (HEAD revisado)
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, HEAD))             # alguem devolveu a branch ao SHA revisado: tip != commit publicado
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))
    row = b["queue"][0]
    assert res["action"] == "SUPERSEDED" and row["state"] == "SUPERSEDED" and row["state"] != "FAILED"
    assert ex.pick(eb.load(), NOW + dt.timedelta(days=2)) is None                        # nunca volta a ser elegivel


def test_an_exception_while_reading_the_remote_after_a_recorded_push_keeps_the_item_pending(monkeypatch):
    gh = FakeGh()

    def boom(wt, branch):
        raise OSError("git nao iniciou")
    monkeypatch.setattr(ex, "remote_tip_of", boom)
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))
    assert res["action"] == "PUBLISH_PENDING" and b["queue"][0]["state"] == "PUBLISH_PENDING"
    assert ex.pick(eb.load(), NOW + dt.timedelta(days=2)) is None


def test_any_unexpected_crash_after_the_commit_was_recorded_goes_to_publish_pending_not_failed(monkeypatch):
    gh = FakeGh()

    def deliver_then_crash(wt, branch, base, py, it, **kw):
        it["published_sha"] = NEWHEAD
        assert kw["record"](NEWHEAD) is True                                             # gravado de forma duravel...
        raise KeyError("falha inesperada depois do registro")                           # ...e o executor quebra de um jeito que nao previu
    monkeypatch.setattr(ex, "deliver", deliver_then_crash)
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))
    row = b["queue"][0]
    assert res["action"] == "FAILED" and row["state"] == "PUBLISH_PENDING" and row["published_sha"] == NEWHEAD and "reconciliar" in row["last_error"]
    assert ex.pick(eb.load(), NOW + dt.timedelta(days=2)) is None


def test_a_definitive_failure_drops_the_recorded_commit_so_a_restart_does_not_mistake_it_for_a_publication(monkeypatch):
    gh = FakeGh()

    def refused(wt, branch, base, py, it, **kw):
        it["published_sha"] = NEWHEAD
        kw["record"](NEWHEAD)
        return ("ERROR", "git push recusado")
    monkeypatch.setattr(ex, "deliver", refused)
    b = bstate(item())
    go(gh, b, Runner(gh, push=False))
    assert b["queue"][0]["state"] == "FAILED" and "published_sha" not in b["queue"][0]


# -- 6a revisao do Codex (#652): graca para push abandonado, excecao apos o registro, remoto tambem com a API em dia -------------------------------------
def test_a_late_push_that_completes_after_a_remote_still_showed_the_reviewed_head_is_recognized_as_done(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    go(gh, bstate(item()), Runner(gh, push=False))
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, HEAD))     # 1a leitura: o servidor ainda nao aplicou
    ex.settle_pending(gh, REPO, NOW)
    assert eb.load()["queue"][0]["state"] == "PUBLISH_PENDING"
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, NEWHEAD))  # o push abandonado TERMINA de ser aplicado
    ex.settle_pending(gh, REPO, NOW + dt.timedelta(seconds=60))
    row = eb.load()["queue"][0]
    assert row["state"] == "DONE_AWAITING_REREVIEW" and row["new_head"] == NEWHEAD   # nunca foi reexecutado: nao houve segundo push


@pytest.mark.parametrize("exc", [OSError("git nao iniciou"), ValueError("saida inesperada"), subprocess.SubprocessError("falha")])
def test_an_exception_after_the_commit_was_recorded_is_a_pending_publication_not_an_error(monkeypatch, exc):
    gh = FakeGh()

    def deliver_raises(wt, branch, base, py, it, **kw):
        it["published_sha"] = NEWHEAD
        kw["record"](NEWHEAD)
        raise exc
    monkeypatch.setattr(ex, "deliver", deliver_raises)
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))
    row = b["queue"][0]
    assert res["action"] == "PUBLISH_PENDING" and row["state"] == "PUBLISH_PENDING" and row["published_sha"] == NEWHEAD and row.get("pending_since")
    assert ex.pick(eb.load(), NOW + dt.timedelta(days=2)) is None


def test_an_exception_provably_before_the_push_is_still_a_plain_failure(monkeypatch):
    gh = FakeGh()

    def deliver_raises(wt, branch, base, py, it, **kw):
        raise OSError("git nao iniciou antes de qualquer commit")                      # nenhum published_sha: comprovadamente antes do push
    monkeypatch.setattr(ex, "deliver", deliver_raises)
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))
    assert res["action"] == "FAILED" and b["queue"][0]["state"] == "FAILED" and "published_sha" not in b["queue"][0]


def test_a_cached_api_showing_the_published_commit_is_still_checked_against_the_remote(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, "9" * 40))     # a branch avancou depois do push, mas a API em cache ainda mostra o commit publicado
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=True))                                              # a API mostra NEWHEAD (o publicado)
    assert res["action"] == "SUPERSEDED" and b["queue"][0]["state"] == "SUPERSEDED" and b["queue"][0]["new_head"] == "9" * 40


def test_a_cached_api_with_an_unreachable_remote_keeps_the_item_pending(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (False, ""))
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=True))
    assert res["action"] == "PUBLISH_PENDING" and b["queue"][0]["state"] == "PUBLISH_PENDING"


def test_recover_stamps_the_pending_window_so_the_grace_period_counts_from_the_restart():
    expired = item(state="RUNNING", owner="morto", lease_expires="2026-11-04T11:00:00Z", published_sha=NEWHEAD)
    b = bstate(expired)
    ex.recover(b, NOW)
    assert b["queue"][0]["state"] == "PUBLISH_PENDING" and b["queue"][0]["pending_since"] == ex.es.now_iso(NOW)


# -- 7a revisao do Codex (#652): graca nao e prova; pending_since = agora; push confirmado --------------------------------------------------------------
def test_pending_since_is_the_moment_the_publication_became_pending_not_the_start_of_a_long_run(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    long_ago = NOW - dt.timedelta(minutes=40)                                                      # o item comecou a executar ha 40 min (agente demorado)
    before = ex.es.now_iso()
    go(gh, bstate(item()), Runner(gh, push=False), now=long_ago)
    row = eb.load()["queue"][0]
    assert row["pending_since"] >= before and row["pending_since"] > ex.es.now_iso(long_ago + dt.timedelta(minutes=30))   # o relogio REAL do momento, nao o `t` do inicio
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, HEAD))
    ex.settle_pending(gh, REPO, ex.dt.datetime.now(ex.dt.timezone.utc))                           # reconciliacao IMEDIATA: dentro da graca contada de agora
    assert eb.load()["queue"][0]["state"] == "PUBLISH_PENDING"


def test_a_late_remote_application_after_the_grace_window_is_still_recognized_as_done(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    go(gh, bstate(item()), Runner(gh, push=False))
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, HEAD))
    ex.settle_pending(gh, REPO, dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=ex.PENDING_GRACE_S * 3))
    assert eb.load()["queue"][0]["state"] == "PUBLISH_MANUAL"
    # o item ficou em PUBLISH_MANUAL: o push tardio nao o reabre sozinho, mas o operador consegue reconciliar
    assert ex.retry_publish(eb.load()["queue"][0]["key"], NOW) is True
    row = eb.load()["queue"][0]
    assert row["state"] == "FAILED" and "published_sha" not in row and "pending_since" not in row


def test_retry_publish_only_releases_a_manual_item(monkeypatch):
    gh = FakeGh()
    go(gh, bstate(item()), Runner(gh))
    assert ex.retry_publish("review:9:7:" + HEAD) is False and ex.retry_publish("nao-existe") is False


def test_the_retry_publish_command_exists(monkeypatch, capsys):
    assert ex.main(["retry-publish", "nao-existe"]) == 1 and json.loads(capsys.readouterr().out) == {"released": False}


def test_a_confirmed_push_whose_remote_was_restored_to_the_reviewed_sha_is_superseded_never_retried(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (False, ""))                       # o push TERMINOU, mas a consulta ao remoto falha
    b = bstate(item())
    go(gh, b, Runner(gh, push=False))
    assert b["queue"][0]["state"] == "PUBLISH_PENDING" and b["queue"][0]["push_confirmed"] is True
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, HEAD))                       # a branch foi RESTAURADA ao SHA revisado antes da reconciliacao
    ex.settle_pending(gh, REPO, NOW + dt.timedelta(seconds=ex.PENDING_GRACE_S * 3))
    row = eb.load()["queue"][0]
    assert row["state"] == "SUPERSEDED" and row["new_head"] == HEAD and "restauracao" in row["last_error"]
    assert ex.pick(eb.load(), NOW + dt.timedelta(days=30)) is None


def test_an_unconfirmed_timeout_push_is_not_marked_as_confirmed(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    go(gh, bstate(item()), Runner(gh, push=False))
    assert "push_confirmed" not in eb.load()["queue"][0]


# -- 8a revisao do Codex (#652): API divergente nunca decide; falha ao iniciar o git na reconciliacao nao derruba o ciclo -------------------------------------
def test_an_api_answer_that_is_neither_the_reviewed_nor_the_published_sha_is_checked_against_the_remote(monkeypatch):
    class CachedOther(FakeGh):
        armed = False

        def __call__(self, path):
            out = super().__call__(path)
            if self.armed and path == f"repos/{REPO}/pulls/7":
                out["head"]["sha"] = "7" * 40                                                           # cache da API: SHA que nao e o revisado nem o publicado
            return out
    gh = CachedOther()

    def publish_then_arm(wt, branch, base, py, it, **kw):
        it["published_sha"] = NEWHEAD
        gh.armed = True                                                                                 # a partir de agora a API responde o SHA divergente
        return ("PUSHED", "fake")
    monkeypatch.setattr(ex, "deliver", publish_then_arm)
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=False))                                                           # o remoto (fixture) confirma que a ponta E o commit publicado
    assert res["action"] == "DONE" and b["queue"][0]["state"] == "DONE_AWAITING_REREVIEW" and b["queue"][0]["new_head"] == NEWHEAD


def test_a_remote_that_differs_from_the_published_commit_is_superseded_whatever_the_api_says(monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(ex, "remote_tip_of", lambda wt, branch: (True, "8" * 40))
    b = bstate(item())
    res = go(gh, b, Runner(gh, push=True))                                                            # API mostra o publicado, remoto mostra outra ponta
    assert res["action"] == "SUPERSEDED" and b["queue"][0]["new_head"] == "8" * 40


@pytest.mark.parametrize("exc", [FileNotFoundError("git"), OSError("sem git"), PermissionError("negado")])
def test_a_git_that_cannot_start_during_reconciliation_leaves_items_pending_and_the_cycle_alive(monkeypatch, exc):
    gh = FakeGh()
    monkeypatch.setattr(ex, "deliver", unconfirmed_deliver)
    go(gh, bstate(item(), item(key="review:10:8:" + HEAD, event_id="review:10", pr=8)), Runner(gh, push=False))
    assert [i["state"] for i in eb.load()["queue"]][:1] == ["PUBLISH_PENDING"]

    def boom(wt, branch):
        raise exc
    monkeypatch.setattr(ex, "remote_tip_of", boom)
    out = ex.settle_pending(gh, REPO, NOW)                                                           # NAO levanta
    assert out and all(o["action"] == "PUBLISH_PENDING" for o in out)
    assert eb.load()["queue"][0]["state"] == "PUBLISH_PENDING"
    res = ex.process_one(gh, POLICY, REPO, True, Runner(gh), "claude", wt_ok, NOW)                    # e o ciclo segue com os outros itens
    assert res["action"] in ("IDLE", "DONE", "FAILED", "PARKED_UNSUPPORTED", "REFUSED", "STALE", "SUPERSEDED") or "action" in res
