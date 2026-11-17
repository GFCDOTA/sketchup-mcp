"""FP-060 (#589/#652): entrega do executor (`tools/orchestration/executor_delivery.py`) — as barreiras ANTES de qualquer efeito, com o `git` injetado
(sem binario `git`, sem rede): sem revalidacao nada e publicado; revalidacao negada ou HEAD remoto diferente param antes de stagear; recusa estruturada do push."""
from __future__ import annotations

from pathlib import Path

from tools.orchestration import executor_delivery as d

BASE = "a" * 40


class Git:
    def __init__(self, remote=BASE):
        self.remote, self.calls = remote, []

    def __call__(self, argv, cwd):
        self.calls.append(argv)
        if argv[:1] == ["ls-remote"]:
            return (0, f"{self.remote}\trefs/heads/b\n") if self.remote else (2, "")
        raise AssertionError(f"git inesperado antes da barreira: {argv}")


def test_without_a_revalidation_nothing_is_published_and_git_is_never_called(tmp_path):
    g = Git()
    out = d.deliver(Path(tmp_path), "b", BASE, "py", {}, run=g, check=lambda *a, **k: (True, ""), revalidate=None)
    assert out[0] == "STALE" and "fail-closed" in out[1] and g.calls == []


def test_a_denied_revalidation_stops_before_any_git_command(tmp_path):
    g = Git()
    out = d.deliver(Path(tmp_path), "b", BASE, "py", {}, run=g, check=lambda *a, **k: (True, ""), revalidate=lambda: (False, "label removida"))
    assert out == ("STALE", "antes de stagear: label removida") and g.calls == []


def test_a_remote_head_that_moved_stops_before_staging(tmp_path):
    g = Git(remote="b" * 40)
    out = d.deliver(Path(tmp_path), "b", BASE, "py", {}, run=g, check=lambda *a, **k: (True, ""), revalidate=lambda: (True, "ok"))
    assert out[0] == "STALE" and "HEAD remoto" in out[1] and [c[0] for c in g.calls] == ["ls-remote"]


def test_remote_head_reads_the_exact_branch_ref():
    g = Git()
    assert d.remote_head(Path("."), "feat/x", g) == BASE and g.calls[0] == ["ls-remote", "--exit-code", "origin", "refs/heads/feat/x"]
    assert d.remote_head(Path("."), "feat/x", Git(remote=None)) is None


def test_only_the_structured_porcelain_line_counts_as_a_definitive_push_refusal():
    assert d.DEFINITIVE_REFUSAL.search("!\trefs/heads/b:refs/heads/b\t[rejected] (non-fast-forward)\n")
    assert d.DEFINITIVE_REFUSAL.search("!\trefs/heads/b:refs/heads/b\t[remote rejected] (hook)\n")
    assert not d.DEFINITIVE_REFUSAL.search("remote: this push was rejected by policy\n")      # palavra solta na saida remota nao e recusa
