"""FP-060 M2 (#606): destino GitHub do publicador do outbox — revisao independente, com reconciliacao pela chave.

Suite deterministica: o GitHub e um objeto em memoria que guarda os reviews. Nada aqui faz chamada de rede, usa token ou toca
o repositorio real. A prova contra o GitHub de verdade e o E2E num PR descartavel, que depende de identidade independente."""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from tools.orchestration import github_review_target as gt
from tools.orchestration import outbox_publisher as op
from tools.orchestration.event_store import EventStore
from tools.orchestration.outbox_publisher import TargetError

REPO, PR, SHA = "GFCDOTA/sketchup-mcp", 77, "a" * 40
REVIEWER, EXECUTOR = "fmmodesto", "fmodesto30"
POLICY = {"reviewers": [REVIEWER], "executor_logins": [EXECUTOR]}


class Crash(BaseException):
    pass


class FakeGitHub:
    """Responde aos poucos caminhos que o destino usa e guarda os reviews postados."""

    def __init__(self, head=SHA, state="open", repo=REPO):
        self.head, self.state, self.repo = head, state, repo
        self.reviews: list[dict] = []
        self.calls: list[tuple] = []
        self.fail: dict[str, str] = {}
        self.page_size = 100

    def __call__(self, method, path, *, token=None, fields=None):
        self.calls.append((method, path, token, dict(fields or {})))
        key = f"{method} {path.split('?')[0]}"
        if key in self.fail:
            raise TargetError(self.fail[key])
        if method == "GET" and path.startswith(f"repos/{REPO}/pulls/{PR}/reviews"):
            page = int(parse_qs(urlsplit(path).query).get("page", ["1"])[0])
            return self.reviews[(page - 1) * self.page_size: page * self.page_size]
        if method == "GET" and path == f"repos/{REPO}/pulls/{PR}":
            return {"state": self.state, "head": {"sha": self.head, "repo": {"full_name": self.repo}}}
        if method == "POST" and path == f"repos/{REPO}/pulls/{PR}/reviews":
            review = {"id": 1000 + len(self.reviews), "user": {"login": REVIEWER}, "commit_id": fields["commit_id"],
                      "body": fields["body"], "state": gt.REVIEW_STATE[fields["event"]]}
            self.reviews.append(review)
            return review
        raise AssertionError(f"chamada inesperada: {method} {path}")

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def entry(key="k1", verdict="REQUEST_CHANGES", **payload):
    base = {"pr": PR, "head_sha": SHA, "verdict": verdict, "body": "Codex CLI (revisor independente)"}
    return {"id": 1, "target": "github", "operation": "publish_review", "idempotency_key": key, "payload": {**base, **payload}}


def target(gh, token="reviewer-token"):
    return gt.GitHubReviewTarget(gh, token=token, reviewer=REVIEWER, repo=REPO)


# -- reconciliacao -----------------------------------------------------------------------------------------------------------
def test_find_returns_nothing_when_the_reviewer_has_not_published_the_key():
    gh = FakeGitHub()
    gh.reviews.append({"id": 1, "user": {"login": REVIEWER}, "body": "outro parecer", "commit_id": SHA})
    assert target(gh).find(entry()) is None and gh.posts() == []


def test_find_recognises_the_review_carrying_the_key_marker():
    gh, t = FakeGitHub(), None
    t = target(gh)
    t.send(entry("k1"))
    assert t.find(entry("k1")) == "github-review:1000" and t.find(entry("k2")) is None


def test_find_ignores_a_marker_written_by_anyone_but_the_independent_reviewer():
    gh = FakeGitHub()
    gh.reviews.append({"id": 5, "user": {"login": EXECUTOR}, "commit_id": SHA, "body": "x\n" + gt.marker("k1")})
    gh.reviews.append({"id": 6, "user": {"login": "intruso"}, "commit_id": SHA, "body": gt.marker("k1")})
    assert target(gh).find(entry("k1")) is None


def test_find_reads_every_page_of_reviews():
    gh = FakeGitHub()
    gh.page_size = 2
    for i in range(5):
        gh.reviews.append({"id": i, "user": {"login": REVIEWER}, "commit_id": SHA, "body": gt.marker(f"old{i}")})
    gh.reviews.append({"id": 99, "user": {"login": REVIEWER}, "commit_id": SHA, "state": "CHANGES_REQUESTED", "body": gt.marker("k1")})

    found = gt.GitHubReviewTarget(gh, token="t", reviewer=REVIEWER, repo=REPO, page_size=2).find(entry("k1"))

    assert found == "github-review:99" and len([c for c in gh.calls if "reviews" in c[1]]) == 3


