"""store_reconcile.py — reconcilia os eventos pendentes do EventStore com os FATOS do GitHub (FP-060 MT-12, #638).

    python -m tools.orchestration.store_reconcile            # so o plano: nada e gravado
    python -m tools.orchestration.store_reconcile --apply    # supersede o que e SEGURO descartar

NAO e um segundo reconciliador: o estado do PR (checks obrigatorios no HEAD) vem de `lifecycle.checks_state`, o Project vem do
`backlog_reconcile` (Issues canonicas, Project vista) e o espelho JSON x SQLite do `shadow_divergence`. O que faltava era ligar o SQLite aos fatos do
GitHub: um evento `CORRECTION_REQUESTED` que ficou PENDING enquanto o PR fechou, foi mergeado ou ganhou HEAD novo nao pode ser executado.

Regras (cada uma tem teste):
- So age sobre eventos PENDING (ou RUNNING com lease vencido): um evento com lease vivo e de outro executor e nunca e tocado;
- A unica correcao automatica e `supersede` (descartar um pedido OBSOLETO), cercada pelo token: o evento e reivindicado antes (`claim_by_id`) e o
  resultado e descartado se outro dono apareceu. Nada e reexecutado, republicado, reaberto nem apagado;
- Falha ao ler o GitHub (rede, 5xx, resposta malformada) vira `ERROR` no relatorio e NAO muda o evento: na duvida o pedido segue como esta;
- Divergencia que nao e segura corrigir sozinha (PR aberto no mesmo HEAD, mas com CI reprovado, por exemplo) e so REPORTADA com codigo;
- Sem `--apply` nada e gravado, nunca."""
from __future__ import annotations

import argparse
import json
import sys
import uuid

from tools.orchestration import event_bridge as eb
from tools.orchestration import lifecycle
from tools.orchestration.event_store import EventStore, LeaseLost

EVENT_TYPE = "CORRECTION_REQUESTED"
LEASE_S = 30.0
OWNER_PREFIX = "store-reconcile:"


def _payload(ev: dict) -> dict:
    p = ev["payload"]
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except ValueError:
            return {}
    return p if isinstance(p, dict) else {}


def open_events(store: EventStore) -> list[dict]:
    """Eventos que ainda podem ser executados: PENDING, ou RUNNING com o lease vencido (dono morto)."""
    now = store.clock()
    return [e for e in store.events() if e["event_type"] == EVENT_TYPE
            and (e["status"] == "PENDING" or (e["status"] == "RUNNING" and e["lease_until"] <= now))]


def judge(ev: dict, pr: dict) -> tuple[str, str]:
    """(codigo, motivo) para um evento aberto diante do PR no GitHub. Puro."""
    p = _payload(ev)
    if pr.get("state") != "open" or pr.get("merged"):
        return "PR_NOT_OPEN", f"PR #{p.get('pr')} nao esta aberto (fechado ou mergeado)"
    head = ((pr.get("head") or {}).get("sha") or "").lower()
    if head != str(p.get("head_sha") or "").lower():
        return "HEAD_MOVED", f"HEAD mudou ({str(p.get('head_sha'))[:8]} -> {head[:8]}): o pedido e do HEAD antigo"
    return "CURRENT", "PR aberto no mesmo HEAD do pedido"


def reconcile(store: EventStore, gh: eb.Gh, repo: str = eb.REPO, apply: bool = False) -> dict:
    """Relatorio por evento aberto. Com `apply`, supersede os obsoletos (HEAD_MOVED / PR_NOT_OPEN); o resto so e reportado."""
    rows = []
    for ev in open_events(store):
        p = _payload(ev)
        row = {"event": ev["id"], "key": ev["idempotency_key"], "pr": p.get("pr")}
        if not isinstance(p.get("pr"), int):
            rows.append({**row, "code": "MALFORMED", "detail": "payload sem PR: nao ha o que conferir; fica como esta"})
            continue
        try:
            pr = gh(f"repos/{repo}/pulls/{p['pr']}")
            if not isinstance(pr, dict):
                raise RuntimeError("resposta do PR nao e um objeto")
            code, detail = judge(ev, pr)
            ci = None
            if code == "CURRENT":
                ci = lifecycle.checks_state(lifecycle._check_runs(gh, repo, pr["head"]["sha"]))
        except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
            rows.append({**row, "code": "ERROR", "detail": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        row.update(code=code, detail=detail)
        if ci is not None:
            row["ci"] = ci
            if ci == "failed":
                row["code"], row["detail"] = "CURRENT_CI_FAILED", "PR aberto no mesmo HEAD, com checks reprovados: so reportado (corrigir e do executor/humano)"
        if apply and code in ("HEAD_MOVED", "PR_NOT_OPEN"):
            row["applied"] = _supersede(store, ev, detail)
        rows.append(row)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["code"]] = counts.get(r["code"], 0) + 1
    return {"applied": apply, "counts": counts, "events": rows}


def _supersede(store: EventStore, ev: dict, reason: str) -> str:
    """'SUPERSEDED' | 'SKIPPED' (alguem reivindicou antes) | 'LEASE_LOST' (perdeu o lease no meio). Nunca levanta por concorrencia."""
    owner = f"{OWNER_PREFIX}{uuid.uuid4().hex[:8]}"
    claimed = store.claim_by_id(ev["id"], owner, LEASE_S)
    if claimed is None:
        return "SKIPPED"
    try:
        store.supersede(claimed, f"reconciliado: {reason}"[:2000])
    except LeaseLost:
        return "LEASE_LOST"
    return "SUPERSEDED"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="supersede os eventos obsoletos; sem isto so planeja")
    ap.add_argument("--repo", default=eb.REPO)
    a = ap.parse_args(argv)
    from tools.orchestration.store_factory import get_store
    report = reconcile(get_store(), eb.gh_json, a.repo, a.apply)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if report["counts"].get("ERROR") else 0


if __name__ == "__main__":
    sys.exit(main())
