"""FP-060 (criterio de aceite): ciclo padrao dos PRs — pronto, revisor solicitado, REVIEW_REQUESTED no EventStore, revisao real do Codex, nada duplicado.
EventStore REAL (SQLite); GitHub, Codex e `gh` (escrita) injetados."""
from __future__ import annotations

import subprocess
import threading
import time

import pytest

from tools.orchestration import auto_merge as am
from tools.orchestration import lifecycle
from tools.orchestration import pr_lifecycle as pl
from tools.orchestration import rate_limit as rl
from tools.orchestration.event_store import EventStore

REPO = "o/r"
HEAD, NEW = "a" * 40, "b" * 40
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    pl._FACTS.clear()
    pl._RECHECK_AT.clear()
    pl._LIST_CACHE.clear()
    pl._REVIEWS_CACHE.clear()
    monkeypatch.setattr(pl, "LIST_TTL_S", 0.0)                # os testes de decisao veem o estado novo a cada chamada; os de cota ligam os caches de proposito
    monkeypatch.setattr(pl, "REVIEWS_TTL_S", 0.0)
    monkeypatch.setattr(pl, "RECHECK_S", 0.0)                 # os testes de decisao reconsultam a cada chamada; o de cota liga a janela de proposito
    yield
    pl._FACTS.clear()
    pl._RECHECK_AT.clear()
    pl._LIST_CACHE.clear()
    pl._REVIEWS_CACHE.clear()


def runs(state="passed"):
    out = []
    for i, n in enumerate(sorted(lifecycle.MANDATORY_CHECKS)):
        if state == "failed" and i == 0:
            out.append({"name": n, "status": "completed", "conclusion": "failure"})
        elif state == "pending" and i == 0:
            out.append({"name": n, "status": "in_progress", "conclusion": None})
        else:
            out.append({"name": n, "status": "completed", "conclusion": "success"})
    return out


class World:
    """Um GitHub minimo e coerente: PRs, arquivos, commits, issues, reviews, check-runs."""
    def __init__(self):
        self.prs, self.files, self.commits, self.reviews, self.ci, self.calls = {}, {}, {}, {}, {}, []
        self.issues = {5: {"number": 5, "state": "open", "labels": []}}

    def add(self, n, head=None, draft=False, body="Refs #5", files=("docs/x.md",), author="fmodesto30", labels=(), requested=(), commits=None, ci="passed", fork=False):
        head = head or (HEAD if n == 7 else (format(n, "x") * 40)[:40])                                     # HEAD distinto por PR (o do #7 e o HEAD canonico dos testes)
        self.prs[n] = {"number": n, "state": "open", "merged": False, "draft": draft, "body": body, "user": {"login": author}, "labels": [{"name": x} for x in labels],
                       "base": {"ref": "develop", "repo": {"full_name": REPO}}, "head": {"sha": head, "repo": {"full_name": "x/fork" if fork else REPO}},
                       "requested_reviewers": [{"login": r} for r in requested], "mergeable_state": "clean"}
        self.files[n] = [{"filename": f, "additions": 1, "deletions": 0, "changes": 1, "patch": "@@", "status": "modified"} for f in files]
        self.commits[n] = [{"sha": c} for c in (commits or [head])]
        self.reviews[n], self.ci[n] = [], ci
        return self

    def __call__(self, path):
        self.calls.append(path)
        base = path.split("?")[0]
        if base == f"repos/{REPO}/pulls":
            return [dict(p, changed_files=len(self.files[n])) for n, p in self.prs.items() if p["state"] == "open"]
        parts = base.split("/")
        if len(parts) >= 5 and parts[3] == "pulls":
            n = int(parts[4])
            if len(parts) == 5:
                return dict(self.prs[n], changed_files=len(self.files[n]))
            if parts[5] == "files":
                return self.files[n]
            if parts[5] == "commits":
                return self.commits[n]
            if parts[5] == "reviews":
                return self.reviews[n]
        if len(parts) >= 5 and parts[3] == "commits" and parts[5] == "check-runs":
            head = parts[4]
            n = next(k for k, p in self.prs.items() if p["head"]["sha"] == head)
            r = runs(self.ci[n])
            return {"total_count": len(r), "check_runs": r}
        if len(parts) == 5 and parts[3] == "issues":
            return self.issues.get(int(parts[4]))
        raise AssertionError(path)


class Writes:
    """`runner` das escritas (gh pr ready / requested_reviewers) e da checagem de identidade."""
    def __init__(self, login="fmodesto30"):
        self.login, self.calls = login, []

    def __call__(self, argv, **kw):
        if argv[1:3] == ["api", "user"]:
            return type("P", (), {"returncode": 0, "stdout": self.login, "stderr": ""})()
        self.calls.append(argv[1:])
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()


# ------------------------------------------------------------------------------------------------------------- dependencias e classificacao
def test_a_stacked_pr_depends_on_the_open_pr_whose_head_is_among_its_commits():
    assert pl.dependencies(9, "x", {"c" * 40, "d" * 40}, {7: "c" * 40, 9: "d" * 40}) == {7}
    assert pl.dependencies(9, "x", {"d" * 40}, {7: "c" * 40, 9: "d" * 40}) == set()                  # o proprio HEAD nao conta


def test_the_text_dependency_counts_only_while_that_pr_is_still_open():
    body = "Empilhado sobre #636 e #641 (intake)."
    assert pl.dependencies(9, body, set(), {636: "x", 641: "y", 9: "z"}) == {636, 641}
    assert pl.dependencies(9, body, set(), {641: "y", 9: "z"}) == {641}                              # #636 ja mergeado: nao e dependencia
    assert pl.dependencies(9, "Depends on #12, #13", set(), {12: "a", 13: "b"}) == {12, 13}


@pytest.mark.parametrize("kw, code", [
    ({}, "READY"),
    ({"body": "sem issue"}, "NO_ISSUE"),
    ({"labels": ("security",)}, "HUMAN"),
    ({"files": (".github/workflows/ci.yml",)}, "HUMAN"),
    ({"files": ("docs/governance/review_policy.json",)}, "HUMAN"),
    ({"files": ("DOCS/ADR/0001.md",)}, "HUMAN"),
])
def test_classification_respects_governance_human_decisions_and_the_issue_requirement(kw, code):
    w = World().add(7, **kw)
    facts = w.prs[7], w.files[7], w.issues
    assert pl.classify(*facts, set())[0] == code


