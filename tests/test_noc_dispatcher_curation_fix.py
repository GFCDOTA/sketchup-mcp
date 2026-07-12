"""kind:curation_fix — laço autônomo de curadoria: UMA sessão Claude (--resume)
num worktree PERSISTENTE. Hermético: mocka _git (sem git real), subprocess, ledger
e o arquivo de sessão (tmp); NÃO toca git/worktree real, o :8765 nem a fila NOC."""
from __future__ import annotations

import types
from pathlib import Path

import pytest

from tools.claude_bridge import noc_dispatcher as nd


# ── roteamento ────────────────────────────────────────────────────────────────
def test_router_routes_curation_fix(monkeypatch):
    calls: list = []
    monkeypatch.setattr(nd, "dispatch_curation_fix",
                        lambda task, dry_run=False: calls.append(task) or {"status": "COMMITTED"})
    res = nd.dispatch_by_kind({"id": "CR-1", "kind": "curation_fix"})
    assert res["status"] == "COMMITTED" and len(calls) == 1


# ── _parse_session_id (puro) ──────────────────────────────────────────────────
def test_parse_session_id():
    assert nd._parse_session_id('{"session_id":"abc-123","result":"ok"}') == "abc-123"
    assert nd._parse_session_id("") is None
    assert nd._parse_session_id("not json") is None
    assert nd._parse_session_id('{"result":"ok"}') is None      # sem session_id
    assert nd._parse_session_id('{"session_id":""}') is None    # vazio


# ── _curation_fix_prompt (puro) ───────────────────────────────────────────────
def test_curation_fix_prompt_carries_gpt_critique():
    task = {"variant_id": "planta_74__x__y__L0", "gpt_nota": 3,
            "gpt_porque": "luz estourada", "gpt_caminho": "1) baixa a exposição"}
    p = nd._curation_fix_prompt(task, Path("/wt"))
    assert "planta_74__x__y__L0" in p and "3/10" in p
    assert "luz estourada" in p and "baixa a exposição" in p
    assert "NAO invente" in p and "push" in p                   # rails no prompt
    assert "LIMITACAO SISTEMICA" in p                           # escape honesto do shell


# ── sessão persistida ─────────────────────────────────────────────────────────
def test_session_file_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(nd, "CURATION_FIX_SESSION", tmp_path / "curation_fix.session")
    monkeypatch.setattr(nd, "NOC_DIR", tmp_path)
    assert nd._read_fix_session() is None
    nd._write_fix_session("sess-xyz")
    assert nd._read_fix_session() == "sess-xyz"


# ── _run_curation_fix_worker: --resume + --output-format json + captura sessão ──
def _fake_proc(rc=0, out="", err=""):
    return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


def test_worker_first_run_no_resume_captures_session(tmp_path, monkeypatch):
    monkeypatch.setattr(nd, "CURATION_FIX_SESSION", tmp_path / "s.session")
    monkeypatch.setattr(nd, "NOC_DIR", tmp_path)
    monkeypatch.setattr(nd, "_worker_env", lambda: {})
    monkeypatch.setattr(nd, "_claude_bin", lambda: "claude")
    seen: list = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return _fake_proc(out='{"session_id":"new-sess"}')

    monkeypatch.setattr(nd.subprocess, "run", fake_run)
    rc, _, _ = nd._run_curation_fix_worker({"variant_id": "v", "gpt_caminho": "x"}, tmp_path)
    assert rc == 0
    cmd = seen[0] if isinstance(seen[0], str) else " ".join(seen[0])
    assert "--output-format json" in cmd and "--resume" not in cmd  # 1a vez: sem resume
    assert nd._read_fix_session() == "new-sess"                     # sessão capturada


def test_worker_second_run_resumes_saved_session(tmp_path, monkeypatch):
    monkeypatch.setattr(nd, "CURATION_FIX_SESSION", tmp_path / "s.session")
    monkeypatch.setattr(nd, "NOC_DIR", tmp_path)
    monkeypatch.setattr(nd, "_worker_env", lambda: {})
    monkeypatch.setattr(nd, "_claude_bin", lambda: "claude")
    (tmp_path / "s.session").write_text("prev-sess", "utf-8")
    seen: list = []
    monkeypatch.setattr(nd.subprocess, "run",
                        lambda cmd, **kw: (seen.append(cmd), _fake_proc(out='{"session_id":"prev-sess"}'))[1])
    nd._run_curation_fix_worker({"variant_id": "v"}, tmp_path)
    cmd = seen[0] if isinstance(seen[0], str) else " ".join(seen[0])
    assert "--resume prev-sess" in cmd                              # reusa a MESMA sessão