def test_find_gives_up_after_the_page_limit_instead_of_pretending_the_key_is_absent():
    gh = FakeGitHub()
    gh.page_size = 1
    for i in range(10):
        gh.reviews.append({"id": i, "user": {"login": REVIEWER}, "commit_id": SHA, "body": "x"})
    with pytest.raises(TargetError, match="paginas"):
        gt.GitHubReviewTarget(gh, token="t", reviewer=REVIEWER, repo=REPO, page_size=1, max_pages=3).find(entry())


# -- envio -------------------------------------------------------------------------------------------------------------------
def test_send_posts_one_review_for_the_exact_head_with_the_key_marker_and_the_reviewer_token():
    gh = FakeGitHub()

    ref = target(gh, token="reviewer-token").send(entry("k1", "APPROVE", body="Aprovado"))

    ((method, path, token, fields),) = gh.posts()
    assert (method, path, token) == ("POST", f"repos/{REPO}/pulls/{PR}/reviews", "reviewer-token")
    assert fields["event"] == "APPROVE" and fields["commit_id"] == SHA
    assert fields["body"].startswith("Aprovado") and fields["body"].endswith(gt.marker("k1")) and ref == "github-review:1000"


@pytest.mark.parametrize("head, state, repo, why", [
    ("b" * 40, "open", REPO, "HEAD"),
    (SHA, "closed", REPO, "nao esta aberto"),
    (SHA, "open", "intruso/fork", "fork"),
])
def test_send_refuses_a_pull_request_that_moved_closed_or_came_from_a_fork(head, state, repo, why):
    gh = FakeGitHub(head=head, state=state, repo=repo)
    with pytest.raises(TargetError, match=why):
        target(gh).send(entry())
    assert gh.posts() == []


@pytest.mark.parametrize("bad", [
    {"pr": "7"}, {"pr": True}, {"pr": 0}, {"head_sha": "abc"}, {"head_sha": "Z" * 40}, {"verdict": "NEEDS_HUMAN"}, {"verdict": "COMMENT"}, {"body": ""},
])
def test_send_and_find_refuse_a_payload_that_is_not_a_complete_review(bad):
    gh = FakeGitHub()
    with pytest.raises(TargetError, match="payload"):
        target(gh).send(entry(**bad))
    with pytest.raises(TargetError, match="payload"):
        target(gh).find(entry(**bad))
    assert gh.calls == []


def test_a_failing_api_call_is_a_target_error_and_a_post_without_an_id_is_not_a_delivery():
    gh = FakeGitHub()
    gh.fail[f"POST repos/{REPO}/pulls/{PR}/reviews"] = "422 do GitHub"
    with pytest.raises(TargetError, match="422"):
        target(gh).send(entry())
    gh.fail.clear()
    original = gh.__call__
    gh2 = lambda method, path, **kw: {} if method == "POST" else original(method, path, **kw)   # noqa: E731
    with pytest.raises(TargetError, match="sem id"):
        target(gh2).send(entry())


# -- integracao com o publicador ---------------------------------------------------------------------------------------------
def queue(store, key="k1", **payload):
    store.publish("REVIEW_REQUESTED", f"ev:{key}", f"job:{key}", {})
    ev = store.claim("REVIEW_REQUESTED", "worker", 60)
    e = entry(key, **payload)
    store.complete(ev, {}, outbox_entries=[{"target": "github", "operation": "publish_review", "payload": e["payload"],
                                            "idempotency_key": key}])


def test_publisher_that_died_after_the_post_does_not_post_a_second_review(tmp_path):
    clock = [1_000_000.0]
    store = EventStore(tmp_path / "events.db", clock=lambda: clock[0])
    gh = FakeGitHub()
    targets = {"github": target(gh)}
    queue(store, "k1")

    def die(entry_, reference):
        raise Crash

    with pytest.raises(Crash):
        op.publish_one(store, targets, "pub-1", lease_seconds=30, after_send=die)
    assert len(gh.reviews) == 1
    clock[0] += gt.GitHubReviewTarget.send_timeout_s + op.SEND_MARGIN_S + 1                    # o lease do morto cobre o teto do envio (GET + POST)

    res = op.publish_one(store, targets, "pub-2", lease_seconds=30)

    assert (res["action"], res["reference"]) == ("RECONCILED", "github-review:1000")
    assert len(gh.reviews) == 1 and len(gh.posts()) == 1


