"""curator.py — o RUNNER: um TICK que amarra o loop semi-autonomo numa unica
passada (single-pass, nunca loop infinito). E o JOB PROPRIO da curadoria, separado
do feeder (que so enche a fila do NOC) — o curator FECHA o laco do gosto:

  1. auto_decider.drain(...)          — decide os objetivos (dry-run por default;
                                        o carteiro so muta com --apply).
  2. taste_writeback.drain_new_verdicts(...)  — materializa os vereditos HUMANOS
                                        novos em references/felipe/verdicts/ (write-
                                        back durable — so o clique do Felipe entra).
  3. rag_freshness.reindex(...) (+ embed se a infra estiver no ar) — pro veredito
                                        virar RECUPERAVEL no RAG.

Honestidade (regra dura): cada passo DEGRADA sozinho se a sua entrada/infra falta —
sem corpus de galeria -> 0 verdict materializado; Qdrant/Ollama off -> 0 embedado,
NOTA honesta, nunca fabrica. Nada de retry em loop: uma passada e acabou.

SEGURANCA: `--dry-run` e o DEFAULT (so classifica/relata, NAO muta); `--apply`
aplica de verdade. Em dry-run os passos 2 e 3 (que escrevem em disco/SQLite/Qdrant)
NAO executam — reportam skip honesto. Determinismo: `now_iso` do reindex e
INJETADO (sem clock em logica testavel); os 3 passos sao INJETAVEIS (mock).

Caps proprios (env): `CURATOR_MAX_DECISIONS` capa as decisoes do carteiro nesta
passada (repassado como cap pro auto_decider.drain).

Uso:
    python -m tools.curator --dry-run     # simula o tick, NAO muta (default)
    python -m tools.curator --apply       # roda o tick de verdade (single-pass)
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from tools import rag_embed_backend as reb
from tools import rag_freshness as rf
from tools import taste_writeback
from tools.interior_studio import auto_decider

ROOT = Path(__file__).resolve().parents[1]


# ── clock / caps / corpus discovery (helpers deterministicos) ────────────────


def _utc_now_iso() -> str:
    """Carimbo ISO UTC — usado SO como default no boundary do reindex (injetado
    nos testes via now_iso, nunca em logica testavel)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _caps_from_env() -> dict | None:
    """Cap proprio do curator: CURATOR_MAX_DECISIONS -> teto de decisoes do
    carteiro nesta passada. Ausente/invalido -> None (auto_decider usa o seu)."""
    raw = os.environ.get("CURATOR_MAX_DECISIONS")
    if raw and raw.strip().lstrip("-").isdigit():
        return {"max_auto_decisions_per_drain": int(raw)}
    return None


def _latest_corpus() -> Path | None:
    """corpus.jsonl mais recente (mtime) da UNICA galeria
    (data/runs/noc_variant_sweep/*/). Mesma semantica do feeder.latest_corpus;
    ausente -> None (o write-back degrada honesto: nada a materializar)."""
    try:
        from tools.claude_bridge._paths import WORKSPACE_ROOT
        root = WORKSPACE_ROOT / "data" / "runs" / "noc_variant_sweep"
    except Exception:  # noqa: BLE001 — fallback repo-relativo se a raiz nao resolver
        root = ROOT / "data" / "runs" / "noc_variant_sweep"
    cands = sorted(Path(root).glob("*/corpus.jsonl"),
                   key=lambda p: (p.stat().st_mtime, str(p)))
    return cands[-1] if cands else None


# ── os 3 passos (defaults = a fiacao viva; injetaveis pra teste) ─────────────


def _decide_step(*, dry_run: bool, caps: dict | None) -> dict:
    """Passo 1: o carteiro decide os objetivos. Repassa dry_run (o carteiro nunca
    muta sem apply) e o cap do curator. Devolve o summary do auto_decider."""
    return auto_decider.drain(dry_run=dry_run, caps=caps)


