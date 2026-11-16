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

from tools.orchestration import auto_merge as am
from tools.orchestration import event_bridge as eb
from tools.orchestration import execution_guards as guards
from tools.orchestration import lifecycle
from tools.orchestration.event_store import EventStore, LeaseLost

EVENT_TYPE = "REVIEW_REQUESTED"
PRODUCER = "review_dispatch"                              # os eventos de PUBLICACAO do codex_reviewer tambem sao REVIEW_REQUESTED (producer proprio): nunca se misturam
LEASE_S = 300.0
HEARTBEAT_S = 60.0
MAX_ATTEMPTS = 5
RETRY_S = 120.0
FACTS_TTL_S = 600.0
REFS = re.compile(r"\brefs?\s*:?\s*#(\d+)", re.I)
DEP_TEXT = re.compile(r"(?:empilhad[oa]\s+sobre|depends?\s+on|depende\s+de|stacked\s+on)\s+((?:#\d+\s*(?:,|\+|&|\be\b|\band\b)?\s*)+)", re.I)
Runner = Callable[..., "subprocess.CompletedProcess"]
_FACTS: dict[tuple, tuple[float, dict]] = {}


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


def candidates(gh: eb.Gh, policy: dict, repo: str) -> list[dict]:
    """PRs abertos do EXECUTOR, nao-fork, base develop (1 chamada paginada)."""
    executors = set(policy.get("executor_logins", []))
    return [p for p in am.complete_list(gh, f"repos/{repo}/pulls?state=open&per_page=100")
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
    open_heads = {p["number"]: (p.get("head") or {}).get("sha", "") for p in am.complete_list(gh, f"repos/{repo}/pulls?state=open&per_page=100")}
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
                reviews = am.complete_list(gh, f"repos/{repo}/pulls/{n}/reviews?per_page=100")
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
            reviews = am.complete_list(gh, f"repos/{repo}/pulls/{n}/reviews?per_page=100")
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
    owner = owner or f"review-worker:{os.getpid()}:{uuid.uuid4().hex[:6]}"
    pending = [e for e in store.events() if e["producer"] == PRODUCER and e["event_type"] == EVENT_TYPE and e["status"] == "PENDING"]
    waiting = []
    for ev in pending:
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
            continue
        if state == "failed":
            owned = store.claim_by_id(ev["id"], owner, 30.0)
            if owned is not None:
                store.supersede(owned, "checks obrigatorios reprovados: nada a revisar; a correcao gera outro HEAD e outro pedido")
            continue
        if state != "passed":
            waiting.append({"event": ev["id"], "pr": n, "action": "WAIT_CHECKS", "reason": f"checks obrigatorios {state}"})
            continue
        claimed = store.claim_by_id(ev["id"], owner, LEASE_S)
        if claimed is None:
            continue                                                                                    # outro worker (ou lease vivo): nao toca
        return _review(store, claimed, gh, policy, repo, review, heartbeat_s)
    return {"action": "IDLE", "waiting": waiting}


def _review(store: EventStore, ev: dict, gh: eb.Gh, policy: dict, repo: str, review: Callable[..., dict] | None, heartbeat_s: float) -> dict:
    n = _payload(ev).get("pr")
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
        if action == "DONE":
            store.complete(ev, {k: v for k, v in result.items() if k in ("action", "verdict", "url", "findings", "head_sha")})
        elif action in ("SKIPPED", "STALE"):
            store.supersede(ev, str(result.get("reason") or action)[:300])
        else:
            store.fail(ev, f"{action}: {str(result.get('reason') or '')[:300]}", retry_delay=RETRY_S)
    except LeaseLost:
        return {"action": "LOST_LEASE", "event": ev["id"], "pr": n}
    return {"action": action, "event": ev["id"], "pr": n, **{k: result[k] for k in ("verdict", "url", "reason") if k in result}}


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
    for name, step in (("prepare", lambda: prepare(gh, policy, repo, execute, runner, now)), ("enqueue", lambda: enqueue(gh, store, policy, repo, execute))):
        try:
            out[name] = step()
        except Exception as exc:  # noqa: BLE001
            out[name] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return out


class ReviewLoop(threading.Thread):
    """A parte LENTA: revisa um PR por vez numa thread propria (a sessao do Codex leva minutos), sem atrasar a reconciliacao de 30 s. `emit(dict)` recebe cada resultado."""

    def __init__(self, gh: eb.Gh, store: EventStore, policy: dict, repo: str, emit: Callable[[dict], None], review: Callable[..., dict] | None = None, idle_s: float = 5.0):
        super().__init__(daemon=True, name="review-loop")
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
    reviewer = ReviewLoop(gh, store, policy, a.repo, emit) if a.execute and store is not None else None
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
