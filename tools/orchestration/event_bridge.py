"""event_bridge.py — listener LOCAL de eventos do GitHub para o executor (FP-057, Issue #589, fase 1: polling + dry-run).

    python -m tools.orchestration.event_bridge poll [--once] [--interval 120] [--repo OWNER/NAME]
    python -m tools.orchestration.event_bridge status

O GitHub e a fonte de verdade e a fila. Este processo roda no Windows do proprietario, autenticado pelo `gh auth` do executor
(`fmodesto30`); nenhum token e lido, gravado ou logado aqui. Faz polling com `gh api`, sem porta publica nem webhook.

FASE 1 = INGESTAO + ENFILEIRAMENTO. NAO executa nada: nem Claude, nem shell, nem git. O texto de reviews e comentarios nunca e
interpretado como comando; so entra na fila a referencia (id, URL, PR, SHA, Issue). Quem decide/reivindica a tarefa continua
sendo `task_scheduler`; trava, relogio e diretorio de estado vem de `execution_state`; dedupe+fila+cursor ficam em UM arquivo proprio (gravacao
atomica unica: nada de dois arquivos que possam divergir). Este modulo nao e um segundo scheduler.

Evento aceito (fail-closed), todos os fatos vindos da API, nunca do texto:
- `review`: `user.login` do evento esta em `review_policy.reviewers` e NAO em `executor_logins`; `state == CHANGES_REQUESTED`;
  `commit_id` e o HEAD ATUAL do PR (senao STALE: revisao de SHA antigo nao aciona); o PR e do repo configurado e cita uma Issue.
- `comment`: mesmo critério de autor, em Issue/PR, com a linha de marcador `EXECUTOR-TASK: #N` (N = Issue alvo). Sem marcador = ignorado.
Idempotencia: chave `event_id:pr:head_sha` guardada no MESMO arquivo da fila (uma unica gravacao atomica, sem dois estados); o mesmo evento nunca enfileira duas vezes,
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
    return {"schema_version": SCHEMA_VERSION, "cursor_comments": None, "queue": [], "seen": [], "diagnostics": [], "backoff_s": 0,
            "last_poll": None, "mode": "dry-run"}


def bridge_path() -> Path:
    env = os.environ.get("EVENT_BRIDGE_STATE_PATH")
    return Path(env) if env else es.state_path().with_name("event_bridge.json")


class BridgeStateCorrupt(ValueError):
    """O arquivo de estado existe mas nao e um estado valido (zerado, vazio, truncado, nao-JSON ou nao-objeto)."""


def _read_bytes(p: Path, tries: int = 50, pause: float = 0.02) -> bytes:
    """Le o arquivo; no Windows, enquanto outro processo o troca (`os.replace`), a abertura recusa por instantes com PermissionError: tenta de novo por ~1 s
    antes de desistir (um erro de verdade persiste)."""
    import time
    for attempt in range(tries):
        try:
            return p.read_bytes()
        except PermissionError:
            if attempt + 1 == tries:
                raise
            time.sleep(pause)
    raise AssertionError("inalcancavel")


def _read_state(p: Path) -> dict:
    raw = _read_bytes(p)
    if not raw.strip(b"\x00 \t\r\n"):
        raise ValueError("arquivo vazio ou so de bytes nulos (zero)")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("a raiz do JSON nao e um objeto")
    # JSON valido mas INCOMPLETO (ex.: `{}`) nao e saudavel: mesclar os padroes perderia fila e deduplicacao e o proximo ciclo reenfileiraria reviews ja vistos
    if not isinstance(data.get("queue"), list):
        raise ValueError("estado sem `queue` (lista): incompleto")
    for key in ("seen", "diagnostics"):
        if key in data and not isinstance(data[key], list):
            raise ValueError(f"`{key}` nao e lista")
    return data


def load(path: Path | None = None) -> dict:
    """Le o estado SEM efeito colateral: arquivo ausente = estado padrao; arquivo corrompido (zerado, vazio, truncado, nao-UTF-8, raiz que nao e objeto)
    levanta `BridgeStateCorrupt` e fica como estava. Quem pode recuperar e so `recover_state`, sob a trava; leitores sem trava (ex.: `status`) nunca mexem."""
    p = path or bridge_path()
    try:
        if p.exists():
            return {**default_bridge_state(), **_read_state(p)}
    except FileNotFoundError:
        pass                                                     # `recover_state` moveu o arquivo entre exists() e a leitura: vale o contrato de "ausente"
    except ValueError as exc:
        raise BridgeStateCorrupt(f"estado do bridge corrompido ({exc}): {p.name}") from exc
    return _pending_state(p) or default_bridge_state()


def _pending_path(p: Path) -> Path:
    return p.with_name(p.name + ".recovered")


QUARANTINE_NAME = re.compile(r"@\.corrupt-\d{14}-\d+-[0-9a-f]{6}")


class PendingUnreadable(RuntimeError):
    """Ha uma recuperacao interrompida (`.recovered`) mas ela NAO pode ser lida agora. NAO e `ValueError`/`BridgeStateCorrupt`: nenhum chamador a trata como "estado
    corrompido a recuperar", entao nada e regravado por cima e o diagnostico da corrupcao original nao se perde; o ciclo falha, tenta de novo e o operador ve o motivo."""


