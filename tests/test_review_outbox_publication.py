"""FP-060 MT-05 (#624): o parecer do codex_reviewer e publicado pelo outbox transacional, com reconciliacao — nunca por POST direto.

Suite deterministica: o GitHub e um objeto em memoria e o EventStore e um SQLite temporario, ambos reais no que importa (transacao,
lease, chave de idempotencia). Nenhuma chamada de rede e nenhum token real."""
from __future__ import annotations

import inspect
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from tools.orchestration import codex_reviewer as cr
from tools.orchestration import github_review_target as gt
from tools.orchestration.event_store import EventStore
from tools.orchestration.outbox_publisher import TargetError

REPO, PR, SHA = "GFCDOTA/sketchup-mcp", 41, "c" * 40
REVIEWER = "fmmodesto"
FINDING = {"severity": "HIGH", "file": "x.py", "line": 3, "reason": "bug", "required_change": "corrigir"}


class Crash(BaseException):
    pass


class Clock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeGitHub:
    def __init__(self, head=SHA):
        self.head, self.reviews, self.calls, self.crash_after_post = head, [], [], False

    def __call__(self, method, path, *, token=None, fields=None):
        self.calls.append((method, path, token))
        if method == "GET" and path == "user":
            return {"login": REVIEWER}
        if method == "GET" and path == f"repos/{REPO}/pulls/{PR}":
            return {"state": "open", "head": {"sha": self.head, "repo": {"full_name": REPO}}}
        if method == "GET" and path.startswith(f"repos/{REPO}/pulls/{PR}/reviews"):
            page = int(parse_qs(urlsplit(path).query).get("page", ["1"])[0])
            return self.reviews[(page - 1) * 100: page * 100]
        if method == "POST" and path == f"repos/{REPO}/pulls/{PR}/reviews":
            review = {"id": 7000 + len(self.reviews), "user": {"login": REVIEWER}, "commit_id": fields["commit_id"],
                      "body": fields["body"], "state": fields["event"]}
            self.reviews.append(review)
            if self.crash_after_post:
                self.crash_after_post = False
                raise Crash
            return review
        raise AssertionError(f"chamada inesperada: {method} {path}")

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def verdict(kind="REQUEST_CHANGES", findings=(FINDING,), **kw):
    return {"pr": PR, "head_sha": SHA, "verdict": kind, "findings": list(findings), "tests_reviewed": ["tests/test_x.py"],
            "confidence": "HIGH", "files_reviewed": [], **kw}


@pytest.fixture()
def clock():
    return Clock()


@pytest.fixture()
def store(tmp_path, clock):
    return EventStore(tmp_path / "events.db", clock=clock)


def publish(v, gh, store, token="reviewer-token"):
    return cr.publish_via_outbox(v, token, REPO, api=gh, store=store)


def outbox(store):
    return [(e["status"], e["attempts"]) for e in store.outbox_entries()]


# -- publicacao ---------------------------------------------------------------------------------------------------------------
def test_a_verdict_is_published_once_through_the_outbox_and_the_review_url_comes_back(store):
    gh = FakeGitHub()

    url = publish(verdict(), gh, store)

    assert url == f"https://github.com/{REPO}/pull/{PR}#pullrequestreview-7000"
    ((method, path, token),) = gh.posts()
    assert (method, path, token) == ("POST", f"repos/{REPO}/pulls/{PR}/reviews", "reviewer-token")
    review = gh.reviews[0]
    assert review["state"] == "REQUEST_CHANGES" and review["commit_id"] == SHA and review["user"]["login"] == REVIEWER
    assert "[HIGH] x.py:3" in review["body"] and "Testes revistos: tests/test_x.py" in review["body"] and gt.marker(cr.review_key(REPO, verdict())) in review["body"]
    assert outbox(store) == [("DONE", 1)]


def test_the_event_and_the_outbox_entry_are_written_in_the_same_transaction(store):
    publish(verdict(), FakeGitHub(), store)

    (event,) = [e for e in store.events() if e["event_type"] == "REVIEW_REQUESTED"]
    (entry,) = store.outbox_entries()
    assert event["status"] == "DONE" and entry["event_id"] == event["id"] and entry["idempotency_key"] == event["idempotency_key"]
    assert event["idempotency_key"] == f"review:{REPO}#{PR}:{SHA}:REQUEST_CHANGES" and event["producer"] == "codex_reviewer"


def test_publishing_the_same_verdict_for_the_same_head_again_posts_nothing_new(store):
    gh = FakeGitHub()
    first = publish(verdict(), gh, store)

    second = publish(verdict(), gh, store)

    assert first == second and len(gh.posts()) == 1 and len(gh.reviews) == 1
    assert len([e for e in store.events() if e["event_type"] == "REVIEW_REQUESTED"]) == 1