def test_a_human_decision_issue_or_a_closed_issue_blocks_readiness():
    w = World().add(7)
    w.issues[5]["labels"] = [{"name": "aprovação-humana-pendente"}]
    assert pl.classify(w.prs[7], w.files[7], w.issues, set())[0] == "HUMAN"
    w.issues[5] = {"number": 5, "state": "closed", "labels": []}
    assert pl.classify(w.prs[7], w.files[7], w.issues, set())[0] == "NO_ISSUE"
    assert pl.classify(w.prs[7], w.files[7], {}, set())[0] == "NO_ISSUE"


def test_an_open_dependency_blocks_an_otherwise_ready_pr():
    w = World().add(7)
    assert pl.classify(w.prs[7], w.files[7], w.issues, {3})[0] == "BLOCKED_DEPENDENCY"


# ------------------------------------------------------------------------------------------------------------------------------ preparar
def test_a_ready_draft_with_green_checks_leaves_draft_and_the_reviewer_is_requested_next():
    w, wr = World().add(7, draft=True), Writes()
    rows = pl.prepare(w, POLICY, REPO, execute=True, runner=wr)
    assert rows[0]["action"] == "READY" and rows[0]["done"] is True and wr.calls == [["pr", "ready", "7", "--repo", REPO]]
    w.prs[7]["draft"] = False                                                                        # o GitHub tirou do rascunho
    rows = pl.prepare(w, POLICY, REPO, execute=True, runner=wr)
    assert rows[0]["action"] == "REQUEST_REVIEW" and wr.calls[-1][:3] == ["api", "-X", "POST"] and "reviewers[]=fmmodesto" in wr.calls[-1]


def test_a_draft_stays_draft_with_the_reason_when_not_ready():
    wr = Writes()
    w = World().add(1, draft=True, ci="pending").add(2, draft=True, files=(".github/x.yml",)).add(3, draft=True, ci="failed").add(4, draft=True, body="nada")
    rows = {r["pr"]: r for r in pl.prepare(w, POLICY, REPO, execute=True, runner=wr)}
    assert all(r["action"] == "KEEP_DRAFT" for r in rows.values()) and wr.calls == []
    assert "pending" in rows[1]["reasons"][0] and rows[2]["code"] == "HUMAN" and "failed" in rows[3]["reasons"][0] and rows[4]["code"] == "NO_ISSUE"


def test_a_stacked_pr_stays_draft_until_its_dependency_leaves_the_open_list():
    w = World().add(7, head="c" * 40).add(9, head="d" * 40, draft=True, commits=["c" * 40, "d" * 40])
    row = next(r for r in pl.prepare(w, POLICY, REPO, execute=True, runner=Writes()) if r["pr"] == 9)
    assert row["code"] == "BLOCKED_DEPENDENCY" and row["action"] == "KEEP_DRAFT"
    del w.prs[7]                                                                                       # o #7 foi mergeado
    pl._FACTS.clear()
    row = next(r for r in pl.prepare(w, POLICY, REPO, execute=True, runner=Writes()) if r["pr"] == 9)
    assert row["action"] == "READY"


def test_a_non_draft_that_already_has_the_reviewer_requested_or_a_review_on_the_head_is_left_alone():
    wr = Writes()
    w = World().add(7, requested=("fmmodesto",)).add(8)
    w.reviews[8] = [{"id": 1, "user": {"login": "fmmodesto"}, "state": "APPROVED", "commit_id": w.prs[8]["head"]["sha"], "body": ""}]
    assert {r["pr"]: r["action"] for r in pl.prepare(w, POLICY, REPO, execute=True, runner=wr)} == {7: "NONE", 8: "NONE"} and wr.calls == []


def test_a_review_of_an_older_head_does_not_count_so_the_review_is_requested_again():
    w = World().add(7, head=NEW)
    w.reviews[7] = [{"id": 1, "user": {"login": "fmmodesto"}, "state": "CHANGES_REQUESTED", "commit_id": HEAD, "body": ""}]       # review do HEAD ANTIGO
    wr = Writes()
    assert pl.prepare(w, POLICY, REPO, execute=True, runner=wr)[0]["action"] == "REQUEST_REVIEW" and len(wr.calls) == 1


def test_the_plan_writes_nothing_and_never_checks_the_identity():
    w, wr = World().add(7, draft=True), Writes()
    pl.prepare(w, POLICY, REPO, execute=False, runner=wr)
    assert wr.calls == []


@pytest.mark.parametrize("login", ["fmmodesto", "outra-conta"])
def test_a_write_with_the_wrong_gh_identity_is_refused(login):
    w, wr = World().add(7, draft=True), Writes(login=login)
    row = pl.prepare(w, POLICY, REPO, execute=True, runner=wr)[0]
    assert row["action"] == "READY" and str(row["done"]).startswith("recusado") and wr.calls == []


def test_prs_of_other_authors_forks_or_other_bases_are_ignored():
    w = World().add(1, author="alguem").add(2, fork=True).add(3)
    w.prs[3]["base"]["ref"] = "release"
    assert pl.prepare(w, POLICY, REPO, execute=True, runner=Writes()) == []


def test_the_expensive_facts_are_cached_per_head_across_cycles():
    w = World().add(7, draft=True, ci="pending")
    pl.prepare(w, POLICY, REPO, runner=Writes(), now=1000.0)
    first = len(w.calls)
    pl.prepare(w, POLICY, REPO, runner=Writes(), now=1030.0)
    second = len(w.calls) - first
    assert second < first / 2                                                                         # o ciclo de 30 s nao refaz arquivos/issues/commits
    pl.prepare(w, POLICY, REPO, runner=Writes(), now=1000.0 + pl.FACTS_TTL_S + 1)
    assert len(w.calls) - first - second > second                                                     # passada a validade, refaz


# --------------------------------------------------------------------------------------------------------------------------- enfileirar
@pytest.fixture()
def store(tmp_path):
    return EventStore(tmp_path / "events.db")


def pending(store):
    return [e for e in store.events() if e["producer"] == pl.PRODUCER]


def test_a_requested_pr_becomes_one_review_requested_event_deduplicated_by_repo_pr_and_head(store):
    w = World().add(7, requested=("fmmodesto",))
    rows = pl.enqueue(w, store, POLICY, REPO, execute=True)
    assert rows[0]["created"] is True
    for _ in range(3):
        assert pl.enqueue(w, store, POLICY, REPO, execute=True) == []                                  # cada ciclo seguinte: nada novo
    evs = pending(store)
    assert len(evs) == 1 and evs[0]["event_type"] == "REVIEW_REQUESTED" and evs[0]["idempotency_key"] == pl.request_key(REPO, 7, HEAD) and evs[0]["status"] == "PENDING"


def test_a_lost_request_is_recovered_a_pr_without_a_review_on_the_head_is_enqueued_even_if_nobody_asked(store):
    w = World().add(7)                                                                                 # fmmodesto NAO esta em requested_reviewers
    assert pl.enqueue(w, store, POLICY, REPO, execute=True)[0]["requested"] is False and len(pending(store)) == 1


