"""pr_lifecycle.py — ciclo padrao dos PRs tecnicos: pronto -> revisao do Codex -> correcao -> aprovacao -> merge protegido (FP-060, criterio de aceite).

    python -m tools.orchestration.pr_lifecycle cycle [--execute]        # um ciclo: prepara, enfileira, revisa UM PR
    python -m tools.orchestration.pr_lifecycle run --interval 30 [--execute] [--watch-pid PID]

NAO e outra arquitetura: reutiliza o EventStore (eventos `REVIEW_REQUESTED`, idempotencia, lease/fencing, DLQ), o `codex_reviewer` (sessao REAL do Codex CLI
com sandbox, publicacao pelo Outbox como `fmmodesto`), o `auto_merge` (gather/decisao/merge protegido), o `event_bridge` (um review CHANGES_REQUESTED vira
`CORRECTION_REQUESTED` para o Claude) e o `lifecycle` (estado dos checks e review no HEAD). Este modulo so liga as pontas que faltavam:

  PREPARAR   PR do executor (nao-fork, base develop, `Refs #N`) e PRONTO quando: Issue citada aberta e sem decisao humana, sem label humana, sem caminho de
             governanca, sem dependencia aberta (PR empilhado: o HEAD de outro PR aberto esta nos seus commits, ou `Empilhado sobre #N` no corpo) e checks
             obrigatorios VERDES no HEAD. Pronto + rascunho => `gh pr ready`. Fora do rascunho e sem revisao pendente => solicita o revisor independente.
             Excecoes (decisao humana, dependencia aberta, sem Issue) ficam como estao e sao REPORTADAS com o motivo.
  ENFILEIRAR PR fora do rascunho com o revisor solicitado OU sem review dele no HEAD atual (solicitacao perdida) => `REVIEW_REQUESTED` no EventStore,
             chave `review-request:<repo>#<PR>:<HEAD>` (deduplica por repositorio, PR e HEAD; HEAD novo = evento novo = nova revisao independente).
  REVISAR    um por ciclo: so com os checks obrigatorios VERDES no HEAD (pendente espera; reprovado descarta o pedido: o HEAD de correcao gera outro). Reivindica
             com lease + heartbeat, chama o `codex_reviewer` (APPROVE/REQUEST_CHANGES publicado como `fmmodesto` pelo Outbox) e conclui, descarta ou falha o evento.
  O QUE VEM DEPOIS e da infraestrutura existente: REQUEST_CHANGES -> bridge -> `CORRECTION_REQUESTED` -> Claude -> novo commit -> novo HEAD -> novo pedido
             aqui; APPROVE -> `auto_merge` (decisao + protecao da branch exigindo aprovacao independente).
Nada aqui altera protecao de branch, labels, politica ou workflows. Sem `--execute` nada e gravado nem chamado com efeito."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from tools.orchestration import auto_merge as am
from tools.orchestration import event_bridge as eb
from tools.orchestration import execution_guards as guards
from tools.orchestration import lifecycle
from tools.orchestration import rate_limit as rl
from tools.orchestration.event_store import EventStore, LeaseLost

EVENT_TYPE = "REVIEW_REQUESTED"
PRODUCER = "review_dispatch"                              # os eventos de PUBLICACAO do codex_reviewer tambem sao REVIEW_REQUESTED (producer proprio): nunca se misturam
LEASE_S = 300.0
HEARTBEAT_S = 60.0
MAX_ATTEMPTS = 5
NEEDS_HUMAN_TRIES = 2                                     # NEEDS_HUMAN e um VEREDITO, nao uma falha: uma repeticao (o Codex e nao deterministico), depois escala sem gastar o resto
RETRY_S = 120.0
FACTS_TTL_S = 600.0
RECHECK_S = 90.0                                          # um evento que esperou os checks (ou deu erro) so e consultado de novo depois disto: poupa a cota da API (5000/h)
_RECHECK_AT: dict[int, float] = {}
REFS = re.compile(r"\brefs?\s*:?\s*#(\d+)", re.I)
DEP_TEXT = re.compile(r"(?:empilhad[oa]\s+sobre|depends?\s+on|depende\s+de|stacked\s+on)\s+((?:#\d+\s*(?:,|\+|&|\be\b|\band\b)?\s*)+)", re.I)
Runner = Callable[..., "subprocess.CompletedProcess"]
_FACTS: dict[tuple, tuple[float, dict]] = {}


def kill_switch() -> Path:
    """O interruptor do ciclo: este arquivo ao lado do estado do bridge para tudo (nenhuma escrita no GitHub, nenhum evento novo, nenhuma revisao nova). Os
    reviews JA em andamento terminam e publicam (um parecer pela metade nao e melhor que um completo)."""
    return eb.bridge_path().with_name("PR_LIFECYCLE_DISABLED")


def request_key(repo: str, number: int, head: str) -> str:
    return f"review-request:{repo}#{int(number)}:{head.lower()}"


def reviewer_login(policy: dict) -> str | None:
    reviewers = policy.get("reviewers") or []
    return reviewers[0] if reviewers else None


def refs_of(body: str | None) -> list[int]:
    return sorted({int(n) for n in REFS.findall(body or "")})


def dependencies(number: int, body: str | None, commit_shas: set[str], open_heads: dict[int, str]) -> set[int]:
    """PRs ABERTOS dos quais este depende: o HEAD de outro PR aberto esta entre os seus commits (empilhamento real) ou o corpo diz `Empilhado sobre #N`.
    PR ja mergeado ou fechado nao e dependencia."""
    structural = {n for n, h in open_heads.items() if n != number and h.lower() in commit_shas}
    named = {int(n) for chunk in DEP_TEXT.findall(body or "") for n in re.findall(r"#(\d+)", chunk)}
    return structural | (named & set(open_heads) - {number})


def classify(pr: dict, files: list[dict], issues: dict[int, dict], deps_open: set[int]) -> tuple[str, list[str]]:
    """('READY'|'HUMAN'|'BLOCKED_DEPENDENCY'|'NO_ISSUE', motivos). Puro. Mesmas regras de decisao humana do `auto_merge`."""
    refs = refs_of(pr.get("body"))
    if not refs:
        return "NO_ISSUE", ["PR sem `Refs #N`"]
    bad = [f"Issue #{n} inexistente ou fechada" for n in refs if not isinstance(issues.get(n), dict) or issues[n].get("state") != "open"]
    if bad:
        return "NO_ISSUE", bad
    human = {x.casefold() for x in am.HUMAN_LABELS}
    reasons = []
    labels = {str(n).casefold() for n in am._names(pr.get("labels"))}
    if labels & human:
        reasons.append(f"label de decisao humana no PR ({', '.join(sorted(labels & human))})")
    for n in refs:
        il = {str(x).casefold() for x in am._names(issues[n].get("labels"))}
        if il & human:
            reasons.append(f"Issue #{n} com decisao humana pendente ({', '.join(sorted(il & human))})")
    hard = tuple(x.casefold() for x in am.HARD_HUMAN_PREFIXES)
    for f in files:
        for name in (f.get("filename"), f.get("previous_filename")):
            if not name:
                continue
            try:
                if guards.norm(str(name)).startswith(hard):
                    reasons.append(f"governanca: {name}")
            except ValueError:
                reasons.append(f"caminho invalido: {name!r}")
    if reasons:
        return "HUMAN", sorted(set(reasons))
    if deps_open:
        return "BLOCKED_DEPENDENCY", [f"depende de PR(s) ainda aberto(s): {', '.join('#%d' % n for n in sorted(deps_open))}"]
    return "READY", []


def _facts(gh: eb.Gh, repo: str, number: int, head: str, now: float) -> dict:
    """Fatos CAROS de um PR (arquivos, Issues, commits), por (PR, HEAD) com validade curta: o ciclo de 30 s nao refaz dezenas de chamadas a cada volta."""
    key = (repo, number, head.lower())
    hit = _FACTS.get(key)
    if hit and now - hit[0] < FACTS_TTL_S:
        return hit[1]
    pr, files, _runs, _reviews, issues = am.gather(gh, repo, number)
    commits = {c["sha"].lower() for c in am.complete_list(gh, f"repos/{repo}/pulls/{number}/commits?per_page=100") if isinstance(c.get("sha"), str)}
    facts = {"pr": pr, "files": files, "issues": issues, "commits": commits}
    _FACTS[key] = (now, facts)
    return facts


LIST_TTL_S = 20.0
REVIEWS_TTL_S = 120.0
_LIST_CACHE: dict[str, tuple[float, list[dict]]] = {}
_REVIEWS_CACHE: dict[tuple, tuple[float, list[dict]]] = {}


def open_prs(gh: eb.Gh, repo: str) -> list[dict]:
    """Os PRs abertos: UMA chamada paginada por ciclo (prepare e enqueue compartilham; antes eram 3 por ciclo de 30 s)."""
    hit = _LIST_CACHE.get(repo)
    if hit and time.monotonic() - hit[0] < LIST_TTL_S:
        return hit[1]
    data = am.complete_list(gh, f"repos/{repo}/pulls?state=open&per_page=100")
    _LIST_CACHE[repo] = (time.monotonic(), data)
    return data


def reviews_of(gh: eb.Gh, repo: str, number: int, head: str) -> list[dict]:
    """Os reviews do PR, em cache por (PR, HEAD) por alguns minutos: o HEAD novo invalida sozinho; a cota da API (5000/h) nao aguenta 1 chamada por PR a cada 30 s."""
    key = (repo, number, head.lower())
    hit = _REVIEWS_CACHE.get(key)
    if hit and time.monotonic() - hit[0] < REVIEWS_TTL_S:
        return hit[1]
    data = am.complete_list(gh, f"repos/{repo}/pulls/{number}/reviews?per_page=100")
    _REVIEWS_CACHE[key] = (time.monotonic(), data)
    return data


def candidates(gh: eb.Gh, policy: dict, repo: str) -> list[dict]:
    """PRs abertos do EXECUTOR, nao-fork, base develop."""
    executors = set(policy.get("executor_logins", []))
    return [p for p in open_prs(gh, repo)
            if (p.get("user") or {}).get("login") in executors and (p.get("base") or {}).get("ref") == am.BASE_BRANCH
            and ((p.get("head") or {}).get("repo") or {}).get("full_name") == repo]


def _requested(pr: dict) -> set[str]:
    return {str(r.get("login", "")).lower() for r in (pr.get("requested_reviewers") or []) if isinstance(r, dict)}


# ----------------------------------------------------------------------------------------------------------------------- preparar
def prepare(gh: eb.Gh, policy: dict, repo: str = eb.REPO, execute: bool = False, runner: Runner = subprocess.run, now: float | None = None) -> list[dict]:
    """Tira do rascunho o PR PRONTO e solicita o revisor independente. Devolve uma linha por PR (acao e motivo). So escreve com `execute`, e so depois de
    verificar que o `gh` e o executor (mesma checagem do merge)."""
    now = time.time() if now is None else now
    reviewer = reviewer_login(policy)
    cands = candidates(gh, policy, repo)
    open_heads = {p["number"]: (p.get("head") or {}).get("sha", "") for p in open_prs(gh, repo)}
    identity: tuple[bool, str] | None = None
    rows = []
    for cand in cands:
        n, head = cand["number"], (cand.get("head") or {}).get("sha", "")
        row: dict = {"pr": n, "head": head[:12], "draft": bool(cand.get("draft"))}
        try:
            facts = _facts(gh, repo, n, head, now)
            deps = dependencies(n, cand.get("body"), facts["commits"], open_heads)
            code, reasons = classify(facts["pr"], facts["files"], facts["issues"], deps)
            row.update(code=code, reasons=reasons)
            if cand.get("draft"):
                if code != "READY":
                    row["action"] = "KEEP_DRAFT"
                    rows.append(row)
                    continue
                runs = am.complete_check_runs(gh, repo, head)
                state = lifecycle.checks_state(runs)
                if state != "passed":
                    row.update(action="KEEP_DRAFT", reasons=[f"checks obrigatorios {state} no HEAD"])
                    rows.append(row)
                    continue
                row["action"] = "READY"
                if execute:
                    identity = identity or am.merge_identity(policy, runner)
                    row["done"] = _gh_write(identity, runner, ["pr", "ready", str(n), "--repo", repo])
                rows.append(row)
                continue
            if reviewer and reviewer.lower() not in _requested(cand):
                reviews = reviews_of(gh, repo, n, head)
                if lifecycle.latest_review(reviews, head, policy) is None:
                    row["action"] = "REQUEST_REVIEW"
                    if execute:
                        identity = identity or am.merge_identity(policy, runner)
                        row["done"] = _gh_write(identity, runner, ["api", "-X", "POST", f"repos/{repo}/pulls/{n}/requested_reviewers", "-f", f"reviewers[]={reviewer}"])
                    rows.append(row)
                    continue
            row["action"] = "NONE"
        except (RuntimeError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            row.update(code="ERROR", reasons=[f"{type(exc).__name__}: {exc}"[:200]], action="NONE")
        rows.append(row)
    return rows


def _gh_write(identity: tuple[bool, str], runner: Runner, args: list[str]) -> bool | str:
    """Uma escrita no GitHub com a identidade do executor e o ambiente SEM tokens de env (o `gh` do keyring). Identidade invalida = nao escreve."""
    if not identity[0]:
        return f"recusado: {identity[1]}"
    from tools.orchestration import event_executor as ex
    try:
        done = runner([am.gh_bin(), *args], env=ex.executor_env(), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"falhou: {type(exc).__name__}"
    return True if done.returncode == 0 else f"falhou: {ex.redact((done.stderr or done.stdout or '')[:200])}"


# --------------------------------------------------------------------------------------------------------------------- enfileirar
def enqueue(gh: eb.Gh, store: EventStore | None, policy: dict, repo: str = eb.REPO, execute: bool = False) -> list[dict]:
    """PR fora do rascunho, com `Refs #N`, com o revisor solicitado OU sem review dele no HEAD atual => `REVIEW_REQUESTED` (idempotente por repo/PR/HEAD).
    Pedidos PENDENTES de um HEAD que ja andou (ou de PR fechado) sao descartados: so o HEAD atual vale."""
    reviewer = (reviewer_login(policy) or "").lower()
    cands = [p for p in candidates(gh, policy, repo) if not p.get("draft")]
    current = {p["number"]: (p.get("head") or {}).get("sha", "").lower() for p in cands}
    rows = []
    if execute and store is not None:                                                                  # descarta o obsoleto antes de criar o novo
        for ev in store.events():
            if ev["producer"] == PRODUCER and ev["event_type"] == EVENT_TYPE and ev["status"] == "PENDING":
                p = _payload(ev)
                if current.get(p.get("pr")) != str(p.get("head_sha", "")).lower():
                    owned = store.claim_by_id(ev["id"], f"obsolete:{uuid.uuid4().hex[:8]}", 30.0)
                    if owned is not None:
                        store.supersede(owned, "HEAD do PR mudou ou PR nao esta mais aberto/pronto: so o HEAD atual vale")
                        rows.append({"event": ev["id"], "action": "SUPERSEDED_OBSOLETE"})
    for pr in cands:
        n, head = pr["number"], (pr.get("head") or {}).get("sha", "").lower()
        if not refs_of(pr.get("body")):
            continue
        key = request_key(repo, n, head)
        if store is not None and any(e["idempotency_key"] == key for e in store.events(job_id=f"pr:{n}")):
            continue                                                                                    # ja existe para este HEAD (qualquer estado): nada a fazer, nada a consultar
        asked = reviewer in _requested(pr)
        if not asked:
            reviews = reviews_of(gh, repo, n, head)
            if lifecycle.latest_review(reviews, head, policy) is not None:
                continue                                                                                # ja revisado neste HEAD
        row = {"pr": n, "head": head[:12], "requested": asked, "action": "ENQUEUE"}
        if execute and store is not None:
            event_id, created = store.publish(EVENT_TYPE, key, f"pr:{n}", {"repo": repo, "pr": n, "head_sha": head}, producer=PRODUCER, max_attempts=MAX_ATTEMPTS)
            row.update(event=event_id, created=created)
        rows.append(row)
    return rows


def _payload(ev: dict) -> dict:
    p = ev.get("payload")
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except ValueError:
            return {}
    return p if isinstance(p, dict) else {}


# ------------------------------------------------------------------------------------------------------------------------- revisar
class _Heartbeat(threading.Thread):
    def __init__(self, store: EventStore, ev: dict, interval: float):
        super().__init__(daemon=True, name=f"review-lease-{ev['id']}")
        self.store, self.ev, self.interval, self._stop_evt, self.lost = store, ev, interval, threading.Event(), False

    def run(self) -> None:
        while not self._stop_evt.wait(self.interval):
            try:
                if not self.store.renew(self.ev, LEASE_S):
                    self.lost = True
                    return
            except Exception:  # noqa: BLE001 — um erro de leitura do banco nao pode matar a revisao; o proximo tick tenta de novo
                continue

    def stop(self) -> None:
        self._stop_evt.set()


def work(gh: eb.Gh, store: EventStore, policy: dict, repo: str = eb.REPO, review: Callable[..., dict] | None = None, owner: str | None = None,
         heartbeat_s: float = HEARTBEAT_S) -> dict:
    """Revisa UM PR: o evento PENDING mais antigo cujo PR esta aberto, no HEAD do pedido e com os checks obrigatorios VERDES. Nunca lanca."""
    if kill_switch().exists():
        return {"action": "IDLE", "disabled": f"interruptor {kill_switch().name} presente"}
    owner = owner or f"review-worker:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    now = store.clock()
    gate, account = rl.RateLimitGate(store), rl.account_key(policy)
    blocked = gate.peek(account, owner, now)
    if blocked is not None:                                                                             # conta do revisor suspensa (limite de uso/autenticacao): nenhuma chamada, nenhum lease
        return {"action": "IDLE", "suspended": blocked.as_dict()}
    # PENDING, ou RUNNING com o lease VENCIDO (o worker morreu no meio da revisao: o evento volta ao pool; o EventStore cerca o resultado do dono antigo)
    pending = [e for e in store.events() if e["producer"] == PRODUCER and e["event_type"] == EVENT_TYPE
               and (e["status"] == "PENDING" or (e["status"] == "RUNNING" and e["lease_until"] <= now))]
    waiting = []
    for ev in pending:
        if _RECHECK_AT.get(ev["id"], 0.0) > time.monotonic():
            continue                                                                                    # esperou ha pouco: nao refaz 2 chamadas por evento a cada tick
        p = _payload(ev)
        n, head = p.get("pr"), str(p.get("head_sha", "")).lower()
        try:
            pr = gh(f"repos/{repo}/pulls/{n}")
            cur = ((pr.get("head") or {}).get("sha") or "").lower()
            if pr.get("state") != "open" or cur != head:
                owned = store.claim_by_id(ev["id"], owner, 30.0)
                if owned is not None:
                    store.supersede(owned, f"PR #{n} {'fechado' if pr.get('state') != 'open' else 'com HEAD novo'}: so o HEAD atual vale")
                continue
            state = lifecycle.checks_state(am.complete_check_runs(gh, repo, head))
        except (RuntimeError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            waiting.append({"event": ev["id"], "pr": n, "action": "ERROR", "reason": f"{type(exc).__name__}: {exc}"[:200]})
            _RECHECK_AT[ev["id"]] = time.monotonic() + RECHECK_S * (2 if "rate limit" in str(exc).lower() else 1)
            continue
        if state == "failed":
            owned = store.claim_by_id(ev["id"], owner, 30.0)
            if owned is not None:
                store.supersede(owned, "checks obrigatorios reprovados: nada a revisar; a correcao gera outro HEAD e outro pedido")
            continue
        if state != "passed":
            waiting.append({"event": ev["id"], "pr": n, "action": "WAIT_CHECKS", "reason": f"checks obrigatorios {state}"})
            _RECHECK_AT[ev["id"]] = time.monotonic() + RECHECK_S
            continue
        try:                                                                                            # RECONCILIA antes de gastar a conta: parecer ja publicado neste HEAD => nao revisa de novo
            fresh = am.complete_list(gh, f"repos/{repo}/pulls/{n}/reviews?per_page=100")                   # leitura nova (sem cache): o review pode ter saido ha segundos
            done = lifecycle.latest_review(fresh, head, policy)
        except (RuntimeError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            waiting.append({"event": ev["id"], "pr": n, "action": "ERROR", "reason": f"reviews: {type(exc).__name__}: {exc}"[:200]})
            _RECHECK_AT[ev["id"]] = time.monotonic() + RECHECK_S
            continue                                                                                    # sem conseguir verificar, nao arrisca um parecer duplicado
        if done is not None:
            owned = store.claim_by_id(ev["id"], owner, 30.0)
            if owned is not None:
                verdict = "APPROVE" if done.get("state") == "APPROVED" else "REQUEST_CHANGES"
                store.complete(owned, {"action": "DONE", "verdict": verdict, "reconciled": True, "review_id": done.get("id"),
                                       "reason": "parecer do revisor ja publicado neste HEAD: nenhuma revisao duplicada"})
                return {"action": "RECONCILED", "event": ev["id"], "pr": n, "verdict": verdict, "review_id": done.get("id")}
            continue
        admission = gate.admit(account, owner, now)                                                     # HEAD e checks JA revalidados acima: so entao a conta pode ser sondada
        if not admission.allowed:
            return {"action": "IDLE", "suspended": admission.block.as_dict() if admission.block else {}}
        claimed = store.claim_by_id(ev["id"], owner, LEASE_S)
        if claimed is None:
            if admission.probe:
                gate.release_probe(account, owner)
            continue                                                                                    # outro worker (ou lease vivo): nao toca
        return _review(store, claimed, gh, policy, repo, review, heartbeat_s, gate, account, owner, admission.probe)
    return {"action": "IDLE", "waiting": waiting}


def _review(store: EventStore, ev: dict, gh: eb.Gh, policy: dict, repo: str, review: Callable[..., dict] | None, heartbeat_s: float,
            gate: rl.RateLimitGate | None = None, account: str = "", owner: str = "", probe: bool = False) -> dict:
    n = _payload(ev).get("pr")
    gate = gate or rl.RateLimitGate(store)
    account = account or rl.account_key(policy)
    if review is None:
        from tools.orchestration import codex_reviewer
        review = codex_reviewer.review_pr
    hb = _Heartbeat(store, ev, heartbeat_s)
    hb.start()
    try:
        result = review(n, gh, policy, repo, do_publish=True)
    except Exception as exc:  # noqa: BLE001 — a sessao do Codex falhou: o evento volta com atraso, nunca fica RUNNING
        result = {"action": "FAILED", "reason": f"{type(exc).__name__}: {exc}"[:300]}
    finally:
        hb.stop()
    action = result.get("action")
    try:
        # estado da CONTA antes do estado do evento: um limite de uso suspende a conta e o evento ESPERA sem gastar tentativa; so uma execucao terminada prova que a cota voltou
        if action == "RATE_LIMITED":
            failure = rl.Failure(rl.USAGE_LIMIT, "limite de uso da conta do revisor", result.get("reset_at"), bool(result.get("ambiguous")))
            block = gate.record_block(account, failure)
            store.defer(ev, f"RATE_LIMITED: {str(result.get('reason') or '')[:240]}", block.until)
            row = {"action": "RATE_LIMITED", "event": ev["id"], "pr": n, "suspended": block.as_dict()}
            return row
        if result.get("codex_ran"):
            gate.record_success(account)
        elif result.get("kind") == rl.AUTH:
            gate.record_block(account, rl.Failure(rl.AUTH, "falha de autenticacao do revisor"))
        elif probe:
            gate.release_probe(account, owner)
        if action == "DONE":
            v = result.get("verdict")
            store.complete(ev, {"action": "DONE", "verdict": v.get("verdict") if isinstance(v, dict) else v, "url": result.get("url"),
                                "findings": len(v.get("findings") or []) if isinstance(v, dict) else None})
        elif action == "RECONCILED":                                                                   # alguem publicou neste HEAD entre o inicio e a escrita: conclui com ESSE parecer
            store.complete(ev, {"action": "DONE", "verdict": "APPROVE" if result.get("state") == "APPROVED" else "REQUEST_CHANGES", "reconciled": True,
                                "review_id": result.get("review_id"), "reason": str(result.get("reason") or "")[:200]})
        elif action == "REVIEW_BLOCKED" and isinstance(result.get("verdict"), dict) and result["verdict"].get("verdict") == "NEEDS_HUMAN" and ev["attempt"] >= NEEDS_HUMAN_TRIES:
            v = result["verdict"]                                                                       # escala: guarda os achados no evento (o arquivo do veredito e sobrescrito a cada tentativa)
            store.complete(ev, {"action": "NEEDS_HUMAN", "verdict": "NEEDS_HUMAN", "escalated": True, "attempts_used": ev["attempt"], "confidence": v.get("confidence"),
                                "findings": [{"severity": f.get("severity"), "where": f"{f.get('file')}:{f.get('line')}", "reason": str(f.get("reason") or "")[:400],
                                              "required_change": str(f.get("required_change") or "")[:300]} for f in (v.get("findings") or [])[:10]]})
            return {"action": "NEEDS_HUMAN", "event": ev["id"], "pr": n, "escalated": True, "findings": len(v.get("findings") or [])}
        elif action in ("SKIPPED", "STALE"):
            store.supersede(ev, str(result.get("reason") or action)[:300])
        else:
            store.fail(ev, f"{action}: {str(result.get('reason') or '')[:300]}", retry_delay=RETRY_S)
    except LeaseLost:
        return {"action": "LOST_LEASE", "event": ev["id"], "pr": n}
    verdict = result.get("verdict")
    row = {"action": action, "event": ev["id"], "pr": n}
    if isinstance(verdict, dict):                                                              # o parecer completo fica no review publicado, nao no log do laco
        row.update(verdict=verdict.get("verdict"), findings=len(verdict.get("findings") or []), head=str(verdict.get("head_sha", ""))[:12])
    elif verdict:
        row["verdict"] = verdict
    row.update({k: result[k] for k in ("url", "reason") if k in result})
    return row


# --------------------------------------------------------------------------------------------------------------------------- ciclo
def enabled() -> bool:
    return os.environ.get("PR_LIFECYCLE_ENABLED") == "1"


def cycle(gh: eb.Gh, policy: dict, repo: str = eb.REPO, execute: bool = False, store: EventStore | None = None, runner: Runner = subprocess.run,
          review: Callable[..., dict] | None = None, now: float | None = None) -> dict:
    """Um ciclo completo. Cada etapa isolada: o erro de uma nao impede as outras. Sem `execute` so planeja."""
    out: dict = {"execute": execute}
    for name, step in (("prepare", lambda: prepare(gh, policy, repo, execute, runner, now)),
                       ("enqueue", lambda: enqueue(gh, store, policy, repo, execute)),
                       ("review", lambda: work(gh, store, policy, repo, review) if execute and store is not None else {"action": "PLANNED"})):
        try:
            out[name] = step()
        except Exception as exc:  # noqa: BLE001
            out[name] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return out


def reconcile_step(gh: eb.Gh, policy: dict, repo: str, execute: bool, store: EventStore | None, runner: Runner = subprocess.run, now: float | None = None) -> dict:
    """A parte RAPIDA do ciclo (prepara + enfileira): roda a cada 30 s sem esperar uma revisao de varios minutos. Cada etapa isolada."""
    out: dict = {"execute": execute}
    if kill_switch().exists():
        return {**out, "disabled": f"interruptor {kill_switch().name} presente: nada e escrito nem enfileirado"}
    steps = [("prepare", lambda: prepare(gh, policy, repo, execute, runner, now)), ("enqueue", lambda: enqueue(gh, store, policy, repo, execute))]
    if execute and store is not None:
        steps.insert(0, ("quota", lambda: quota_step(store, policy)))
    if execute and store is not None and os.environ.get(am.ENABLE_ENV) == "1":
        steps.append(("merge", lambda: merge_step(gh, store, policy, repo, runner)))
    for name, step in steps:
        try:
            res = step()
            if name == "quota" and not res:
                continue                                                                              # conta saudavel e nada a recuperar: o log nao muda
            out[name] = res
        except Exception as exc:  # noqa: BLE001
            out[name] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return out


def quota_step(store: EventStore, policy: dict) -> dict:
    """Recuperacao automatica por limite de uso, a cada ciclo (e portanto apos QUALQUER reinicio do supervisor ou do Windows): reenfileira o que foi para a DLQ so por cota e
    MOSTRA a conta suspensa (estado, reset, episodios). Idempotente e barato: so leituras quando nao ha nada a fazer."""
    gate, account = rl.RateLimitGate(store), rl.account_key(policy)
    out: dict = {}
    requeued = rl.requeue_quota_dlq(store, gate, account, PRODUCER)
    if requeued:
        out["requeued"] = requeued
    suspended = gate.status()
    if suspended:
        out["suspended"] = suspended
    return out


def approved_candidates(store: EventStore, repo: str) -> set[int]:
    """PRs com um APPROVE concluido no EventStore para o HEAD que o pedido citou (barato: nenhuma chamada ao GitHub). So eles podem estar prontos para o merge."""
    found = set()
    for e in store.events():
        if e["producer"] == PRODUCER and e["event_type"] == EVENT_TYPE and e["status"] == "DONE":
            p, res = _payload(e), _payload({"payload": e.get("result")})
            if str(res.get("verdict", "")).upper() == "APPROVE" and p.get("repo") == repo and isinstance(p.get("pr"), int):
                found.add(p["pr"])
    return found


def merge_step(gh: eb.Gh, store: EventStore, policy: dict, repo: str, runner: Runner = subprocess.run) -> dict:
    """Merge protegido (`auto_merge.cycle`, DESLIGADO sem `AUTOMERGE_ENABLED=1`) restrito aos PRs aprovados pelo Codex: o ciclo de 30 s nao relê o GitHub inteiro por PR.
    A decisao, a identidade, a protecao da branch exigindo aprovacao independente, o interruptor e a confirmacao do merge sao todos do `auto_merge`."""
    approved = approved_candidates(store, repo)
    if not approved:
        return {"enabled": True, "prs": []}

    def only(path: str):
        data = gh(path)
        return [p for p in data if p.get("number") in approved] if path.startswith(f"repos/{repo}/pulls?state=open") and isinstance(data, list) else data
    return am.cycle(only, policy, repo, apply=True, runner=runner)


class ReviewLoop(threading.Thread):
    """A parte LENTA: revisa um PR por vez NESTA thread (a sessao do Codex leva minutos), sem atrasar a reconciliacao de 30 s. `emit(dict)` recebe cada resultado.
    `ReviewPool` roda N destas em paralelo: a exclusao entre elas e a do EventStore (claim atomico, lease, e UM PR por vez porque o job do evento e `pr:<N>`)."""

    def __init__(self, gh: eb.Gh, store: EventStore, policy: dict, repo: str, emit: Callable[[dict], None], review: Callable[..., dict] | None = None, idle_s: float = 15.0,
                 name: str = "review-loop"):
        super().__init__(daemon=True, name=name)
        self.gh, self.store, self.policy, self.repo, self.emit, self.review, self.idle_s = gh, store, policy, repo, emit, review, idle_s
        self._stop_evt = threading.Event()

    def run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                out = work(self.gh, self.store, self.policy, self.repo, self.review)
            except Exception as exc:  # noqa: BLE001 — nunca derruba a thread: o proximo tick tenta de novo
                out = {"action": "ERROR", "reason": f"{type(exc).__name__}: {exc}"[:200]}
            if out.get("action") != "IDLE":
                self.emit({"review": out})
            if out.get("action") in ("IDLE", "ERROR"):
                self._stop_evt.wait(self.idle_s)

    def stop(self) -> None:
        self._stop_evt.set()


MAX_WORKERS = 3


class ReviewPool:
    """Ate `MAX_WORKERS` revisoes independentes em paralelo (worktree isolada por PR/SHA no `codex_reviewer`, lease + heartbeat por evento). Nunca duas no mesmo PR."""

    def __init__(self, workers: int, *a, **kw):
        n = max(1, min(int(workers), MAX_WORKERS))
        self.loops = [ReviewLoop(*a, name=f"review-loop-{i + 1}", **kw) for i in range(n)]

    def start(self) -> None:
        for i, loop in enumerate(self.loops):
            loop.start()
            if i + 1 < len(self.loops):
                time.sleep(0.2)                                                  # escalona a partida: cada um escolhe um evento diferente sem disputar o mesmo

    def stop(self) -> None:
        for loop in self.loops:
            loop.stop()


def main(argv: list[str] | None = None) -> int:
    from tools.orchestration import event_executor as ex
    from tools.orchestration.store_factory import get_store
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("cycle", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("--execute", action="store_true", help="escreve no GitHub e no EventStore e roda o Codex; sem isto so planeja")
        sp.add_argument("--repo", default=eb.REPO)
        if name == "run":
            sp.add_argument("--interval", type=int, default=30)
            sp.add_argument("--watch-pid", type=int, default=None)
            sp.add_argument("--workers", type=int, default=1, help=f"revisoes em paralelo (1..{MAX_WORKERS})")
    a = ap.parse_args(argv)
    policy = eb.load_policy()
    gh = am.slurp_client
    store = get_store() if a.execute else None
    if a.cmd == "cycle":
        print(json.dumps(cycle(gh, policy, a.repo, a.execute, store), indent=1, ensure_ascii=False, default=str))
        return 0
    lock = ex.InstanceLock(eb.bridge_path().with_name("pr_lifecycle.instance.lock"))
    if not lock.acquire():
        print(json.dumps({"fatal": "outra instancia do pr_lifecycle ja roda: nao inicia"}))
        return 4
    print_lock = threading.Lock()

    def emit(obj: dict) -> None:
        with print_lock:
            print(json.dumps({"at": dt.datetime.now(dt.timezone.utc).isoformat(), **obj}, ensure_ascii=False, default=str), flush=True)
    reviewer = ReviewPool(a.workers, gh, store, policy, a.repo, emit) if a.execute and store is not None else None
    if reviewer is not None:
        reviewer.start()
    try:
        while True:
            if a.watch_pid is not None and not ex.pid_alive(a.watch_pid):
                return 5
            emit(reconcile_step(gh, policy, a.repo, a.execute, store))
            if not ex.sleep_watching(a.interval, a.watch_pid):
                return 5
    finally:
        if reviewer is not None:
            reviewer.stop()
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
