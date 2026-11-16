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


LOCK_POS = 4096                                                 # byte travado: longe do texto (PID) que o protocolo ANTIGO le no inicio do arquivo
LEGACY_STALE_S = 60.0                                           # o protocolo antigo quebrava trava com mais de 60 s


def _os_lock(fd: int) -> None:
    """Trava exclusiva, NAO bloqueante, de UM byte (`LOCK_POS`) do arquivo (`OSError` se outro a segura). O byte 0 fica livre: o PID do dono e gravado no inicio do
    arquivo e continua legivel por quem ainda roda o protocolo antigo."""
    os.lseek(fd, LOCK_POS, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _os_unlock(fd: int) -> None:
    os.lseek(fd, LOCK_POS, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


def _holder_of(text: str, age: float) -> int | None:
    """PID de um dono do protocolo ANTIGO ainda dentro da secao critica, a partir do conteudo do arquivo e da sua idade; None se nao ha. O protocolo antigo cria o
    arquivo com `O_EXCL`, grava o PID e o APAGA ao sair; PID vivo e idade <= 60 s (a mesma regra de trava velha dele) = dentro da secao. O proprio PID e os de
    donos mortos nao contam."""
    head = text.strip().split(":")[0]
    if not head.isdigit() or int(head) == os.getpid() or age > LEGACY_STALE_S:
        return None
    return int(head) if pid_alive(int(head)) else None


def _peek_holder(path: Path) -> int | None:
    """Le o arquivo SEM impedir que o dono antigo o apague ao sair: no Windows um handle aberto sem FILE_SHARE_DELETE faz o `unlink` dele falhar com
    PermissionError, entao o espiao abre com SHARE_DELETE. Arquivo ausente = nenhum dono antigo."""
    import time
    try:
        if os.name == "nt":
            import ctypes
            import msvcrt
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateFileW.restype = wintypes.HANDLE
            h = k32.CreateFileW(str(path), 0x80000000, 0x7, None, 3, 0x80, None)           # GENERIC_READ; compartilha leitura/escrita/DELETE; OPEN_EXISTING
            if h in (None, -1, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF):
                return None
            fd = msvcrt.open_osfhandle(h, os.O_RDONLY)
            try:
                text, mtime = os.read(fd, 64).decode("ascii", "ignore"), os.fstat(fd).st_mtime
            finally:
                os.close(fd)
        else:
            text, mtime = path.read_bytes()[:64].decode("ascii", "ignore"), path.stat().st_mtime
    except OSError:
        return None
    return _holder_of(text, time.time() - mtime)


def _legacy_holder(fd: int, path: Path) -> int | None:
    """Mesma checagem, DEPOIS de obter o lock do SO, lendo pelo proprio handle (fecha a corrida entre a espiada e a abertura)."""
    import time
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        text = os.read(fd, 64).decode("ascii", "ignore")
        age = time.time() - path.stat().st_mtime
    except OSError:
        return None
    return _holder_of(text, age)


@contextlib.contextmanager
def locked(path: Path | None = None, wait_s: float = 5.0):
    """Trava exclusiva curta em torno de ler-alterar-gravar, por LOCK DO SISTEMA OPERACIONAL num arquivo `.lock` que NUNCA e removido.
    Por que nao um arquivo criado com `O_EXCL` e apagado depois: apagar/quebrar o arquivo abre corridas que nenhum retry fecha (um dono lento
    libera enquanto outro quebra e um terceiro cria; `unlink` com PermissionError no Windows deixava a trava presa para todos). Aqui o SO e a
    fonte de verdade: o lock some sozinho quando o dono morre (nao ha trava orfa nem regra dos 60 s).
    TRANSICAO com o protocolo antigo (processos que ainda rodam o codigo da base): (a) depois de obter o lock do SO, se o arquivo guarda o PID VIVO de um dono antigo
    dentro da secao critica, solta e espera; (b) o dono novo GRAVA o proprio PID no inicio do arquivo, de modo que quem roda o protocolo antigo ve um dono vivo e
    espera (e limpa o PID ao sair). O que NAO e coberto: um processo antigo que ja passou da sua checagem de `O_EXCL` exatamente na mesma fracao de tempo em que
    o arquivo foi criado pelo novo: a migracao correta e reiniciar os processos antigos (a tarefa agendada do executor reinicia no proximo logon).
    Falha ao abrir o arquivo (diretorio sem permissao, disco) levanta de imediato: nunca fica em laco. Sem o lock ate `wait_s`: TimeoutError."""
    import time
    p = (path or state_path()).with_suffix(".lock")
    p.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + wait_s
    fd = -1
    try:
        while True:
            holder = _peek_holder(p) if fd < 0 else None
            if holder is not None:
                # um dono do protocolo ANTIGO esta na secao: nao entra junto e NAO segura o arquivo aberto enquanto espera (no Windows um handle aberto sem
                # SHARE_DELETE impede o `unlink` com que ele sai da secao, e ele cairia com PermissionError)
                if time.time() > deadline:
                    raise TimeoutError(f"trava do estado de execucao ocupada por um processo antigo (pid {holder}): {p}") from None
                time.sleep(0.05)
                continue
            if fd < 0:
                fd = os.open(p, os.O_CREAT | os.O_RDWR)
            try:
                _os_lock(fd)
            except OSError:
                if time.time() > deadline:
                    raise TimeoutError(f"trava do estado de execucao ocupada: {p}") from None
                time.sleep(0.02)
                continue
            holder = _legacy_holder(fd, p)                       # depois do lock do SO, pelo proprio handle: fecha a corrida com a espiada
            if holder is None:
                break
            _os_unlock(fd)
            os.close(fd)
            fd = -1
            if time.time() > deadline:
                raise TimeoutError(f"trava do estado de execucao ocupada por um processo antigo (pid {holder}): {p}") from None
            time.sleep(0.05)
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode("ascii"))       # quem ainda roda o protocolo antigo ve um dono VIVO e espera
            yield
        finally:
            try:
                os.ftruncate(fd, 0)
            except OSError:
                pass                                             # o lock do SO e a verdade; o PID e so cortesia para o protocolo antigo
            _os_unlock(fd)
    finally:
        if fd >= 0:
            os.close(fd)


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
