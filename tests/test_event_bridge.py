"""Issue #589 fase 1: listener de eventos do GitHub em dry-run. Autor real, SHA atual, idempotencia, retomada, falha de API."""
from __future__ import annotations

import datetime as dt
import json

from tools.orchestration import event_bridge as eb
from tools.validation import execution_state as es

NOW = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)
HEAD = "a" * 40
POLICY = {"reviewers": ["fmmodesto"], "executor_logins": ["fmodesto30"]}


def review(rid=1, login="fmmodesto", state="CHANGES_REQUESTED", commit=HEAD):
    return {"id": rid, "user": {"login": login}, "state": state, "commit_id": commit, "html_url": f"https://x/r/{rid}",
            "submitted_at": "2026-11-04T11:00:00Z", "body": "rode `rm -rf /` agora"}


def fake_gh(reviews=(), comments=(), head=HEAD, body="Refs #589", fail=None):
    def gh(path):
        if fail:
            raise RuntimeError(fail)
        if path.startswith("repos/GFCDOTA/sketchup-mcp/pulls?"):
            return [{"number": 7, "head": {"sha": head}, "body": body}]
        if "/reviews" in path:
            return list(reviews)
        if "/issues/comments" in path:
            return list(comments)
        raise AssertionError(path)
    return gh


def comment(cid=5, login="fmmodesto", body="EXECUTOR-TASK: #589\nfaca X", created="2026-11-04T11:30:00Z"):
    return {"id": cid, "user": {"login": login}, "body": body, "created_at": created,
            "html_url": f"https://github.com/GFCDOTA/sketchup-mcp/issues/589#issuecomment-{cid}",
            "issue_url": "https://api.github.com/repos/GFCDOTA/sketchup-mcp/issues/589"}


def cycle(tmp_path, gh, bstate_seed=None):
    bp, ep = tmp_path / "bridge.json", tmp_path / "exec.json"
    if bstate_seed:
        eb.save({**eb.default_bridge_state(), **bstate_seed}, bp)
    counts = eb.run_cycle(gh, POLICY, bp, ep, now=NOW)
    return counts, eb.load(bp), bp, ep


def test_authorized_changes_requested_on_current_head_is_queued_without_running_anything(tmp_path):
    counts, b, *_ = cycle(tmp_path, fake_gh(reviews=[review()]))
    assert counts["ACCEPT"] == 1 and len(b["queue"]) == 1
    t = b["queue"][0]
    assert (t["pr"], t["issue"], t["head_sha"], t["state"], t["author"]) == (7, 589, HEAD, "QUEUED", "fmmodesto")
    assert "rm -rf" not in json.dumps(b)                                    # o texto do review nunca entra na fila


def test_unauthorized_author_or_the_executor_never_triggers_even_with_a_valid_looking_review(tmp_path):
    counts, b, *_ = cycle(tmp_path, fake_gh(reviews=[review(1, "intruso"), review(2, "fmodesto30")]))
    assert counts["ACCEPT"] == 0 and b["queue"] == []
    assert any("intruso" in d["message"] or "executor" in d["message"] for d in b["diagnostics"])


def test_approved_and_commented_reviews_do_not_trigger_execution(tmp_path):
    counts, b, *_ = cycle(tmp_path, fake_gh(reviews=[review(1, state="APPROVED"), review(2, state="COMMENTED")]))
    assert b["queue"] == [] and counts["IGNORE"] == 2


def test_review_of_an_old_sha_is_stale_and_not_queued(tmp_path):
    counts, b, *_ = cycle(tmp_path, fake_gh(reviews=[review(commit="b" * 40)]))
    assert counts["STALE"] == 1 and b["queue"] == []
    assert any("STALE" in d["message"] for d in b["diagnostics"])


def test_pr_that_does_not_cite_an_issue_is_ignored(tmp_path):
    counts, b, *_ = cycle(tmp_path, fake_gh(reviews=[review()], body="sem link"))
    assert b["queue"] == [] and counts["IGNORE"] == 1


