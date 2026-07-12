"""feeder.py — alimentador da fila NOC: enche a fila com trabalho SEGURO e
CAPADO quando o gate esta ocioso, pra o atuador nunca dormir sem lenha.

Sinais (probes READ-ONLY na arvore do motor + data/runs do workspace):
  (a) ociosidade do gate  = idade do ultimo registro de .ai_bridge/audit/audit.jsonl
      (fonte primaria de consults do cockpit; rows tem "t" epoch);
  (b) variantes PENDING_VISION no corpus mais recente de
      data/runs/noc_variant_sweep/*/corpus.jsonl (last-wins por variant_id,
      mesma semantica do variant_sweep.sweep);
  (c) vision_requests pendentes nos out-dirs de data/runs/noc_correction/*
      (requests - consumed por queue_key, REUSANDO _pending_requests do
      vision_queue_consumer — zero segunda implementacao da identidade);
  (d) o que ja esta pendente na fila + o que o feeder ja enfileirou HOJE
      (ids com prefixo NF-<YYYYMMDD>-, checados na fila E no ledger).

Plano -> enfileira com caps DEFAULT:
  - 1 correction_cycle/dia por planta (default planta_74);
  - 1 variant-sweep/dia (REAL su-free: o dispatcher passa --dry-run pro
    tools.variant_sweep, que nesse modo gera registros REAIS com
    PENDING_VISION honesto — barato, sem SketchUp, sem visao);
  - ate `drain_cap` (default 3) variant-vision-drain/ciclo — LOOP FECHADO:
    quando o sweep acima (ou um ciclo anterior) deixa variantes PENDING_VISION
    no corpus, o feeder enfileira 1 task por variante (id NF-<dia>-visdrain-
    <variant_id>) que o dispatcher roda via dispatch_variant_vision_drain
    (`tools.variant_sweep --ask-vision --only <variant_id>`, painel
    colaborativo de 3 juizes) — nunca mais que `drain_cap` por ciclo;
  - dedup duro: NUNCA enfileira kind+fixture (ou kind+variant_id, no caso do
    drain) que ja esta pendente na fila.

Limitacoes HONESTAS (declaradas no plano, nunca kind inventado):
  - excesso de PENDING_VISION alem do drain_cap fica pra ciclos seguintes
    (nao enfileira as 50 variantes de uma vez so);
  - o drain de vision_requests via fila (kind correction_cycle) exige
    task["render"] explicito do estado ATUAL do modelo; o feeder NAO fabrica
    render (sem ele o consumer bloqueia BLOCKED_NEEDS_RENDER e o pedido fica).

Rails: o feeder so PREPARA (append na fila, append-only, mesmo idioma
jsonl_io); quem age e o dispatcher; veredito visual continua exclusivo do
Felipe (human_verdict sempre null; design_patterns_observed e' conhecimento
observacional acumulado do painel de 3 juizes, NUNCA um veredito estetico).
Deterministico e idempotente: --today/--now injetados, ids
NF-<YYYYMMDD>-<slug> — rodar 2x no mesmo dia = zero task nova. Exit 0 sempre
(feeder sem sinal nao e erro).

Uso:
    python -m tools.feeder --dry-run                 # imprime o plano
    python -m tools.feeder --once                    # aplica (append na fila)
    python -m tools.feeder --once --no-sweep         # so correction_cycle
    python -m tools.feeder --once --no-drain         # sem drain de PENDING_VISION
    python -m tools.feeder --today 20260703 --now 1783118000  # teste
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from tools.jsonl_io import append_jsonl, read_jsonl

REPO_ROOT = Path(__file__).resolve().parents[1]

# Statuses terminais IMPORTADOS do dispatcher (lockstep REAL, fonte unica —
# a mesma constante que _terminal_ids() consome): task com status fora deste
# set continua PENDENTE na fila (pick_task re-pega).
from tools.claude_bridge import noc_dispatcher as _nd  # noqa: E402

TERMINAL = _nd.TERMINAL_STATUSES

DEFAULT_IDLE_MIN = 30
DEFAULT_SWEEP_N = 8
ID_PREFIX = "NF"


# ── probes (read-only) ───────────────────────────────────────────────────────


def probe_gate_idle(audit_path: Path, now: float) -> dict:
    """Idade do ultimo evento do gate. Sem arquivo/linha valida -> last_t=None
    (tratado como OCIOSO, honesto no report: gate que nunca falou esta parado)."""
    rows = read_jsonl(audit_path)
    ts = [r["t"] for r in rows if isinstance(r.get("t"), (int, float))]
    last_t = max(ts) if ts else None
    idle_sec = (now - last_t) if last_t is not None else None
    return {"audit": str(audit_path), "last_t": last_t, "idle_sec": idle_sec}


def latest_corpus(variant_root: Path) -> Path | None:
    """corpus.jsonl mais recente (mtime) entre data/runs/noc_variant_sweep/*/."""
    cands = sorted(Path(variant_root).glob("*/corpus.jsonl"),
                   key=lambda p: (p.stat().st_mtime, str(p)))
    return cands[-1] if cands else None


