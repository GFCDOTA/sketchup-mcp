"""Roteamento kind:variant-sweep no NOC dispatcher (FP-034). Hermetico: mocka
ledger (lista em memoria), _run (subprocess) e WT_PARENT/VARIANT_OUT_ROOT; NAO
toca git real, worktree real, o :8765 nem a fila NOC de producao."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.claude_bridge import noc_dispatcher as nd


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """Isola ledger (captura em lista) e o out-root do sweep (tmp)."""
    rows: list = []
    monkeypatch.setattr(nd, "ledger_append", rows.append)
    monkeypatch.setattr(nd, "VARIANT_OUT_ROOT", tmp_path / "noc_variant_sweep")
    return rows


def _capture_worker(monkeypatch, task):
    """Captura a closure _worker injetada em dispatch() via o seam."""
    holder: dict = {}

    def spy_dispatch(t, dry_run=False, run_worker=None):
        holder["task"], holder["worker"] = t, run_worker
        return {"task_id": t.get("id"), "status": "SPY"}

    monkeypatch.setattr(nd, "dispatch", spy_dispatch)
    nd.dispatch_variant_sweep(task)
    return holder["worker"]


def test_router_routes_variant_sweep_hyphen_exact(monkeypatch, sandbox):
    calls: list = []

    def spy_dispatch(task, dry_run=False, run_worker=nd._run_worker):
        calls.append({"task": task, "run_worker": run_worker})
        return {"task_id": task.get("id"), "status": "COMMITTED"}

    monkeypatch.setattr(nd, "dispatch", spy_dispatch)
    task = {"id": "VS1", "title": "sweep planta_74", "safe": True,
            "kind": "variant-sweep", "appearance": True}
    res = nd.dispatch_by_kind(task)
    assert res["status"] == "COMMITTED"
    assert len(calls) == 1
    assert calls[0]["run_worker"] is not nd._run_worker  # seam com worker proprio
    assert task["verify_file"] == "artifacts/variant_sweep/planta_74/corpus.jsonl"


def test_router_underscore_kind_falls_through_to_claude(monkeypatch, sandbox):
    # 'variant_sweep' (underscore) NAO e' o kind da spec: cai no fallthrough
    # claude (dispatch com o run_worker DEFAULT) — pinado pra typo nao virar
    # `claude -p` silencioso em producao sem ninguem notar no teste
    calls: list = []

    def spy_dispatch(task, dry_run=False, run_worker=nd._run_worker):
        calls.append({"run_worker": run_worker})
        return {"task_id": task.get("id"), "status": "COMMITTED"}

    monkeypatch.setattr(nd, "dispatch", spy_dispatch)
    task = {"id": "VS2", "kind": "variant_sweep", "safe": True}
    nd.dispatch_by_kind(task)
    assert len(calls) == 1
    assert calls[0]["run_worker"] is nd._run_worker
    assert "verify_file" not in task


def test_worker_runs_sweep_from_dispatcher_tree_and_copies_evidence(
        monkeypatch, sandbox, tmp_path):
    out = nd.VARIANT_OUT_ROOT / "planta_74"
    out.mkdir(parents=True)
    (out / "corpus.jsonl").write_text('{"variant_id": "v1"}\n', encoding="utf-8")
    (out / "contact_sheet.png").write_bytes(b"\x89PNG fake")
    v1 = out / "planta_74__baseline__warm_compact__L0"
    v1.mkdir()
    (v1 / "iso.png").write_bytes(b"\x89PNG fake iso")

    cmds: list = []

    def fake_run(cmd, cwd=None, timeout=120):
        cmds.append({"cmd": list(cmd), "cwd": cwd})
        return 0, "", ""

    monkeypatch.setattr(nd, "_run", fake_run)
    task = {"id": "VS3", "kind": "variant-sweep", "n": 4}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-vs3"
    wt.mkdir()
    rc, _, _ = worker(task, wt)
    assert rc == 0
    assert len(cmds) == 1
    cmd = cmds[0]["cmd"]
    assert cmd[cmd.index("-m") + 1] == "tools.variant_sweep"
    assert cmd[cmd.index("--n") + 1] == "4"
    assert "--dry-run" in cmd
    # DESVIO pinado: cwd = arvore do DISPATCHER (o wt off origin/develop nao
    # tem o codigo novo pre-merge; o sweep so PRODUZ evidencia)
    assert Path(str(cmds[0]["cwd"])) == nd.REPO_ROOT
    dest = wt / "artifacts" / "variant_sweep" / "planta_74"
    assert (dest / "corpus.jsonl").is_file()
    # >=1 .png copiado -> _appearance_changed dispara VISUAL_REVIEW_QUEUED
    pngs = list(dest.rglob("*.png"))
    assert len(pngs) >= 1


def test_worker_timeout_becomes_rc1_not_exception(monkeypatch, sandbox,
                                                  tmp_path):
    # TimeoutExpired NAO pode propagar: viraria linha de ledger sem status e a
    # task re-dispararia pra sempre (paridade com o correction_cycle)
    def hanging_run(cmd, cwd=None, timeout=120):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(nd, "_run", hanging_run)
    task = {"id": "VS4", "kind": "variant-sweep"}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-vs4"
    wt.mkdir()
    rc, _, err = worker(task, wt)
    assert rc == 1
    assert "TimeoutExpired" in err
    assert not (wt / "artifacts").exists()   # falha nao copia evidencia


def test_worker_failure_rc_propagates_without_copy(monkeypatch, sandbox,
                                                   tmp_path):
    monkeypatch.setattr(nd, "_run",
                        lambda cmd, cwd=None, timeout=120: (1, "", "boom"))
    task = {"id": "VS5", "kind": "variant-sweep"}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-vs5"
    wt.mkdir()
    rc, _, err = worker(task, wt)
    assert rc == 1
    assert not (wt / "artifacts").exists()


def test_verify_file_setdefault_respects_existing_value(monkeypatch, sandbox):
    monkeypatch.setattr(nd, "dispatch",
                        lambda t, dry_run=False, run_worker=None:
                        {"status": "SPY"})
    task = {"id": "VS6", "kind": "variant-sweep",
            "verify_file": "artifacts/custom/check.jsonl"}
    nd.dispatch_variant_sweep(task)
    assert task["verify_file"] == "artifacts/custom/check.jsonl"


def test_ledger_single_entry_with_honest_kind(monkeypatch, sandbox, tmp_path):
    # rota SKIPPED_WT_EXISTS exercita o dispatch() REAL sem git (wt pre-
    # existente): 1 linha no ledger com o kind honesto 'variant-sweep'
    wt_parent = tmp_path / "wts"
    (wt_parent / "wt-noc-vs7").mkdir(parents=True)
    monkeypatch.setattr(nd, "WT_PARENT", wt_parent)
    task = {"id": "VS7", "title": "sweep", "kind": "variant-sweep"}
    res = nd.dispatch_by_kind(task)
    assert res["status"] == "SKIPPED_WT_EXISTS"
    assert len(sandbox) == 1
    assert sandbox[0]["kind"] == "variant-sweep"
