"""FP-060 (#646): barreiras da entrega (`tools/orchestration/executor_delivery.py`) ANTES de qualquer efeito, com o `git` injetado (sem binario, sem rede)."""
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


def test_no_revalidation_publishes_nothing_and_runs_no_git(tmp_path):
    g = Git()
    out = d.deliver(Path(tmp_path), "b", BASE, "py", {}, run=g, check=lambda *a, **k: (True, ""), revalidate=None, message="feat: x")
    assert out[0] == "STALE" and g.calls == []


def test_a_denied_revalidation_stops_before_any_git(tmp_path):
    g = Git()
    out = d.deliver(Path(tmp_path), "b", BASE, "py", {}, run=g, check=lambda *a, **k: (True, ""), revalidate=lambda: (False, "label removida"), message="feat: x")
    assert out == ("STALE", "antes de stagear: label removida") and g.calls == []


def test_a_moved_remote_head_stops_before_staging(tmp_path):
    g = Git(remote="b" * 40)
    out = d.deliver(Path(tmp_path), "b", BASE, "py", {}, run=g, check=lambda *a, **k: (True, ""), revalidate=lambda: (True, "ok"), message="feat: x")
    assert out[0] == "STALE" and [c[0] for c in g.calls] == ["ls-remote"]
