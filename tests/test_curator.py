"""curator — o RUNNER que amarra o loop semi-autonomo numa passada. Hermetico:
os 3 passos sao injetados (mock) ou monkeypatchados; nenhum teste toca a fila
NOC de producao, o rag_freshness.db real, o Qdrant nem o :8765."""
from __future__ import annotations

import json

from tools import curator as cur
from tools import rag_freshness as rf

# ── o tick encadeia os 3 passos, na ordem, e agrega ──────────────────────────


def test_tick_chains_three_steps_in_order_and_aggregates():
    calls: list = []

    def decide(**kw):
        calls.append(("decide", kw))
        return {"decided": [1, 2], "escalated": [], "refused": [3],
                "left_pending": [4, 5, 6], "audit_records": []}

    def writeback(**kw):
        calls.append(("writeback", kw))
        return {"materialized": 2}

    def reindex(**kw):
        calls.append(("reindex", kw))
        return {"chunks": 5, "embedded": 4}

    rep = cur.tick(dry_run=True, now_iso="T0", caps={"max_auto_decisions_per_drain": 9},
                   decide=decide, writeback=writeback, reindex=reindex)

    assert [c[0] for c in calls] == ["decide", "writeback", "reindex"]  # ordem
    assert rep["decisions"] == {"decided": 2, "escalated": 0,
                                "refused": 1, "left_pending": 3}
    assert rep["verdicts_materialized"] == 2
    assert rep["reindex"] == {"chunks": 5, "embedded": 4}
    assert rep["dry_run"] is True
    # dry_run propagado pra CADA passo; caps -> decide; now_iso -> reindex
    assert all(c[1].get("dry_run") is True for c in calls)
    assert calls[0][1]["caps"] == {"max_auto_decisions_per_drain": 9}
    assert calls[2][1]["now_iso"] == "T0"


# ── dry-run NAO muta (os passos que escrevem em disco fazem early-return) ─────


def test_dry_run_writeback_and_reindex_never_mutate():
    wb = cur._writeback_step(dry_run=True)
    assert wb["materialized"] == 0 and "dry_run" in wb["note"]
    idx = cur._reindex_step(dry_run=True, now_iso=None)
    assert idx["chunks"] == 0 and idx["embedded"] == 0 and "dry_run" in idx["note"]


def test_decide_step_forwards_dry_run_and_caps(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(cur.auto_decider, "drain",
                        lambda **kw: seen.update(kw) or {})
    cur._decide_step(dry_run=True, caps={"max_auto_decisions_per_drain": 2})
    assert seen["dry_run"] is True
    assert seen["caps"] == {"max_auto_decisions_per_drain": 2}


# ── cada passo degrada sozinho quando falta entrada/infra (single-pass) ──────


def test_writeback_degrades_when_no_gallery_corpus(monkeypatch):
    monkeypatch.setattr(cur, "_latest_corpus", lambda: None)
    wb = cur._writeback_step(dry_run=False)
    assert wb["materialized"] == 0 and "corpus" in wb["note"]


def test_reindex_degrades_when_infra_off(monkeypatch, tmp_path):
    con = rf.connect(tmp_path / "freshness.db")
    monkeypatch.setattr(cur.rf, "connect", lambda *a, **k: con)
    monkeypatch.setattr(cur.rf, "reindex",
                        lambda c, **k: {"corpus_version": "cv123",
                                        "chunks_reindexed": 3, "chunks_reused": 1})
    monkeypatch.setattr(cur.reb, "infra_up", lambda *a, **k: False)
    idx = cur._reindex_step(dry_run=False, now_iso="2026-01-01T00:00:00Z")
    assert idx["chunks"] == 3            # so os (re)indexados novos
    assert idx["embedded"] == 0          # infra off -> 0 embedado (degrada)
    assert "off" in idx["note"].lower() or "indispon" in idx["note"].lower()


def test_reindex_embeds_when_infra_up(monkeypatch, tmp_path):
    con = rf.connect(tmp_path / "freshness.db")
    monkeypatch.setattr(cur.rf, "connect", lambda *a, **k: con)
    monkeypatch.setattr(cur.rf, "reindex",
                        lambda c, **k: {"corpus_version": "cv123",
                                        "chunks_reindexed": 2, "chunks_reused": 0})
    monkeypatch.setattr(cur.reb, "infra_up", lambda *a, **k: True)
    monkeypatch.setattr(cur.reb, "reindex_qdrant",
                        lambda c, **k: {"embedded": 2, "deleted": 0})
    idx = cur._reindex_step(dry_run=False, now_iso="2026-01-01T00:00:00Z")
    assert idx["embedded"] == 2 and "note" not in idx


def test_tick_single_pass_survives_all_steps_empty():
    rep = cur.tick(
        dry_run=False, now_iso="T0",
        decide=lambda **k: {"decided": [], "escalated": [], "refused": [],
                            "left_pending": [], "audit_records": []},
        writeback=lambda **k: {"materialized": 0, "note": "sem corpus"},
        reindex=lambda **k: {"chunks": 0, "embedded": 0, "note": "infra off"})
    assert rep["verdicts_materialized"] == 0
    assert rep["reindex"] == {"chunks": 0, "embedded": 0, "note": "infra off"}
    assert rep["verdicts_note"] == "sem corpus"


# ── CLI: --dry-run e o DEFAULT (nunca muta sem --apply) ──────────────────────


def test_cli_default_is_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(cur, "tick", lambda **kw: {"dry_run": kw["dry_run"]})
    assert cur.main([]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True


def test_cli_apply_disables_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(cur, "tick", lambda **kw: {"dry_run": kw["dry_run"]})
    assert cur.main(["--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is False


def test_caps_from_env(monkeypatch):
    monkeypatch.delenv("CURATOR_MAX_DECISIONS", raising=False)
    assert cur._caps_from_env() is None
    monkeypatch.setenv("CURATOR_MAX_DECISIONS", "4")
    assert cur._caps_from_env() == {"max_auto_decisions_per_drain": 4}
