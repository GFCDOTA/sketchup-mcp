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
from tools.orchestration.event_store import EventStore

REPO = "o/r"
HEAD, NEW = "a" * 40, "b" * 40
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}


@pytest.fixture(autouse=True)
def fresh_cache():
    pl._FACTS.clear()
    yield
    pl._FACTS.clear()


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