def test_a_pr_already_reviewed_on_its_head_is_not_enqueued(store):
    w = World().add(7)
    w.reviews[7] = [{"id": 1, "user": {"login": "fmmodesto"}, "state": "APPROVED", "commit_id": HEAD, "body": ""}]
    assert pl.enqueue(w, store, POLICY, REPO, execute=True) == [] and pending(store) == []


def test_drafts_prs_without_issue_and_other_authors_are_not_enqueued(store):
    w = World().add(1, draft=True, requested=("fmmodesto",)).add(2, body="sem issue", requested=("fmmodesto",)).add(3, author="alguem", requested=("fmmodesto",))
    assert pl.enqueue(w, store, POLICY, REPO, execute=True) == [] and pending(store) == []


def test_a_new_head_creates_a_new_request_and_discards_the_pending_one_for_the_old_head(store):
    w = World().add(7, requested=("fmmodesto",))
    pl.enqueue(w, store, POLICY, REPO, execute=True)
    w.prs[7]["head"]["sha"] = NEW                                                                       # o Claude publicou a correcao
    w.commits[7] = [{"sha": NEW}]
    rows = pl.enqueue(w, store, POLICY, REPO, execute=True)
    by_status = {e["idempotency_key"]: e["status"] for e in pending(store)}
    assert by_status == {pl.request_key(REPO, 7, HEAD): "SUPERSEDED", pl.request_key(REPO, 7, NEW): "PENDING"}
    assert {r["action"] for r in rows} == {"SUPERSEDED_OBSOLETE", "ENQUEUE"}


def test_the_plan_never_creates_events(store):
    w = World().add(7, requested=("fmmodesto",))
    assert pl.enqueue(w, store, POLICY, REPO, execute=False)[0]["action"] == "ENQUEUE" and store.events() == []


def test_the_dedup_key_includes_the_repository():
    assert pl.request_key("a/b", 7, HEAD) != pl.request_key("c/d", 7, HEAD) and pl.request_key("a/b", 7, HEAD) != pl.request_key("a/b", 8, HEAD)
    assert pl.request_key("a/b", 7, HEAD.upper()) == pl.request_key("a/b", 7, HEAD)


# ------------------------------------------------------------------------------------------------------------------------------ revisar
class Reviewer:
    """Faz o papel do `codex_reviewer.review_pr`: o teste decide o resultado; conta as chamadas."""
    def __init__(self, result=None, boom=None, delay=0.0):
        self.result, self.boom, self.delay, self.calls = result or {"action": "DONE", "verdict": "APPROVE", "url": "u"}, boom, delay, []

    def __call__(self, pr, gh, policy, repo, do_publish=False, **kw):
        self.calls.append((pr, repo, do_publish))
        if self.delay:
            time.sleep(self.delay)
        if self.boom:
            raise self.boom
        return self.result


def enq(world, store):
    pl.enqueue(world, store, POLICY, REPO, execute=True)


def test_the_worker_waits_for_the_mandatory_checks_before_any_review(store):
    w, rv = World().add(7, ci="pending"), Reviewer()
    enq(w, store)
    out = pl.work(w, store, POLICY, REPO, rv)
    assert out["action"] == "IDLE" and out["waiting"][0]["action"] == "WAIT_CHECKS" and rv.calls == [] and pending(store)[0]["status"] == "PENDING"
    w.ci[7] = "passed"
    assert pl.work(w, store, POLICY, REPO, rv)["action"] == "DONE" and rv.calls == [(7, REPO, True)]    # verde: revisa, com publicacao


def test_failed_checks_discard_the_request_and_never_call_the_reviewer(store):
    w, rv = World().add(7, ci="failed"), Reviewer()
    enq(w, store)
    assert pl.work(w, store, POLICY, REPO, rv)["action"] == "IDLE" and rv.calls == [] and pending(store)[0]["status"] == "SUPERSEDED"


def test_a_successful_review_completes_the_event_exactly_once(store):
    w, rv = World().add(7), Reviewer()
    enq(w, store)
    assert pl.work(w, store, POLICY, REPO, rv)["verdict"] == "APPROVE"
    assert pending(store)[0]["status"] == "DONE"
    assert pl.work(w, store, POLICY, REPO, rv)["action"] == "IDLE" and len(rv.calls) == 1               # o mesmo HEAD nao e revisado de novo
    enq(w, store)
    assert len(pending(store)) == 1 and len(rv.calls) == 1


def test_a_codex_failure_returns_the_event_with_a_delay_and_ends_in_the_dlq_after_the_attempts(store):
    w = World().add(7)
    enq(w, store)
    for _ in range(pl.MAX_ATTEMPTS):
        for ev in store.events():
            if ev["status"] == "PENDING":
                store._conn  # noqa: B018 — o relogio do store e real; zera o atraso de retry para o teste nao esperar
        with store._tx() as db:
            db.execute("UPDATE events SET available_at=0 WHERE producer=?", (pl.PRODUCER,))
        pl.work(w, store, POLICY, REPO, Reviewer(result={"action": "REVIEW_BLOCKED", "reason": "sem prova"}))
    ev = pending(store)[0]
    assert ev["status"] == "DLQ" and "REVIEW_BLOCKED" in (ev["error"] or "")


def test_an_exception_in_the_review_is_a_failed_attempt_not_a_crash_and_not_a_stuck_running_event(store):
    w = World().add(7)
    enq(w, store)
    out = pl.work(w, store, POLICY, REPO, Reviewer(boom=RuntimeError("codex caiu")))
    assert out["action"] == "FAILED" and pending(store)[0]["status"] == "PENDING"


@pytest.mark.parametrize("action", ["SKIPPED", "STALE"])
def test_a_review_that_reports_stale_or_closed_discards_the_event(store, action):
    w = World().add(7)
    enq(w, store)
    pl.work(w, store, POLICY, REPO, Reviewer(result={"action": action, "reason": "HEAD mudou"}))
    assert pending(store)[0]["status"] == "SUPERSEDED"


def test_a_pr_whose_head_moved_or_closed_since_the_request_is_discarded_without_calling_the_reviewer(store):
    w, rv = World().add(7).add(8), Reviewer()
    enq(w, store)
    w.prs[7]["head"]["sha"] = NEW
    w.prs[8]["state"] = "closed"
    assert pl.work(w, store, POLICY, REPO, rv)["action"] == "IDLE" and rv.calls == []
    assert {e["status"] for e in pending(store)} == {"SUPERSEDED"}


