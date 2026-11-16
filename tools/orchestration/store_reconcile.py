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
- Cada evento e VINCULADO ao repositorio de origem (`payload.repo`, gravado pelo bridge): o numero do PR so vale dentro do seu repositorio. Evento de OUTRO
  repositorio (`OTHER_REPO`) ou antigo, sem identidade comprovavel (`UNKNOWN_REPO`), e preservado e reportado, nunca consultado nem aplicado;
- Com o executor JSON consumindo a fila (modo sombra, o padrao), a fila JSON e a dona do trabalho e o SQLite so e atualizado DEPOIS da execucao: um evento
  PENDING cujo item JSON ainda esta ativo (QUEUED/RUNNING/FAILED/BLOCKED_*) NAO e descartado (`JSON_ACTIVE`), e uma fila JSON ilegivel nao autoriza aplicar nada.
  So com `EXECUTOR_SOURCE=sqlite` (o SQLite autoritativo, protegido pelo lease do claim) a aplicacao decide sozinha;
- Falha ao ler o GitHub (rede, 5xx, resposta malformada) vira `ERROR` no relatorio e NAO muda o evento: na duvida o pedido segue como esta;
- Divergencia que nao e segura corrigir sozinha (PR aberto no mesmo HEAD, mas com CI reprovado, por exemplo) e so REPORTADA com codigo;
- Sem `--apply` nada e gravado, nunca."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tools.orchestration import event_bridge as eb
from tools.orchestration import lifecycle
from tools.orchestration.event_store import EventStore
from tools.validation import execution_state as es

EVENT_TYPE = "CORRECTION_REQUESTED"
SHA = re.compile(r"[0-9a-f]{40}")
# DONE_AWAITING_REREVIEW NAO e "terminou": o executor grava esse estado no JSON ANTES de sincronizar DONE para o SQLite; descartar o evento nessa janela perderia o resultado
# efetivo da execucao. So os estados cujo desfecho no store e o mesmo (SUPERSEDED) ou que nunca executaram sao considerados terminados.
FINISHED_JSON = frozenset({"SUPERSEDED", "REFUSED", "PARKED_UNSUPPORTED"})      # estados em que o item JSON nao tem mais trabalho


def sqlite_is_authoritative() -> bool:
    """O SQLite so e a fonte do executor se a variavel pede E o executor REAL sabe consumir dela (`event_executor.sq`, o modulo de claim do SQLite). So a variavel nao basta:
    um executor sem esse caminho continua consumindo a fila JSON, e desligar a protecao dela deixaria descartar um evento enquanto o executor JSON trabalha nele."""
    if os.environ.get("EXECUTOR_SOURCE", "json").strip().lower() != "sqlite":
        return False
    try:
        from tools.orchestration import event_executor as executor
    except Exception:  # noqa: BLE001 — sem como verificar o executor: a protecao da fila JSON fica LIGADA
        return False
    source = getattr(executor, "sq", None)
    return source is not None and callable(getattr(source, "is_sqlite", None)) and bool(source.is_sqlite())


def queue_problem(queue: object) -> str:
    """'' se a fila tem a ESTRUTURA que a protecao precisa (lista de objetos com `kind`, `state`, `pr` inteiro e `head_sha` de texto nos itens de review); senao o motivo.
    `{"queue": null}` ou itens quebrados nao podem virar "fila vazia": sem evidencia de que o executor JSON nao e dono, nada e descartado."""
    if not isinstance(queue, list):
        return "`queue` nao e uma lista"
    for n, i in enumerate(queue):
        if not isinstance(i, dict):
            return f"item #{n} nao e um objeto"
        if i.get("kind") == "review" and (not isinstance(i.get("state"), str) or not isinstance(i.get("head_sha"), str)
                                           or not isinstance(i.get("pr"), int) or isinstance(i.get("pr"), bool)):
            return f"item de review #{n} sem `state`/`head_sha` de texto ou `pr` inteiro"
        if i.get("kind") == "review" and not SHA.fullmatch(i["head_sha"].lower()):
            return f"item de review #{n} com `head_sha` que nao e um SHA completo de 40 hex (identidade do trabalho nao comprovavel)"
        if not isinstance(i.get("kind"), str):
            return f"item #{n} sem `kind`"
    return ""