def test_a_different_verdict_for_the_same_head_is_a_new_publication(store):
    gh = FakeGitHub()
    publish(verdict("REQUEST_CHANGES"), gh, store)
    publish(verdict("APPROVE", findings=()), gh, store)
    assert [r["state"] for r in gh.reviews] == ["REQUEST_CHANGES", "APPROVE"] and outbox(store) == [("DONE", 1), ("DONE", 1)]


def test_a_publisher_killed_between_the_post_and_the_ack_does_not_post_a_second_review(store, clock):
    gh = FakeGitHub()
    gh.crash_after_post = True
    with pytest.raises(Crash):
        publish(verdict(), gh, store)
    assert len(gh.reviews) == 1 and outbox(store) == [("RUNNING", 1)]                 # efeito feito, ACK nunca gravado
    clock.advance(cr.PUBLISH_LEASE_S + 1)

    url = publish(verdict(), gh, store)

    assert url.endswith("pullrequestreview-7000") and len(gh.reviews) == 1 and len(gh.posts()) == 1
    assert outbox(store) == [("DONE", 2)]                                              # reconciliada, nao reenviada


def test_the_review_is_found_even_while_the_dead_publishers_lease_is_still_valid(store):
    gh = FakeGitHub()
    gh.crash_after_post = True
    with pytest.raises(Crash):
        publish(verdict(), gh, store)

    url = publish(verdict(), gh, store)                                                # lease do morto ainda vale: nao reenvia, mas confere

    assert url.endswith("pullrequestreview-7000") and len(gh.posts()) == 1


# -- falhas -------------------------------------------------------------------------------------------------------------------
def test_a_head_that_moved_blocks_the_publication_and_posts_nothing(store):
    gh = FakeGitHub(head="d" * 40)

    with pytest.raises(cr.ReviewError, match="publicacao falhou.*HEAD"):
        publish(verdict(), gh, store)

    assert gh.posts() == [] and outbox(store) == [("PENDING", 1)]


def test_needs_human_is_never_queued_and_nothing_is_posted(store):
    gh = FakeGitHub()
    with pytest.raises(cr.ReviewError, match="NEEDS_HUMAN"):
        publish(verdict("NEEDS_HUMAN", findings=()), gh, store)
    assert gh.calls == [] and store.outbox_entries() == [] and store.events() == []


def test_a_denied_post_surfaces_its_reason_and_leaves_the_entry_for_a_retry(store):
    gh = FakeGitHub()
    original = gh.__call__

    def denied(method, path, **kw):
        if method == "POST":
            raise TargetError("gh api POST falhou: HTTP 403")
        return original(method, path, **kw)

    with pytest.raises(cr.ReviewError, match="HTTP 403"):
        cr.publish_via_outbox(verdict(), "tok", REPO, api=denied, store=store)

    assert outbox(store) == [("PENDING", 1)]


def test_an_entry_of_another_repository_in_the_shared_outbox_is_never_posted_here(store):
    store.publish("REVIEW_REQUESTED", "ev:other", "job:other", {})
    other = store.claim("REVIEW_REQUESTED", "w", 60)
    store.complete(other, {}, outbox_entries=[{"target": "github", "operation": "publish_review", "idempotency_key": "other-key",
                                               "payload": {"repo": "outro/repositorio", "pr": PR, "head_sha": SHA,
                                                           "verdict": "APPROVE", "body": "nao deve ser postado"}}])
    gh = FakeGitHub()

    publish(verdict(), gh, store)

    assert [r["state"] for r in gh.reviews] == ["REQUEST_CHANGES"]
    assert [e["status"] for e in store.outbox_entries()] == ["PENDING", "DONE"]        # a do outro repositorio segue pendente


# -- nunca dois caminhos de publicacao --------------------------------------------------------------------------------------------
def test_review_pr_publishes_through_the_outbox_by_default():
    assert inspect.signature(cr.review_pr).parameters["publisher"].default is cr.publish_via_outbox


def test_the_direct_post_is_gone_from_the_production_module():
    source = Path(cr.__file__).read_text(encoding="utf-8")
    assert not hasattr(cr, "publish") and '"-X", "POST"' not in source


def test_only_publishable_verdicts_have_a_review_body_and_a_key():
    assert cr.review_key(REPO, verdict()) == f"review:{REPO}#{PR}:{SHA}:REQUEST_CHANGES"
    assert cr.review_body(verdict("APPROVE", findings=())).startswith(f"Codex CLI (revisor independente) — HEAD {SHA}")