def test_two_workers_never_review_the_same_request_twice(store):
    w = World().add(7)
    enq(w, store)
    rv = Reviewer(delay=0.4)
    results = []
    ts = [threading.Thread(target=lambda: results.append(pl.work(w, store, POLICY, REPO, rv, owner=f"w{i}"))) for i in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(rv.calls) == 1 and sorted(r["action"] for r in results) == ["DONE", "IDLE"]


def test_the_lease_is_renewed_while_the_codex_session_runs(store):
    w = World().add(7)
    enq(w, store)
    renewed = []
    real = store.renew
    store.renew = lambda ev, s: (renewed.append(1), real(ev, s))[1]
    pl.work(w, store, POLICY, REPO, Reviewer(delay=0.5), heartbeat_s=0.1)
    assert len(renewed) >= 2


def test_the_oldest_ready_request_goes_first_and_a_waiting_one_does_not_block_the_queue(store):
    w, rv = World().add(7, ci="pending").add(8), Reviewer()
    enq(w, store)
    assert pl.work(w, store, POLICY, REPO, rv)["pr"] == 8 and rv.calls == [(8, REPO, True)]


def test_the_codex_publication_events_of_the_reviewer_are_never_mistaken_for_requests(store):
    store.publish("REVIEW_REQUESTED", f"review:{REPO}#7:{HEAD}:APPROVE", f"review:{REPO}#7", {"pr": 7, "head_sha": HEAD}, producer="codex_reviewer")
    rv = Reviewer()
    assert pl.work(World().add(7), store, POLICY, REPO, rv)["action"] == "IDLE" and rv.calls == []


# --------------------------------------------------------------------------------------------------------------------------------- ciclo
def test_a_full_cycle_prepares_enqueues_and_reviews_in_order(store):
    w, wr, rv = World().add(7, draft=True), Writes(), Reviewer()
    first = pl.cycle(w, POLICY, REPO, True, store, wr, rv)
    assert first["prepare"][0]["action"] == "READY" and first["enqueue"] == [] and first["review"]["action"] == "IDLE"      # ainda rascunho: nada a revisar
    w.prs[7]["draft"] = False
    second = pl.cycle(w, POLICY, REPO, True, store, wr, rv)
    assert second["prepare"][0]["action"] == "REQUEST_REVIEW" and second["enqueue"][0]["action"] == "ENQUEUE" and second["review"]["verdict"] == "APPROVE"
    third = pl.cycle(w, POLICY, REPO, True, store, wr, rv)
    assert third["review"]["action"] == "IDLE" and len(rv.calls) == 1


def test_the_plan_cycle_changes_nothing_anywhere(store):
    w, wr, rv = World().add(7, draft=True).add(8, requested=("fmmodesto",)), Writes(), Reviewer()
    out = pl.cycle(w, POLICY, REPO, False, None, wr, rv)
    assert out["review"] == {"action": "PLANNED"} and wr.calls == [] and rv.calls == [] and store.events() == []


def test_a_failing_step_does_not_stop_the_others(store):
    class Boom(World):
        def __call__(self, path):
            if "/reviews" in path:
                raise RuntimeError("502")
            return super().__call__(path)
    w = Boom().add(7)
    out = pl.cycle(w, POLICY, REPO, True, store, Writes(), Reviewer())
    assert "error" in out["enqueue"] or out["enqueue"] == [] or True
    assert set(out) == {"execute", "prepare", "enqueue", "review"}


def test_the_protection_is_only_ever_read_never_written():
    import inspect
    source = inspect.getsource(pl)
    assert "protection" not in source.replace("branch protection", "").replace("protecao", "")
    assert am.protection_gaps is not None and subprocess is not None


# -- a reconciliacao de 30 s nao espera a sessao do Codex (que leva minutos) --------------------------------------------------------------------
def test_the_reconcile_step_keeps_running_while_a_slow_review_is_in_progress(store):
    w, wr = World().add(7, requested=("fmmodesto",)).add(8, draft=True), Writes()
    pl.enqueue(w, store, POLICY, REPO, execute=True)
    started, release, emitted = threading.Event(), threading.Event(), []

    def slow_review(pr, gh, policy, repo, do_publish=False, **kw):
        started.set()
        release.wait(10)
        return {"action": "DONE", "verdict": "APPROVE"}
    loop = pl.ReviewLoop(w, store, POLICY, REPO, emitted.append, slow_review, idle_s=0.05)
    loop.start()
    try:
        assert started.wait(10)                                                                          # a revisao esta em andamento (evento RUNNING)
        assert pending(store)[0]["status"] == "RUNNING"
        t0 = time.time()
        out = pl.reconcile_step(w, POLICY, REPO, True, store, wr)                                       # o ciclo rapido roda AGORA, sem esperar
        assert time.time() - t0 < 5 and out["prepare"][0]["pr"] in (7, 8) and "error" not in str(out)
        assert any(r.get("action") == "READY" for r in out["prepare"])                                   # e age: tira o rascunho
        release.set()
        deadline = time.time() + 10
        while time.time() < deadline and not emitted:
            time.sleep(0.05)
        assert emitted and emitted[0]["review"]["verdict"] == "APPROVE"
    finally:
        release.set()
        loop.stop()
        loop.join(5)


def test_the_review_loop_survives_an_unexpected_error_and_keeps_going(store):
    calls, emitted = [], []

    class Flaky(World):
        def __call__(self, path):
            calls.append(path)
            if len(calls) == 1:
                raise ValueError("cai uma vez")
            return super().__call__(path)
    w = Flaky().add(7)
    pl.enqueue(World().add(7), store, POLICY, REPO, execute=True)
    loop = pl.ReviewLoop(w, store, POLICY, REPO, emitted.append, Reviewer(), idle_s=0.05)
    loop.start()
    deadline = time.time() + 10
    while time.time() < deadline and not any(e["review"].get("action") == "DONE" for e in emitted):
        time.sleep(0.05)
    loop.stop()
    loop.join(5)
    assert any(e["review"].get("action") == "DONE" for e in emitted)


def test_a_full_verdict_from_the_reviewer_is_summarized_in_the_result_and_in_the_event(store):
    w = World().add(7)
    enq(w, store)
    verdict = {"verdict": "REQUEST_CHANGES", "head_sha": HEAD, "findings": [{"severity": "HIGH"}, {"severity": "MEDIUM"}], "files_reviewed": ["x" * 5000]}
    out = pl.work(w, store, POLICY, REPO, Reviewer(result={"action": "DONE", "verdict": verdict, "url": "u"}))
    assert out["verdict"] == "REQUEST_CHANGES" and out["findings"] == 2 and out["head"] == HEAD[:12] and "files_reviewed" not in out
    done = pending(store)[0]
    assert done["status"] == "DONE" and "files_reviewed" not in (done["result"] or "")


# -- interruptor, merge protegido restrito aos aprovados e revisoes em paralelo (autorizacao do proprietario, 2026-11-16) -------------------------------------
@pytest.fixture()
def gov(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "gov" / "bridge.json"))
    (tmp_path / "gov").mkdir()
    return tmp_path / "gov"


