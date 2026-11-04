"""collectors.py — leitura SOMENTE-LEITURA do estado real (FP-058). Sem Qt. Todo I/O externo entra por funcao injetavel (testavel).

Reutiliza o que o bridge/executor JA gravam (nada de monitor concorrente): `runs/governance/event_bridge.json` (last_poll, mode,
fila, diagnosticos), `event_bridge.log` (um JSON por ciclo), `event_executor.instance.lock`, `EXECUTOR_DISABLED`, `executor/*.log`,
a tabela de processos e a Tarefa Agendada. Ausencia de dado => GRAY/`indisponivel`, nunca verde.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tools.orchestration.agent_bar.models import AgentStatus, Event, Level, Snapshot

TASK_NAME = "sketchup-mcp event bridge"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # Windows: subprocesso da barra nunca abre janela de console
STALE_HEARTBEAT_S = 600                 # o listener faz ciclo a cada ~120 s: 10 min sem ciclo = parado/travado
LISTENER_RE = re.compile(r"event_executor(\.py)?\s+run|event_executor run|run_event_bridge", re.I)
EXECUTOR_RE = re.compile(r"event_executor(\.py)?\s+run|event_executor run", re.I)


@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    name: str
    cmdline: str = ""
    created: str | None = None          # ISO UTC


def _now(now: dt.datetime | None) -> dt.datetime:
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)


def parse_iso(text: object) -> dt.datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        v = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)


def default_gov_dir() -> Path:
    """`runs/governance` do checkout PRINCIPAL (o que o listener usa), mesmo se a barra roda de uma worktree."""
    env = os.environ.get("AGENT_BAR_GOV_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parents[3]
    try:
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=here, capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        common = Path(r.stdout.strip())
        if r.returncode == 0 and r.stdout.strip():
            return ((common if common.is_absolute() else here / common).resolve().parent / "runs" / "governance")
    except (OSError, subprocess.SubprocessError):
        pass
    return here / "runs" / "governance"


# ------------------------------------------------------------------------------------------------ I/O injetavel (real)
def list_processes(timeout: float = 15.0) -> list[Proc] | None:
    """Tabela de processos via CIM (Windows). None = indisponivel (nao e 'lista vazia')."""
    if os.name != "nt":
        return None
    ps = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine,"
          "@{n='C';e={if($_.CreationDate){$_.CreationDate.ToUniversalTime().ToString('o')}}} | ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WINDOW)
        data = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if data is None:
        return None
    if isinstance(data, dict):
        data = [data]
    return [Proc(int(d["ProcessId"]), int(d["ParentProcessId"] or 0), str(d["Name"] or ""), str(d.get("CommandLine") or ""), d.get("C"))
            for d in data if isinstance(d, dict) and d.get("ProcessId") is not None]


def task_state(timeout: float = 15.0) -> str | None:
    """Estado da Tarefa Agendada ('Running', 'Ready', 'Disabled'...) ou None se nao observavel/inexistente."""
    if os.name != "nt":
        return None
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            f"(Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction Stop).State"],
                           capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    out = r.stdout.strip()
    return out if r.returncode == 0 and out else None


def run_gh(args: list[str], timeout: float = 20.0) -> tuple[int, str]:
    exe = shutil.which("gh") or "gh"
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return r.returncode, (r.stdout if r.returncode == 0 else (r.stdout + r.stderr)).strip()


# ----------------------------------------------------------------------------------------------------- arquivos do bridge
def read_bridge(gov: Path) -> dict | None:
    """event_bridge.json ou None (ausente/corrompido => o chamador marca ambiguo, nunca verde)."""
    try:
        d = json.loads((gov / "event_bridge.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def read_log_tail(gov: Path, n: int = 40) -> tuple[list[dict], int, bool]:
    """(registros JSON validos dos ultimos n, linhas ilegiveis, tem NUL). Log de ciclo: uma linha JSON cada."""
    p = gov / "event_bridge.log"
    try:
        raw = p.read_bytes()
    except OSError:
        return [], 0, False
    nul = b"\x00" in raw
    lines = raw.decode("utf-8", errors="replace").replace("\x00", "").splitlines()[-n:]
    ok, bad = [], 0
    for ln in lines:
        if not ln.strip():
            continue
        try:
            obj = json.loads(ln)
        except ValueError:
            bad += 1
            continue
        if isinstance(obj, dict):
            ok.append(obj)
        else:
            bad += 1
    return ok, bad, nul


def lock_holder(gov: Path) -> str | None:
    """PID gravado no InstanceLock (a partir do byte 16: o byte 0 fica travado no Windows). None se nao observavel."""
    try:
        fd = os.open(gov / "event_executor.instance.lock", os.O_RDONLY)
    except OSError:
        return None
    try:
        os.lseek(fd, 16, os.SEEK_SET)
        return os.read(fd, 32).decode("ascii", "replace").strip() or None
    except OSError:
        return None
    finally:
        os.close(fd)


# ------------------------------------------------------------------------------------------------------------ processos
def descendants(procs: list[Proc], roots: set[int]) -> list[Proc]:
    out, frontier = [], set(roots)
    seen = set(roots)
    while frontier:
        nxt = {p.pid for p in procs if p.ppid in frontier and p.pid not in seen}
        out += [p for p in procs if p.pid in nxt]
        seen |= nxt
        frontier = nxt
    return out


def executor_roots(procs: list[Proc]) -> list[Proc]:
    """Raizes de cadeia do executor: python 'event_executor run' cujo pai NAO e outro 'event_executor run' (o shim do venv e o pai)."""
    ex = [p for p in procs if p.name.lower().startswith("python") and EXECUTOR_RE.search(p.cmdline)]
    pids = {p.pid for p in ex}
    return [p for p in ex if p.ppid not in pids]


def _age(iso: str | None, now: dt.datetime) -> int | None:
    t = parse_iso(iso)
    return None if t is None else max(0, int((now - t).total_seconds()))


# ------------------------------------------------------------------------------------------------------------ coletores
def collect_listener(gov: Path, procs: list[Proc] | None, tstate: str | None, now: dt.datetime | None = None,
                     stale_s: int = STALE_HEARTBEAT_S) -> tuple[AgentStatus, dict]:
    """(status, extras). extras: mode, heartbeat_age_s, kill_switch, concurrent_instances, lock_holder, last_error, roots."""
    n = _now(now)
    kill = (gov / "EXECUTOR_DISABLED").exists() if gov.exists() else None
    holder = lock_holder(gov)
    bridge = read_bridge(gov)
    logs, bad_lines, nul = read_log_tail(gov)
    hb_iso = (bridge or {}).get("last_poll")
    hb = _age(hb_iso, n)
    last_log = logs[-1] if logs else {}
    mode = "indisponivel"
    if bridge and bridge.get("mode") in ("dry-run", "execute") and "execute" in last_log:
        a, b = bridge["mode"] == "execute", bool(last_log["execute"])
        mode = "EXECUTE" if a and b else "DRY_RUN" if (not a and not b) else "ambiguo"
    elif "execute" in last_log:
        mode = "EXECUTE" if last_log["execute"] else "DRY_RUN"
    elif bridge and bridge.get("mode") in ("dry-run", "execute"):
        mode = "EXECUTE" if bridge["mode"] == "execute" else "DRY_RUN"
    diags = (bridge or {}).get("diagnostics") or []
    last_error = next((d.get("message") for d in reversed(diags) if isinstance(d, dict) and re.search(r"FAILED|erro|fatal|BLOCKED", str(d.get("message")), re.I)), None)
    if last_log.get("fatal"):
        last_error = str(last_log["fatal"])
    extras = {"mode": mode, "heartbeat_age_s": hb, "kill_switch": kill, "concurrent_instances": None, "lock_holder": holder,
              "last_error": last_error, "roots": []}
    if procs is None:
        return AgentStatus("Listener", Level.GRAY, "Indisponivel", "tabela de processos nao observavel"), extras
    roots = executor_roots(procs)
    extras["concurrent_instances"] = len(roots)
    extras["roots"] = [p.pid for p in roots]
    launchers = [p for p in procs if p.name.lower().startswith("powershell") and "run_event_bridge" in p.cmdline]
    pid = roots[0].pid if roots else None
    since = roots[0].created if roots else None
    if len(roots) > 1:
        return AgentStatus("Listener", Level.RED, "Instancias concorrentes", f"{len(roots)} executores: pids {[p.pid for p in roots]}", pid, since), extras
    if not roots:
        if tstate == "Running" or launchers:
            return AgentStatus("Listener", Level.RED, "Tarefa ativa sem processo", f"tarefa {tstate}; executor ausente (morreu?)"), extras
        return AgentStatus("Listener", Level.GRAY, "Desligado", f"tarefa: {tstate or 'nao observavel'}"), extras
    if kill:
        return AgentStatus("Listener", Level.YELLOW, "Kill switch ativo", "EXECUTOR_DISABLED presente: nao consome a fila", pid, since), extras
    if bridge is None or (not logs and bad_lines):
        return AgentStatus("Listener", Level.YELLOW, "Estado ilegivel", "event_bridge.json/log ausente ou corrompido", pid, since), extras
    if hb is None:
        return AgentStatus("Listener", Level.YELLOW, "Sem heartbeat", "event_bridge.json sem last_poll valido", pid, since), extras
    if hb > stale_s:
        return AgentStatus("Listener", Level.RED, "Heartbeat velho", f"ultimo ciclo ha {hb}s (> {stale_s}s)", pid, since), extras
    if mode == "ambiguo":
        return AgentStatus("Listener", Level.YELLOW, "Modo ambiguo", "bridge e log discordam sobre execute", pid, since), extras
    note = f"ciclo ha {hb}s" + (f"; {bad_lines} linha(s) de log ilegivel" if bad_lines else "") + ("; NUL no log" if nul else "")
    return AgentStatus("Listener", Level.GREEN, mode if mode != "indisponivel" else "Online", note, pid, since), extras


def collect_claude(procs: list[Proc] | None, listener_roots: list[int], gov: Path, now: dt.datetime | None = None,
                   installed: Callable[[], bool] = lambda: bool(shutil.which("claude"))) -> AgentStatus:
    """So conta como 'executando' o claude.exe DESCENDENTE do executor monitorado; outros claude.exe nao sao atribuidos."""
    n = _now(now)
    if procs is None:
        return AgentStatus("Claude", Level.GRAY, "Indisponivel", "tabela de processos nao observavel")
    claudes = [p for p in procs if p.name.lower() in ("claude.exe", "claude")]
    mine = [p for p in descendants(procs, set(listener_roots)) if p.name.lower() in ("claude.exe", "claude")] if listener_roots else []
    foreign = len(claudes) - len(mine)
    extra = f"; +{foreign} sessao(oes) Claude fora do orquestrador (nao monitoradas)" if foreign else ""
    if mine:
        p = mine[0]
        dur = _age(p.created, n)
        return AgentStatus("Claude", Level.BLUE, "Executando", f"filho do executor, {dur}s" + extra, p.pid, p.created)
    last = _last_run(gov)
    if not listener_roots:
        return AgentStatus("Claude", Level.GRAY, "Sem orquestrador", ("instalado" if installed() else "nao instalado") + extra)
    if last and last["failed"]:
        return AgentStatus("Claude", Level.RED, "Ultima execucao falhou", f"{last['name']}" + extra)
    return AgentStatus("Claude", Level.YELLOW, "Ocioso", (f"ultima execucao: {last['name']}" if last else "nenhuma execucao registrada") + extra)


def _last_run(gov: Path) -> dict | None:
    d = gov / "executor"
    try:
        logs = sorted(d.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    if not logs:
        return None
    p = logs[0]
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    failed = '"is_error": true' in text.lower() or "entrega" in text.lower() and ("blocked_guards" in text.lower() or "failed_checks" in text.lower())
    return {"name": p.name, "failed": failed, "mtime": p.stat().st_mtime}


def collect_codex(which: Callable[[str], str | None] = shutil.which) -> AgentStatus:
    """Codex instalado NAO e revisor operacional: ate existir integracao automatica, sempre 'Nao integrado' (GRAY)."""
    installed = bool(which("codex"))
    return AgentStatus("Codex", Level.GRAY, "Nao integrado", "CLI instalada, sem revisor automatico" if installed else "CLI nao encontrada")


class GithubCache:
    """Cache com TTL para nao consultar o GitHub a cada ciclo local."""

    def __init__(self, ttl_s: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.clock, self._at, self._val = ttl_s, clock, None, None

    def get(self, key: str, fetch: Callable[[], object]) -> object:
        now = self.clock()
        if self._at is not None and self._val is not None and self._val[0] == key and now - self._at < self.ttl:
            return self._val[1]
        v = fetch()
        self._at, self._val = now, (key, v)
        return v


def current_pr(bridge: dict | None) -> int | None:
    """PR atual = item de fila mais recente em andamento; senao o ultimo item da fila. Sem fila => None (nao inventa)."""
    q = [i for i in (bridge or {}).get("queue", []) if isinstance(i, dict) and isinstance(i.get("pr"), int)]
    if not q:
        return None
    active = [i for i in q if i.get("state") in ("RUNNING", "QUEUED", "FAILED", "DONE_AWAITING_REREVIEW")]
    return (active or q)[-1]["pr"]


def collect_github(pr: int | None, gh: Callable[[list[str]], tuple[int, str]] = run_gh, repo: str = "GFCDOTA/sketchup-mcp"
                   ) -> tuple[AgentStatus, dict]:
    rc, out = gh(["api", "user", "--jq", ".login"])
    if rc != 0:
        return AgentStatus("GitHub", Level.RED, "Sem conexao/auth", out[:120]), {"checks": "indisponivel", "pr_url": None}
    login = out.strip()
    if pr is None:
        return AgentStatus("GitHub", Level.GREEN, "Conectado", f"login {login}; sem PR em andamento"), {"checks": "sem PR", "pr_url": None}
    rc, out = gh(["pr", "view", str(pr), "--repo", repo, "--json", "url,state,headRefOid,reviewDecision,statusCheckRollup"])
    try:
        d = json.loads(out) if rc == 0 else None
    except ValueError:
        d = None
    if not isinstance(d, dict):
        return AgentStatus("GitHub", Level.YELLOW, "PR ilegivel", f"login {login}; PR #{pr} nao lido"), {"checks": "indisponivel", "pr_url": None}
    rolls = [c.get("conclusion") or c.get("status") or "" for c in d.get("statusCheckRollup") or [] if isinstance(c, dict)]
    ok = sum(1 for c in rolls if c in ("SUCCESS", "NEUTRAL", "SKIPPED"))
    bad = sum(1 for c in rolls if c in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"))
    pend = len(rolls) - ok - bad
    summary = f"{ok} ok / {pend} pendente(s) / {bad} falha(s)" if rolls else "sem checks"
    head = str(d.get("headRefOid") or "")[:7]
    rev = d.get("reviewDecision") or "sem decisao"
    detail = f"PR #{pr} {head}: {summary}; review {rev}"
    changes = rev == "CHANGES_REQUESTED"
    lvl = Level.RED if bad else Level.YELLOW if (pend or not rolls or changes) else Level.GREEN
    label = "Falha em checks" if bad else "Checks pendentes" if pend else "Review pede mudancas" if changes else "Conectado"
    return AgentStatus("GitHub", lvl, label, detail), \
        {"checks": summary, "pr_url": d.get("url")}


def recent_events(gov: Path, n: int = 20) -> list[Event]:
    logs, _bad, _nul = read_log_tail(gov, 200)
    ev = [Event(str(r.get("at", "?")), str(r.get("action") or r.get("fatal") and "FATAL" or "ciclo"), str(r.get("item") or ""),
                str(r.get("reason") or r.get("fatal") or "")) for r in logs]
    return list(reversed(ev[-n:]))


def collect_snapshot(gov: Path | None = None, procs_fn=list_processes, task_fn=task_state, gh=run_gh, cache: GithubCache | None = None,
                     now: dt.datetime | None = None) -> Snapshot:
    """Uma coleta completa. Chamar FORA da thread de UI."""
    g = gov or default_gov_dir()
    n = _now(now)
    procs = procs_fn()
    listener, ex = collect_listener(g, procs, task_fn(), n)
    claude = collect_claude(procs, ex["roots"], g, n)
    bridge = read_bridge(g)
    pr = current_pr(bridge)
    fetch = lambda: collect_github(pr, gh)  # noqa: E731
    github, gx = cache.get(f"pr{pr}", fetch) if cache else fetch()
    return Snapshot(at=n.isoformat(), claude=claude, codex=collect_codex(), listener=listener, github=github, pr=pr,
                    pr_url=gx.get("pr_url"), mode=ex["mode"], heartbeat_age_s=ex["heartbeat_age_s"], kill_switch=ex["kill_switch"],
                    concurrent_instances=ex["concurrent_instances"], lock_holder=ex["lock_holder"], last_error=ex["last_error"],
                    events=recent_events(g), backlog={"Ready": None, "In Progress": None, "GPT Review": None, "Blocked": None},
                    github_checks=gx.get("checks", "indisponivel"))