def _pending_state(p: Path) -> dict | None:
    """Estado limpo (com o diagnostico) que uma recuperacao INTERROMPIDA deixou pronto ao lado: o arquivo corrompido ja foi para a quarentena mas o novo
    ainda nao tomou o lugar. Lido no lugar do padrao, o diagnostico nao se perde. `None` SO quando nao ha pendencia; pendencia existente e ilegivel levanta
    `PendingUnreadable` (nunca e tratada como ausencia)."""
    q = _pending_path(p)
    if not q.exists():
        return None
    try:
        state = {**default_bridge_state(), **_read_state(q)}
        # um objeto JSON valido mas INCOMPLETO (ex.: `{}`) NAO e uma recuperacao: sem o marcador `recovery` e o diagnostico, promove-lo apagaria a trava de `BLOCKED_RECOVERY`
        # (o proximo poll enfileiraria reviews como QUEUED sem `release-recovery`). Pendente de estrutura invalida e tratado como ilegivel: nada e movido nem sobrescrito.
        recovery = state.get("recovery")
        if not isinstance(recovery, dict) or not isinstance(recovery.get("quarantine"), str) or not recovery["quarantine"] or not state.get("diagnostics"):
            raise ValueError("pendencia sem o marcador `recovery` (quarentena) ou sem diagnostico")
        return state
    except FileNotFoundError:
        return None                                                  # concluida por outro processo entre exists() e a leitura
    except (ValueError, OSError) as exc:
        raise PendingUnreadable(f"recuperacao pendente ilegivel ({type(exc).__name__}): {q.name}; nada e regravado por cima") from exc