def test_head_that_moved_before_the_send_fails_the_entry_and_posts_nothing(tmp_path):
    store = EventStore(tmp_path / "events.db")
    gh = FakeGitHub(head="c" * 40)
    queue(store, "k1")

    res = op.publish_one(store, {"github": target(gh)}, "pub-1", lease_seconds=30)

    assert res["action"] == "FAILED" and "HEAD" in res["reason"] and gh.posts() == []


# -- identidade ---------------------------------------------------------------------------------------------------------------
def test_target_is_built_only_from_an_independent_identity():
    users = {"reviewer-token": REVIEWER, "executor-token": EXECUTOR}
    gh = FakeGitHub()

    built = gt.from_policy(POLICY, REPO, gh, token="reviewer-token", gh_user=users.get)

    assert built.reviewer == REVIEWER and gh.calls == []
    with pytest.raises(TargetError, match="executor"):
        gt.from_policy(POLICY, REPO, gh, token="executor-token", gh_user=users.get)
    with pytest.raises(TargetError, match="ausente"):
        gt.from_policy(POLICY, REPO, gh, token="", gh_user=users.get)
    with pytest.raises(TargetError, match="invalido"):
        gt.from_policy(POLICY, REPO, gh, token="desconhecido", gh_user=users.get)
    with pytest.raises(TargetError, match="reviewers"):
        gt.from_policy({"reviewers": ["outro"], "executor_logins": [EXECUTOR]}, REPO, gh, token="reviewer-token", gh_user=users.get)


def test_the_token_never_appears_in_an_error_message():
    gh = FakeGitHub()
    gh.fail[f"GET repos/{REPO}/pulls/{PR}"] = "401 Bad credentials para segredo-do-revisor"
    with pytest.raises(TargetError) as exc:
        target(gh, token="segredo-do-revisor").send(entry())
    assert "segredo-do-revisor" not in str(exc.value) and "401" in str(exc.value)


def test_default_api_passes_the_token_through_the_environment_and_never_the_command_line(monkeypatch):
    seen = {}

    class Done:
        returncode, stdout, stderr = 0, '{"id": 3}', ""

    def run(argv, **kw):
        seen.update(argv=argv, env=kw["env"])
        return Done()

    monkeypatch.setattr(gt.subprocess, "run", run)

    assert gt.gh_api("POST", "repos/x/y/pulls/1/reviews", token="segredo", fields={"event": "APPROVE"}) == {"id": 3}
    assert "segredo" not in " ".join(seen["argv"]) and seen["env"]["GH_TOKEN"] == "segredo"
    assert seen["argv"][-2:] == ["-f", "event=APPROVE"] and seen["argv"][3] == "POST"


def test_default_api_reports_a_failed_call_without_the_token(monkeypatch):
    class Failed:
        returncode, stdout, stderr = 1, "", "HTTP 401 for segredo"

    monkeypatch.setattr(gt.subprocess, "run", lambda *a, **k: Failed())
    with pytest.raises(TargetError) as exc:
        gt.gh_api("GET", "repos/x/y", token="segredo")
    assert "segredo" not in str(exc.value) and "401" in str(exc.value)


# -- revisao do Codex (#619, 0b97e44a): lease durante todo o POST; guarda do PR descartavel da prova E2E -------------------------------------------------
def test_the_github_target_declares_a_send_ceiling_covering_its_get_and_post():
    assert gt.GitHubReviewTarget.send_timeout_s == 2 * gt.GH_CALL_TIMEOUT_S


def test_a_post_slower_than_the_original_lease_is_never_doubled_by_a_second_publisher(tmp_path):
    import threading
    clock = [1_000_000.0]
    store = EventStore(tmp_path / "events.db", clock=lambda: clock[0])
    gh = FakeGitHub()
    queue(store, "k1")
    entered, release, results = threading.Event(), threading.Event(), {}
    real = gh.__call__

    def slow_api(method, path, **kw):
        if method == "POST":
            entered.set()
            release.wait(10)                                                                       # o POST ainda esta em voo
        return real(method, path, **kw)
    t1 = threading.Thread(target=lambda: results.update(first=op.publish_one(store, {"github": target(slow_api)}, "pub-1", lease_seconds=30)))
    t1.start()
    assert entered.wait(10)
    clock[0] += 31                                                                                 # o lease ORIGINAL (30 s) venceu durante o POST
    second = op.publish_one(store, {"github": target(gh)}, "pub-2", lease_seconds=30)
    assert second == {"action": "IDLE"}                                                            # ninguem reconcilia enquanto o POST pode aparecer
    release.set()
    t1.join(10)
    assert results["first"]["action"] == "SENT" and len(gh.posts()) == 1 and len(gh.reviews) == 1