def json_item_active(queue: list[dict], payload: dict) -> bool:
    """O executor JSON ainda e dono deste pedido? Mesmo PR + mesmo HEAD, em um item de review que nao terminou."""
    head = str(payload.get("head_sha") or "").lower()
    return any(isinstance(i, dict) and i.get("kind") == "review" and i.get("pr") == payload.get("pr") and str(i.get("head_sha") or "").lower() == head
               and i.get("state") not in FINISHED_JSON for i in queue)


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


def valid_pr(pr: object) -> bool:
    """So uma resposta COMPLETA do PR decide algo: objeto com `state` conhecido, `merged` booleano e `head.sha` de 40 hex. `{}` ou `{"state": "open"}` nao
    provam que o pedido esta obsoleto."""
    if not isinstance(pr, dict) or pr.get("state") not in ("open", "closed") or not isinstance(pr.get("merged"), bool):
        return False
    sha = (pr.get("head") or {}).get("sha") if isinstance(pr.get("head"), dict) else None
    return isinstance(sha, str) and bool(SHA.fullmatch(sha.lower()))


def judge(ev: dict, pr: dict) -> tuple[str, str]:
    """(codigo, motivo) para um evento aberto diante do PR no GitHub. Puro. Pre-condicao: `valid_pr(pr)` e `head_sha` do evento valido."""
    p = _payload(ev)
    if pr.get("state") != "open" or pr.get("merged"):
        return "PR_NOT_OPEN", f"PR #{p.get('pr')} nao esta aberto (fechado ou mergeado)"
    head = ((pr.get("head") or {}).get("sha") or "").lower()
    if head != str(p.get("head_sha") or "").lower():
        return "HEAD_MOVED", f"HEAD mudou ({str(p.get('head_sha'))[:8]} -> {head[:8]}): o pedido e do HEAD antigo"
    return "CURRENT", "PR aberto no mesmo HEAD do pedido"


