"""event_bridge.py — listener LOCAL de eventos do GitHub para o executor (FP-057, Issue #589, fase 1: polling + dry-run).

    python -m tools.orchestration.event_bridge poll [--once] [--interval 120] [--repo OWNER/NAME]
    python -m tools.orchestration.event_bridge status

O GitHub e a fonte de verdade e a fila. Este processo roda no Windows do proprietario, autenticado pelo `gh auth` do executor
(`fmodesto30`); nenhum token e lido, gravado ou logado aqui. Faz polling com `gh api`, sem porta publica nem webhook.

FASE 1 = INGESTAO + ENFILEIRAMENTO. NAO executa nada: nem Claude, nem shell, nem git. O texto de reviews e comentarios nunca e
interpretado como comando; so entra na fila a referencia (id, URL, PR, SHA, Issue). Quem decide/reivindica a tarefa continua
sendo `task_scheduler`; o checkpoint/`once` e o de `execution_state`. Este modulo nao e um segundo scheduler.

Evento aceito (fail-closed), todos os fatos vindos da API, nunca do texto:
- `review`: `user.login` do evento esta em `review_policy.reviewers` e NAO em `executor_logins`; `state == CHANGES_REQUESTED`;
  `commit_id` e o HEAD ATUAL do PR (senao STALE: revisao de SHA antigo nao aciona); o PR e do repo configurado e cita uma Issue.
- `comment`: mesmo critério de autor, em Issue/PR, com a linha de marcador `EXECUTOR-TASK: #N` (N = Issue alvo). Sem marcador = ignorado.
Idempotencia: chave `event_id:pr:head_sha` registrada com `execution_state.once`; o mesmo evento nunca enfileira duas vezes,
inclusive apos reinicio (cursor e fila persistidos em `runs/governance/event_bridge.json`).
Executor offline (PC desligado/sem sessao): nada e consumido; ao voltar, o proximo ciclo le as revisoes ainda validas (reviews sao
listados do PR aberto, nao por cursor) e os comentarios desde o cursor, entao nada se perde. Credencial indisponivel: o launcher
`run_event_bridge.ps1` sai com codigo 3 e mensagem ("gh sem login"); falha de API em ciclo vira diagnostico em `status`.
Falha da API/rate limit: backoff exponencial, diagnostico persistido e nada e perdido (o cursor so avanca apos enfileirar).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from tools.validation import execution_state as es

REPO = "GFCDOTA/sketchup-mcp"
SCHEMA_VERSION = 1
MARKER = re.compile(r"^\s*EXECUTOR-TASK\s*:\s*#(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
REFS = re.compile(r"\b(?:Refs|Closes|Fixes)\s+#(\d+)", re.IGNORECASE)
MAX_BACKOFF_S = 3600
Gh = Callable[[str], object]


def default_bridge_state() -> dict:
    return {"schema_version": SCHEMA_VERSION, "cursor_comments": None, "queue": [], "diagnostics": [], "backoff_s": 0,
            "last_poll": None, "mode": "dry-run"}


def bridge_path() -> Path:
    env = os.environ.get("EVENT_BRIDGE_STATE_PATH")
    return Path(env) if env else es.state_path().with_name("event_bridge.json")


def load(path: Path | None = None) -> dict:
    p = path or bridge_path()
    return {**default_bridge_state(), **json.loads(p.read_text(encoding="utf-8"))} if p.exists() else default_bridge_state()


def save(state: dict, path: Path | None = None) -> None:
    blob = json.dumps(state)
    if any(k in blob for k in ("ghp_", "github_pat_", "gho_", "BEGIN PRIVATE KEY")):
        raise ValueError("o estado do bridge nao guarda segredos")
    p = path or bridge_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, p)


def load_policy(path: Path | None = None) -> dict:
    p = path or Path(__file__).resolve().parents[2] / "docs/governance/review_policy.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _is_authorized(login: str, policy: dict) -> tuple[bool, str]:
    reviewers = [x.lower() for x in policy.get("reviewers", [])]
    executors = [x.lower() for x in policy.get("executor_logins", [])]
    if not reviewers:
        return False, "nenhum revisor autorizado configurado"
    if login.lower() in executors:
        return False, f"autor {login!r} e o executor"
    if login.lower() not in reviewers:
        return False, f"autor {login!r} nao e revisor autorizado"
    return True, ""


def classify(event: dict, pr: dict | None, policy: dict, repo: str = REPO) -> tuple[str, str]:
    """('ACCEPT'|'STALE'|'IGNORE', motivo). Puro. `event`: normalizado por `normalize_review`/`normalize_comment`."""
    ok, why = _is_authorized(event.get("author", ""), policy)
    if not ok:
        return "IGNORE", why
    if event.get("repo") != repo:
        return "IGNORE", f"repo {event.get('repo')!r} != {repo!r}"
    if not pr:
        return "IGNORE", "fato do PR indisponivel (fail-closed)"
    if event["kind"] == "review":
        if event.get("state") != "CHANGES_REQUESTED":
            return "IGNORE", f"estado {event.get('state')!r} nao aciona execucao"
        if not event.get("commit_id") or event["commit_id"].lower() != (pr.get("head_sha") or "").lower():
            return "STALE", f"revisao de {str(event.get('commit_id'))[:8]} != HEAD atual {str(pr.get('head_sha'))[:8]}"
        if not pr.get("refs"):
            return "IGNORE", "PR nao cita Issue (Refs #N)"
        return "ACCEPT", ""
    if event["kind"] == "comment":
        if not event.get("target_issue"):
            return "IGNORE", "sem marcador EXECUTOR-TASK"
        return "ACCEPT", ""
    return "IGNORE", f"tipo desconhecido {event['kind']!r}"


def normalize_review(raw: dict, pr: dict, repo: str = REPO) -> dict:
    return {"kind": "review", "event_id": f"review:{raw.get('id')}", "author": (raw.get("user") or {}).get("login", ""),
            "state": (raw.get("state") or "").upper(), "commit_id": raw.get("commit_id"), "pr": pr["number"], "repo": repo,
            "url": raw.get("html_url"), "submitted_at": raw.get("submitted_at"), "target_issue": None}


def normalize_comment(raw: dict, repo: str = REPO) -> dict:
    m = MARKER.search(raw.get("body") or "")
    num = re.search(r"/(?:issues|pull)/(\d+)", raw.get("issue_url") or raw.get("html_url") or "")
    return {"kind": "comment", "event_id": f"comment:{raw.get('id')}", "author": (raw.get("user") or {}).get("login", ""),
            "pr": None, "repo": repo, "url": raw.get("html_url"), "submitted_at": raw.get("created_at"),
            "target_issue": int(m.group(1)) if m else None, "thread": int(num.group(1)) if num else None}


def task_key(event: dict, head_sha: str | None) -> str:
    return f"{event['event_id']}:{event.get('pr') or event.get('thread')}:{head_sha or '-'}"


def ingest(event: dict, pr: dict | None, policy: dict, bstate: dict, estate: dict, now: dt.datetime | None = None,
           repo: str = REPO) -> tuple[str, str]:
    """Decide e, se ACCEPT e primeira vez, enfileira. Devolve (decisao, motivo). So referencias entram na fila, nunca o texto."""
    verdict, why = classify(event, pr, policy, repo)
    if verdict != "ACCEPT":
        return verdict, why
    key = task_key(event, (pr or {}).get("head_sha"))
    if not es.once(estate, "bridge:" + key):
        return "DUPLICATE", "evento ja enfileirado (idempotencia event_id+PR+SHA)"
    issue = event["target_issue"] or sorted(pr["refs"])[0]
    bstate["queue"].append({"key": key, "kind": event["kind"], "event_id": event["event_id"], "pr": event.get("pr"),
                            "issue": issue, "head_sha": (pr or {}).get("head_sha"), "author": event["author"],
                            "url": event["url"], "state": "QUEUED", "queued_at": es.now_iso(now)})
    return "ACCEPT", ""


def diagnose(bstate: dict, message: str, now: dt.datetime | None = None, keep: int = 50) -> None:
    bstate["diagnostics"] = (bstate["diagnostics"] + [{"at": es.now_iso(now), "message": message[:500]}])[-keep:]


def next_backoff(current: int, base: int = 30) -> int:
    return min(MAX_BACKOFF_S, max(base, current * 2))


def gh_json(path: str):
    """`gh api` com o login ja existente (keyring). Sem shell, sem token no processo filho alem do que o proprio gh resolve."""
    out = subprocess.run([os.environ.get("GH_BIN", "gh"), "api", "--paginate", path], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or out.stdout).strip()[:300] or f"gh api falhou ({out.returncode})")
    text = out.stdout.strip()
    # --paginate concatena paginas JSON ([...][...]): une as listas
    if text.startswith("[") and "][" in text:
        text = "[" + text.replace("][", ",")[1:-1] + "]"
    return json.loads(text or "[]")


def pr_facts(pr_raw: dict) -> dict:
    return {"number": pr_raw["number"], "head_sha": (pr_raw.get("head") or {}).get("sha", ""),
            "refs": sorted({int(n) for n in REFS.findall(pr_raw.get("body") or "")})}


def poll_once(gh: Gh, policy: dict, bstate: dict, estate: dict, repo: str = REPO, now: dt.datetime | None = None) -> dict:
    """Um ciclo de polling (dry-run: so enfileira). Erro de API => backoff + diagnostico, sem perder estado. Devolve contagens."""
    counts = {"ACCEPT": 0, "DUPLICATE": 0, "STALE": 0, "IGNORE": 0, "ERROR": 0}
    try:
        prs = gh(f"repos/{repo}/pulls?state=open&per_page=100")
        for raw_pr in prs:
            facts = pr_facts(raw_pr)
            for raw in gh(f"repos/{repo}/pulls/{raw_pr['number']}/reviews?per_page=100"):
                verdict, why = ingest(normalize_review(raw, facts, repo), facts, policy, bstate, estate, now, repo)
                counts[verdict] += 1
                if verdict in ("STALE", "IGNORE") and (raw.get("state") or "").upper() == "CHANGES_REQUESTED":
                    diagnose(bstate, f"review {raw.get('id')} PR #{facts['number']} {verdict}: {why}", now)
        since = bstate.get("cursor_comments")
        newest = since
        if since is None:                                               # 1o ciclo: nao reprocessar o historico de comentarios
            bstate["cursor_comments"] = es.now_iso(now)
            bstate["backoff_s"] = 0
            bstate["last_poll"] = es.now_iso(now)
            return counts
        for raw in gh(f"repos/{repo}/issues/comments?per_page=100" + (f"&since={since}" if since else "")):
            ev = normalize_comment(raw, repo)
            verdict, why = ingest(ev, {"head_sha": "", "refs": []}, policy, bstate, estate, now, repo)
            counts[verdict] += 1
            if ev["submitted_at"] and (newest is None or ev["submitted_at"] > newest):
                newest = ev["submitted_at"]
        bstate["cursor_comments"] = newest                              # so avanca depois de processar a pagina inteira
        bstate["backoff_s"] = 0
    except Exception as exc:                                             # noqa: BLE001 — qualquer falha vira diagnostico + backoff
        counts["ERROR"] += 1
        bstate["backoff_s"] = next_backoff(bstate.get("backoff_s", 0))
        diagnose(bstate, f"poll falhou ({type(exc).__name__}): {exc}; proximo em {bstate['backoff_s']}s", now)
    bstate["last_poll"] = es.now_iso(now)
    return counts


def run_cycle(gh: Gh, policy: dict, bpath: Path | None = None, epath: Path | None = None, repo: str = REPO,
              now: dt.datetime | None = None) -> dict:
    """Um ciclo com persistencia sob trava: carrega, enfileira, grava os DOIS estados atomicamente."""
    with es.locked(epath):
        estate = es.load(epath)
        bstate = load(bpath)
        counts = poll_once(gh, policy, bstate, estate, repo, now)
        es.save(estate, epath)
        save(bstate, bpath)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("poll")
    pp.add_argument("--once", action="store_true")
    pp.add_argument("--interval", type=int, default=120)
    pp.add_argument("--repo", default=REPO)
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        b = load()
        print(json.dumps({"mode": b["mode"], "last_poll": b["last_poll"], "queued": len(b["queue"]), "backoff_s": b["backoff_s"],
                          "diagnostics": b["diagnostics"][-5:]}, indent=1, ensure_ascii=False))
        return 0
    policy = load_policy()
    while True:
        counts = run_cycle(gh_json, policy, repo=a.repo)
        print(json.dumps({"at": es.now_iso(), "dry_run": True, **counts}), flush=True)
        if a.once:
            return 1 if counts["ERROR"] else 0
        time.sleep(max(a.interval, load()["backoff_s"]))


if __name__ == "__main__":
    sys.exit(main())