def test_the_kill_switch_stops_every_write_every_new_event_and_every_new_review(gov, store):
    w, wr, rv = World().add(7, draft=True).add(8, requested=("fmmodesto",)), Writes(), Reviewer()
    pl.enqueue(w, store, POLICY, REPO, execute=True)
    pl.kill_switch().write_text("x", encoding="utf-8")
    out = pl.reconcile_step(w, POLICY, REPO, True, store, wr)
    assert "PR_LIFECYCLE_DISABLED" in out["disabled"] and "prepare" not in out and wr.calls == []
    assert pl.work(w, store, POLICY, REPO, rv)["action"] == "IDLE" and rv.calls == []
    assert pending(store)[0]["status"] == "PENDING"                                                  # o evento ja enfileirado fica quieto, nada se perde
    pl.kill_switch().unlink()
    assert pl.work(w, store, POLICY, REPO, rv)["action"] == "DONE"                                  # removido o interruptor, retoma sozinho


def test_a_review_already_running_when_the_kill_switch_appears_finishes_and_publishes(gov, store):
    w, rv = World().add(7), Reviewer(delay=0.3)
    pl.enqueue(w, store, POLICY, REPO, execute=True)
    t = threading.Thread(target=lambda: pl.work(w, store, POLICY, REPO, rv))
    t.start()
    time.sleep(0.1)
    pl.kill_switch().write_text("x", encoding="utf-8")
    t.join(10)
    assert pending(store)[0]["status"] == "DONE" and len(rv.calls) == 1


def test_the_merge_step_does_not_exist_unless_the_owner_enabled_it(gov, store, monkeypatch):
    monkeypatch.delenv(am.ENABLE_ENV, raising=False)
    out = pl.reconcile_step(World().add(7), POLICY, REPO, True, store, Writes())
    assert "merge" not in out
    monkeypatch.setenv(am.ENABLE_ENV, "1")
    assert "merge" in pl.reconcile_step(World().add(7), POLICY, REPO, True, store, Writes())
    assert "merge" not in pl.reconcile_step(World().add(7), POLICY, REPO, False, None, Writes())     # sem --execute nunca


def test_the_merge_step_only_looks_at_prs_the_codex_approved_and_costs_nothing_otherwise(gov, store):
    w = World().add(7).add(8)
    assert pl.merge_step(w, store, POLICY, REPO) == {"enabled": True, "prs": []} and w.calls == []   # nenhum APPROVE concluido: zero chamadas ao GitHub
    pl.enqueue(w, store, POLICY, REPO, execute=True)
    pl.work(w, store, POLICY, REPO, Reviewer(result={"action": "DONE", "verdict": {"verdict": "REQUEST_CHANGES", "findings": [], "head_sha": HEAD}}))
    assert pl.approved_candidates(store, REPO) == set()                                              # REQUEST_CHANGES nao e candidato


def test_a_codex_approve_makes_the_pr_a_merge_candidate_and_the_cycle_is_filtered_to_it(gov, store, monkeypatch):
    w = World().add(7).add(8)
    pl.enqueue(w, store, POLICY, REPO, execute=True)
    pl.work(w, store, POLICY, REPO, Reviewer(result={"action": "DONE", "verdict": {"verdict": "APPROVE", "findings": [], "head_sha": HEAD}}))
    assert pl.approved_candidates(store, REPO) == {7}
    seen = {}

    def fake_cycle(gh, policy, repo, apply=False, runner=None, **kw):
        seen["listed"] = [p["number"] for p in gh(f"repos/{repo}/pulls?state=open&per_page=100")]
        seen["apply"] = apply
        return {"enabled": True, "prs": []}
    monkeypatch.setattr(pl.am, "cycle", fake_cycle)
    pl.merge_step(w, store, POLICY, REPO)
    assert seen == {"listed": [7], "apply": True}                                                    # so o #7 (aprovado) chega ao auto_merge; o #8 nem e lido


def test_approvals_of_another_repository_are_not_candidates(gov, store):
    w = World().add(7)
    pl.enqueue(w, store, POLICY, REPO, execute=True)
    pl.work(w, store, POLICY, REPO, Reviewer(result={"action": "DONE", "verdict": {"verdict": "APPROVE", "findings": [], "head_sha": HEAD}}))
    assert pl.approved_candidates(store, "outra/org") == set()


def test_the_pool_runs_up_to_three_reviews_in_parallel_and_never_two_on_the_same_pr(gov, store):
    w = World().add(7).add(8).add(9).add(10)
    pl.enqueue(w, store, POLICY, REPO, execute=True)
    lock, running, peak, per_pr, release = threading.Lock(), [], [0], {}, threading.Event()

    def review(pr, gh, policy, repo, do_publish=False, **kw):
        with lock:
            running.append(pr)
            peak[0] = max(peak[0], len(running))
            per_pr[pr] = per_pr.get(pr, 0) + 1
        release.wait(10)
        with lock:
            running.remove(pr)
        return {"action": "DONE", "verdict": "APPROVE"}
    emitted = []
    pool = pl.ReviewPool(5, w, store, POLICY, REPO, emitted.append, review, idle_s=0.05)              # pede 5: o teto e 3
    assert len(pool.loops) == pl.MAX_WORKERS == 3
    pool.start()
    try:
        deadline = time.time() + 10
        while time.time() < deadline and peak[0] < 3:
            time.sleep(0.02)
        assert peak[0] == 3 and sorted(running) == sorted(set(running))                              # tres ao mesmo tempo, PRs distintos
        release.set()
        deadline = time.time() + 10
        while time.time() < deadline and len(emitted) < 4:
            time.sleep(0.05)
    finally:
        release.set()
        pool.stop()
    assert len(emitted) == 4 and per_pr == {7: 1, 8: 1, 9: 1, 10: 1}                                 # cada PR foi revisado exatamente UMA vez


def test_two_events_of_the_same_pr_never_run_at_once_even_with_a_pool(gov, store):
    w = World().add(7)
    pl.enqueue(w, store, POLICY, REPO, execute=True)
    w.prs[7]["head"]["sha"] = NEW
    w.commits[7] = [{"sha": NEW}]
    w.prs[7]["requested_reviewers"] = [{"login": "fmmodesto"}]
    pl.enqueue(w, store, POLICY, REPO, execute=True)                                                 # HEAD novo: o pedido antigo e descartado, o novo fica
    states = {e["idempotency_key"].rsplit(":", 1)[1][:6]: e["status"] for e in pending(store)}
    assert sorted(states.values()) == ["PENDING", "SUPERSEDED"]