def pending_vision_variants(corpus: Path | None) -> list[str]:
    """variant_ids cujo registro LAST-WINS esta PENDING_VISION E que sao variantes
    de sweep DRENAVEIS. REUSA corpus_to_rag._last_wins (identidade unica do
    last-wins por variant_id; o corpus e append-only, a ultima linha por id vale).

    EXCLUI a evidencia sintetica de APARENCIA (noc-<tid> / noc-evidence): esses ja
    foram pra VISUAL_REVIEW do Felipe e nao sao drenaveis — re-enfileira-los faz o
    dispatcher re-emitir com variant_id ainda mais aninhado (o bug do id recursivo
    que crescia todo dia). Fonte unica do marcador em noc_dispatcher."""
    if corpus is None:
        return []
    from tools.corpus_to_rag import _last_wins
    return sorted(r["variant_id"] for r in _last_wins(corpus)
                  if r.get("verdict") == "PENDING_VISION"
                  and not _nd.is_appearance_evidence_variant(r))


def pending_vision_requests(correction_root: Path) -> dict:
    """{fixture: n_pending} por out-dir de data/runs/noc_correction/*. Reusa a
    identidade de consumo do consumer (requests - consumed por queue_key)."""
    from tools.vision_queue_consumer import _pending_requests
    out: dict = {}
    root = Path(correction_root)
    if not root.is_dir():
        return out
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        n = len(_pending_requests(d))
        if n:
            out[d.name] = n
    return out


def queue_state(queue_path: Path, ledger_path: Path) -> dict:
    """Fila + ledger -> ids conhecidos, tasks PENDENTES.

    Pendente = o que o pick_task do dispatcher AINDA PEGARIA (elegibilidade
    real, nao aproximacao): safe:false NUNCA roda (pick_task pula) e nunca
    ganha status terminal — contar como pendente starvaria o cap diario pra
    sempre; task SEM id RODA no pick_task (None nunca entra em done) — tem
    que contar pro dedup kind+fixture, senao o feeder duplica o kind no dia."""
    tasks = read_jsonl(queue_path)
    ledger = read_jsonl(ledger_path)
    terminal_ids = {r.get("task_id") for r in ledger
                    if r.get("status") in TERMINAL} - {None}
    pending = [t for t in tasks
               if t.get("safe") is not False and t.get("id") not in terminal_ids]
    return {
        "queue_ids": [t.get("id") for t in tasks if t.get("id")],
        "ledger_ids": sorted({r.get("task_id") for r in ledger if r.get("task_id")}),
        "pending": pending,
    }


# ── task builders (schema REAL da fila — campos que o dispatcher le) ─────────


def corr_task(today: str, fixture: str) -> dict:
    return {
        "id": f"{ID_PREFIX}-{today}-corr-{fixture}",
        "title": f"feeder: 1 ciclo correction_loop {fixture}",
        "safe": True,
        "kind": "correction_cycle",
        "fixture": fixture,
        "max_cycles": 1,
        "enqueued_by": "feeder",
    }


def sweep_task(today: str, plant: str, n: int) -> dict:
    return {
        "id": f"{ID_PREFIX}-{today}-sweep-{plant}",
        "title": f"feeder: variant sweep su-free {plant} (n={n})",
        "safe": True,
        "kind": "variant-sweep",  # HIFEN byte-exato (spec FP-034)
        "plant": plant,
        "n": n,
        "appearance": True,  # sweep copia .png -> rota VISUAL_REVIEW; campo e
        "enqueued_by": "feeder",  # informativo pro dashboard (drift documentado)
    }


def drain_task(today: str, plant: str, variant_id: str) -> dict:
    """kind:variant-vision-drain (fecha o loop): 1 variante PENDING_VISION do
    corpus drenada via o painel colaborativo de 3 juizes (dispatch_variant_-
    vision_drain -> tools.variant_sweep --ask-vision --only <variant_id>). Id
    determinístico por dia+variante (nunca a mesma variante 2x no mesmo dia)."""
    return {
        "id": f"{ID_PREFIX}-{today}-visdrain-{variant_id}",
        "title": f"feeder: drain PENDING_VISION {variant_id} (painel 3 juizes)",
        "safe": True,
        "kind": "variant-vision-drain",  # HIFEN byte-exato (paridade com variant-sweep)
        "plant": plant,
        "variant_id": variant_id,
        "enqueued_by": "feeder",
    }


