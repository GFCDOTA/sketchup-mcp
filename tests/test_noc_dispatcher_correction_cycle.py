"""Roteamento kind:correction_cycle no NOC dispatcher (FP-033 slice 3).
Hermético: mocka ledger (lista em memória), _run (subprocess) e _git; NÃO toca
git real, worktree real, o :8765 nem a fila NOC de produção."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from tools.claude_bridge import noc_dispatcher as nd


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """Isola ledger (captura em lista) e o out-root do correction_loop (tmp)."""
    rows: list = []
    monkeypatch.setattr(nd, "ledger_append", rows.append)
    monkeypatch.setattr(nd, "CORRECTION_OUT_ROOT", tmp_path / "noc_correction")
    return rows


def _capture_worker(monkeypatch, task):
    """Captura a closure _worker injetada em dispatch() via o seam."""
    holder: dict = {}

    def spy_dispatch(t, dry_run=False, run_worker=None):
        holder["task"], holder["worker"] = t, run_worker
        return {"task_id": t.get("id"), "status": "SPY"}

    monkeypatch.setattr(nd, "dispatch", spy_dispatch)
    nd.dispatch_correction_cycle(task)
    return holder["worker"]


def test_dispatch_seam_default_unchanged():
    # trava o seam: o atuador vivo do caminho claude continua com _run_worker
    default = inspect.signature(nd.dispatch).parameters["run_worker"].default
    assert default is nd._run_worker


def test_router_routes_correction_cycle_via_dispatch_seam(monkeypatch, sandbox):
    calls: list = []

    def spy_dispatch(task, dry_run=False, run_worker=nd._run_worker):
        calls.append({"task": task, "dry_run": dry_run, "run_worker": run_worker})
        return {"task_id": task.get("id"), "status": "COMMITTED"}

    monkeypatch.setattr(nd, "dispatch", spy_dispatch)
    task = {"id": "C1", "title": "ciclo planta_74", "safe": True,
            "kind": "correction_cycle", "fixture": "planta_74"}
    res = nd.dispatch_by_kind(task)
    assert res["status"] == "COMMITTED"
    assert len(calls) == 1
    assert calls[0]["run_worker"] is not nd._run_worker
    assert task["verify_file"] == \
        "artifacts/correction_loop/planta_74/loop_result.json"


def test_ledger_single_entry_with_kind(monkeypatch, sandbox, tmp_path):
    # rota SKIPPED_WT_EXISTS exercita o dispatch() REAL sem git (wt pré-existente):
    # 1 linha no ledger, com o kind honesto (sem a linha dupla do fallback local_llm)
    wt_parent = tmp_path / "wts"
    (wt_parent / "wt-noc-c2").mkdir(parents=True)
    monkeypatch.setattr(nd, "WT_PARENT", wt_parent)
    task = {"id": "C2", "title": "ciclo", "kind": "correction_cycle",
            "fixture": "planta_74"}
    res = nd.dispatch_by_kind(task)
    assert res["status"] == "SKIPPED_WT_EXISTS"
    assert len(sandbox) == 1
    assert sandbox[0]["kind"] == "correction_cycle"


def test_worker_runs_consumer_then_loop_exit3_is_success(monkeypatch, sandbox,
                                                         tmp_path):
    out = nd.CORRECTION_OUT_ROOT / "planta_74"
    out.mkdir(parents=True)
    (out / "vision_requests.jsonl").write_text(
        json.dumps({"type": "wall_stub", "severity": "WARN",
                    "source": "deterministic", "evidence": "stub",
                    "route": "NEEDS_VISION",
                    "queued_as": "vision_requests"}) + "\n", encoding="utf-8")
    (out / "loop_result.json").write_text(
        '{"state": "PENDING_VISION"}\n', encoding="utf-8")
    (out / "consensus_candidate.json").write_text('{}\n', encoding="utf-8")

    cmds: list = []
    rc_by_module = {"tools.vision_queue_consumer": 0, "tools.correction_loop": 3}

    def fake_run(cmd, cwd=None, timeout=120):
        cmds.append({"cmd": list(cmd), "cwd": cwd})
        return rc_by_module[cmd[cmd.index("-m") + 1]], "", ""

    monkeypatch.setattr(nd, "_run", fake_run)
    task = {"id": "C3", "kind": "correction_cycle", "fixture": "planta_74"}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-c3"
    wt.mkdir()
    rc, _, _ = worker(task, wt)
    assert rc == 0                    # loop exit 3 = enfileirado, NÃO é falha
    mods = [c["cmd"][c["cmd"].index("-m") + 1] for c in cmds]
    assert mods == ["tools.vision_queue_consumer", "tools.correction_loop"]
    assert all(Path(str(c["cwd"])) == wt for c in cmds)
    loop_cmd = cmds[1]["cmd"]
    assert loop_cmd[loop_cmd.index("--max-cycles") + 1] == "1"
    dest = wt / "artifacts" / "correction_loop" / "planta_74"
    assert (dest / "loop_result.json").exists()
    assert (dest / "consensus_candidate.json").exists()


def test_worker_loop_exit1_is_failure(monkeypatch, sandbox, tmp_path):
    # sem fila de visão pendente -> consumer NÃO roda; loop STALL/RED (1) -> falha
    cmds: list = []

    def fake_run(cmd, cwd=None, timeout=120):
        cmds.append(list(cmd))
        return 1, "", "stall"

    monkeypatch.setattr(nd, "_run", fake_run)
    task = {"id": "C4", "kind": "correction_cycle", "fixture": "planta_74"}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-c4"
    wt.mkdir()
    rc, _, err = worker(task, wt)
    assert rc == 1
    assert len(cmds) == 1
    assert "tools.correction_loop" in cmds[0]
    assert not (wt / "artifacts").exists()        # falha não copia evidência


def test_consensus_candidate_filename_matches_appearance_heuristic(monkeypatch,
                                                                   tmp_path):
    # garante a rota VISUAL_REVIEW_QUEUED sem lógica nova: no worktree fresco a
    # candidata chega UNTRACKED num dir novo; sem -uall o git colapsa pra
    # `?? artifacts/correction_loop/` e o filename some — o check exige -uall e
    # a linha untracked REAL (`?? <path completo>`) tem que casar
    def fake_git(args, cwd=None, timeout=120):
        assert args[:3] == ["status", "--porcelain", "-uall"]
        return 0, "?? artifacts/correction_loop/planta_74/consensus_candidate.json\n", ""

    monkeypatch.setattr(nd, "_git", fake_git)
    assert nd._appearance_changed(tmp_path) is True


def test_appearance_check_would_miss_collapsed_untracked_dir(monkeypatch,
                                                             tmp_path):
    # regressão do bug: a saída COLAPSADA (sem -uall) não casa com padrão nenhum;
    # se alguém remover o -uall, o teste acima quebra e este documenta o porquê
    def fake_git(args, cwd=None, timeout=120):
        assert "-uall" in args
        return 0, "?? artifacts/correction_loop/\n", ""

    monkeypatch.setattr(nd, "_git", fake_git)
    assert nd._appearance_changed(tmp_path) is False


def test_worker_forwards_task_render_to_consumer(monkeypatch, sandbox, tmp_path):
    out = nd.CORRECTION_OUT_ROOT / "planta_74"
    out.mkdir(parents=True)
    (out / "vision_requests.jsonl").write_text('{"type": "wall_stub"}\n',
                                               encoding="utf-8")
    cmds: list = []

    def fake_run(cmd, cwd=None, timeout=120):
        cmds.append(list(cmd))
        return 0, "", ""

    monkeypatch.setattr(nd, "_run", fake_run)
    task = {"id": "C5", "kind": "correction_cycle", "fixture": "planta_74",
            "render": ["runs/render_top.png", "runs/render_iso.png"]}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-c5"
    wt.mkdir()
    worker(task, wt)
    consumer_cmd = cmds[0]
    assert "tools.vision_queue_consumer" in consumer_cmd
    renders = [consumer_cmd[i + 1] for i, tok in enumerate(consumer_cmd)
               if tok == "--render"]
    assert renders == ["runs/render_top.png", "runs/render_iso.png"]


def test_worker_timeout_becomes_rc1_not_exception(monkeypatch, sandbox,
                                                  tmp_path):
    # TimeoutExpired NÃO pode propagar: viraria linha de ledger sem status e a
    # task re-dispararia pra sempre (paridade com _run_worker)
    import subprocess

    def hanging_run(cmd, cwd=None, timeout=120):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(nd, "_run", hanging_run)
    task = {"id": "C6", "kind": "correction_cycle", "fixture": "planta_74"}
    worker = _capture_worker(monkeypatch, task)
    wt = tmp_path / "wt-noc-c6"
    wt.mkdir()
    rc, _, err = worker(task, wt)
    assert rc == 1
    assert "TimeoutExpired" in err