def recover_state(path: Path | None = None) -> dict:
    """Recupera um estado corrompido. O CHAMADOR TEM DE SEGURAR `es.locked(path)` (e `run_cycle` o faz): sob a trava o arquivo e relido (outro processo pode ja
    ter recuperado) e so entao o corrompido e PRESERVADO ao lado (`.corrupt-<data>-<pid>-<id>`, nome unico, nada e apagado) e substituido por um estado limpo
    COM o diagnostico, gravado de forma duravel (a proxima leitura ainda o ve). Nao ha restauracao de copia anterior: uma versao velha pode ter a tarefa
    como QUEUED logo antes do claim RUNNING e permitir execucao dupla. Consequencias aceitas e declaradas: o estado volta limpo (cursor e vistos zerados);
    os reviews sao relidos do GitHub no proximo poll e cada item segue preso ao HEAD revisado (o preflight descarta o que ja foi atendido); comentarios
    anteriores nao sao relidos, e o executor so age sobre reviews. Se nao der para preservar o arquivo, levanta `BridgeStateCorrupt` e nao recria nada."""
    import uuid
    p = path or bridge_path()
    try:
        state = load(p)                                          # relido sob a trava: ja recuperado por outro?
        if not p.exists() and _pending_state(p) is not None:
            es.replace_retry(_pending_path(p), p)                # recuperacao interrompida entre a quarentena e a gravacao: CONCLUI (o diagnostico ja esta no pendente)
        return state
    except BridgeStateCorrupt as exc:
        reason = str(exc)
    # Duas fases, retomaveis: (1) o estado limpo COM o diagnostico vai para `<estado>.recovered` de forma duravel; (2) o corrompido vai para a quarentena;
    # (3) o pendente toma o lugar do estado. Parar entre (2) e (3) nao perde nada: `load` le o pendente e a proxima recuperacao conclui o passo (3).
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    candidate = p.with_name(f"{p.name}.corrupt-{stamp}-{os.getpid()}-{uuid.uuid4().hex[:6]}")
    pending = _pending_state(p)                                  # a recuperacao ANTERIOR deixou um pendente? ilegivel LEVANTA PendingUnreadable: nunca o sobrescreve
    if pending is not None:
        state = pending                                          # pendente legivel (parada antes da quarentena): RETOMA com o diagnostico e o nome de quarentena ja gravados
        named = (state.get("recovery") or {}).get("quarantine")
        # o nome vem de um ARQUIVO (pode estar corrompido/alterado) e `os.replace` sobrescreve: so vale o formato EXATO que esta recuperacao gera para ESTE arquivo e um
        # destino que ainda NAO existe; qualquer outra coisa (outro arquivo, o oficial, uma quarentena existente) e ignorada e o nome novo, unico, e mantido
        if isinstance(named, str) and QUARANTINE_NAME.fullmatch(named.replace(p.name, "@", 1)) and named.startswith(p.name + ".corrupt-") and not p.with_name(named).exists():
            candidate = p.with_name(named)
        else:
            # o nome registrado e invalido ou colide: a evidencia vai para o nome NOVO e o OPERADOR precisa ver ESTE nome (nao o registrado) ao liberar a recuperacao; o nome
            # efetivo e o diagnostico sao gravados de forma duravel na pendencia ANTES de mover o arquivo corrompido (uma interrupcao depois retoma com o nome certo)
            state["recovery"] = {**state["recovery"], "quarantine": candidate.name, "registered_name_rejected": str(named)[:120]}
            diagnose(state, f"nome de quarentena registrado ({str(named)[:80]!r}) invalido ou ja existente: o arquivo corrompido sera preservado em {candidate.name}")
            _write_state(_pending_path(p), state)
    else:
        state = default_bridge_state()
        diagnose(state, f"{reason}; preservado em {candidate.name}; estado limpo, reviews relidos do GitHub no proximo poll (cursor e vistos zerados); reviews "
                        "re-aceitos ficam em BLOCKED_RECOVERY ate `release-recovery` (limites e contadores perdidos nao sao reconstituidos)")
        state["recovery"] = {"at": es.now_iso(), "quarantine": candidate.name}
        _write_state(_pending_path(p), state)
    try:
        es.replace_retry(p, candidate)                           # atomico (com retry de leitor aberto no Windows); nome unico: nunca sobrescreve outra quarentena
    except FileNotFoundError:
        diagnose(state, "o arquivo corrompido ja havia sido removido por outro processo")
        _write_state(_pending_path(p), state)
    except OSError as os_exc:
        raise BridgeStateCorrupt(f"{reason} e nao foi possivel preserva-lo: {os_exc}") from os_exc
    es.replace_retry(_pending_path(p), p)                        # passo (3): o estado limpo toma o lugar
    return state


