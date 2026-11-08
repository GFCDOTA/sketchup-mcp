"""FP-059/F4 (#601): reconciliador duravel — estado derivado dos FATOS do GitHub, transicoes registradas, idempotencia, recuperacao, merge/HEAD novo/CI."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from tools.orchestration import lifecycle as lc

HEAD = "a" * 40
NEW = "b" * 40
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}
REPO = "o/r"
NOW = dt.datetime(2026, 11, 5, 0, 0, tzinfo=dt.timezone.utc)


NAMES = sorted(lc.MANDATORY_CHECKS)


def run(conclusion="success", status="completed", name="x"):
    return {"name": name, "status": status, "conclusion": conclusion}


def all_green():
    return [run(name=n) for n in NAMES]


def all_green_except(bad_name, **overrides):
    return [run(name=n, **overrides) if n == bad_name else run(name=n) for n in NAMES]


def all_green_without(*exclude):
    return [run(name=n) for n in NAMES if n not in exclude]


def rev(state, head=HEAD, user="fmmodesto", rid=1):
    return {"id": rid, "user": {"login": user}, "state": state, "commit_id": head}


def pr(head=HEAD, state="open", merged=False, labels=("executor-ok",), body="Refs #589"):
    return {"number": 7, "state": state, "merged": merged, "body": body, "labels": [{"name": n} for n in labels], "head": {"sha": head, "ref": "feat/x"}}


class World:
    """GitHub falso e mutavel."""

    def __init__(self, **kw):
        self.pr, self.runs, self.reviews = kw.get("pr", pr()), kw.get("runs", all_green()), kw.get("reviews", [])
        self.fail_list = False

    def __call__(self, path):
        if path.startswith(f"repos/{REPO}/pulls?state=open"):
            if self.fail_list:
                raise RuntimeError("rate limit")
            return [self.pr] if self.pr["state"] == "open" else []
        if path == f"repos/{REPO}/pulls/7":
            return self.pr
        if path.startswith(f"repos/{REPO}/commits/") and "check-runs" in path:
            return {"check_runs": self.runs}
        if path.startswith(f"repos/{REPO}/pulls/7/reviews"):
            return self.reviews
        raise AssertionError(path)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_BRIDGE_STATE_PATH", str(tmp_path / "gov" / "bridge.json"))


def cycle(w, **kw):
    return lc.reconcile(w, POLICY, REPO, now=NOW, **kw)


def state_of(tmp_path):
    return lc.load(tmp_path / "gov" / "lifecycle.json")["prs"]["7"]


# ----------------------------------------------------------------------------------------------------- derivacao pura
@pytest.mark.parametrize("p,runs,reviews,expected", [
    (pr(), all_green(), [], "REVIEW_QUEUED"),
    (pr(), all_green_except(NAMES[0], conclusion=None, status="in_progress"), [], "WAITING_CI"),
    (pr(), [], [], "WAITING_CI"),
    (pr(), all_green_except(NAMES[0], conclusion="failure"), [], "CI_FAILED"),
    (pr(), all_green(), [rev("CHANGES_REQUESTED")], "CHANGES_REQUESTED"),
    (pr(), all_green(), [rev("APPROVED")], "APPROVED"),
    (pr(), all_green(), [rev("APPROVED", head=NEW)], "REVIEW_QUEUED"),                     # review de SHA antigo nao vale
    (pr(), all_green(), [rev("APPROVED", user="fmodesto30")], "REVIEW_QUEUED"),             # executor nunca aprova
    (pr(), all_green(), [rev("APPROVED", user="intruso")], "REVIEW_QUEUED"),                # autor nao autorizado
    (pr(), all_green(), [rev("CHANGES_REQUESTED", rid=1), rev("APPROVED", rid=2)], "APPROVED"),  # vale o ultimo
    (pr(), all_green(), [rev("COMMENTED")], "REVIEW_QUEUED"),
    (pr(state="closed"), all_green(), [], "SUPERSEDED"),
    (pr(state="closed", merged=True), all_green(), [], "COMPLETED"),
])
def test_state_is_derived_from_facts_only(p, runs, reviews, expected):
    assert lc.derive(p, runs, reviews, POLICY)[0] == expected


def test_approved_never_means_automatic_merge():
    state, reason, _ = lc.derive(pr(), all_green(), [rev("APPROVED")], POLICY)
    assert state == "APPROVED" and "nao e automatico" in reason and lc.NEXT["APPROVED"] == "await_merge_policy"


# ------------------------------------------------------------------------------------------- transicoes e durabilidade
def test_first_cycle_records_the_transition_with_the_full_contract_and_persists_it(tmp_path):
    out = cycle(World())
    assert out["tracked"] == 1 and out["errors"] == [] and len(out["transitions"]) == 1
    t = out["transitions"][0]
    assert {"issue", "pr", "branch", "head_sha", "review_id", "from", "to", "actor", "reason", "attempt", "timestamp", "correlation_id"} <= set(t)
    assert (t["from"], t["to"], t["pr"], t["head_sha"], t["issue"], t["actor"]) == ("NEW", "REVIEW_QUEUED", 7, HEAD, 589, "reconciler")
    assert state_of(tmp_path)["state"] == "REVIEW_QUEUED"
    logged = [json.loads(x) for x in (tmp_path / "gov" / "lifecycle.log").read_text(encoding="utf-8").splitlines()]
    assert logged[0]["correlation_id"] == t["correlation_id"]


def test_unchanged_facts_produce_no_new_transition_and_no_log_spam(tmp_path):
    cycle(World())
    out = cycle(World())
    assert out["transitions"] == [] and len((tmp_path / "gov" / "lifecycle.log").read_text(encoding="utf-8").splitlines()) == 1


def test_new_head_invalidates_previous_results_as_stale_head_then_requeues(tmp_path):
    w = World(reviews=[rev("CHANGES_REQUESTED")])
    cycle(w)
    assert state_of(tmp_path)["state"] == "CHANGES_REQUESTED"
    w.pr = pr(head=NEW)                                                           # o executor publicou uma correcao
    out = cycle(w)
    tos = [t["to"] for t in out["transitions"]]
    assert tos[0] == "STALE_HEAD" and tos[-1] == "REVIEW_QUEUED" and state_of(tmp_path)["head_sha"] == NEW


def test_ci_going_from_pending_to_green_moves_to_review_queued(tmp_path):
    w = World(runs=all_green_except(NAMES[0], conclusion=None, status="in_progress"))
    cycle(w)
    assert state_of(tmp_path)["state"] == "WAITING_CI"
    w.runs = all_green()
    cycle(w)
    assert state_of(tmp_path)["state"] == "REVIEW_QUEUED"


def test_merge_is_reconciled_even_though_the_pr_left_the_open_list(tmp_path):
    w = World(reviews=[rev("APPROVED")])
    cycle(w)
    assert state_of(tmp_path)["state"] == "APPROVED"
    w.pr = pr(state="closed", merged=True)
    out = cycle(w)
    assert state_of(tmp_path)["state"] == "COMPLETED" and out["transitions"][-1]["to"] == "COMPLETED"
    assert any(a["action"] == "cleanup_local" for a in out["actions"])
    assert cycle(w)["tracked"] == 0                                               # concluido sai do rastreio


def test_unauthorized_pr_without_the_label_is_not_tracked(tmp_path):
    out = cycle(World(pr=pr(labels=("bug",))))
    assert out["tracked"] == 0 and not (tmp_path / "gov" / "lifecycle.json").exists() or lc.load(tmp_path / "gov" / "lifecycle.json")["prs"] == {}


def test_state_survives_a_restart_and_resumes_without_duplicating(tmp_path):
    w = World()
    cycle(w)
    first = state_of(tmp_path)
    again = lc.reconcile(w, POLICY, REPO, now=NOW)                                # "novo processo": so o arquivo carrega o estado
    assert again["transitions"] == [] and state_of(tmp_path)["history"] == first["history"]


def test_corrupt_state_file_recovers_to_empty_and_rebuilds_from_github(tmp_path):
    (tmp_path / "gov").mkdir()
    (tmp_path / "gov" / "lifecycle.json").write_text("{lixo", encoding="utf-8")
    out = cycle(World())
    assert out["errors"] == [] and state_of(tmp_path)["state"] == "REVIEW_QUEUED"


def test_github_failure_is_reported_not_fatal_and_changes_nothing(tmp_path):
    w = World()
    cycle(w)
    before = (tmp_path / "gov" / "lifecycle.json").read_text(encoding="utf-8")
    w.fail_list = True
    out = cycle(w)
    assert out["errors"] and "rate limit" in out["errors"][0] and (tmp_path / "gov" / "lifecycle.json").read_text(encoding="utf-8") == before


# ------------------------------------------------------------------------------------------------------ acoes / Codex
def test_dry_run_only_plans_the_codex_review_and_never_calls_it(tmp_path):
    calls = []
    out = cycle(World(), codex_review=lambda *a, **k: calls.append(a) or {"action": "DONE"})
    assert out["actions"][0] == {"pr": 7, "head_sha": HEAD, "action": "codex_review", "result": "PLANNED (dry-run)"} and calls == []


def test_execute_runs_the_codex_review_once_per_head_idempotently(tmp_path):
    calls = []
    w = World()
    fake = lambda n, gh, policy, repo: calls.append(n) or {"action": "DONE"}  # noqa: E731
    cycle(w, execute=True, codex_review=fake)
    cycle(w, execute=True, codex_review=fake)
    assert calls == [7]                                                            # mesma acao no mesmo HEAD nao repete
    w.pr = pr(head=NEW)
    cycle(w, execute=True, codex_review=fake)
    assert calls == [7, 7]                                                         # HEAD novo => nova revisao


def test_no_codex_review_is_planned_while_ci_is_pending_or_a_review_already_exists():
    for w in (World(runs=all_green_except(NAMES[0], conclusion=None, status="in_progress")), World(reviews=[rev("APPROVED")]), World(reviews=[rev("CHANGES_REQUESTED")])):
        assert not any(a["action"] == "codex_review" for a in cycle(w)["actions"])


def test_reconciler_never_merges_or_writes_to_github():
    import inspect
    src = inspect.getsource(lc)
    for forbidden in ("gh pr merge", "/merge\"", "-X POST", "-X PUT", "-X PATCH", "git push"):
        assert forbidden not in src


def test_listener_cycle_runs_the_reconciler_in_the_same_loop_and_never_breaks_on_its_failure(monkeypatch, tmp_path):
    from tools.orchestration import event_executor as ex
    monkeypatch.setenv("EXECUTION_STATE_PATH", str(tmp_path / "exec.json"))
    monkeypatch.setattr(ex.eb, "run_cycle", lambda *a, **k: {"ACCEPT": 0})
    monkeypatch.setattr(ex, "process_one", lambda *a, **k: {"action": "IDLE"})
    out = ex.run_cycle(World(), POLICY, REPO, now=NOW)
    assert out["action"] == "IDLE" and out["reconcile"]["tracked"] == 1 and out["reconcile"]["transitions"] == ["#7 NEW->REVIEW_QUEUED"]
    assert out["reconcile"]["actions"] == ["#7 codex_review"]
    monkeypatch.setattr("tools.orchestration.lifecycle.reconcile", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "boom" in ex.run_cycle(World(), POLICY, REPO, now=NOW)["reconcile"]["errors"][0]


# ------------------------------------------------------------------- negative: mandatory checks
class TestChecksStateMandatory:
    """checks_state DEVE exigir TODOS os checks obrigatorios com success."""

    def test_single_green_check_is_not_passed(self):
        assert lc.checks_state([run(name=NAMES[0])]) == "pending"

    def test_subset_green_is_not_passed(self):
        assert lc.checks_state([run(name=n) for n in NAMES[:4]]) == "pending"

    def test_one_mandatory_absent_is_pending(self):
        assert lc.checks_state(all_green_without(NAMES[3])) == "pending"

    def test_mandatory_check_skipped_is_failed(self):
        assert lc.checks_state(all_green_except(NAMES[0], conclusion="skipped")) == "failed"

    def test_mandatory_check_neutral_is_failed(self):
        assert lc.checks_state(all_green_except(NAMES[0], conclusion="neutral")) == "failed"

    def test_mandatory_check_pending_is_pending(self):
        assert lc.checks_state(all_green_except(NAMES[0], conclusion=None, status="in_progress")) == "pending"

    def test_all_mandatory_green_is_passed(self):
        assert lc.checks_state(all_green()) == "passed"

    def test_extra_non_mandatory_does_not_affect_pass(self):
        assert lc.checks_state(all_green() + [run(name="extra-info", conclusion="neutral")]) == "passed"

    def test_extra_failing_non_mandatory_fails(self):
        assert lc.checks_state(all_green() + [run(name="extra", conclusion="failure")]) == "failed"

    def test_subset_green_derives_waiting_ci_not_review_queued(self):
        state, _, _ = lc.derive(pr(), [run(name=NAMES[0])], [], POLICY)
        assert state == "WAITING_CI"


# ------------------------------------------------------------------------------ negative: old HEAD
class TestOldHeadSha:
    """Review em SHA antigo nao pode contar para o HEAD atual."""

    def test_approved_on_old_sha_leaves_review_queued(self, tmp_path):
        out = cycle(World(reviews=[rev("APPROVED", head=NEW)]))
        assert out["transitions"][0]["to"] == "REVIEW_QUEUED"

    def test_changes_requested_on_old_sha_leaves_review_queued(self, tmp_path):
        out = cycle(World(reviews=[rev("CHANGES_REQUESTED", head=NEW)]))
        assert out["transitions"][0]["to"] == "REVIEW_QUEUED"


# ------------------------------------------------------------------------------- pagination
class TestPagination:
    """_list_open_prs deve coletar TODOS os PRs abertos, paginando."""

    def test_single_page(self):
        called = []

        def gh(path):
            called.append(path)
            return [pr()]

        result = lc._list_open_prs(gh, REPO, per_page=50)
        assert len(result) == 1 and len(called) == 1

    def test_multiple_pages(self):
        prs = [{"number": i, "state": "open", "labels": [{"name": "executor-ok"}]} for i in range(5)]

        def gh(path):
            per_pg = int(path.split("per_page=")[1].split("&")[0])
            pg = int(path.split("&page=")[1].split("&")[0]) if "&page=" in path else 1
            start = (pg - 1) * per_pg
            return prs[start:start + per_pg]

        result = lc._list_open_prs(gh, REPO, per_page=2)
        assert len(result) == 5

    def test_exact_per_page_boundary(self):
        prs = [{"number": i} for i in range(4)]
        pages_called = []

        def gh(path):
            per_pg = int(path.split("per_page=")[1].split("&")[0])
            pg = int(path.split("&page=")[1].split("&")[0]) if "&page=" in path else 1
            pages_called.append(pg)
            start = (pg - 1) * per_pg
            return prs[start:start + per_pg]

        result = lc._list_open_prs(gh, REPO, per_page=2)
        assert len(result) == 4 and pages_called == [1, 2, 3]

    def test_non_list_response_stops(self):
        assert lc._list_open_prs(lambda p: {"error": "bad"}, REPO) == []

    def test_safety_cap_at_20_pages(self):
        result = lc._list_open_prs(lambda p: [{"number": 1}] * 50, REPO, per_page=50)
        assert len(result) == 1000