def _writeback_step(*, dry_run: bool) -> dict:
    """Passo 2: materializa os vereditos HUMANOS novos no RAG. Em dry_run NAO
    escreve (skip honesto). Sem corpus de galeria -> 0 (degrada, nao fabrica)."""
    if dry_run:
        return {"materialized": 0, "note": "dry_run: write-back nao executado"}
    corpus = _latest_corpus()
    if corpus is None:
        return {"materialized": 0, "note": "sem corpus de galeria — nada a materializar"}
    con = rf.connect()
    try:
        n = taste_writeback.drain_new_verdicts(corpus, con)
    finally:
        con.close()
    return {"materialized": n, "corpus": str(corpus)}


def _reindex_step(*, dry_run: bool, now_iso: str | None) -> dict:
    """Passo 3: reindexa (chunka) as fontes e, se a infra estiver no ar, embeda no
    Qdrant pro veredito virar recuperavel. Em dry_run NAO toca o indice. Qdrant/
    Ollama off -> embedded=0 + NOTA honesta (degrada pro faceted, nunca fabrica)."""
    if dry_run:
        return {"chunks": 0, "embedded": 0, "note": "dry_run: reindex nao executado"}
    now_iso = now_iso or _utc_now_iso()
    con = rf.connect()
    try:
        rep = rf.reindex(con, now_iso=now_iso)
        chunks = rep["chunks_reindexed"]
        corpus_version = rep["corpus_version"]
        embedded = 0
        note = None
        if reb.infra_up():
            try:
                emb = reb.reindex_qdrant(con, corpus_version=corpus_version,
                                         now_iso=now_iso)
                embedded = emb["embedded"]
            except reb.InfraUnavailable as e:  # infra caiu no meio -> degrada honesto
                note = f"embed pulado (infra indisponivel): {e}"
        else:
            note = "embed pulado: Qdrant/Ollama off (degradacao honesta)"
        out = {"chunks": chunks, "embedded": embedded,
               "corpus_version": corpus_version}
        if note:
            out["note"] = note
        return out
    finally:
        con.close()


# ── o tick ───────────────────────────────────────────────────────────────────


def tick(*, dry_run: bool = True, now_iso: str | None = None,
         caps: dict | None = None,
         decide=_decide_step, writeback=_writeback_step,
         reindex=_reindex_step) -> dict:
    """Uma passada do loop: encadeia decide -> writeback -> reindex (nesta ordem —
    o veredito materializado no passo 2 e chunkado pelo passo 3). SINGLE-PASS:
    roda cada passo UMA vez e retorna; nunca faz retry/loop. Os 3 passos sao
    injetaveis (teste). Retorna
    {dry_run, decisions:{decided,escalated,refused,left_pending}, verdicts_materialized,
     reindex:{chunks,embedded}}."""
    decisions = decide(dry_run=dry_run, caps=caps)
    verdicts = writeback(dry_run=dry_run)
    idx = reindex(dry_run=dry_run, now_iso=now_iso)

    dec_counts = {k: len(decisions.get(k, []))
                  for k in ("decided", "escalated", "refused", "left_pending")}
    reindex_out = {"chunks": idx.get("chunks", 0),
                   "embedded": idx.get("embedded", 0)}
    if idx.get("note"):
        reindex_out["note"] = idx["note"]

    report = {
        "dry_run": dry_run,
        "decisions": dec_counts,
        "verdicts_materialized": verdicts.get("materialized", 0),
        "reindex": reindex_out,
    }
    if verdicts.get("note"):
        report["verdicts_note"] = verdicts["note"]
    return report


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(
        description="curator — o tick que amarra o loop semi-autonomo (single-pass)")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--dry-run", action="store_true",
                     help="simula o tick, NAO muta (default)")
    grp.add_argument("--apply", action="store_true",
                     help="roda o tick de verdade (aplica os 3 passos, single-pass)")
    ap.add_argument("--now-iso", default=None,
                    help="carimbo ISO injetado p/ o reindex (teste/determinismo)")
    a = ap.parse_args(argv)
    # DEFAULT = seguro: sem --apply nunca muta.
    dry_run = not a.apply
    report = tick(dry_run=dry_run, now_iso=a.now_iso, caps=_caps_from_env())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
