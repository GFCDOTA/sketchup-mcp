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
import re
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
INTAKE_AGENT = None                     # SEM nome: `decide` exclui dos conflitos so os claims do agente dado, e nenhum claim tem agente None => todo claim ativo (de qualquer nome, inclusive "intake") e externo


@dataclass
class IntakePlan:
    candidate: bd.Verdict | None
    skipped: list[str] = field(default_factory=list)                 # "#N: motivo" para cada Issue elegivel que a barreira recusou


def spec_hash(issue: dict) -> str:
    """Identifica o PEDIDO (titulo + corpo). Editar a Issue muda o hash; reler a mesma Issue nao."""
    raw = json.dumps([issue.get("title") or "", issue.get("body") or ""], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def refusal(verdict: bd.Verdict, readiness: dict[int, dict] | None = None, project_known: bool = False, known: frozenset[int] | None = None) -> str | None:
    """Motivo da barreira do intake para uma Issue ja elegivel pelo agendador, ou None. `project_known`: o Project FOI consultado (entao a Issue ausente do resultado ou
    sem status NAO esta em `Ready`). `known`: numeros das Issues carregadas (dependencia fora dela = nao comprovada)."""
    node = verdict.node
    if node.number in node.deps:
        return f"a Issue #{node.number} depende dela mesma: dependencia reflexiva nunca e concluida"
    if known is not None:
        missing = sorted(d for d in node.deps if d != node.number and d not in known)
        if missing:
            return "dependencia(s) " + ", ".join(f"#{d}" for d in missing) + " nao carregada(s): conclusao nao comprovada (a lista de Issues pode estar truncada ou a referencia e invalida)"
    if AUTH_LABEL not in node.labels:
        return f"sem a label `{AUTH_LABEL}` (autorizacao humana)"
    if node.spec not in ALLOWED_SPECS:
        return f"SPEC {node.spec!r} fora de {sorted(ALLOWED_SPECS)}: o intake so aceita orquestracao, nunca geometria/mobiliario"
    entry = (readiness or {}).get(node.number) or {}
    if str(entry.get("state", "")).upper() == "BLOCKED":                    # ausencia de registro e permitida; um registro AUDITADO como bloqueado (humano/ambiente/outro) nunca
        return "a auditoria de prontidao registra a Issue como BLOCKED: nao ha passo executavel pronto"
    if entry.get("needs_sketchup") is True:
        return "a auditoria de prontidao diz que exige SketchUp"
    if verdict.action != "implement":
        return f"acao do agendador e {verdict.action!r}, nao 'implement' (retomar ou desbloquear nao e um pedido novo de implementacao)"
    if project_known and node.status != "Ready":
        return f"status do Project e {node.status!r}, nao 'Ready'" if node.status is not None else "o Project foi consultado mas a Issue nao tem status (ausente do Project): nao esta em 'Ready'"
    if node.status is not None and node.status != "Ready":
        return f"status do Project e {node.status!r}, nao 'Ready'"
    return None


# todas as formas com que um PR aponta uma Issue no GitHub (palavras de fechamento) e as do projeto (`Refs`, `Relates to`); `#N` em lista conta cada numero
_LINK = re.compile(r"\b(?:refs?|relates?\s+to|close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*((?:#\d+(?:\s*(?:,|\band\b|\be\b)\s*)?)+)", re.I)


def linked_issues(body: str | None) -> set[int]:
    return {int(n) for grp in _LINK.findall(body or "") for n in re.findall(r"#(\d+)", grp)}


def _ui_links(pr: dict) -> set[int]:
    """Vinculos feitos pela interface do GitHub (barra lateral "Development"): nao aparecem no corpo, vem em `closingIssuesReferences`."""
    return {int(r["number"]) for r in (pr.get("closingIssuesReferences") or []) if isinstance(r, dict) and isinstance(r.get("number"), int)}


def open_pr_for(prs: list[dict], number: int) -> int | None:
    """Um PR ABERTO ja vinculado a Issue (palavra no corpo OU vinculo manual na interface): nunca um pedido novo por cima."""
    return next((int(p["number"]) for p in prs if number in linked_issues(p.get("body")) | _ui_links(p)), None)


def plan(issues: list[dict], prs: list[dict], state: dict, statuses: dict[int, str] | None = None,
         readiness: dict[int, dict] | None = None, agent: str | None = INTAKE_AGENT) -> IntakePlan:
    """O candidato do intake: a primeira Issue ELEGIVEL (ordem do agendador) que passa na barreira. Puro."""
    _task, verdicts = ts.decide(issues, prs, state, statuses, None, agent, None)       # readiness=None: ver o docstring do modulo
    skipped, chosen = [], None
    known = frozenset(int(i["number"]) for i in issues)
    for v in verdicts:
        if not v.eligible:
            continue
        why = refusal(v, readiness, project_known=statuses is not None, known=known)
        if why is None and (linked := open_pr_for(prs, v.node.number)) is not None:
            why = f"o PR #{linked} (aberto) ja esta vinculado a Issue #{v.node.number}: nao e um pedido novo de implementacao"
        if why is None and v.node.number in es.active_claims(state):                 # qualquer claim ATIVO na Issue, de qualquer agente: nunca um pedido novo por cima
            why = f"a Issue #{v.node.number} tem claim ativo de {state['claims'][str(v.node.number)].get('agent')!r}: nao e um pedido novo de implementacao"
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
    if len(issues) >= bd.LOAD_LIMIT or len(prs) >= bd.LOAD_LIMIT:                  # lista possivelmente TRUNCADA: um PR/Issue omitido poderia liberar trabalho duplicado
        print(json.dumps({"candidate": None, "skipped": [], "error": f"lista de Issues/PRs atingiu o limite de {bd.LOAD_LIMIT}: possivelmente truncada, nada e publicado"}))
        return 2
    path = es.state_path()
    readiness = bd.load_readiness()                                                 # so para recusar o que a auditoria marcou como SketchUp
    # a trava do estado de execucao vale da LEITURA dos claims ate a GRAVACAO do pedido: um claim concorrente (executor reivindicando a Issue ou o componente) nao pode
    # entrar entre a decisao e a publicacao. A trava e curta (le um JSON, grava uma linha SQLite); o que e lento (gh) ja foi lido antes.
    # A trava do estado de execucao e CURTA (espera 5 s; uma trava com mais de 60 s e tida como abandonada): NADA lento (gh) roda dentro dela. Ordem:
    #   1) le os claims sob a trava e planeja; 2) RELE o GitHub FORA da trava; 3) sob a trava: rele os claims, decide de novo com os fatos novos e grava;
    #   4) pos-checagem: um PR vinculado que abriu entre a releitura e a gravacao descarta o pedido (supersede). Janela residual: entre (2) e (4), coberta por (4).
    with es.locked(path):
        state = es.load(path)
    result = plan(issues, prs, state, statuses, readiness)
    out: dict = {"candidate": None if result.candidate is None else {
        "issue": result.candidate.node.number, "title": result.candidate.node.title}, "skipped": result.skipped}
    if a.cmd == "publish" and a.apply and result.candidate is not None:
        fresh_issues, fresh_statuses, fresh_prs = bd.load(statuses=a.project)              # o status do Project tambem e RELIDO: Ready pode ter saido no meio
        if len(fresh_issues) >= bd.LOAD_LIMIT or len(fresh_prs) >= bd.LOAD_LIMIT:
            out.update(published=None, note=f"a revalidacao atingiu o limite de {bd.LOAD_LIMIT} (lista possivelmente truncada): nada foi publicado")
            print(json.dumps(out, indent=1, ensure_ascii=False))
            return 2
        from tools.orchestration.store_factory import get_store
        with es.locked(path):
            again = plan(fresh_issues, fresh_prs, es.load(path), fresh_statuses if a.project else None, readiness)
            if again.candidate is None or again.candidate.node.number != result.candidate.node.number:
                out["published"] = None
                out["note"] = "a revalidacao mudou o candidato (PR novo, claim ou Issue alterada): nada foi publicado"
                out["revalidated_skipped"] = again.skipped
                print(json.dumps(out, indent=1, ensure_ascii=False))
                return 1
            store = get_store()
            event_id, created = publish(store, again.candidate, fresh_issues)
        out["published"] = {"event_id": event_id, "created": created}
        _i, _s, after_prs = bd.load(statuses=False)
        linked = open_pr_for(after_prs, again.candidate.node.number)
        if linked is not None:                                                            # recem-criado OU identico ja PENDING: o PR vinculado vence os dois
            owned = store.claim_by_id(event_id, "intake:post-check", 30.0)                # so pega evento ainda reivindicavel (PENDING); um ja em execucao fica com o executor
            if owned is not None:
                store.supersede(owned, f"o PR #{linked} foi vinculado a Issue enquanto o pedido era gravado: descartado")
                out["superseded"] = {"event_id": event_id, "pr": linked}
    elif a.cmd == "publish":
        out["published"] = None
        out["note"] = "sem --apply (ou sem candidato): nada foi gravado"
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0 if result.candidate is not None else 1


if __name__ == "__main__":
    sys.exit(main())