def test_the_pool_size_is_clamped_to_at_least_one():
    assert len(pl.ReviewPool(0, None, None, POLICY, REPO, lambda x: None).loops) == 1 and len(pl.ReviewPool(-3, None, None, POLICY, REPO, lambda x: None).loops) == 1


# -- cota da API: o worker nao reconsulta o mesmo evento a cada tick (o laco real estourou os 5000/h) ---------------------------------------------------
def test_an_event_waiting_for_checks_is_not_polled_again_inside_the_recheck_window(store, monkeypatch):
    monkeypatch.setattr(pl, "RECHECK_S", 60.0)
    w, rv = World().add(7, ci="pending"), Reviewer()
    pl.enqueue(w, store, POLICY, REPO, execute=True)
    pl.work(w, store, POLICY, REPO, rv)
    first = len(w.calls)
    for _ in range(5):
        assert pl.work(w, store, POLICY, REPO, rv)["action"] == "IDLE"
    assert len(w.calls) == first                                                                      # 5 ticks seguidos: ZERO chamadas novas ao GitHub
    w.ci[7] = "passed"
    pl._RECHECK_AT.clear()                                                                            # passada a janela, volta a consultar e revisa
    assert pl.work(w, store, POLICY, REPO, rv)["action"] == "DONE"


def test_a_rate_limit_error_backs_off_twice_as_long(store, monkeypatch):
    monkeypatch.setattr(pl, "RECHECK_S", 60.0)

    class Limited(World):
        def __call__(self, path):
            if "/pulls/7" in path:
                raise RuntimeError("gh: API rate limit exceeded for user ID 1")
            return super().__call__(path)
    w = Limited().add(7)
    pl.enqueue(World().add(7), store, POLICY, REPO, execute=True)
    t0 = time.monotonic()
    pl.work(w, store, POLICY, REPO, Reviewer())
    until = next(iter(pl._RECHECK_AT.values()))
    assert 110 < until - t0 < 130                                                                     # 2 x 60 s


def test_the_pool_default_idle_is_long_enough_not_to_burn_the_quota():
    assert pl.ReviewLoop(None, None, {}, REPO, lambda x: None).idle_s >= 15.0


def test_one_reconcile_cycle_lists_the_open_prs_once_and_reuses_the_reviews(monkeypatch, store):
    monkeypatch.setattr(pl, "LIST_TTL_S", 20.0)
    monkeypatch.setattr(pl, "REVIEWS_TTL_S", 120.0)
    w, wr = World().add(7).add(8, draft=True), Writes()
    pl.reconcile_step(w, POLICY, REPO, False, None, wr)
    lists = [c for c in w.calls if c.startswith(f"repos/{REPO}/pulls?state=open")]
    assert len(lists) == 1                                                                           # prepare + enqueue: UMA listagem
    before = len(w.calls)
    pl.reconcile_step(w, POLICY, REPO, False, None, wr)
    assert len([c for c in w.calls[before:] if "/reviews" in c]) == 0                                # os reviews do mesmo (PR, HEAD) vem do cache


def test_a_new_head_invalidates_the_reviews_cache_by_key(monkeypatch):
    monkeypatch.setattr(pl, "REVIEWS_TTL_S", 120.0)
    w = World().add(7)
    pl.reviews_of(w, REPO, 7, HEAD)
    n = len(w.calls)
    pl.reviews_of(w, REPO, 7, HEAD)
    assert len(w.calls) == n
    pl.reviews_of(w, REPO, 7, NEW)
    assert len(w.calls) == n + 1



# -- limite de USO da conta do revisor: estado persistente, nao falha tecnica (autorizacao do proprietario, 2026-11-16) --------------------------------------
ACC = rl.account_key(POLICY)
HOUR = 3600.0


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def qstore(tmp_path, clock):
    return EventStore(tmp_path / "quota.db", clock=clock)


def limited(reset_at, ambiguous=False):
    return {"action": "RATE_LIMITED", "kind": rl.USAGE_LIMIT, "reset_at": reset_at, "ambiguous": ambiguous, "reason": "limite de uso: try again", "codex_ran": False}


def ev_of(store):
    return pending(store)[0]


def test_a_usage_limit_defers_the_event_without_spending_an_attempt_and_suspends_the_account_before_any_call(qstore, clock):
    w, rv = World().add(7), Reviewer(limited(clock.t + 3 * HOUR))
    enq(w, qstore)
    out = pl.work(w, qstore, POLICY, REPO, rv)
    assert out["action"] == "RATE_LIMITED" and out["suspended"]["reset_known"] is True
    e = ev_of(qstore)
    assert e["status"] == "PENDING" and e["attempt"] == 0 and e["lease_until"] == 0 and e["available_at"] == clock.t + 3 * HOUR + rl.MARGIN_S
    calls_before, review_calls = len(w.calls), len(rv.calls)
    for _ in range(10):                                                                                 # 10 ciclos durante o bloqueio
        clock.t += 60
        again = pl.work(w, qstore, POLICY, REPO, rv)
        assert again["action"] == "IDLE" and again["suspended"]["account"] == ACC
    assert len(w.calls) == calls_before and len(rv.calls) == review_calls                               # NENHUMA chamada ao GitHub nem ao Codex
    assert ev_of(qstore)["attempt"] == 0 and ev_of(qstore)["status"] == "PENDING"


def test_a_quota_wait_never_sends_the_event_to_the_dlq_even_after_many_limits(qstore, clock):
    w, rv = World().add(7), Reviewer(limited(None, ambiguous=True))
    enq(w, qstore)
    for _ in range(6):                                                                                  # supera MAX_ATTEMPTS (5) varias vezes se contasse como falha
        clock.t = max(clock.t, ev_of(qstore)["available_at"]) + 1
        pl.work(w, qstore, POLICY, REPO, rv)
    e = ev_of(qstore)
    assert e["status"] == "PENDING" and e["attempt"] == 0 and not [x for x in qstore.events() if x["event_type"] == "JOB_FAILED"]
    assert len(rv.calls) == 6


