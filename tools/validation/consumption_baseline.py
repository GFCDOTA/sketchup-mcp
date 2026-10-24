"""consumption_baseline.py — gate de integracao nominal (FP-055 P7, #418): o que existe so conta se a geracao CONSOME.

Mede, com o rastreio dinamico do `pipeline_audit`, o estado de cada capacidade do catalogo (INVOKED / CONSUMED), dos
modulos vigiados (executados na geracao?), dos especialistas e das receitas, e compara com o retrato versionado em
`docs/governance/consumption_baseline.v1.json`. Diverge nas DUAS direcoes:

- REGRESSAO  uma capacidade que era chamada/consumida deixou de ser (alguem removeu a chamada, descartou a saida);
- MELHORIA   algo passou a ser consumido e o retrato nao foi atualizado (senao uma regressao futura passaria sem aviso);
- NOVA / REMOVIDA  capacidade fora do retrato.

O relatorio lista tambem o que continua NAO consumido (o "relatorio de nao consumidos" da spec). Nao e prova de aparencia
nem de geometria no SketchUp: REFLECTED_IN_MODEL / VALIDATED seguem `NOT_EVALUATED` (L2 / geracao completa, P8).

Uso (processo novo, escala da planta):  PT_TO_M=0.0259 python -m tools.validation.consumption_baseline [--write]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs/governance/consumption_baseline.v1.json"


def capture(trace: dict | None = None) -> dict:
    from tools.navigation import pipeline_audit as pa
    trace = trace or pa.trace_generation()
    caps = pa.capability_inventory(trace)
    specs = pa.specialist_inventory(trace)
    recipes = pa.recipe_inventory(trace)
    return {
        "schema_version": "consumption_baseline.v1",
        "capabilities": {c["id"]: {"INVOKED": bool(c["INVOKED"]), "CONSUMED": bool(c["CONSUMED"])} for c in sorted(caps, key=lambda c: c["id"])},
        "watched_executed": {m["component"]: bool(m["EXECUTED_IN_GENERATION"]) for m in pa.watched_modules(trace)},
        "specialists_invoked": sum(bool(s["INVOKED"]) for s in specs),
        "specialists_total": len(specs),
        "recipes_consumed": sum(bool(r["CONSUMED"]) for r in recipes),
        "recipes_total": len(recipes),
    }


def compare(baseline: dict, now: dict) -> list[str]:
    """Divergencias com prefixo estavel: REGRESSAO / MELHORIA / NOVA / REMOVIDA."""
    out: list[str] = []
    for cid in sorted(set(baseline["capabilities"]) | set(now["capabilities"])):
        b, n = baseline["capabilities"].get(cid), now["capabilities"].get(cid)
        if b is None:
            out.append(f"NOVA capacidade fora do retrato: {cid} {n}")
        elif n is None:
            out.append(f"REMOVIDA do catalogo: {cid}")
        else:
            for k in ("INVOKED", "CONSUMED"):
                if b[k] and not n[k]:
                    out.append(f"REGRESSAO {cid}: {k} era true e agora e false")
                elif n[k] and not b[k]:
                    out.append(f"MELHORIA {cid}: {k} passou a true (atualizar o retrato)")
    for comp in sorted(set(baseline["watched_executed"]) | set(now["watched_executed"])):
        b, n = baseline["watched_executed"].get(comp), now["watched_executed"].get(comp)
        if b is None or n is None:
            out.append(f"NOVA/REMOVIDA modulo vigiado: {comp}")
        elif b and not n:
            out.append(f"REGRESSAO modulo vigiado {comp}: deixou de ser executado")
        elif n and not b:
            out.append(f"MELHORIA modulo vigiado {comp}: passou a ser executado (atualizar o retrato)")
    for k in ("specialists_invoked", "recipes_consumed"):
        if now[k] < baseline[k]:
            out.append(f"REGRESSAO {k}: {baseline[k]} -> {now[k]}")
        elif now[k] > baseline[k]:
            out.append(f"MELHORIA {k}: {baseline[k]} -> {now[k]} (atualizar o retrato)")
    for k in ("specialists_total", "recipes_total"):
        if now[k] != baseline[k]:
            out.append(f"NOVA/REMOVIDA {k}: {baseline[k]} -> {now[k]}")
    return out


def not_consumed(state: dict) -> list[str]:
    """Relatorio de nao consumidos: capacidades e modulos vigiados que a geracao nao usa."""
    rows = [f"capacidade {cid}: INVOKED={v['INVOKED']} CONSUMED={v['CONSUMED']}" for cid, v in state["capabilities"].items() if not v["CONSUMED"]]
    rows += [f"modulo vigiado {c}: nao executado" for c, ok in state["watched_executed"].items() if not ok]
    rows.append(f"especialistas invocados {state['specialists_invoked']}/{state['specialists_total']}; "
                f"receitas consumidas {state['recipes_consumed']}/{state['recipes_total']}")
    return rows


def main(argv: list[str]) -> int:
    now = capture()
    if "--write" in argv:
        BASELINE.write_text(json.dumps(now, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"retrato gravado em {BASELINE}")
        return 0
    print("\n".join(not_consumed(now)))
    diffs = compare(json.loads(BASELINE.read_text("utf-8")), now)
    print("\n".join(diffs) or "consumption_baseline: IDENTICO")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