# ── plano ────────────────────────────────────────────────────────────────────

DEFAULT_DRAIN_CAP = 3  # teto de variantes PENDING_VISION drenadas por ciclo (nao 50 de uma vez)


def build_plan(*, today: str, now: float, queue_path: Path, ledger_path: Path,
               audit_path: Path, variant_root: Path, correction_root: Path,
               plants: list[str], sweep_n: int, idle_min: float,
               no_correction: bool = False, no_sweep: bool = False,
               no_drain: bool = False, drain_cap: int = DEFAULT_DRAIN_CAP) -> dict:
    gate = probe_gate_idle(audit_path, now)
    idle = gate["idle_sec"] is None or gate["idle_sec"] >= idle_min * 60
    gate["idle"] = idle
    gate["threshold_min"] = idle_min

    corpus = latest_corpus(variant_root)
    var_pending = pending_vision_variants(corpus)
    corr_pending = pending_vision_requests(correction_root)

    qs = queue_state(queue_path, ledger_path)
    known_ids = set(qs["queue_ids"]) | set(qs["ledger_ids"])
    feeder_today = sorted(i for i in known_ids
                          if isinstance(i, str) and i.startswith(f"{ID_PREFIX}-{today}-"))
    # chave de dedup por kind: correction_cycle/variant-sweep dedupam por
    # (kind, fixture-ou-plant) — variant-vision-drain dedupa por (kind,
    # variant_id), pois varias variantes do MESMO plant podem estar pendentes
    # ao mesmo tempo (fixture/plant sozinho colidiria todas numa so chave).
    pending_kinds = set()
    for t in qs["pending"]:
        k = (t.get("kind") or "claude").lower()
        if k == "variant-vision-drain":
            pending_kinds.add((k, t.get("variant_id") or ""))
        else:
            pending_kinds.add((k, t.get("fixture") or t.get("plant") or ""))

    plan: list[dict] = []
    skipped: list[dict] = []

    def consider(task: dict, kind_key: tuple, disabled: bool, what: str) -> None:
        if disabled:
            skipped.append({"what": what, "reason": "desligado por flag"})
        elif task["id"] in known_ids:
            skipped.append({"what": what,
                            "reason": f"cap 1/dia: {task['id']} ja existe (fila/ledger)"})
        elif kind_key in pending_kinds:
            skipped.append({"what": what,
                            "reason": f"dedup: kind+fixture {kind_key} ja pendente na fila"})
        elif not idle:
            skipped.append({"what": what,
                            "reason": f"gate ATIVO ha {gate['idle_sec']:.0f}s "
                                      f"(< {idle_min:.0f}min) — sem sinal de ociosidade"})
        else:
            plan.append(task)

    for plant in plants:
        consider(corr_task(today, plant), ("correction_cycle", plant),
                 no_correction, f"correction_cycle {plant}")
    consider(sweep_task(today, plants[0], sweep_n), ("variant-sweep", plants[0]),
             no_sweep, f"variant-sweep {plants[0]}")

    # Loop fechado: PENDING_VISION detectado -> enfileira drain via o painel de
    # 3 juizes (dispatch_variant_vision_drain), capado (nao enfileira 50 de
    # uma vez). plants[0] e' o mesmo plant do corpus mais recente lido acima
    # (latest_corpus/pending_vision_variants nao distinguem por plant hoje —
    # mesma limitacao ja existente do sweep_task, nao nova desta fatia).
    drain_plant = plants[0] if plants else "planta_74"
    for vid in var_pending[:drain_cap]:
        consider(drain_task(today, drain_plant, vid),
                 ("variant-vision-drain", vid),
                 no_drain, f"variant-vision-drain {vid}")

    limitations: list[str] = []
    if len(var_pending) > drain_cap:
        limitations.append(
            f"{len(var_pending)} variante(s) PENDING_VISION no corpus {corpus}; "
            f"so as primeiras {drain_cap} entraram no plano deste ciclo (cap "
            "drain_cap) — as restantes drenam em ciclos seguintes.")
    if corr_pending:
        limitations.append(
            f"vision_requests pendentes {corr_pending}: o drain via fila (kind "
            "correction_cycle) exige task['render'] explicito do estado ATUAL do "
            "modelo; o feeder NAO fabrica render — sem ele o consumer bloqueia "
            "BLOCKED_NEEDS_RENDER (honesto) e o pedido permanece na fila de visao.")

    return {
        "feeder": "feeder/1.1.0",
        "today": today,
        "signals": {
            "gate": gate,
            "variant_pending_vision": {"corpus": str(corpus) if corpus else None,
                                       "variants": var_pending,
                                       "count": len(var_pending)},
            "correction_pending_vision": corr_pending,
            "queue": {"total": len(qs["queue_ids"]),
                      "pending_ids": sorted(t["id"] for t in qs["pending"]
                                            if t.get("id")),
                      "feeder_today": feeder_today},
        },
        "plan": plan,
        "skipped": skipped,
        "limitations": limitations,
    }