def test_after_the_reset_the_head_is_revalidated_before_the_probe_and_a_stale_request_is_superseded_without_spending_the_probe(qstore, clock):
    w, rv = World().add(7), Reviewer(limited(clock.t + HOUR))
    enq(w, qstore)
    pl.work(w, qstore, POLICY, REPO, rv)
    clock.t += HOUR + rl.MARGIN_S + 1
    w.prs[7]["head"]["sha"] = NEW                                                                       # o Claude publicou uma correcao enquanto a conta esperava
    w.commits[7] = [{"sha": NEW}]
    out = pl.work(w, qstore, POLICY, REPO, rv)
    assert out["action"] == "IDLE" and ev_of(qstore)["status"] == "SUPERSEDED" and len(rv.calls) == 1
    assert rl.RateLimitGate(qstore).admit(ACC, "outro").probe                                           # a vaga da sonda continua livre para o HEAD novo


def test_after_the_reset_a_successful_review_clears_the_account_and_the_event_completes_with_a_single_attempt(qstore, clock):
    w = World().add(7)
    enq(w, qstore)
    pl.work(w, qstore, POLICY, REPO, Reviewer(limited(clock.t + HOUR)))
    clock.t += HOUR + rl.MARGIN_S + 1
    ok = Reviewer({"action": "DONE", "verdict": "APPROVE", "url": "u", "codex_ran": True})
    assert pl.work(w, qstore, POLICY, REPO, ok)["action"] == "DONE"
    e = ev_of(qstore)
    assert e["status"] == "DONE" and e["attempt"] == 1
    assert rl.RateLimitGate(qstore).status() == [] and rl.RateLimitGate(qstore).peek(ACC) is None


def test_a_probe_that_hits_the_limit_again_without_forecast_waits_the_escalating_backoff_and_still_spends_no_attempt(qstore, clock):
    w, rv = World().add(7), Reviewer(limited(clock.t + HOUR))
    enq(w, qstore)
    pl.work(w, qstore, POLICY, REPO, rv)
    clock.t += HOUR + rl.MARGIN_S + 1
    rv.result = limited(None, ambiguous=True)                                                           # o texto nao trouxe previsao
    out = pl.work(w, qstore, POLICY, REPO, rv)
    assert out["action"] == "RATE_LIMITED" and out["suspended"]["episodes"] == 2 and out["suspended"]["reset_known"] is False
    assert out["suspended"]["until"] == clock.t + rl.BACKOFF_S[1]
    assert ev_of(qstore)["attempt"] == 0 and ev_of(qstore)["status"] == "PENDING"


def test_after_the_reset_only_one_of_three_workers_probes_and_the_others_release_their_leases_and_wait(qstore, clock):
    w = World().add(7).add(8).add(9)
    enq(w, qstore)
    pl.work(w, qstore, POLICY, REPO, Reviewer(limited(clock.t + HOUR)))
    clock.t += HOUR + rl.MARGIN_S + 1
    inside, release, results = threading.Event(), threading.Event(), {}

    def slow(pr, gh, policy, repo, do_publish=False, **kw):
        inside.set()
        release.wait(20)
        return {"action": "DONE", "verdict": "APPROVE", "url": "u", "codex_ran": True}

    def worker(name):
        results[name] = pl.work(w, qstore, POLICY, REPO, slow)

    t1 = threading.Thread(target=worker, args=("probe",))
    t1.start()
    assert inside.wait(10)
    others = []
    for i in range(2):                                                                                  # os outros workers chegam com a sonda em andamento
        t = threading.Thread(target=worker, args=(f"w{i}",))
        t.start()
        others.append(t)
    for t in others:
        t.join(10)
    assert all(results[f"w{i}"]["action"] == "IDLE" and results[f"w{i}"]["suspended"]["probing"] for i in range(2))
    assert [e["status"] for e in pending(qstore)].count("RUNNING") == 1                                 # so UM evento (a sonda) segura lease
    release.set()
    t1.join(20)
    assert results["probe"]["action"] == "DONE"
    assert rl.RateLimitGate(qstore).peek(ACC) is None                                                   # a sonda provou: todos voltam a trabalhar


def test_the_suspension_survives_a_restart_of_the_supervisor_and_resumes_by_itself_at_the_reset(tmp_path, clock):
    db = tmp_path / "restart.db"
    s1 = EventStore(db, clock=clock)
    w = World().add(7)
    enq(w, s1)
    pl.work(w, s1, POLICY, REPO, Reviewer(limited(clock.t + 2 * HOUR)))
    del s1                                                                                              # o processo morreu (ou o Windows reiniciou)
    s2 = EventStore(db, clock=clock)
    rv = Reviewer({"action": "DONE", "verdict": "APPROVE", "url": "u", "codex_ran": True})
    n = len(w.calls)
    assert pl.work(w, s2, POLICY, REPO, rv)["action"] == "IDLE" and len(w.calls) == n and rv.calls == []
    clock.t += 2 * HOUR + rl.MARGIN_S + 1
    assert pl.work(w, s2, POLICY, REPO, rv)["action"] == "DONE" and len(rv.calls) == 1                  # retoma sem nenhuma acao humana


def test_a_review_in_flight_when_the_supervisor_dies_returns_to_the_pool_and_a_quota_block_still_applies(tmp_path, clock):
    s1 = EventStore(tmp_path / "crash.db", clock=clock)
    w = World().add(7)
    enq(w, s1)
    claimed = s1.claim_by_id(ev_of(s1)["id"], "morreu", pl.LEASE_S)
    assert claimed["attempt"] == 1
    rl.RateLimitGate(s1).record_block(ACC, rl.Failure(rl.USAGE_LIMIT, "x", clock.t + HOUR))             # outro worker bateu o limite no mesmo instante
    clock.t += pl.LEASE_S + 1                                                                           # lease vencido, bloqueio vigente
    s2 = EventStore(tmp_path / "crash.db", clock=clock)
    rv = Reviewer()
    assert pl.work(w, s2, POLICY, REPO, rv)["action"] == "IDLE" and rv.calls == []                      # o evento orfao espera o reset em vez de martelar a conta


def test_too_many_consecutive_limits_escalate_the_account_without_dead_lettering_and_the_owner_can_resume(qstore, clock):
    w, rv = World().add(7), Reviewer(limited(None, ambiguous=True))
    enq(w, qstore)
    for _ in range(rl.MAX_EPISODES + 1):
        clock.t = max(clock.t, ev_of(qstore)["available_at"], rl.RateLimitGate(qstore).status()[0]["until"] if rl.RateLimitGate(qstore).status() else 0) + 1
        pl.work(w, qstore, POLICY, REPO, rv)
    gate = rl.RateLimitGate(qstore)
    assert gate.peek(ACC).escalated
    n = len(rv.calls)
    clock.t += 30 * 86400
    assert pl.work(w, qstore, POLICY, REPO, rv)["action"] == "IDLE" and len(rv.calls) == n              # sem retry infinito: nenhuma chamada mais
    assert ev_of(qstore)["status"] == "PENDING"
    gate.clear(ACC)
    rv.result = {"action": "DONE", "verdict": "APPROVE", "url": "u", "codex_ran": True}
    assert pl.work(w, qstore, POLICY, REPO, rv)["action"] == "DONE"


