"""execution_state.py — checkpoint duravel da execucao e reivindicacoes (claims) por tarefa (FP-057 P2).

NAO e um segundo backlog: o GitHub continua canonico. O manifesto guarda so o que permite retomar sem a memoria da conversa:
SPEC/fase ativas, tarefa corrente, branch, commit-base, PRs abertos e revisoes pendentes que ESTA execucao conhece, a ultima
operacao segura e um registro de operacoes ja feitas (`done_ops`) para nunca repetir efeito. Sem segredos.

Armazenamento: `runs/governance/execution_state.json` na RAIZ COMUM do repositorio (todas as worktrees enxergam o mesmo arquivo;
`runs/` e scratch ignorado pelo git). `EXECUTION_STATE_PATH` sobrescreve (testes). Escrita atomica (arquivo temporario + replace)
e trava por `O_EXCL` para dois executores nao reivindicarem a mesma tarefa. A reivindicacao tem validade (`lease_expires`):
execucao morta nao bloqueia para sempre.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

SCHEMA_VERSION = 1
LEASE_HOURS = 6
PHASES = ("SELECTED", "INVESTIGATING", "EDITING", "PR_OPEN", "CI_PENDING", "MERGING", "BOARD_SYNC", "DONE")


def default_state() -> dict:
    return {"schema_version": SCHEMA_VERSION, "active_spec": None, "active_phase": None, "current_issue": None,
            "current_branch": None, "base_commit": None, "last_verified_commit": None, "open_pull_requests": [],
            "pending_reviews": [], "blocked_issues": [], "next_eligible_issues": [], "last_successful_gate": None,
            "last_audit": None, "recovery_instructions": [], "claims": {}, "done_ops": []}


def state_path() -> Path:
    env = os.environ.get("EXECUTION_STATE_PATH")
    if env:
        return Path(env)
    common = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True).stdout.strip()
    root = Path(common).resolve().parent if common else Path.cwd()
    return root / "runs/governance/execution_state.json"


def load(path: Path | None = None) -> dict:
    p = path or state_path()
    if not p.exists():
        return default_state()
    data = json.loads(p.read_text(encoding="utf-8"))
    return {**default_state(), **data}


def save(state: dict, path: Path | None = None) -> None:
    blob = json.dumps(state)
    if any(k in blob for k in ("ghp_", "github_pat_", "gho_", "BEGIN PRIVATE KEY")):
        raise ValueError("o manifesto nao guarda segredos")
    p = path or state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, p)


def pid_alive(pid: int) -> bool:
    """O processo `pid` existe? Windows: OpenProcess+WaitForSingleObject (os.kill(pid, 0) TERMINARIA o processo no Windows)."""
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x00100000, False, int(pid))                     # SYNCHRONIZE
        if not h:
            return False
        try:
            return k32.WaitForSingleObject(h, 0) == 0x102                    # WAIT_TIMEOUT => ainda vivo
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_lock(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _lock_owner_dead(p: Path, raw: str | None = None) -> bool:
    """A trava guarda `<pid>:<token>` do dono. Dono morto (crash duro DURANTE a secao critica, ex. heartbeat) => trava orfa: quebrar ja,
    em vez de bloquear todo mundo por 60 s. Sem PID legivel (formato antigo/escrita parcial) => nao decide aqui (regra dos 60 s)."""
    raw = _read_lock(p) if raw is None else raw
    pid = (raw or "").split(":", 1)[0]
    return pid.isdigit() and int(pid) != os.getpid() and not pid_alive(int(pid))


def _unlink_retry(p: Path, tries: int = 100, pause: float = 0.02) -> None:
    """No Windows, outro thread/processo que acabou de abrir ou de dar `stat` no arquivo faz o `unlink` falhar com PermissionError
    (WinError 32/5) por instantes; desistir ali deixava a trava presa e TODOS os demais esperavam ate o timeout."""
    import time
    for _ in range(tries):
        try:
            p.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(pause)
    p.unlink(missing_ok=True)


def _release(p: Path, token: str) -> None:
    """Solta A PROPRIA trava: so remove o arquivo se ele ainda tem o token deste dono. Se a trava foi quebrada (dono dado como morto ou velho
    demais) e outro dono criou a dele, remover o arquivo derrubaria a trava do OUTRO e abriria a secao critica para um terceiro."""
    import time
    for _ in range(100):
        raw = _read_lock(p)
        if raw is not None and raw != token:
            return
        if raw is None and not p.exists():
            return
        try:
            p.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.02)


def _break_stale(p: Path, observed: str | None) -> bool:
    """Quebra uma trava julgada orfa/velha sem corrida: so UM quebrador por vez (guarda `.break`), e dentro da guarda a trava e RELIDA: se o conteudo mudou
    desde o julgamento (outro quebrador ja a trocou) ou ela ja nao esta orfa/velha, nada e removido. Enquanto o arquivo velho existe ninguem consegue criar
    a trava nova (`O_EXCL`), entao entre a releitura e o `unlink` so o dono original (que so remove o que tem o proprio token) pode mexer nele."""
    import time
    guard = p.with_name(p.name + ".break")
    try:
        fd = os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except (FileExistsError, PermissionError):
        try:
            if time.time() - guard.stat().st_mtime > 60:                 # guarda abandonada por um quebrador que morreu
                _unlink_retry(guard)
        except OSError:
            pass
        return False
    os.close(fd)
    try:
        now = _read_lock(p)
        try:
            age = time.time() - p.stat().st_mtime
        except OSError:
            return False                                                 # ja foi solta: nada a quebrar
        if now != observed or not (age > 60 or _lock_owner_dead(p, now)):
            return False
        _unlink_retry(p)
        return True
    finally:
        _unlink_retry(guard)


@contextlib.contextmanager
def locked(path: Path | None = None, wait_s: float = 5.0):
    """Trava exclusiva curta em torno de ler-alterar-gravar. Dono morto (PID gravado) ou trava velha (> 60 s) => quebrada (`_break_stale`).
    PermissionError ao criar/inspecionar a trava (Windows: arquivo em uso ou com exclusao pendente) significa OCUPADA, nao erro."""
    import time
    import uuid
    p = (path or state_path()).with_suffix(".lock")
    p.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}:{uuid.uuid4().hex}"
    deadline = time.time() + wait_s
    while True:
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, token.encode("ascii"))
            finally:
                os.close(fd)
            break
        except (FileExistsError, PermissionError):
            observed = _read_lock(p)
            try:
                age = time.time() - p.stat().st_mtime
            except FileNotFoundError:
                continue                                             # o dono soltou a trava entre o open e o stat: tenta de novo
            except PermissionError:
                age = 0.0                                            # exclusao pendente: ainda ocupada, olha de novo
            if (age > 60 or _lock_owner_dead(p, observed)) and _break_stale(p, observed):
                continue
            if time.time() > deadline:
                raise TimeoutError(f"trava do estado de execucao ocupada: {p}") from None
            time.sleep(0.02)
    try:
        yield
    finally:
        _release(p, token)


def now_iso(now: dt.datetime | None = None) -> str:
    return (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def lease_expired(claim: dict, now: dt.datetime | None = None) -> bool:
    return (claim.get("lease_expires") or "") < now_iso(now)


def active_claims(state: dict, now: dt.datetime | None = None) -> dict[int, dict]:
    return {int(n): c for n, c in state["claims"].items() if not lease_expired(c, now)}


def claim(state: dict, issue: int, agent: str, branch: str, base_commit: str, components: list[str],
          now: dt.datetime | None = None) -> dict:
    """Reivindica `issue`. Erro se outra execucao ativa (lease valido) a tem; reivindicar de novo a propria e idempotente."""
    cur = state["claims"].get(str(issue))
    if cur and not lease_expired(cur, now) and cur["agent"] != agent:
        raise ValueError(f"#{issue} reivindicada por {cur['agent']} ate {cur['lease_expires']}")
    t = now or dt.datetime.now(dt.timezone.utc)
    new = {"agent": agent, "branch": branch, "base_commit": base_commit, "components": sorted(components), "state": "SELECTED",
           "claimed_at": (cur or {}).get("claimed_at") or now_iso(t), "lease_expires": now_iso(t + dt.timedelta(hours=LEASE_HOURS))}
    state["claims"][str(issue)] = new
    state["current_issue"], state["current_branch"], state["base_commit"] = issue, branch, base_commit
    return new


def advance(state: dict, issue: int, phase: str, now: dt.datetime | None = None) -> None:
    """Avanca a fase da tarefa (nunca volta) e renova o lease."""
    if phase not in PHASES:
        raise ValueError(f"fase desconhecida: {phase}")
    c = state["claims"][str(issue)]
    if PHASES.index(phase) < PHASES.index(c["state"]):
        raise ValueError(f"#{issue}: {c['state']} -> {phase} volta no tempo")
    c["state"] = phase
    c["lease_expires"] = now_iso((now or dt.datetime.now(dt.timezone.utc)) + dt.timedelta(hours=LEASE_HOURS))


def release(state: dict, issue: int) -> None:
    state["claims"].pop(str(issue), None)
    if state.get("current_issue") == issue:
        state["current_issue"] = state["current_branch"] = state["base_commit"] = None


def once(state: dict, key: str) -> bool:
    """True na PRIMEIRA vez que `key` e vista (e registra); False se a operacao ja foi feita: nunca repetir efeito."""
    if key in state["done_ops"]:
        return False
    state["done_ops"].append(key)
    return True


def plan_recovery(claim_: dict, facts: dict) -> tuple[str, str]:
    """(proxima fase, acao segura) para uma tarefa interrompida, a partir de FATOS do GitHub/git (injetados; puro).
    facts: branch_exists, pr (None | {number, state, merged, checks: 'pending'|'pass'|'fail'}), board_synced, issue_closed."""
    pr = facts.get("pr")
    if facts.get("issue_closed") and facts.get("board_synced"):
        return "DONE", "nada a fazer: concluida e reconciliada"
    if pr and pr.get("merged"):
        return "BOARD_SYNC", "reconciliar Issue, evidencia e board (PR ja mergeada: nao mergear de novo)"
    if pr and pr.get("state") == "OPEN":
        if pr.get("checks") == "fail":
            return "EDITING", "investigar o check reprovado, corrigir e atualizar o MESMO PR (nao abrir outro)"
        if pr.get("checks") == "pending":
            return "CI_PENDING", "aguardar os checks do PR existente"
        return "MERGING", "checks verdes: mergear com --match-head-commit"
    if facts.get("branch_exists"):
        return "EDITING", "retomar na branch existente (conferir commits locais antes de refazer)"
    return "SELECTED", "criar a branch a partir de origin/develop e comecar"