def apply_plan(report: dict, queue_path: Path) -> int:
    """Append das tasks planejadas na fila (append-only, nunca reescreve)."""
    tasks = report["plan"]
    if tasks:
        append_jsonl(Path(queue_path), tasks)
    return len(tasks)


# ── CLI ──────────────────────────────────────────────────────────────────────


def _default_runs_root() -> Path:
    from tools.claude_bridge._paths import WORKSPACE_ROOT
    return WORKSPACE_ROOT / "data" / "runs"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="feeder — enche a fila NOC com trabalho seguro e capado")
    ap.add_argument("--dry-run", action="store_true",
                    help="imprime o plano, NAO escreve (default se --once ausente)")
    ap.add_argument("--once", action="store_true", help="aplica: append na fila")
    ap.add_argument("--today", default=None, help="YYYYMMDD (teste/idempotencia)")
    ap.add_argument("--now", type=float, default=None,
                    help="epoch injetado p/ ociosidade (teste)")
    ap.add_argument("--engine-root", type=Path, default=REPO_ROOT,
                    help="arvore do motor (default: este repo)")
    ap.add_argument("--queue", type=Path, default=None,
                    help="default: <engine-root>/.ai_bridge/noc/queue.jsonl")
    ap.add_argument("--ledger", type=Path, default=None,
                    help="default: <engine-root>/.ai_bridge/noc/actions.jsonl")
    ap.add_argument("--runs-root", type=Path, default=None,
                    help="default: <workspace>/data/runs (noc_correction/, noc_variant_sweep/)")
    ap.add_argument("--idle-min", type=float, default=DEFAULT_IDLE_MIN,
                    help=f"gate ocioso ha >= N min = sinal (default {DEFAULT_IDLE_MIN})")
    ap.add_argument("--plants", nargs="+", default=["planta_74"])
    ap.add_argument("--n", type=int, default=DEFAULT_SWEEP_N,
                    help=f"celulas do sweep su-free (default {DEFAULT_SWEEP_N})")
    ap.add_argument("--no-correction", action="store_true")
    ap.add_argument("--no-sweep", action="store_true",
                    help="nao enfileira variant-sweep (ex.: prova ao vivo)")
    ap.add_argument("--no-drain", action="store_true",
                    help="nao enfileira variant-vision-drain (loop fechado desligado)")
    ap.add_argument("--drain-cap", type=int, default=DEFAULT_DRAIN_CAP,
                    help=f"teto de variant-vision-drain/ciclo (default {DEFAULT_DRAIN_CAP})")
    a = ap.parse_args(argv)

    now = a.now if a.now is not None else time.time()
    today = a.today or datetime.fromtimestamp(now).strftime("%Y%m%d")
    engine = Path(a.engine_root)
    queue = a.queue or engine / ".ai_bridge" / "noc" / "queue.jsonl"
    ledger = a.ledger or engine / ".ai_bridge" / "noc" / "actions.jsonl"
    audit = engine / ".ai_bridge" / "audit" / "audit.jsonl"
    runs = a.runs_root or _default_runs_root()

    report = build_plan(
        today=today, now=now, queue_path=queue, ledger_path=ledger,
        audit_path=audit, variant_root=Path(runs) / "noc_variant_sweep",
        correction_root=Path(runs) / "noc_correction",
        plants=list(a.plants), sweep_n=a.n, idle_min=a.idle_min,
        no_correction=a.no_correction, no_sweep=a.no_sweep,
        no_drain=a.no_drain, drain_cap=a.drain_cap)

    if a.once and not a.dry_run:
        report["applied"] = apply_plan(report, queue)
        report["queue"] = str(queue)
    else:
        report["applied"] = 0
        report["note"] = "dry-run: nada escrito (use --once pra aplicar)"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
