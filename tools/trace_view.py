#!/usr/bin/env python3
"""trace_view — lê um trace do AI Pipeline Inspector no terminal.

Enquanto a UI da Fase 5 não existe, este é o ÚNICO jeito de olhar uma run. E
mesmo depois vai continuar sendo útil: em CI, por SSH, num handoff — onde não
há browser.

REGRA DE HONESTIDADE: nunca afirma integridade por conta própria. Roda
`replay.validate()` e imprime o veredito. Esta CLI nasceu porque um relatório
escrito à mão afirmou "25 eventos, zero lacunas" e a tabela transcrita pulava o
`seq=20` — o dado estava certo, a apresentação não. Agora quem responde é o
código.

Uso:
    python -m tools.trace_view                     # a run mais recente
    python -m tools.trace_view --list              # lista as runs gravadas
    python -m tools.trace_view <runId>             # uma run pelo id
    python -m tools.trace_view <caminho.jsonl>     # um arquivo direto
    python -m tools.trace_view --tree              # só a árvore
    python -m tools.trace_view --json              # o resumo em JSON
    python -m tools.trace_view --check             # só valida; exit 1 se violar
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.observability.replay import RunTrace, load_run, timeline, validate
from core.observability.sink import default_traces_dir

CAT_ABBR = {"RAG": "RAG", "LLM": "LLM", "HARNESS": "HARN", "TOOL": "TOOL",
            "DETERMINISTIC": "DET", "DATABASE": "DB", "OBSERVABILITY": "OBS"}
STATUS_MARK = {"ok": " ", "started": "|", "failed": "X", "degraded": "!",
               "skipped": "-"}

# Chaves que valem espaço na linha. `meta` tem muito mais; o `--json` mostra tudo.
DETAIL_KEYS = (
    "backendRequested", "backendActual", "fallbackTriggered", "resultingTaxonomy",
    "intentMatchedExecution", "fallbackReason", "candidatesCount", "nRetrieved",
    "nSelected", "nRejected", "collection", "embedModel", "indexKind",
    "promptTokens", "completionTokens", "totalTokens", "model", "totalChars",
    "sections", "gate", "verdict", "terminal", "cycle", "fix", "reason", "counts",
)
# Resumo curto no nó da árvore.
NODE_KEYS = ("candidatesCount", "nRetrieved", "nSelected", "collection",
             "promptTokens", "completionTokens", "fallbackTriggered")


# ---------------------------------------------------------------------------
# descoberta
# ---------------------------------------------------------------------------


def list_traces(directory: Path) -> list[Path]:
    """Runs gravadas, da mais recente para a mais antiga."""
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.jsonl"), key=lambda p: p.stat().st_mtime,
                  reverse=True)


def resolve(target: str | None, directory: Path) -> Path | None:
    """Aceita caminho, runId, ou nada (= a mais recente)."""
    if target:
        p = Path(target)
        if p.is_file():
            return p
        p = directory / (target if target.endswith(".jsonl") else f"{target}.jsonl")
        return p if p.is_file() else None
    found = list_traces(directory)
    return found[0] if found else None


# ---------------------------------------------------------------------------
# árvore: spans + eventos pontuais, mesclados por seq
# ---------------------------------------------------------------------------


def build_view(trace: RunTrace) -> tuple[dict, dict, dict]:
    """(spans, pontos_por_span, filhos_por_span).

    Um span vem de um par started/finished. Um evento PONTUAL (`emit` solto)
    herda o span aberto — e precisa aparecer DENTRO dele, senão o `rag.degraded`
    some da árvore justo quando é ele que explica o fallback.
    """
    spans: dict[str, dict] = {}
    points: dict[str | None, list] = {}
    order: list[str] = []

    for ev in trace.events:
        sid = ev.span_id
        if sid is None:
            points.setdefault(None, []).append(ev)
            continue
        if sid not in spans:
            spans[sid] = {"component": ev.component, "parent": ev.parent_span_id,
                          "cat": ev.category.value, "status": ev.status.value,
                          "dur": ev.duration_ms, "seq": ev.seq, "meta": {}}
            order.append(sid)
        elif ev.duration_ms is not None:            # o `finished` fecha o span
            spans[sid].update(dur=ev.duration_ms, status=ev.status.value,
                              meta=ev.meta)
        else:
            points.setdefault(sid, []).append(ev)

    children: dict[str | None, list[str]] = {}
    for sid in order:
        parent = spans[sid]["parent"]
        children.setdefault(parent if parent in spans else None, []).append(sid)

    return spans, points, children


def _fmt_detail(meta: dict, keys) -> str:
    bits = []
    for k in keys:
        val = meta.get(k)
        if val in (None, [], {}):
            continue
        if k == "sections":
            val = " ".join(f"{s['source'].split('/')[0][:7]}:{s['pct']}%"
                           for s in val)
        bits.append(f"{k}={val}")
    return "  ".join(bits)


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def render_header(trace: RunTrace, path: Path, out=None) -> bool:
    """Cabeçalho + veredito dos invariantes. Devolve True se o trace é íntegro.

    `out=None` resolve para `sys.stdout` NA CHAMADA. Um default `out=sys.stdout`
    ligaria o stream no momento da definição do módulo — quebrando captura de
    teste e qualquer redirecionamento.
    """
    out = out or sys.stdout
    violations = validate(trace)
    last = trace.events[-1].seq if trace.events else 0
    print("=" * 96, file=out)
    print(f"TRACE {(trace.trace_id or '?')[:8]}   run {trace.run_id}", file=out)
    print(f"eventos={len(trace.events)}  seq=1..{last}  "
          f"terminal={trace.terminal_status}  "
          f"duração={(trace.total_duration_ms or 0) / 1000:.2f}s  "
          f"arquivo={path.stat().st_size / 1024:.1f} KB", file=out)
    if violations:
        print(f"INVARIANTES: {len(violations)} VIOLAÇÃO(ÕES)", file=out)
        for v in violations:
            print(f"   x {v.code}: {v.detail}", file=out)
    else:
        print("INVARIANTES: OK — 1 run.started · 1 terminal · seq contíguo · "
              "ts monotônico · nenhum parent órfão · não truncado", file=out)
    print("=" * 96, file=out)
    return not violations


def render_timeline(trace: RunTrace, out=None) -> None:
    out = out or sys.stdout
    print(f"{'t+s':>7} {'seq':>4} {'cat':<5}   {'evento':<28} {'ms':>8}  detalhe",
          file=out)
    print("-" * 96, file=out)
    for offset, ev in timeline(trace):
        dur = f"{ev.duration_ms:8.1f}" if ev.duration_ms is not None else " " * 8
        print(f"{offset / 1000:7.2f} {ev.seq:>4} "
              f"{CAT_ABBR.get(ev.category.value, '?'):<5} "
              f"{STATUS_MARK.get(ev.status.value, '?'):1} {ev.name:<28} {dur}  "
              f"{_fmt_detail(ev.meta, DETAIL_KEYS)[:120]}", file=out)


def render_tree(trace: RunTrace, out=None) -> None:
    out = out or sys.stdout
    spans, points, children = build_view(trace)

    def rows_under(sid):
        rows = [("span", spans[c]["seq"], c) for c in children.get(sid, [])]
        rows += [("point", ev.seq, ev) for ev in points.get(sid, [])]
        return sorted(rows, key=lambda r: r[1])       # a ordem conta a história

    def render(sid, depth):
        sp = spans[sid]
        flag = {"failed": "  FAIL", "degraded": "  DEGRADED"}.get(sp["status"], "")
        dur = f"{sp['dur']:9.1f}ms" if sp["dur"] is not None else "          -"
        detail = _fmt_detail(sp["meta"], NODE_KEYS)
        pad = "   " * depth
        print(f"{pad}+- {sp['component']:<28}{dur}  [{sp['cat']}]{flag}"
              + (f"  {detail}" if detail else ""), file=out)
        for kind, _seq, item in rows_under(sid):
            if kind == "span":
                render(item, depth + 1)
            else:
                extra = (item.meta.get("fallbackReason") or item.meta.get("terminal")
                         or item.meta.get("gate") or "")
                print(f"{pad}   .  {item.name:<28}{'':11}  {str(extra)[:48]}",
                      file=out)

    print(f"\nÁRVORE — run {trace.run_id}", file=out)
    print("-" * 96, file=out)
    for kind, _seq, item in rows_under(None):
        if kind == "span":
            render(item, 1)
        elif not item.name.startswith("run."):
            extra = (item.meta.get("gate") or item.meta.get("terminal")
                     or item.meta.get("fix") or "")
            print(f"   .  {item.name:<28}{'':11}  {str(extra)[:48]}", file=out)


def summary(trace: RunTrace) -> dict:
    """Resumo serializável — o que um script ou o CI consumiria."""
    by_category: dict[str, int] = {}
    for ev in trace.events:
        by_category[ev.category.value] = by_category.get(ev.category.value, 0) + 1
    return {
        "runId": trace.run_id,
        "traceId": trace.trace_id,
        "events": len(trace.events),
        "terminal": trace.terminal_status,
        "durationMs": trace.total_duration_ms,
        "complete": trace.complete,
        "truncated": trace.truncated,
        "byCategory": by_category,
        "violations": [{"code": v.code, "detail": v.detail}
                       for v in validate(trace)],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.trace_view",
        description="Lê um trace do AI Pipeline Inspector no terminal.")
    ap.add_argument("target", nargs="?",
                    help="runId ou caminho .jsonl (default: a run mais recente)")
    ap.add_argument("--dir", type=Path, default=None,
                    help="diretório de traces (default: .ai_bridge/traces)")
    ap.add_argument("--list", action="store_true", help="lista as runs gravadas")
    ap.add_argument("--tree", action="store_true", help="só a árvore")
    ap.add_argument("--events", action="store_true", help="só a linha do tempo")
    ap.add_argument("--json", action="store_true", help="resumo em JSON")
    ap.add_argument("--check", action="store_true",
                    help="só valida os invariantes; exit 1 se houver violação")
    ns = ap.parse_args(argv)

    directory = ns.dir or default_traces_dir()

    if ns.list:
        found = list_traces(directory)
        if not found:
            print(f"(nenhum trace em {directory})")
            return 1
        for p in found:
            tr = load_run(p)
            bad = validate(tr)
            mark = "!" if bad else " "
            print(f"{mark} {tr.run_id:<44} {len(tr.events):>4} ev  "
                  f"{(tr.total_duration_ms or 0) / 1000:>7.2f}s  "
                  f"{tr.terminal_status or '(aberto)'}")
        return 0

    path = resolve(ns.target, directory)
    if path is None:
        print(f"trace não encontrado (procurei em {directory})", file=sys.stderr)
        return 2

    trace = load_run(path)
    if not trace.events:
        print(f"{path} não tem evento legível", file=sys.stderr)
        return 2

    if ns.json:
        print(json.dumps(summary(trace), ensure_ascii=False, indent=2))
        return 0 if not validate(trace) else 1

    if ns.check:
        ok = render_header(trace, path)
        return 0 if ok else 1

    ok = render_header(trace, path)
    if not ns.tree:
        render_timeline(trace)
    if not ns.events:
        render_tree(trace)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
