"""Roteamento kind:variant-vision-drain no NOC dispatcher (fecha o loop do
night_feeder). Hermetico: mocka ledger (lista em memoria), _run (subprocess) e
WT_PARENT/VARIANT_OUT_ROOT; NAO toca git real, worktree real, o :8765 nem a
fila NOC de producao."""
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
    nd.dispatch_variant_vision_drain(task)
    return holder["worker"]


def test_router_routes_variant_vision_drain_hyphen_exact(monkeypatch, sandbox):
    calls: list = []

    def spy_dispatch(task, dry_run=False, run_worker=nd._run_worker):
        calls.append({"task": task, "run_worker": run_worker})
        return {"task_id": task.get("id"), "status": "COMMITTED"}

    monkeypatch.setattr(nd, "dispatch", spy_dispatch)
    task = {"id": "VD1", "title": "drain v1", "safe": True,
            "kind": "variant-vision-drain", "plant": "planta_74",
            "variant_id": "planta_74__v1"}
    res = nd.dispatch_by_kind(task)
    assert res["status"] == "COMMITTED"
    assert len(calls) == 1
    assert calls[0]["run_worker"] is not nd._run_worker  # seam com worker proprio
    assert task["verify_file"] == "artifacts/variant_sweep/planta_74/corpus.jsonl"


def test_router_underscore_kind_falls_through_to_claude(monkeypatch, sandbox):
    # 'variant_vision_drain' (underscore) NAO e' o kind da spec: cai no
    # fallthrough claude (run_worker DEFAULT) — mesma pinagem anti-typo do
    # precedente variant-sweep
    calls: list = []

    def spy_dispatch(task, dry_run=False, run_worker=nd._run_worker):
        calls.append({"run_worker": run_worker})
        return {"task_id": task.get("id"), "status": "COMMITTED"}

    monkeypatch.setattr(nd, "dispatch", spy_dispatch)
    task = {"id": "VD2", "kind": "variant_vision_drain", "safe": True}
    nd.dispatch_by_kind(task)
    assert len(calls) == 1
    assert calls[0]["run_worker"] is nd._run_worker
    assert "verify_file" not in task


def test_worker_runs_ask_vision_only_for_this_variant(monkeypatch, sandbox,
                                                       tmp_path):
    out = nd.VARIANT_OUT_ROOT / "planta_74"
    out.mkdir(parents=True)
    (out / "corpus.jsonl").write_text('{"variant_id": "v1"}\n', encoding="utf-8")
    (out / "contact_sheet.png").write_bytes(b"\x89PNG fake")
    vdir = out / "planta_74__baseline__warm_compact__L0"
    vdir.mkdir()
    (vdir / "iso.png").write_bytes(b"\x89PNG fake iso")

    cmds: list = []

    def fake_run(cmd, cwd=None, timeout=120):
        cmds.append({"cmd": list(cmd), "cwd": cwd})
        return 0, "", ""

    monkeypatch.setattr(nd, "_run", fake_run)
    task = {"id": "VD3", "kind": "variant-vision-drain", "plant": "planta_74",
            "variant_id": "planta_74__baseline__warm_compact__L0"}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-vd3"
    wt.mkdir()
    rc, _, _ = worker(task, wt)
    assert rc == 0
    assert len(cmds) == 1
    cmd = cmds[0]["cmd"]
    assert cmd[cmd.index("-m") + 1] == "tools.variant_sweep"
    assert "--ask-vision" in cmd
    assert cmd[cmd.index("--only") + 1] == "planta_74__baseline__warm_compact__L0"
    assert "--dry-run" not in cmd   # drain PRECISA da chamada real ao painel
    # mesmo DESVIO do variant-sweep: cwd = arvore do DISPATCHER
    assert Path(str(cmds[0]["cwd"])) == nd.REPO_ROOT
    dest = wt / "artifacts" / "variant_sweep" / "planta_74"
    assert (dest / "corpus.jsonl").is_file()
    assert (dest / "planta_74__baseline__warm_compact__L0" / "iso.png").is_file()


def test_worker_missing_variant_id_fails_without_running_subprocess(
        monkeypatch, sandbox, tmp_path):
    cmds: list = []
    monkeypatch.setattr(nd, "_run",
                        lambda cmd, cwd=None, timeout=120: cmds.append(cmd) or (0, "", ""))
    task = {"id": "VD4", "kind": "variant-vision-drain", "plant": "planta_74"}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-vd4"
    wt.mkdir()
    rc, _, err = worker(task, wt)
    assert rc == 1
    assert "variant_id" in err
    assert cmds == []                 # nunca gasta subprocess sem saber o que drenar


def test_worker_timeout_becomes_rc1_not_exception(monkeypatch, sandbox, tmp_path):
    # TimeoutExpired NAO pode propagar: viraria linha de ledger sem status e a
    # task re-dispararia pra sempre (paridade com correction_cycle/variant-sweep)
    def hanging_run(cmd, cwd=None, timeout=120):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(nd, "_run", hanging_run)
    task = {"id": "VD5", "kind": "variant-vision-drain", "plant": "planta_74",
            "variant_id": "v1"}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-vd5"
    wt.mkdir()
    rc, _, err = worker(task, wt)
    assert rc == 1
    assert "TimeoutExpired" in err
    assert not (wt / "artifacts").exists()   # falha nao copia evidencia


def test_worker_failure_rc_propagates_without_copy(monkeypatch, sandbox, tmp_path):
    monkeypatch.setattr(nd, "_run",
                        lambda cmd, cwd=None, timeout=120: (1, "", "boom"))
    task = {"id": "VD6", "kind": "variant-vision-drain", "plant": "planta_74",
            "variant_id": "v1"}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-vd6"
    wt.mkdir()
    rc, _, err = worker(task, wt)
    assert rc == 1
    assert not (wt / "artifacts").exists()


def test_verify_file_setdefault_respects_existing_value(monkeypatch, sandbox):
    monkeypatch.setattr(nd, "dispatch",
                        lambda t, dry_run=False, run_worker=None:
                        {"status": "SPY"})
    task = {"id": "VD7", "kind": "variant-vision-drain", "plant": "planta_74",
            "variant_id": "v1", "verify_file": "artifacts/custom/check.jsonl"}
    nd.dispatch_variant_vision_drain(task)
    assert task["verify_file"] == "artifacts/custom/check.jsonl"


def test_ledger_single_entry_with_honest_kind(monkeypatch, sandbox, tmp_path):
    # rota SKIPPED_WT_EXISTS exercita o dispatch() REAL sem git (wt pre-
    # existente): 1 linha no ledger com o kind honesto 'variant-vision-drain'
    wt_parent = tmp_path / "wts"
    (wt_parent / "wt-noc-vd8").mkdir(parents=True)
    monkeypatch.setattr(nd, "WT_PARENT", wt_parent)
    task = {"id": "VD8", "title": "drain", "kind": "variant-vision-drain",
            "plant": "planta_74", "variant_id": "v1"}
    res = nd.dispatch_by_kind(task)
    assert res["status"] == "SKIPPED_WT_EXISTS"
    assert len(sandbox) == 1
    assert sandbox[0]["kind"] == "variant-vision-drain"