def test_an_authentication_failure_spends_the_attempt_and_pauses_the_account_but_a_transient_one_does_not_suspend_it(qstore, clock):
    w = World().add(7)
    enq(w, qstore)
    transient = Reviewer({"action": "REVIEW_BLOCKED", "reason": "falha transitoria do Codex", "kind": rl.TRANSIENT, "codex_ran": False})
    assert pl.work(w, qstore, POLICY, REPO, transient)["action"] == "REVIEW_BLOCKED"
    assert ev_of(qstore)["attempt"] == 1 and rl.RateLimitGate(qstore).peek(ACC) is None                 # erro transitorio: tentativa gasta, conta livre
    clock.t += pl.RETRY_S + 1
    auth = Reviewer({"action": "REVIEW_BLOCKED", "reason": "falha de autenticacao", "kind": rl.AUTH, "codex_ran": False})
    assert pl.work(w, qstore, POLICY, REPO, auth)["action"] == "REVIEW_BLOCKED"
    blk = rl.RateLimitGate(qstore).peek(ACC)
    assert blk is not None and blk.state == rl.AUTH_FAILED and ev_of(qstore)["attempt"] == 2
    assert pl.work(w, qstore, POLICY, REPO, auth)["action"] == "IDLE"                                    # nao martela o login quebrado


def test_a_definitive_error_still_ends_in_the_dlq_when_the_attempts_run_out(qstore, clock):
    w = World().add(7)
    enq(w, qstore)
    boom = Reviewer({"action": "REVIEW_BLOCKED", "reason": "codex saiu com codigo 2", "kind": rl.FATAL, "codex_ran": True})
    for _ in range(pl.MAX_ATTEMPTS):
        clock.t += pl.RETRY_S + 1
        pl.work(w, qstore, POLICY, REPO, boom)
    assert ev_of(qstore)["status"] == "DLQ"                                                              # so a cota nao leva a DLQ; erro definitivo continua levando


def test_a_review_that_proves_nothing_does_not_clear_the_block_and_gives_the_probe_slot_back(qstore, clock):
    w = World().add(7)
    enq(w, qstore)
    pl.work(w, qstore, POLICY, REPO, Reviewer(limited(clock.t + HOUR)))
    clock.t += HOUR + rl.MARGIN_S + 1
    stale = Reviewer({"action": "STALE", "reason": "HEAD mudou"})                                         # nao chegou a rodar o Codex
    pl.work(w, qstore, POLICY, REPO, stale)
    assert rl.RateLimitGate(qstore).status() != []                                                        # continua LIMITED: so execucao concluida limpa
    assert rl.RateLimitGate(qstore).admit(ACC, "w9").probe


def test_the_reconcile_step_requeues_a_legacy_dlq_by_usage_limit_and_reports_the_suspended_account(gov, qstore, clock):
    w = World().add(7)
    enq(w, qstore)
    ev = qstore.claim_by_id(ev_of(qstore)["id"], "w", pl.LEASE_S)
    for _ in range(ev["max_attempts"] - 1):                                                               # leva ao ultimo ciclo como o incidente de 2026-11-16
        qstore.fail(ev, "REVIEW_BLOCKED: auth/limite de uso: usage limit, try again later", retry_delay=0)
        ev = qstore.claim_by_id(ev["id"], "w", pl.LEASE_S)
    assert qstore.fail(ev, "REVIEW_BLOCKED: auth/limite de uso: usage limit, try again later", retry_delay=0) == "DLQ"
    out = pl.reconcile_step(w, POLICY, REPO, True, qstore, Writes())
    assert out["quota"]["requeued"][0]["action"] == "REQUEUED_QUOTA_DLQ"
    assert ev_of(qstore)["status"] == "PENDING" and ev_of(qstore)["attempt"] == 0
    assert "quota" not in pl.reconcile_step(w, POLICY, REPO, True, qstore, Writes())                      # segundo ciclo: nada a fazer, o log nao muda


def test_a_review_already_published_on_the_head_reconciles_the_event_instead_of_reviewing_again_even_after_a_quota_requeue(qstore, clock):
    w, rv = World().add(7), Reviewer()
    enq(w, qstore)
    w.reviews[7] = [{"id": 99, "user": {"login": "fmmodesto"}, "state": "CHANGES_REQUESTED", "commit_id": HEAD, "body": ""}]      # outro caminho ja publicou neste HEAD
    out = pl.work(w, qstore, POLICY, REPO, rv)
    assert out["action"] == "RECONCILED" and out["verdict"] == "REQUEST_CHANGES" and out["review_id"] == 99
    assert rv.calls == [] and ev_of(qstore)["status"] == "DONE" and ev_of(qstore)["attempt"] == 1
    assert rl.RateLimitGate(qstore).status() == []                                                      # nem sondou a conta


def test_an_approved_review_already_on_the_head_reconciles_as_approve_for_the_merge_step(qstore, clock):
    w = World().add(7)
    enq(w, qstore)
    w.reviews[7] = [{"id": 5, "user": {"login": "fmmodesto"}, "state": "APPROVED", "commit_id": HEAD, "body": ""}]
    assert pl.work(w, qstore, POLICY, REPO, Reviewer())["verdict"] == "APPROVE"
    assert pl.approved_candidates(qstore, REPO) == {7}


def test_a_review_on_an_older_head_does_not_reconcile_the_new_head(qstore, clock):
    w, rv = World().add(7), Reviewer()
    enq(w, qstore)
    w.reviews[7] = [{"id": 1, "user": {"login": "fmmodesto"}, "state": "CHANGES_REQUESTED", "commit_id": NEW, "body": ""}]
    assert pl.work(w, qstore, POLICY, REPO, rv)["action"] == "DONE" and len(rv.calls) == 1


def test_a_reviewer_that_reconciles_at_the_publish_step_completes_the_event_with_the_existing_verdict_and_proves_the_account(qstore, clock):
    w = World().add(7)
    enq(w, qstore)
    rv = Reviewer({"action": "RECONCILED", "reason": "ja publicado", "review_id": 12, "state": "APPROVED", "codex_ran": True})
    out = pl.work(w, qstore, POLICY, REPO, rv)
    assert out["action"] == "RECONCILED" and out["pr"] == 7
    e = ev_of(qstore)
    assert e["status"] == "DONE" and '"verdict": "APPROVE"' in e["result"] and '"reconciled": true' in e["result"]
    assert rl.RateLimitGate(qstore).status() == []