def test_a_target_without_a_send_ceiling_or_atomic_idempotency_is_refused_before_any_send(tmp_path):
    store = EventStore(tmp_path / "events.db")
    queue(store, "k1")
    sent = []

    class Bare:
        def find(self, entry_):
            return None

        def send(self, entry_):
            sent.append(entry_)
            return "x"
    res = op.publish_one(store, {"github": Bare()}, "pub-1", lease_seconds=30)
    assert res["action"] == "FAILED" and "send_timeout_s" in res["reason"] and sent == []


def disposable(**over):
    base = {"state": "open", "draft": True, "body": f"prova descartavel\n{gt.DISPOSABLE_MARKER}", "changed_files": 0,
            "head": {"sha": SHA}, "user": {"login": EXECUTOR}}
    return {**base, **over}


def test_a_verifiably_disposable_pr_passes_the_e2e_guard():
    assert gt.require_disposable_pr(disposable(), REVIEWER) == (SHA, EXECUTOR)


@pytest.mark.parametrize("over,why", [({"body": "um draft comum"}, "marcador"), ({"body": None}, "marcador"), ({"changed_files": 3}, "altera"),
                                      ({"changed_files": None}, "altera"), ({"draft": False}, "draft"), ({"state": "closed"}, "draft"),
                                      ({"user": {"login": REVIEWER}}, "autor"), ({"head": {"sha": "zz"}}, "HEAD")])
def test_an_ordinary_or_non_empty_pr_is_refused_by_the_e2e_guard(over, why):
    with pytest.raises(gt.NotDisposable, match=why):
        gt.require_disposable_pr(disposable(**over), REVIEWER)


def test_the_e2e_guard_raises_instead_of_asserting_so_python_dash_o_cannot_remove_it():
    import subprocess
    import sys
    code = ("from tools.orchestration import github_review_target as gt\n"
            "try:\n    gt.require_disposable_pr({'state': 'open', 'draft': True, 'body': 'comum', 'changed_files': 0, 'head': {'sha': 'a'*40},"
            " 'user': {'login': 'x'}}, 'r')\nexcept gt.NotDisposable:\n    print('RECUSADO')\n")
    r = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True, cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    assert r.stdout.strip() == "RECUSADO", r.stderr[-400:]


def test_the_e2e_script_uses_the_guard_and_no_assert():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "artifacts/review/fp060/m2_outbox/2026-11-15_github_disposable_pr/e2e_outbox_github.py").read_text(encoding="utf-8")
    assert "gt.require_disposable_pr(pr, target.reviewer)" in src and "\nassert " not in src
    assert src.index("require_disposable_pr(") < src.index("store.complete(")                    # a guarda vem ANTES de existir entrada no outbox


# -- revisao do Codex (#619, af3a7c54): o review achado pelo marcador precisa ser do HEAD e do veredito da entrada ------------------------------------------
@pytest.mark.parametrize("override", [{"commit_id": "c" * 40}, {"state": "APPROVED"}, {"state": "COMMENTED"}])
def test_a_marked_review_with_another_commit_or_verdict_is_never_reconciled(override):
    gh = FakeGitHub()
    t = target(gh)
    t.send(entry("k1"))
    gh.reviews[0].update(override)
    with pytest.raises(TargetError, match="outro efeito"):
        t.find(entry("k1"))


def test_the_publisher_gives_no_ack_and_no_second_post_for_a_marked_review_with_another_effect(tmp_path):
    store = EventStore(tmp_path / "events.db")
    gh = FakeGitHub()
    queue(store, "k1")
    target(gh).send(entry("k1"))
    gh.reviews[0]["commit_id"] = "c" * 40
    posts = len(gh.posts())
    res = op.publish_one(store, {"github": target(gh)}, "pub-1", lease_seconds=30)
    assert res["action"] == "FAILED" and "outro efeito" in res["reason"] and len(gh.posts()) == posts