def read_json_queue(path: Path | None = None) -> list[dict]:
    """A fila JSON REAL, sem os padroes de `eb.load()`: arquivo ausente ou objeto sem a chave `queue` viram uma lista vazia la, e uma fila vazia INVENTADA autorizaria
    SUPERSEDED sem prova de que o executor JSON nao tem o trabalho. Aqui o arquivo tem de existir e ter `queue` (lista) explicita; senao e erro (fail-closed)."""
    p = path or eb.bridge_path()
    if not p.is_file():
        raise FileNotFoundError(f"fila JSON ausente: {p.name}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("queue"), list):
        raise ValueError(f"fila JSON sem a chave `queue` (lista): {p.name}")
    return data["queue"]


def reconcile(store: EventStore, gh: eb.Gh, repo: str = eb.REPO, apply: bool = False, json_queue: list[dict] | None = None,
              sqlite_authoritative: bool | None = None) -> dict:
    """Relatorio por evento aberto. Com `apply`, supersede os obsoletos (HEAD_MOVED / PR_NOT_OPEN) cujo dono nao e o executor JSON; o resto so e reportado.
    `json_queue`: a fila JSON consumida (lida do disco se nao for dada). `sqlite_authoritative`: padrao pelo `EXECUTOR_SOURCE`."""
    authoritative = sqlite_is_authoritative() if sqlite_authoritative is None else sqlite_authoritative
    queue, queue_error = json_queue, ""
    if apply and not authoritative and queue is None:
        try:
            queue = read_json_queue()
            problem = queue_problem(queue)
            if problem:
                raise ValueError(problem)
        except (ValueError, OSError, KeyError, TypeError) as exc:                                              # ilegivel/invalida: fail-closed, nada e aplicado
            queue, queue_error = [], f"fila JSON ilegivel ou invalida ({type(exc).__name__}: {str(exc)[:80]}): nada e aplicado"
    elif apply and not authoritative and queue is not None and queue_problem(queue):
        queue, queue_error = [], f"fila JSON invalida ({queue_problem(queue)}): nada e aplicado"
    rows = []
    for ev in open_events(store):
        p = _payload(ev)
        row = {"event": ev["id"], "key": ev["idempotency_key"], "pr": p.get("pr")}
        event_repo = p.get("repo")
        if not isinstance(event_repo, str) or not event_repo:
            rows.append({**row, "code": "UNKNOWN_REPO", "detail": "evento sem identidade de repositorio (anterior ao vinculo): preservado, nao consultado"})
            continue
        if event_repo.lower() != repo.lower():
            rows.append({**row, "code": "OTHER_REPO", "detail": f"evento do repositorio {event_repo!r}, nao de {repo!r}: preservado, nao consultado"})
            continue
        if not isinstance(p.get("pr"), int) or isinstance(p.get("pr"), bool) or not isinstance(p.get("head_sha"), str) \
                or not SHA.fullmatch(p["head_sha"].lower()):
            rows.append({**row, "code": "MALFORMED", "detail": "payload sem PR inteiro ou sem head_sha valido: obsolescencia nao comprovavel; fica como esta"})
            continue
        try:
            pr = gh(f"repos/{repo}/pulls/{p['pr']}")
            if not valid_pr(pr):
                raise RuntimeError("resposta do PR incompleta ou malformada (state/merged/head.sha): nada e decidido")
            code, detail = judge(ev, pr)
            ci = None
            if code == "CURRENT":
                ci = lifecycle.checks_state(lifecycle._check_runs(gh, repo, pr["head"]["sha"]))
        except (RuntimeError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:      # inclui TimeoutExpired: erro do evento, o resto segue
            rows.append({**row, "code": "ERROR", "detail": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        row.update(code=code, detail=detail)
        if ci is not None:
            row["ci"] = ci
            if ci == "failed":
                row["code"], row["detail"] = "CURRENT_CI_FAILED", "PR aberto no mesmo HEAD, com checks reprovados: so reportado (corrigir e do executor/humano)"
        if apply and code in ("HEAD_MOVED", "PR_NOT_OPEN"):
            if queue_error:
                row["applied"], row["skipped_because"] = "SKIPPED", queue_error
            elif not authoritative and json_queue is None:
                # a fila foi lida ANTES da consulta ao GitHub e sem a trava do bridge: o bridge publica no SQLite antes de salvar a fila JSON, entao uma copia velha pode nao ter
                # o item que o executor JSON ja comecou. A decisao e a transicao no SQLite acontecem SOB a trava compartilhada, com a fila RELIDA e validada.
                try:
                    with es.locked(eb.bridge_path()):
                        fresh = read_json_queue()
                        problem = queue_problem(fresh)
                        if problem:
                            raise ValueError(problem)
                        if json_item_active(fresh, p):
                            row["applied"], row["skipped_because"] = "SKIPPED", "JSON_ACTIVE: o executor JSON ainda e dono do item; o resultado sera sincronizado depois da execucao"
                        else:
                            row["applied"] = _supersede(store, ev, detail)
                except (ValueError, OSError, KeyError, TypeError, TimeoutError) as exc:
                    row["applied"], row["skipped_because"] = "SKIPPED", f"fila JSON ilegivel, invalida ou trava ocupada ({type(exc).__name__}: {str(exc)[:80]}): nada e aplicado"
            elif not authoritative and json_item_active(queue or [], p):
                row["applied"], row["skipped_because"] = "SKIPPED", "JSON_ACTIVE: o executor JSON ainda e dono do item; o resultado sera sincronizado depois da execucao"
            else:
                row["applied"] = _supersede(store, ev, detail)
        rows.append(row)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["code"]] = counts.get(r["code"], 0) + 1
    return {"applied": apply, "counts": counts, "events": rows}


def _supersede(store: EventStore, ev: dict, reason: str) -> str:
    """'SUPERSEDED' | 'SKIPPED' (o evento ganhou um dono vivo ou ja mudou de estado). Operacao delimitada a ESTE evento (`supersede_obsolete`): nao reivindica nem
    faz a limpeza global de eventos alheios que o claim faz; inclui eventos em backoff de retry."""
    return "SUPERSEDED" if store.supersede_obsolete(ev["id"], f"reconciliado: {reason}") else "SKIPPED"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="supersede os eventos obsoletos; sem isto so planeja")
    ap.add_argument("--repo", default=eb.REPO)
    a = ap.parse_args(argv)
    from tools.orchestration.store_factory import get_store, store_path
    if a.apply:
        store = get_store()
    else:                                                                   # o plano NUNCA grava: nem cria o banco, nem o esquema
        try:
            store = EventStore.open_existing(store_path())
        except FileNotFoundError:
            print(json.dumps({"applied": False, "counts": {}, "events": [], "store": "ausente (nada foi criado)"}, indent=1, ensure_ascii=False))
            return 0
    report = reconcile(store, eb.gh_json, a.repo, a.apply)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if report["counts"].get("ERROR") else 0


if __name__ == "__main__":
    sys.exit(main())
