"""lifecycle.py — reconciliador duravel do ciclo de vida de PRs (FP-059, Issue #601, fase F4). NAO e um orquestrador novo: roda DENTRO do ciclo do listener
existente (`event_executor.run_cycle`), derivando o estado do PR dos FATOS do GitHub e registrando transicoes duraveis.

Fatos (REST, baratos): PR aberto/fechado/mergeado, HEAD, label `executor-ok`, check-runs do HEAD, reviews dos revisores autorizados NO HEAD ATUAL e o registro do
Codex (`runs/governance/codex/last_review.json`). Estado derivado (`WAITING_CI`, `CI_FAILED`, `REVIEW_QUEUED`, `CHANGES_REQUESTED`, `APPROVED`, `COMPLETED`,
`SUPERSEDED`, `STALE_HEAD`) e a proxima acao PLANEJADA. Em DRY_RUN so registra e planeja; so `execute=True` aciona o revisor Codex (e nunca publica sem identidade
independente). Merge NUNCA e automatico aqui. Persistencia: `runs/governance/lifecycle.json` (estado atual por PR, gravacao atomica) + `lifecycle.log` (JSONL de
transicoes com correlation_id). Recuperacao: depois de reiniciar o Windows o proximo ciclo le o arquivo, reconsulta o GitHub e continua sem duplicar (a chave de
idempotencia de cada acao e `pr:head_sha:acao`)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import uuid
from pathlib import Path
from typing import Callable

from tools.orchestration import event_bridge as eb
from tools.orchestration import execution_guards as guards

KEEP = 20
PENDING = ("queued", "in_progress", "pending", "waiting", "requested", None)

MANDATORY_CHECKS = frozenset({
    "uv lock is current",
    "pytest (py3.11)",
    "pytest (py3.12)",
    "deterministic fidelity gates",
    "mcp server (smoke + stdio handshake)",
    "qg: backlog, issues and specs",
    "qg: PR policy",
    "qg: geometry, program and integration",
})


def state_path() -> Path:
    return eb.bridge_path().with_name("lifecycle.json")


def log_path() -> Path:
    return eb.bridge_path().with_name("lifecycle.log")


def load(path: Path | None = None) -> dict:
    p = path or state_path()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema_version": 1, "prs": {}, "actions": []}
    return d if isinstance(d, dict) and isinstance(d.get("prs"), dict) else {"schema_version": 1, "prs": {}, "actions": []}


def save(state: dict, path: Path | None = None) -> None:
    p = path or state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8", newline="\n")
    os.replace(tmp, p)


def now_iso(now: dt.datetime | None = None) -> str:
    return (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def checks_state(runs: list[dict], mandatory: frozenset[str] = MANDATORY_CHECKS) -> str:
    """'passed' | 'failed' | 'pending' | 'none' a partir dos check-runs do HEAD.

    Exige que TODOS os checks obrigatorios estejam presentes, completed e com
    conclusion=success.  Subconjunto verde nunca e 'passed': checks ausentes
    sao 'pending'; conclusoes nao-success em check obrigatorio sao 'failed'."""
    if not runs:
        return "none"
    by_name: dict[str, dict] = {}
    for r in runs:
        by_name[r.get("name", "")] = r
    for r in by_name.values():
        c = r.get("conclusion")
        if c in ("failure", "cancelled", "timed_out", "action_required", "startup_failure"):
            return "failed"
    for name in mandatory:
        r = by_name.get(name)
        if r is None or r.get("status") != "completed":
            return "pending"
        if r.get("conclusion") != "success":
            return "failed"
    return "passed"


def latest_review(reviews: list[dict], head: str, policy: dict) -> dict | None:
    """Ultimo review de revisor AUTORIZADO (nao-executor) no HEAD ATUAL; ignora COMMENTED/PENDING e reviews de SHA antigo."""
    ok = [r for r in reviews if isinstance(r, dict) and (r.get("user") or {}).get("login") in policy.get("reviewers", [])
          and (r.get("user") or {}).get("login") not in policy.get("executor_logins", []) and r.get("state") in ("APPROVED", "CHANGES_REQUESTED")
          and str(r.get("commit_id", "")).lower() == head.lower()]
    return ok[-1] if ok else None


def derive(pr: dict, runs: list[dict], reviews: list[dict], policy: dict) -> tuple[str, str, int | None]:
    """(estado, motivo, review_id). Puro."""
    if pr.get("merged"):
        return "COMPLETED", "PR mergeado", None
    if pr.get("state") != "open":
        return "SUPERSEDED", "PR fechado sem merge", None
    head = (pr.get("head") or {}).get("sha", "")
    cs = checks_state(runs)
    if cs == "failed":
        return "CI_FAILED", "checks do HEAD reprovados", None
    if cs in ("pending", "none"):
        return "WAITING_CI", f"checks {cs}", None
    rv = latest_review(reviews, head, policy)
    if rv is None:
        return "REVIEW_QUEUED", "CI verde e nenhum review autorizado no HEAD atual", None
    if rv["state"] == "CHANGES_REQUESTED":
        return "CHANGES_REQUESTED", f"review {rv['id']} pede mudancas no HEAD atual", rv["id"]
    return "APPROVED", f"review {rv['id']} aprovou o HEAD atual (merge segue a politica: nao e automatico)", rv["id"]


NEXT = {"REVIEW_QUEUED": "codex_review", "CHANGES_REQUESTED": "executor_correct", "CI_FAILED": "executor_fix_ci", "APPROVED": "await_merge_policy",
        "COMPLETED": "cleanup_local", "WAITING_CI": "wait", "SUPERSEDED": "none"}


def transition(rec: dict | None, issue: int | None, pr: int, branch: str, head: str, new: str, reason: str, review_id: int | None, now: dt.datetime | None) -> dict:
    return {"issue": issue, "pr": pr, "branch": branch, "head_sha": head, "review_id": review_id, "from": (rec or {}).get("state", "NEW"), "to": new,
            "actor": "reconciler", "reason": reason, "attempt": (rec or {}).get("attempt", 0), "timestamp": now_iso(now), "correlation_id": uuid.uuid4().hex}


def refs_issue(body: str) -> int | None:
    """Primeira Issue citada como `Refs #N` no corpo do PR (mesma convencao do bridge)."""
    m = re.search(r"\bRefs\s+#(\d+)", body or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


def _paginated_list(gh: eb.Gh, url: str, per_page: int = 100, max_pages: int = 20) -> list[dict]:
    """Fetch all items from a paginated GitHub list endpoint.  Fail-closed:
    non-list responses and safety-cap overflow raise RuntimeError."""
    items: list[dict] = []
    page = 1
    while True:
        batch = gh(f"{url}{'&' if '?' in url else '?'}per_page={per_page}&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError(f"non-list response from {url} page {page}: {type(batch).__name__}")
        items.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
        if page > max_pages:
            raise RuntimeError(f"safety cap ({max_pages} pages) exceeded for {url}; {len(items)} items so far")
    return items


def _check_runs(gh: eb.Gh, repo: str, head: str, per_page: int = 100, max_pages: int = 10) -> list[dict]:
    """Fetch ALL check-runs for a commit, paginating and verifying total_count.
    Fail-closed: raises on incomplete or malformed responses."""
    all_runs: list[dict] = []
    total: int | None = None
    page = 1
    while True:
        resp = gh(f"repos/{repo}/commits/{head}/check-runs?per_page={per_page}&page={page}")
        if not isinstance(resp, dict) or "check_runs" not in resp:
            raise RuntimeError(f"malformed check-runs response for {head[:8]} page {page}")
        batch = resp["check_runs"]
        if total is None:
            total = resp.get("total_count", 0)
        all_runs.extend(batch)
        if len(all_runs) >= total or len(batch) < per_page:
            break
        page += 1
        if page > max_pages:
            raise RuntimeError(f"check-runs safety cap ({max_pages} pages) exceeded for {head[:8]}; got {len(all_runs)}/{total}")
    if total is not None and len(all_runs) < total:
        raise RuntimeError(f"check-runs incomplete for {head[:8]}: got {len(all_runs)}, expected {total}")
    return all_runs


def _list_open_prs(gh: eb.Gh, repo: str, per_page: int = 50) -> list[dict]:
    """Busca TODOS os PRs abertos com paginacao.  Fail-closed: erros propagam."""
    return _paginated_list(gh, f"repos/{repo}/pulls?state=open", per_page=per_page)


def reconcile(gh: eb.Gh, policy: dict, repo: str = eb.REPO, execute: bool = False, now: dt.datetime | None = None,
              codex_review: Callable[..., dict] | None = None, state_file: Path | None = None) -> dict:
    """Um ciclo. Rastreia PRs abertos com a label de autorizacao + os que ja estavam no estado (para ver o merge). Nunca lanca."""
    out = {"tracked": 0, "transitions": [], "actions": [], "errors": []}
    st = load(state_file)
    try:
        cfg = guards.load_config()
        opened = _list_open_prs(gh, repo)
        numbers = {p["number"] for p in opened if isinstance(p, dict) and guards.label_ok(p.get("labels"), cfg)}
        numbers |= {int(n) for n, r in st["prs"].items() if r.get("state") not in ("COMPLETED", "SUPERSEDED")}
    except (PermissionError, RuntimeError, KeyError, ValueError, TypeError, OSError) as exc:
        out["errors"].append(f"lista de PRs: {type(exc).__name__}: {exc}")
        return out
    for n in sorted(numbers):
        try:
            pr = gh(f"repos/{repo}/pulls/{n}")
            head = (pr.get("head") or {}).get("sha", "")
            runs = _check_runs(gh, repo, head) if head else []
            reviews = _paginated_list(gh, f"repos/{repo}/pulls/{n}/reviews")
            new, reason, rid = derive(pr, runs, reviews if isinstance(reviews, list) else [], policy)
            rec = st["prs"].get(str(n))
            if rec and rec.get("head_sha") and rec["head_sha"] != head and new not in ("COMPLETED", "SUPERSEDED"):
                t0 = transition(rec, rec.get("issue"), n, (pr.get("head") or {}).get("ref", ""), head, "STALE_HEAD",
                                f"HEAD {rec['head_sha'][:8]} -> {head[:8]}: resultados anteriores invalidados", None, now)
                out["transitions"].append(t0)
                rec = {**rec, "state": "STALE_HEAD"}
            if not rec or rec.get("state") != new or rec.get("head_sha") != head or rec.get("review_id") != rid:
                t = transition(rec, refs_issue(pr.get("body", "")), n, (pr.get("head") or {}).get("ref", ""), head, new, reason, rid, now)
                out["transitions"].append(t)
                hist = ((rec or {}).get("history") or [])[-(KEEP - 1):] + [{k: t[k] for k in ("from", "to", "timestamp", "correlation_id", "head_sha")}]
                st["prs"][str(n)] = {"state": new, "head_sha": head, "review_id": rid, "issue": t["issue"], "branch": t["branch"], "attempt": (rec or {}).get("attempt", 0),
                                     "updated": t["timestamp"], "next_action": NEXT[new], "history": hist}
            else:
                st["prs"][str(n)]["next_action"] = NEXT[new]
            out["tracked"] += 1
            action = NEXT[new]
            key = f"{n}:{head}:{action}"
            if action in ("codex_review", "cleanup_local") and key not in st["actions"]:
                result = "PLANNED (dry-run)"
                if execute and action == "codex_review":
                    if codex_review is None:
                        from tools.orchestration import (
                            codex_reviewer,  # import tardio: so quando executa
                        )
                        codex_review = codex_reviewer.review_pr
                    result = codex_review(n, gh, policy, repo).get("action", "?")
                    st["actions"] = (st["actions"] + [key])[-200:]           # idempotencia: mesma acao no mesmo HEAD nao repete
                out["actions"].append({"pr": n, "head_sha": head, "action": action, "result": result})
        except (PermissionError, RuntimeError, KeyError, ValueError, TypeError, OSError, AttributeError) as exc:
            out["errors"].append(f"PR #{n}: {type(exc).__name__}: {exc}")
    save(st, state_file)
    if out["transitions"]:
        lp = log_path()
        lp.parent.mkdir(parents=True, exist_ok=True)
        with lp.open("a", encoding="utf-8", newline="\n") as f:
            for t in out["transitions"]:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return out
