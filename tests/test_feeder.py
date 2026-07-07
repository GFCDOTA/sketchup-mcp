"""feeder — alimentador da fila NOC. Hermetico: paths TODOS injetados
(tmp), clock injetado (--now/--today); NAO toca a fila NOC de producao, o
git nem o :8765."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import feeder as nf
from tools.jsonl_io import append_jsonl, read_jsonl

NOW = 1_783_118_000.0
TODAY = "20260703"


@pytest.fixture
def env(tmp_path):
    """Arvore minima do motor + runs-root, tudo em tmp."""
    engine = tmp_path / "engine"
    (engine / ".ai_bridge" / "noc").mkdir(parents=True)
    (engine / ".ai_bridge" / "audit").mkdir(parents=True)
    runs = tmp_path / "runs"
    (runs / "noc_variant_sweep").mkdir(parents=True)
    (runs / "noc_correction").mkdir(parents=True)
    return {
        "engine": engine,
        "runs": runs,
        "queue": engine / ".ai_bridge" / "noc" / "queue.jsonl",
        "ledger": engine / ".ai_bridge" / "noc" / "actions.jsonl",
        "audit": engine / ".ai_bridge" / "audit" / "audit.jsonl",
    }


def _audit(env, age_sec: float) -> None:
    append_jsonl(env["audit"], [{"t": NOW - age_sec, "kind": "consult"}])


def _run(env, capsys, *extra) -> dict:
    argv = ["--today", TODAY, "--now", str(NOW),
            "--engine-root", str(env["engine"]),
            "--runs-root", str(env["runs"]), *extra]
    rc = nf.main(argv)
    assert rc == 0                       # exit 0 SEMPRE (sem sinal nao e erro)
    return json.loads(capsys.readouterr().out)


def test_idle_gate_plans_corr_and_sweep_dry_run_writes_nothing(env, capsys):
    _audit(env, age_sec=7200)            # 2h ocioso > 30min default
    rep = _run(env, capsys, "--dry-run")
    ids = [t["id"] for t in rep["plan"]]
    assert ids == [f"NF-{TODAY}-corr-planta_74", f"NF-{TODAY}-sweep-planta_74"]
    assert rep["applied"] == 0
    assert not env["queue"].exists()     # dry-run: fila intocada


def test_once_appends_real_queue_schema(env, capsys):
    _audit(env, age_sec=7200)
    rep = _run(env, capsys, "--once")
    assert rep["applied"] == 2
    rows = read_jsonl(env["queue"])
    corr = next(r for r in rows if r["kind"] == "correction_cycle")
    sweep = next(r for r in rows if r["kind"] == "variant-sweep")  # hifen exato
    assert corr["fixture"] == "planta_74" and corr["safe"] is True
    assert corr["max_cycles"] == 1
    assert sweep["plant"] == "planta_74" and sweep["safe"] is True
    assert sweep["n"] == 8 and sweep["appearance"] is True
    assert all(r["id"].startswith(f"NF-{TODAY}-") for r in rows)


def test_idempotent_second_run_same_day_zero_new(env, capsys):
    _audit(env, age_sec=7200)
    _run(env, capsys, "--once")
    rep2 = _run(env, capsys, "--once")
    assert rep2["applied"] == 0
    assert rep2["plan"] == []
    assert len(read_jsonl(env["queue"])) == 2       # nada duplicado
    assert all("cap 1/dia" in s["reason"] for s in rep2["skipped"])


def test_dedup_kind_fixture_already_pending_in_queue(env, capsys):
    _audit(env, age_sec=7200)
    append_jsonl(env["queue"], [{"id": "M9", "kind": "correction_cycle",
                                 "fixture": "planta_74", "safe": True}])
    rep = _run(env, capsys, "--once")
    kinds = [t["kind"] for t in rep["plan"]]
    assert kinds == ["variant-sweep"]               # corr dedupado, sweep entra
    assert any("dedup" in s["reason"] for s in rep["skipped"])


def test_terminal_manual_task_does_not_block_daily_cap(env, capsys):
    # M9 ja COMMITTED no ledger -> NAO esta mais pendente -> feeder pode planejar
    _audit(env, age_sec=7200)
    append_jsonl(env["queue"], [{"id": "M9", "kind": "correction_cycle",
                                 "fixture": "planta_74", "safe": True}])
    append_jsonl(env["ledger"], [{"task_id": "M9", "status": "COMMITTED"}])
    rep = _run(env, capsys, "--dry-run")
    assert f"NF-{TODAY}-corr-planta_74" in [t["id"] for t in rep["plan"]]


def test_active_gate_skips_enqueue_but_reports_signals(env, capsys):
    _audit(env, age_sec=60)              # gate falou ha 1min -> ATIVO
    rep = _run(env, capsys, "--once")
    assert rep["plan"] == [] and rep["applied"] == 0
    assert rep["signals"]["gate"]["idle"] is False
    assert all("gate ATIVO" in s["reason"] for s in rep["skipped"])
    assert not env["queue"].exists()


def test_missing_audit_is_honest_idle(env, capsys):
    rep = _run(env, capsys, "--dry-run")            # sem audit.jsonl
    assert rep["signals"]["gate"]["last_t"] is None
    assert rep["signals"]["gate"]["idle"] is True   # gate que nunca falou = parado
    assert len(rep["plan"]) == 2


def test_vision_signals_lastwins_and_honest_limitations(env, capsys):
    _audit(env, age_sec=7200)
    # corpus mais recente: v1 supersedido (last-wins CANDIDATE), v2 pendente
    run_dir = env["runs"] / "noc_variant_sweep" / "s1"
    run_dir.mkdir()
    append_jsonl(run_dir / "corpus.jsonl", [
        {"variant_id": "v1", "verdict": "PENDING_VISION"},
        {"variant_id": "v1", "verdict": "CANDIDATE"},
        {"variant_id": "v2", "verdict": "PENDING_VISION"},
    ])
    # vision_requests: 2 pedidos, 1 ja consumido (identidade queue_key)
    from tools.jsonl_io import queue_key
    corr = env["runs"] / "noc_correction" / "planta_74"
    corr.mkdir()
    r1 = {"type": "wall_stub", "room": "sala", "evidence": "e1"}
    r2 = {"type": "door_gap", "room": "quarto", "evidence": "e2"}
    append_jsonl(corr / "vision_requests.jsonl", [r1, r2])
    append_jsonl(corr / "vision_consumed.jsonl",
                 [{"signature": list(queue_key(r1))}])
    rep = _run(env, capsys, "--dry-run")
    assert rep["signals"]["variant_pending_vision"]["variants"] == ["v2"]
    assert rep["signals"]["correction_pending_vision"] == {"planta_74": 1}
    # loop fechado: v2 PENDING_VISION agora ENFILEIRA um drain (nao fica so
    # em limitations) — a limitation que sobra e' a do correction_cycle, que
    # esta fatia nao mexeu
    ids = [t["id"] for t in rep["plan"]]
    assert f"NF-{TODAY}-visdrain-v2" in ids
    lims = " ".join(rep["limitations"])
    assert "BLOCKED_NEEDS_RENDER" in lims            # feeder nao fabrica render


def test_pending_vision_variant_enqueues_drain_task(env, capsys):
    _audit(env, age_sec=7200)
    run_dir = env["runs"] / "noc_variant_sweep" / "s1"
    run_dir.mkdir()
    append_jsonl(run_dir / "corpus.jsonl", [
        {"variant_id": "planta_74__v1", "verdict": "PENDING_VISION"},
    ])
    rep = _run(env, capsys, "--once")
    rows = read_jsonl(env["queue"])
    drain = next(r for r in rows if r["kind"] == "variant-vision-drain")
    assert drain["id"] == f"NF-{TODAY}-visdrain-planta_74__v1"
    assert drain["variant_id"] == "planta_74__v1"
    assert drain["plant"] == "planta_74" and drain["safe"] is True
    assert rep["applied"] == 3  # corr + sweep + 1 drain


def test_drain_cap_limits_tasks_per_cycle(env, capsys):
    _audit(env, age_sec=7200)
    run_dir = env["runs"] / "noc_variant_sweep" / "s1"
    run_dir.mkdir()
    append_jsonl(run_dir / "corpus.jsonl", [
        {"variant_id": f"v{i}", "verdict": "PENDING_VISION"} for i in range(5)
    ])
    rep = _run(env, capsys, "--dry-run", "--drain-cap", "2")
    drain_ids = [t["id"] for t in rep["plan"] if t["kind"] == "variant-vision-drain"]
    assert len(drain_ids) == 2                       # nunca as 5 de uma vez
    assert "so as primeiras 2" in " ".join(rep["limitations"])


def test_no_drain_flag_disables_vision_drain(env, capsys):
    _audit(env, age_sec=7200)
    run_dir = env["runs"] / "noc_variant_sweep" / "s1"
    run_dir.mkdir()
    append_jsonl(run_dir / "corpus.jsonl", [
        {"variant_id": "v1", "verdict": "PENDING_VISION"},
    ])
    rep = _run(env, capsys, "--dry-run", "--no-drain")
    assert [t["kind"] for t in rep["plan"]] == ["correction_cycle", "variant-sweep"]
    assert any("desligado por flag" in s["reason"] for s in rep["skipped"]
               if "visdrain" in s["what"] or "drain" in s["what"])


def test_drain_dedup_by_variant_id_not_plant(env, capsys):
    # 2 variantes PENDING_VISION do MESMO plant: uma ja pendente na fila (kind
    # variant-vision-drain, variant_id=v1) NAO pode bloquear v2 — dedup por
    # (kind, variant_id), nao por (kind, plant), senao v2 nunca entraria
    _audit(env, age_sec=7200)
    run_dir = env["runs"] / "noc_variant_sweep" / "s1"
    run_dir.mkdir()
    append_jsonl(run_dir / "corpus.jsonl", [
        {"variant_id": "v1", "verdict": "PENDING_VISION"},
        {"variant_id": "v2", "verdict": "PENDING_VISION"},
    ])
    append_jsonl(env["queue"], [{"id": "M9", "kind": "variant-vision-drain",
                                 "plant": "planta_74", "variant_id": "v1",
                                 "safe": True}])
    rep = _run(env, capsys, "--dry-run")
    drain_ids = {t["variant_id"] for t in rep["plan"]
                if t["kind"] == "variant-vision-drain"}
    assert drain_ids == {"v2"}                        # v1 dedupado, v2 entra


def test_no_sweep_flag_for_live_prova(env, capsys):
    _audit(env, age_sec=7200)
    rep = _run(env, capsys, "--once", "--no-sweep")
    assert [t["kind"] for t in rep["plan"]] == ["correction_cycle"]
    assert rep["applied"] == 1
    rows = read_jsonl(env["queue"])
    assert len(rows) == 1 and rows[0]["id"] == f"NF-{TODAY}-corr-planta_74"


def test_default_without_flags_is_dry_run(env, capsys):
    _audit(env, age_sec=7200)
    rep = _run(env, capsys)                          # nem --once nem --dry-run
    assert rep["applied"] == 0 and not env["queue"].exists()
    assert "dry-run" in rep["note"]


def test_terminal_statuses_stay_lockstep_with_dispatcher():
    # Lockstep ESTRUTURAL: feeder consome a MESMA constante que _terminal_ids()
    # do dispatcher (fonte unica — drift impossivel por construcao)…
    from tools.claude_bridge import noc_dispatcher as nd
    assert nf.TERMINAL is nd.TERMINAL_STATUSES
    # …e o PIN abaixo e' independente da definicao: se o dispatcher ganhar/
    # perder status terminal, ele FALHA e forca atualizacao consciente aqui.
    assert nd.TERMINAL_STATUSES == {
        "COMMITTED", "VISUAL_REVIEW_QUEUED", "NOOP", "VERIFY_FAILED",
        "LOCAL_LLM_DONE", "LOCAL_LLM_OFFLINE", "SKIPPED_PURPOSE_NOT_ALLOWED",
    }


def test_unsafe_parked_task_does_not_starve_daily_corr(env, capsys):
    # safe:false NUNCA e executada pelo pick_task e nunca ganha status terminal:
    # se contasse como pendente, starvaria o correction_cycle diario PRA SEMPRE
    # (fila e append-only). Pendente = elegibilidade real do dispatcher.
    _audit(env, age_sec=7200)
    append_jsonl(env["queue"], [{"id": "M9", "kind": "correction_cycle",
                                 "fixture": "planta_74", "safe": False}])
    rep = _run(env, capsys, "--dry-run")
    assert f"NF-{TODAY}-corr-planta_74" in [t["id"] for t in rep["plan"]]


def test_idless_task_still_counts_for_dedup(env, capsys):
    # task SEM id RODA no pick_task (None nunca entra em done) -> e' pendente
    # de verdade; o dedup kind+fixture tem que ve-la ou o feeder duplica o dia
    _audit(env, age_sec=7200)
    append_jsonl(env["queue"], [{"kind": "correction_cycle",
                                 "fixture": "planta_74", "safe": True}])
    rep = _run(env, capsys, "--dry-run")
    assert [t["kind"] for t in rep["plan"]] == ["variant-sweep"]
    assert any("dedup" in s["reason"] for s in rep["skipped"])