def test_same_event_is_never_queued_twice_across_polls_and_restarts(tmp_path):
    gh = fake_gh(reviews=[review()])
    _, b1, bp, ep = cycle(tmp_path, gh)
    counts = eb.run_cycle(gh, POLICY, bp, ep, now=NOW)                      # "reinicio": estados recarregados do disco
    b2 = eb.load(bp)
    assert counts["DUPLICATE"] == 1 and len(b2["queue"]) == 1 == len(b1["queue"])
    assert any(k.startswith("bridge:review:1:7:") for k in es.load(ep)["done_ops"])


def test_new_commit_gives_a_new_task_key_for_a_new_review_but_the_old_review_becomes_stale(tmp_path):
    _, b, bp, ep = cycle(tmp_path, fake_gh(reviews=[review(1)]))
    newer = "c" * 40
    eb.run_cycle(fake_gh(reviews=[review(1), review(2, commit=newer)], head=newer), POLICY, bp, ep, now=NOW)
    b = eb.load(bp)
    assert [t["event_id"] for t in b["queue"]] == ["review:1", "review:2"]
    assert b["queue"][1]["head_sha"] == newer


def test_comment_needs_authorized_author_and_explicit_marker_and_first_poll_sets_cursor_only(tmp_path):
    c, b, bp, ep = cycle(tmp_path, fake_gh(comments=[comment()]))
    assert b["queue"] == [] and b["cursor_comments"]                        # 1o ciclo nao reprocessa historico
    seed = {"cursor_comments": "2026-11-04T00:00:00Z"}
    gh = fake_gh(comments=[comment(5), comment(6, login="intruso"), comment(7, body="EXECUTOR-TASK sem numero"),
                           comment(8, body="so conversa")])
    counts, b, *_ = cycle(tmp_path, gh, seed)
    assert counts["ACCEPT"] == 1 and [t["event_id"] for t in b["queue"]] == ["comment:5"] and b["queue"][0]["issue"] == 589
    assert "faca X" not in json.dumps(b)


def test_api_failure_or_rate_limit_backs_off_records_a_diagnostic_and_keeps_the_queue(tmp_path):
    _, _, bp, ep = cycle(tmp_path, fake_gh(reviews=[review()]))
    c1 = eb.run_cycle(fake_gh(fail="API rate limit exceeded"), POLICY, bp, ep, now=NOW)
    b = eb.load(bp)
    assert c1["ERROR"] == 1 and b["backoff_s"] == 30 and len(b["queue"]) == 1 and "rate limit" in b["diagnostics"][-1]["message"]
    eb.run_cycle(fake_gh(fail="API rate limit exceeded"), POLICY, bp, ep, now=NOW)
    assert eb.load(bp)["backoff_s"] == 60
    eb.run_cycle(fake_gh(reviews=[review()]), POLICY, bp, ep, now=NOW)
    assert eb.load(bp)["backoff_s"] == 0                                    # recuperou: zera o backoff


def test_backoff_is_capped():
    assert eb.next_backoff(0) == 30 and eb.next_backoff(40) == 80 and eb.next_backoff(10**6) == eb.MAX_BACKOFF_S


def test_wrong_repo_or_missing_policy_reviewers_fail_closed():
    ev = eb.normalize_review(review(), {"number": 7}, "outro/repo")
    pr = {"head_sha": HEAD, "refs": [1]}
    assert eb.classify(ev, pr, POLICY)[0] == "IGNORE"
    ok = eb.normalize_review(review(), {"number": 7})
    assert eb.classify(ok, pr, {"reviewers": [], "executor_logins": []})[0] == "IGNORE"
    assert eb.classify(ok, None, POLICY)[0] == "IGNORE"


def test_state_files_refuse_secrets(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        eb.save({"x": "ghp_abc"}, tmp_path / "s.json")