def test_worker_retries_fresh_when_resume_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(nd, "CURATION_FIX_SESSION", tmp_path / "s.session")
    monkeypatch.setattr(nd, "NOC_DIR", tmp_path)
    monkeypatch.setattr(nd, "_worker_env", lambda: {})
    monkeypatch.setattr(nd, "_claude_bin", lambda: "claude")
    (tmp_path / "s.session").write_text("gone-sess", "utf-8")
    calls: list = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if len(calls) == 1:  # 1º com --resume falha: sessão sumiu
            return _fake_proc(rc=1, err="No conversation found with session ID: gone-sess")
        return _fake_proc(out='{"session_id":"fresh-sess"}')       # 2º sem resume

    monkeypatch.setattr(nd.subprocess, "run", fake_run)
    rc, _, _ = nd._run_curation_fix_worker({"variant_id": "v"}, tmp_path)
    assert rc == 0 and len(calls) == 2
    assert nd._read_fix_session() == "fresh-sess"


# ── dispatch_curation_fix: worktree PERSISTENTE + roteamento de status ─────────
class _FakeGit:
    """Fake de _git: registra chamadas, responde por subcomando."""
    def __init__(self, porcelain="M tools/x.py"):
        self.calls: list = []
        self.porcelain = porcelain

    def __call__(self, args, cwd=None, timeout=None):
        self.calls.append(list(args))
        if args[:1] == ["status"]:
            return 0, self.porcelain, ""
        return 0, "", ""

    def ran(self, *sub):
        return any(c[:len(sub)] == list(sub) for c in self.calls)


@pytest.fixture
def fixflow(tmp_path, monkeypatch):
    wt = tmp_path / "wt-curation-fix"
    wt.mkdir()                                   # existe → pula criação do worktree
    monkeypatch.setattr(nd, "CURATION_FIX_WT", wt)
    rows: list = []
    monkeypatch.setattr(nd, "ledger_append", rows.append)
    monkeypatch.setattr(nd, "_emit_appearance_gallery_item", lambda t, w: {"variant_id": "gi"})
    monkeypatch.setattr(nd, "_read_fix_session", lambda: "sess")
    return {"wt": wt, "rows": rows, "monkeypatch": monkeypatch}


def test_dispatch_appearance_routes_visual_review_and_keeps_worktree(fixflow):
    mp = fixflow["monkeypatch"]
    git = _FakeGit()
    mp.setattr(nd, "_git", git)
    mp.setattr(nd, "_appearance_changed", lambda wt: True)
    res = nd.dispatch_curation_fix({"id": "CR-fix-1", "title": "t"},
                                   run_worker=lambda t, w: (0, "ok", ""))
    assert res["status"] == "VISUAL_REVIEW_QUEUED"
    assert res["gallery_item"] == "gi"
    assert not git.ran("worktree", "remove")     # PERSISTENTE: nunca remove
    assert fixflow["rows"] and fixflow["rows"][-1]["status"] == "VISUAL_REVIEW_QUEUED"


def test_dispatch_deterministic_commits(fixflow):
    mp = fixflow["monkeypatch"]
    mp.setattr(nd, "_git", _FakeGit())
    mp.setattr(nd, "_appearance_changed", lambda wt: False)
    res = nd.dispatch_curation_fix({"id": "CR-fix-2", "title": "t"},
                                   run_worker=lambda t, w: (0, "ok", ""))
    assert res["status"] == "COMMITTED"


def test_dispatch_no_change_is_noop(fixflow):
    mp = fixflow["monkeypatch"]
    mp.setattr(nd, "_git", _FakeGit(porcelain=""))   # worker não mexeu em nada
    mp.setattr(nd, "_appearance_changed", lambda wt: False)
    res = nd.dispatch_curation_fix({"id": "CR-fix-3", "title": "t"},
                                   run_worker=lambda t, w: (0, "", ""))
    assert res["status"] == "NOOP"


def test_dispatch_dry_run_no_worker(fixflow):
    mp = fixflow["monkeypatch"]
    mp.setattr(nd, "_git", _FakeGit())
    called = []
    res = nd.dispatch_curation_fix({"id": "CR-fix-4", "title": "t"}, dry_run=True,
                                   run_worker=lambda t, w: called.append(1))
    assert res["status"] == "DRY_RUN" and called == []
