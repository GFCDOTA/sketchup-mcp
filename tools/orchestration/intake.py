"""intake.py — Issue pronta e AUTORIZADA no backlog vira um evento `IMPLEMENT_REQUESTED` no EventStore (FP-060 MT-11, #637, estagio 1).

    python -m tools.orchestration.intake plan [--project]            # so mostra o candidato e por que os demais ficaram de fora
    python -m tools.orchestration.intake publish [--project] --apply  # publica o evento (idempotente); sem --apply e igual a `plan`

NAO e um escalonador novo: a eleicao e a do `task_scheduler.decide` (dependencias, bloqueios, claims, PRs abertos, prontidao). O que este modulo
acrescenta e uma barreira a mais, nesta ordem:
  1. a Issue precisa trazer a label `executor-intake`, aplicada por um humano: ninguem e implementado so por estar `Ready`;
  2. a SPEC da Issue precisa estar em `ALLOWED_SPECS` (hoje so FP-060: orquestracao). Specs de geometria/mobiliario/render nunca entram, mesmo
     com a label; ampliar a lista e uma mudanca de codigo, com revisao. Se a auditoria de prontidao disser `needs_sketchup`, recusa tambem;
  3. a Issue precisa estar elegivel pelo agendador (dependencias, bloqueios, claims, PRs abertos), em `Ready` quando o Project e conhecido.
O registro `docs/governance/task_readiness.json` NAO e exigido aqui: ele pede um PR para cada Issue, e a label humana mais a lista de specs
fazem o papel de autorizacao. Uma tarefa cadastrada no board nao precisa de commit para ser considerada.
Publicar e so GRAVAR o pedido: hoje nada no executor consome `IMPLEMENT_REQUESTED` (o worker de implementacao e o estagio 2 da #637), entao
publicar nao executa nada. A chave de idempotencia inclui o hash do titulo e do corpo: o mesmo pedido nunca duplica; uma Issue editada gera
um pedido novo (o anterior, se ainda pendente, segue o seu proprio caminho)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field

from tools.validation import backlog_discovery as bd
from tools.validation import execution_state as es
from tools.validation import task_scheduler as ts

AUTH_LABEL = "executor-intake"
ALLOWED_SPECS = frozenset({"FP-060"})
EVENT_TYPE = "IMPLEMENT_REQUESTED"
AGGREGATE = "issue"
PRODUCER = "intake"


@dataclass
class IntakePlan:
    candidate: bd.Verdict | None
    skipped: list[str] = field(default_factory=list)                 # "#N: motivo" para cada Issue elegivel que a barreira recusou


def spec_hash(issue: dict) -> str:
    """Identifica o PEDIDO (titulo + corpo). Editar a Issue muda o hash; reler a mesma Issue nao."""
    raw = json.dumps([issue.get("title") or "", issue.get("body") or ""], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def refusal(verdict: bd.Verdict, readiness: dict[int, dict] | None = None) -> str | None:
    """Motivo da barreira do intake para uma Issue ja elegivel pelo agendador, ou None."""
    node = verdict.node
    if AUTH_LABEL not in node.labels:
        return f"sem a label `{AUTH_LABEL}` (autorizacao humana)"
    if node.spec not in ALLOWED_SPECS:
        return f"SPEC {node.spec!r} fora de {sorted(ALLOWED_SPECS)}: o intake so aceita orquestracao, nunca geometria/mobiliario"
    if (readiness or {}).get(node.number, {}).get("needs_sketchup") is True:
        return "a auditoria de prontidao diz que exige SketchUp"
    if verdict.action != "implement":
        return f"acao do agendador e {verdict.action!r}, nao 'implement' (retomar ou desbloquear nao e um pedido novo de implementacao)"
    if node.status is not None and node.status != "Ready":
        return f"status do Project e {node.status!r}, nao 'Ready'"
    return None


def plan(issues: list[dict], prs: list[dict], state: dict, statuses: dict[int, str] | None = None,
         readiness: dict[int, dict] | None = None, agent: str = "claude") -> IntakePlan:
    """O candidato do intake: a primeira Issue ELEGIVEL (ordem do agendador) que passa na barreira. Puro."""
    _task, verdicts = ts.decide(issues, prs, state, statuses, None, agent, None)       # readiness=None: ver o docstring do modulo
    skipped, chosen = [], None
    for v in verdicts:
        if not v.eligible:
            continue
        why = refusal(v, readiness)
        if why is None and chosen is None:
            chosen = v
        elif why is not None:
            skipped.append(f"#{v.node.number}: {why}")
    return IntakePlan(chosen, skipped)


def publish_args(verdict: bd.Verdict, issues: list[dict]) -> dict:
    """kwargs de `EventStore.publish` para o pedido de implementacao da Issue escolhida."""
    number = verdict.node.number
    issue = next(i for i in issues if i["number"] == number)
    digest = spec_hash(issue)
    return dict(event_type=EVENT_TYPE, idempotency_key=f"implement:issue:{number}:{digest}", job_id=f"issue:{number}",
                payload={"issue": number, "title": issue.get("title") or "", "spec_hash": digest,
                         "spec": verdict.node.spec, "fase": verdict.node.fase},
                correlation_id=f"intake:issue:{number}", aggregate_type=AGGREGATE, producer=PRODUCER)


def publish(store, verdict: bd.Verdict, issues: list[dict]) -> tuple[int, bool]:
    """(event_id, criado). Idempotente: o mesmo pedido devolve o evento que ja existe."""
    return store.publish(**publish_args(verdict, issues))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("plan", "publish"))
    ap.add_argument("--project", action="store_true", help="le o status do Project (custa cota GraphQL)")
    ap.add_argument("--apply", action="store_true", help="com `publish`: grava o evento; sem isto so planeja")
    a = ap.parse_args(argv)
    issues, statuses, prs = bd.load(statuses=a.project)
    path = es.state_path()
    with es.locked(path):
        state = es.load(path)
    result = plan(issues, prs, state, statuses, bd.load_readiness())               # so para recusar o que a auditoria marcou como SketchUp
    out: dict = {"candidate": None if result.candidate is None else {
        "issue": result.candidate.node.number, "title": result.candidate.node.title}, "skipped": result.skipped}
    if a.cmd == "publish" and a.apply and result.candidate is not None:
        from tools.orchestration.store_factory import get_store
        event_id, created = publish(get_store(), result.candidate, issues)
        out["published"] = {"event_id": event_id, "created": created}
    elif a.cmd == "publish":
        out["published"] = None
        out["note"] = "sem --apply (ou sem candidato): nada foi gravado"
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0 if result.candidate is not None else 1


if __name__ == "__main__":
    sys.exit(main())
