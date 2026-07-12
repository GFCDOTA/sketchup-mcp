"""curation_review.py — laço autônomo de revisão de curadoria em lote.

O laço é UM processo determinístico (roda no tick do atuador; nenhuma sessão
Claude na maior parte dele):

  1. select_items()  — o que precisa revisar, SEM humano escolher: variante com
     render, sem veredito humano terminal, ainda não revisada NESTE render.
  2. status → "em_analise"   (sidecar curation_status.jsonl — o card mostra ao vivo)
  3. scorer(item) → GPT-no-Docker :8899 (nota/10 + porquê + caminho_pro_10).
     O scorer é INJETÁVEL: os testes rodam sem HTTP nem git.
  4. status → "revisado" + grava a review (sidecar gpt_reviews.jsonl)
  5. decide_followup() → DONE | NEEDS_FIX | NEEDS_FELIPE
  6. NEEDS_FIX → enfileira uma task kind:"curation_fix" no queue.jsonl (o dispatcher
     a executa numa sessão Claude única — fatia 2).

Rails (invariantes):
- GOSTO é do Felipe: o veredito IMPROVED/SAME/WORSE (human_verdict) só o clique
  humano escreve. A máquina dá NOTA + crítica (decide o *visual* e o auto-fix),
  nunca gosto.
- APARÊNCIA nunca auto-aprova: a correção que muda render vira VISUAL_REVIEW no
  dispatcher — fila do Felipe.
- Oráculo offline / imagem não vista → status "oraculo_offline", NUNCA fabrica
  veredito (mesma honestidade do gpt_docker_visual_score).

Determinístico e idempotente: clock injetado (--now/--today); re-revisa uma
variante só quando o RENDER muda (chave = render_refs.sha256). Dry-run é o default
(nada escrito, não chama o GPT); --apply roda o laço de verdade.

Uso:
    python -m tools.curation_review --plant planta_74            # dry-run: o que revisaria
    python -m tools.curation_review --plant planta_74 --apply    # revisa (grava sidecars)
    python -m tools.curation_review --apply --enqueue-fix        # + enfileira correções
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime
from pathlib import Path

from tools.claude_bridge.noc_dispatcher import is_appearance_evidence_variant
from tools.corpus_to_rag import _last_wins
from tools.jsonl_io import append_jsonl, read_jsonl

REPO_ROOT = Path(__file__).resolve().parents[1]

# ── vocabulário de status do card (sidecar curation_status.jsonl, last-wins) ──
ST_QUEUED = "na_fila"
ST_ANALYZING = "em_analise"
ST_REVIEWED = "revisado"
ST_FIXING = "corrigindo"
ST_DONE = "concluido"
ST_NEEDS_FELIPE = "aguardando_felipe"
ST_ORACLE_OFFLINE = "oraculo_offline"

# ── rotas de follow-up (decisão do que fazer com a nota do GPT) ──────────────
FOLLOWUP_DONE = "DONE"          # nota alta / sem caminho acionável — não mexe
FOLLOWUP_FIX = "NEEDS_FIX"      # nota baixa + caminho do GPT — vale corrigir
FOLLOWUP_FELIPE = "NEEDS_FELIPE"  # sem nota (cego/offline) — escala, nunca auto

NOTA_FIX_THRESHOLD = 7          # nota < 7 (com caminho) → corrigir; >= 7 → done
DEFAULT_CAP = 6                 # itens revisados por passada (cabe no tick de ~15min)
ID_PREFIX = "CR"

STATUS_FILE = "curation_status.jsonl"
REVIEW_FILE = "gpt_reviews.jsonl"
RUNS_FILE = "curation_runs.jsonl"   # run-log por passada (visibilidade no cockpit)


# ── predicados puros sobre um registro do corpus (last-wins) ─────────────────


def _has_render(rec: dict) -> bool:
    return bool((rec.get("render_refs") or {}).get("iso"))


def _render_sha(rec: dict) -> str:
    return (rec.get("render_refs") or {}).get("sha256") or ""


def _human_decided(rec: dict) -> bool:
    """Felipe já deu veredito de gosto? (_last_wins sobrepõe como dict
    {verdict,note,t}; o cru pode ser str)."""
    hv = rec.get("human_verdict")
    if isinstance(hv, dict):
        return bool(hv.get("verdict"))
    return bool(hv)


def select_items(records: list[dict], *, reviews: dict[str, dict]) -> list[dict]:
    """Itens que precisam da revisão do GPT. Política determinística, sem humano
    escolher:
      - tem render (o GPT precisa da imagem);
      - NÃO é evidência sintética de aparência (noc-<tid> / noc-evidence) — esses
        já foram pra VISUAL_REVIEW do Felipe e são a raiz do variant_id recursivo;
      - veredito humano = GOSTO respeitado (nunca re-pedimos), mas ele valeu pro
        render DA ÉPOCA: se o render mudou (sha≠ da última nota), a NOTA da
        máquina re-acompanha — senão o card mostra render novo com crítica velha
        (caso real: o sweep ganhou o shell e o grid re-emite os MESMOS ids);
      - ainda não revisado NESTE render (re-revisa só quando o render muda —
        chave = render_refs.sha256; sem sha → sempre revisa, honesto).
    """
    out: list[dict] = []
    for rec in records:
        vid = rec.get("variant_id")
        if not vid:
            continue
        if is_appearance_evidence_variant(rec):
            continue
        if not _has_render(rec):
            continue
        sha = _render_sha(rec)
        prev = reviews.get(vid)
        if _human_decided(rec) and (prev is None or not sha
                                    or prev.get("render_sha") == sha):
            continue
        if prev and sha and prev.get("render_sha") == sha:
            continue
        out.append(rec)
    return out


def decide_followup(item: dict, score) -> tuple[str, str]:
    """Rota do follow-up + razão. `score` é um VisualScore-like
    (nota/caminho_pro_10/image_viewed) ou None. NUNCA fabrica: sem nota do GPT
    (offline/cego) → NEEDS_FELIPE (escala, não auto-conserta no escuro)."""
    if score is None or not getattr(score, "image_viewed", False) or score.nota is None:
        return FOLLOWUP_FELIPE, "sem nota do GPT (offline/cego) — nao auto, escala pro Felipe"
    if score.nota >= NOTA_FIX_THRESHOLD:
        return FOLLOWUP_DONE, f"nota {score.nota}/10 >= {NOTA_FIX_THRESHOLD} — sem correcao automatica"
    caminho = (getattr(score, "caminho_pro_10", "") or "").strip()
    if not caminho:
        return FOLLOWUP_FELIPE, f"nota {score.nota}/10 mas sem caminho acionavel do GPT — escala"
    return FOLLOWUP_FIX, f"nota {score.nota}/10 < {NOTA_FIX_THRESHOLD} + caminho do GPT — corrigir"


def build_fix_task(item: dict, score, today: str) -> dict:
    """Task kind:curation_fix pro dispatcher (fatia 2). Schema real da fila —
    campos que o dispatcher lê + a crítica do GPT que vira o prompt de correção.
    Id determinístico por dia+variante (dedup como o feeder)."""
    vid = item["variant_id"]
    return {
        "id": f"{ID_PREFIX}-{today}-fix-{vid}",
        "title": f"curation_review: corrigir {vid} (GPT nota {score.nota}/10)",
        "safe": True,
        "kind": "curation_fix",
        "plant": item.get("plant", "planta_74"),
        "variant_id": vid,
        "gpt_nota": score.nota,
        "gpt_porque": (getattr(score, "porque", "") or "")[:2000],
        "gpt_caminho": (getattr(score, "caminho_pro_10", "") or "")[:2000],
        "enqueued_by": "curation_review",
    }


# ── sidecars (I/O fino, append-only, last-wins) ──────────────────────────────


def sidecar_last_wins(path: Path, key: str = "variant_id") -> dict[str, dict]:
    """Mapa {variant_id: último registro} de um sidecar jsonl (last-wins por
    ordem de arquivo — o sidecar é append-only, a última linha por id vale)."""
    out: dict[str, dict] = {}
    for r in read_jsonl(Path(path)):
        vid = r.get(key)
        if vid:
            out[vid] = r
    return out


def _write_status(out_dir: Path, vid: str, status: str, *, now: float, detail: str = "") -> None:
    append_jsonl(Path(out_dir) / STATUS_FILE,
                 [{"variant_id": vid, "status": status, "t": now, "detail": detail}])


def _write_review(out_dir: Path, vid: str, score, *, render_sha: str, now: float) -> None:
    append_jsonl(Path(out_dir) / REVIEW_FILE, [{
        "variant_id": vid,
        "nota": score.nota,
        "porque": getattr(score, "porque", "") or "",
        "caminho_pro_10": getattr(score, "caminho_pro_10", "") or "",
        "factivel_10": getattr(score, "factivel_10", "") or "",
        "image_viewed": bool(getattr(score, "image_viewed", False)),
        "url": getattr(score, "url", "") or "",
        "render_sha": render_sha,
        "t": now,
    }])


# ── o laço (1 passada) ───────────────────────────────────────────────────────


def _card_status_for_route(route: str, *, enqueue_fix: bool) -> str:
    if route == FOLLOWUP_FIX:
        return ST_FIXING if enqueue_fix else ST_REVIEWED
    if route == FOLLOWUP_FELIPE:
        return ST_NEEDS_FELIPE
    return ST_DONE


def run_batch(*, corpus_path: Path, out_dir: Path, scorer, now: float, today: str,
              cap: int = DEFAULT_CAP, apply: bool = False, enqueue_fix: bool = False,
              queue_path: Path | None = None, known_ids: frozenset = frozenset(),
              trigger: str = "auto") -> dict:
    """UMA passada do laço. `scorer(item) -> VisualScore|None` é injetável.

    Dry-run (apply=False): calcula o que revisaria, NÃO chama o scorer nem escreve.
    --apply: roda o laço (status → GPT → review → decisão), grava os sidecars +
    UMA linha de run-log (curation_runs.jsonl — o cockpit mostra "o que o sistema
    fez neste tick"), e (se enqueue_fix) enfileira as correções deduplicadas.
    """
    corpus_path = Path(corpus_path)
    out_dir = Path(out_dir)
    records = _last_wins(corpus_path)
    reviews = sidecar_last_wins(out_dir / REVIEW_FILE)
    selected = select_items(records, reviews=reviews)
    batch = selected[:cap]

    if not apply:
        return {
            "curation_review": "curation_review/1.0.0",
            "today": today, "corpus": str(corpus_path),
            "n_records": len(records), "n_selected": len(selected),
            "would_review": [r["variant_id"] for r in batch],
            "applied": False,
            "note": "dry-run: nada escrito, GPT não consultado (use --apply)",
        }

    results: list[dict] = []
    fixes: list[dict] = []
    for item in batch:
        vid = item["variant_id"]
        sha = _render_sha(item)
        _write_status(out_dir, vid, ST_ANALYZING, now=now, detail="GPT analisando o render")
        score = scorer(item)  # bloqueia ~60s no real; injetado nos testes
        if score is None or not getattr(score, "image_viewed", False):
            _write_status(out_dir, vid, ST_ORACLE_OFFLINE, now=now,
                          detail="GPT não viu a imagem (offline/cego)")
            results.append({"variant_id": vid, "route": FOLLOWUP_FELIPE,
                            "card": ST_ORACLE_OFFLINE, "nota": None})
            continue
        _write_review(out_dir, vid, score, render_sha=sha, now=now)
        route, reason = decide_followup(item, score)
        card = _card_status_for_route(route, enqueue_fix=enqueue_fix)
        _write_status(out_dir, vid, ST_REVIEWED, now=now, detail=f"nota {score.nota}/10")
        if card != ST_REVIEWED:
            _write_status(out_dir, vid, card, now=now, detail=reason)
        fix_task = None
        if route == FOLLOWUP_FIX and enqueue_fix:
            candidate = build_fix_task(item, score, today)
            if candidate["id"] not in known_ids:
                fix_task = candidate
                fixes.append(fix_task)
        results.append({"variant_id": vid, "nota": score.nota, "route": route,
                        "reason": reason, "card": card,
                        "fix_id": fix_task["id"] if fix_task else None})

    if enqueue_fix and fixes and queue_path is not None:
        append_jsonl(Path(queue_path), fixes)

    report = {
        "curation_review": "curation_review/1.0.0",
        "today": today, "corpus": str(corpus_path),
        "n_records": len(records), "n_selected": len(selected),
        "n_reviewed": len([r for r in results if r.get("nota") is not None]),
        "results": results,
        "enqueued_fixes": [t["id"] for t in fixes],
        "applied": True,
    }
    # run-log: UMA linha por passada aplicada (mesmo padrão do auto_decider_runs) —
    # é o que o cockpit mostra em "o que a revisão autônoma fez a cada tick".
    # Passada vazia TAMBÉM loga (n_reviewed=0 = "rodou e não havia nada") — a
    # visibilidade de "rodou às HH:MM" é o ponto, não só quando há trabalho.
    append_jsonl(out_dir / RUNS_FILE, [{
        "t": now, "today": today, "trigger": trigger,
        "n_selected": len(selected), "n_reviewed": report["n_reviewed"],
        "remaining": max(0, len(selected) - len(batch)),
        "reviewed": [{"variant_id": r["variant_id"], "nota": r.get("nota"),
                      "route": r.get("route")} for r in results],
        "enqueued_fixes": report["enqueued_fixes"],
    }])
    return report


# ── scorer real (não exercido em dry-run; injetado nos testes) ───────────────


def make_default_scorer(corpus_dir: Path, *, branch: str, bridge_url: str, timeout_s: int):
    """Scorer de produção: resolve o render do corpus (data/runs, fora do repo),
    COPIA pro repo (artifacts/review/<plant>/curation/), publica na URL raw e
    pergunta ao GPT-no-Docker. Degrada honesto (None) se não há render ou o
    publish/oráculo falha — nunca fabrica nota."""
    from tools.gpt_docker_visual_score import score_render

    def _scorer(item: dict):
        iso = (item.get("render_refs") or {}).get("iso")
        if not iso:
            return None
        src = (Path(corpus_dir) / iso).resolve()
        if not src.is_file():
            return None
        vid = item["variant_id"]
        plant = item.get("plant", "planta_74")
        dst = REPO_ROOT / "artifacts" / "review" / plant / "curation" / f"{vid}.png"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        try:
            return score_render(dst, branch=branch, bridge_url=bridge_url, timeout_s=timeout_s)
        except (RuntimeError, FileNotFoundError):
            return None  # erro de publish/oráculo → degrade honesto

    return _scorer


# ── CLI ──────────────────────────────────────────────────────────────────────


def _default_runs_root() -> Path:
    from tools.claude_bridge._paths import WORKSPACE_ROOT
    return WORKSPACE_ROOT / "data" / "runs"


def _known_ids(queue_path: Path, ledger_path: Path) -> frozenset:
    ids = {t.get("id") for t in read_jsonl(Path(queue_path)) if t.get("id")}
    ids |= {r.get("task_id") for r in read_jsonl(Path(ledger_path)) if r.get("task_id")}
    return frozenset(i for i in ids if i)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="curation_review — revisa a fila de curadoria em lote via GPT-no-Docker")
    ap.add_argument("--plant", default="planta_74")
    ap.add_argument("--runs-root", type=Path, default=None,
                    help="default: <workspace>/data/runs")
    ap.add_argument("--corpus", type=Path, default=None,
                    help="default: <runs>/noc_variant_sweep/<plant>/corpus.jsonl")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="onde gravar os sidecars (default: dir do corpus)")
    ap.add_argument("--apply", action="store_true", help="roda o laço e grava (default: dry-run)")
    ap.add_argument("--enqueue-fix", action="store_true",
                    help="enfileira tasks curation_fix pros itens NEEDS_FIX (fatia 2)")
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP,
                    help=f"itens revisados por passada (default {DEFAULT_CAP})")
    ap.add_argument("--bridge-url", default="http://127.0.0.1:8899")
    ap.add_argument("--branch", default="develop", help="branch p/ publicar o render (URL raw)")
    ap.add_argument("--timeout", type=int, default=200)
    ap.add_argument("--today", default=None, help="YYYYMMDD (teste/idempotência)")
    ap.add_argument("--now", type=float, default=None, help="epoch injetado (teste)")
    ap.add_argument("--trigger", default="auto", choices=("auto", "manual"),
                    help="proveniência no run-log (tick=auto, botão=manual)")
    ap.add_argument("--queue", type=Path, default=None,
                    help="default: <repo>/.ai_bridge/noc/queue.jsonl")
    ap.add_argument("--ledger", type=Path, default=None,
                    help="default: <repo>/.ai_bridge/noc/actions.jsonl")
    a = ap.parse_args(argv)

    now = a.now if a.now is not None else time.time()
    today = a.today or datetime.fromtimestamp(now).strftime("%Y%m%d")
    runs = a.runs_root or _default_runs_root()
    corpus = a.corpus or Path(runs) / "noc_variant_sweep" / a.plant / "corpus.jsonl"
    out_dir = a.out_dir or corpus.parent
    queue = a.queue or REPO_ROOT / ".ai_bridge" / "noc" / "queue.jsonl"
    ledger = a.ledger or REPO_ROOT / ".ai_bridge" / "noc" / "actions.jsonl"

    scorer = make_default_scorer(corpus.parent, branch=a.branch,
                                 bridge_url=a.bridge_url, timeout_s=a.timeout)
    report = run_batch(
        corpus_path=corpus, out_dir=out_dir, scorer=scorer, now=now, today=today,
        cap=a.cap, apply=a.apply, enqueue_fix=a.enqueue_fix, queue_path=queue,
        known_ids=_known_ids(queue, ledger), trigger=a.trigger)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