def _write_state(p: Path, state: dict) -> None:
    es.write_durable(p, json.dumps(state, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


def save(state: dict, path: Path | None = None) -> None:
    blob = json.dumps(state)
    if any(k in blob for k in ("ghp_", "github_pat_", "gho_", "BEGIN PRIVATE KEY")):
        raise ValueError("o estado do bridge nao guarda segredos")
    p = path or bridge_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    _write_state(p, state)
    try:
        _pending_path(p).unlink()                                # o estado oficial existe: uma pendencia antiga nao pode ressuscitar depois
    except OSError:
        pass


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


def ingest(event: dict, pr: dict | None, policy: dict, bstate: dict, now: dt.datetime | None = None,
           repo: str = REPO) -> tuple[str, str]:
    """Decide e, se ACCEPT e primeira vez, enfileira. Devolve (decisao, motivo). So referencias entram na fila, nunca o texto."""
    verdict, why = classify(event, pr, policy, repo)
    if verdict != "ACCEPT":
        return verdict, why
    key = task_key(event, (pr or {}).get("head_sha"))
    if key in bstate["seen"] or any(t["key"] == key for t in bstate["queue"]):
        return "DUPLICATE", "evento ja enfileirado (idempotencia event_id+PR+SHA)"
    bstate["seen"].append(key)                                          # dedupe e fila no MESMO arquivo: uma gravacao so
    issue = event["target_issue"] or sorted(pr["refs"])[0]
    # Apos uma RECUPERACAO o estado perdeu tentativas esgotadas e o contador diario: um review que ja gastou os limites voltaria a executar. Fail-closed: o que
    # entra depois da recuperacao fica BLOQUEADO ate o operador liberar (`release-recovery`); nada e executado sobre limites que ninguem consegue comprovar.
    blocked = bool(bstate.get("recovery"))
    bstate["queue"].append({"key": key, "kind": event["kind"], "event_id": event["event_id"], "pr": event.get("pr"),
                            "issue": issue, "head_sha": (pr or {}).get("head_sha"), "author": event["author"],
                            "url": event["url"], "state": "BLOCKED_RECOVERY" if blocked else "QUEUED", "queued_at": es.now_iso(now)})
    return "ACCEPT", ""


def release_recovery(path: Path | None = None, now: dt.datetime | None = None) -> int:
    """Libera, SOB A TRAVA, os itens BLOCKED_RECOVERY (voltam a QUEUED, sem tentativas contadas) e encerra o modo de recuperacao. Decisao do OPERADOR depois de
    conferir o que foi preservado em quarentena. Devolve quantos itens foram liberados."""
    p = path or bridge_path()
    with es.locked(p):
        state = load(p)
        released = 0
        for item in state["queue"]:
            if item.get("state") == "BLOCKED_RECOVERY":
                item["state"] = "QUEUED"
                released += 1
        was = state.pop("recovery", None)
        diagnose(state, f"recuperacao liberada pelo operador ({released} item(ns)); quarentena {(was or {}).get('quarantine', '?')}", now)
        save(state, p)
    return released


def diagnose(bstate: dict, message: str, now: dt.datetime | None = None, keep: int = 50) -> None:
    bstate["diagnostics"] = (bstate["diagnostics"] + [{"at": es.now_iso(now), "message": message[:500]}])[-keep:]


def next_backoff(current: int, base: int = 30) -> int:
    return min(MAX_BACKOFF_S, max(base, current * 2))


def gh_json(path: str):
    """`gh api` com o login ja existente (keyring). Sem shell, sem token no processo filho alem do que o proprio gh resolve."""
    # `gh` escreve UTF-8; sem `encoding` o Python decodifica pelo locale (cp1252 no Windows) e uma resposta com byte invalido nele (ex.: um PR com
    # emoji ou travessao) derruba a thread de leitura e devolve `stdout=None`. O launcher setava PYTHONUTF8; nao dependa disso.
    out = subprocess.run([os.environ.get("GH_BIN", "gh"), "api", "--paginate", path], capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=120)
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


def _shadow_publish(store, event: dict, pr_facts: dict) -> None:
    """Dual-write to EventStore (shadow mode, SPEC §6.3 step 4).  Best-effort:
    a failure here never blocks the JSON queue."""
    try:
        from tools.orchestration.store_factory import (
            _inc,
            _record_shadow_error,
            bridge_to_store_args,
        )
        args = bridge_to_store_args(event, pr_facts)
        if args:
            store.publish(**args)
            _inc("publish_ok")
    except Exception as exc:  # noqa: BLE001
        from tools.orchestration.store_factory import _inc, _record_shadow_error
        _inc("publish_err")
        _record_shadow_error(exc)


def poll_once(gh: Gh, policy: dict, bstate: dict, repo: str = REPO, now: dt.datetime | None = None,
              store=None) -> dict:
    """Um ciclo de polling (dry-run: so enfileira). Erro de API => backoff + diagnostico, sem perder estado. Devolve contagens."""
    counts = {"ACCEPT": 0, "DUPLICATE": 0, "STALE": 0, "IGNORE": 0, "ERROR": 0}
    try:
        prs = gh(f"repos/{repo}/pulls?state=open&per_page=100")
        for raw_pr in prs:
            facts = pr_facts(raw_pr)
            for raw in gh(f"repos/{repo}/pulls/{raw_pr['number']}/reviews?per_page=100"):
                ev = normalize_review(raw, facts, repo)
                verdict, why = ingest(ev, facts, policy, bstate, now, repo)
                counts[verdict] += 1
                if verdict == "ACCEPT" and store is not None:
                    _shadow_publish(store, ev, facts)
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
            verdict, why = ingest(ev, {"head_sha": "", "refs": []}, policy, bstate, now, repo)
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


def run_cycle(gh: Gh, policy: dict, bpath: Path | None = None, repo: str = REPO, now: dt.datetime | None = None,
              store=None) -> dict:
    """Um ciclo sob trava: carrega, enfileira e grava UM unico arquivo (fila + chaves vistas + cursor) com `os.replace`.
    Crash antes do replace = nada mudou (o proximo ciclo reenfileira uma vez); crash depois = tudo gravado. Sem estado em dois lugares.
    When ``store`` is given, accepted events are also shadow-published to the EventStore (SPEC §6.3)."""
    with es.locked(bpath or bridge_path()):
        try:
            bstate = load(bpath)
        except BridgeStateCorrupt:
            bstate = recover_state(bpath)                        # unico ponto que recupera: sob a trava, e o diagnostico fica gravado
        counts = poll_once(gh, policy, bstate, repo, now, store=store)
        save(bstate, bpath)
    return counts


def check_identity(gh: Gh, policy: dict) -> str:
    """Fail-closed: o `gh` em uso tem de ser o EXECUTOR (`executor_logins`) e nunca um revisor. Devolve o login ou levanta."""
    login = (gh("user") or {}).get("login", "")
    if login.lower() not in [x.lower() for x in policy.get("executor_logins", [])] or             login.lower() in [x.lower() for x in policy.get("reviewers", [])]:
        raise PermissionError(f"gh autenticado como {login!r}: o bridge so roda como executor {policy.get('executor_logins')}")
    return login


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("poll")
    pp.add_argument("--once", action="store_true")
    pp.add_argument("--interval", type=int, default=120)
    pp.add_argument("--repo", default=REPO)
    sub.add_parser("status")
    sub.add_parser("release-recovery")
    a = ap.parse_args(argv)
    if a.cmd == "release-recovery":
        print(json.dumps({"released": release_recovery()}))
        return 0
    if a.cmd == "status":
        b = load()
        print(json.dumps({"mode": b["mode"], "last_poll": b["last_poll"], "queued": len(b["queue"]), "backoff_s": b["backoff_s"], "recovery": b.get("recovery"),
                          "diagnostics": b["diagnostics"][-5:]}, indent=1, ensure_ascii=False))
        return 0
    policy = load_policy()
    try:
        check_identity(gh_json, policy)
    except (PermissionError, RuntimeError) as exc:
        print(json.dumps({"at": es.now_iso(), "fatal": str(exc)[:300]}), flush=True)
        return 3
    while True:
        counts = run_cycle(gh_json, policy, repo=a.repo)
        print(json.dumps({"at": es.now_iso(), "dry_run": True, **counts}), flush=True)
        if a.once:
            return 1 if counts["ERROR"] else 0
        time.sleep(max(a.interval, load()["backoff_s"]))


if __name__ == "__main__":
    sys.exit(main())
