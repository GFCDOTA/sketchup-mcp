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

from tools.orchestration.agent_bar.models import AgentStatus, Event, GroupedEvent, Level, Snapshot

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


def run_gh(args: list[str], timeout: float = 60.0) -> tuple[int, str]:
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


DESKTOP_RE = re.compile(r"--type=|AnthropicClaude|--startup", re.I)           # app Claude Desktop (Electron) e seus auxiliares
CODEX_RE = re.compile(r"(@openai[/\\]codex|[/\\]codex(\.exe|\.js|\.cmd)?(\s|\"|$)|\bcodex\s+(exec|review|resume|login))", re.I)


def short_cmd(cmd: str, n: int = 120) -> str:
    """Linha de comando resumida e sem segredos (tokens conhecidos redatados)."""
    c = re.sub(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|Bearer\s+\S+)", "[REDACTED]", " ".join(cmd.split()))
    return c if len(c) <= n else c[: n - 1] + "…"


def is_claude(p: Proc) -> bool:
    return p.name.lower() in ("claude.exe", "claude")


def is_codex(p: Proc) -> bool:
    n = p.name.lower()
    return n in ("codex.exe", "codex") or (n in ("node.exe", "node") and bool(CODEX_RE.search(p.cmdline)))


def collect_claude(procs: list[Proc] | None, listener_roots: list[int], gov: Path, now: dt.datetime | None = None,
                   installed: Callable[[], bool] = lambda: bool(shutil.which("claude"))) -> AgentStatus:
    """So conta como 'executando' o claude.exe DESCENDENTE do executor monitorado. Processos vivos fora dele sao separados em
    sessoes interativas (Claude Code) e auxiliares do app Desktop; sessoes historicas (so em disco) nunca entram aqui."""
    n = _now(now)
    if procs is None:
        return AgentStatus("Claude", Level.GRAY, "Indisponivel", "tabela de processos nao observavel")
    claudes = [p for p in procs if is_claude(p)]
    mine = [p for p in descendants(procs, set(listener_roots)) if is_claude(p)] if listener_roots else []
    mine_ids = {p.pid for p in mine}
    others = [p for p in claudes if p.pid not in mine_ids]
    desktop = [p for p in others if DESKTOP_RE.search(p.cmdline)]
    sessions = [p for p in others if not DESKTOP_RE.search(p.cmdline)]
    extra = ""
    if sessions:
        extra += f"; {len(sessions)} sessao(oes) interativa(s) viva(s) fora do orquestrador (pid {', '.join(str(p.pid) for p in sessions[:3])})"
    if desktop:
        extra += f"; app Desktop: {len(desktop)} processo(s) auxiliar(es), nao sao execucao"
    if mine:
        p = mine[0]
        return AgentStatus("Claude", Level.BLUE, "Executando", f"filho do executor, ha {_age(p.created, n)}s" + extra, p.pid, p.created, short_cmd(p.cmdline))
    last = _last_run(gov)
    if not listener_roots:
        return AgentStatus("Claude", Level.GRAY, "Sem orquestrador", ("CLI instalada" if installed() else "CLI nao instalada") + extra)
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
        text = p.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return None
    failed = '"is_error": true' in text or ("entrega" in text and ("blocked_guards" in text or "failed_checks" in text))
    return {"name": p.name, "failed": failed, "mtime": p.stat().st_mtime}


def read_codex_record(gov: Path) -> dict | None:
    """Contrato para a futura integracao: `runs/governance/codex/last_review.json` {status, pr, sha, verdict, at, error}. Ausente = nao integrado."""
    try:
        d = json.loads((gov / "codex" / "last_review.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("status") in ("running", "done", "failed") else None


def collect_codex(procs: list[Proc] | None = None, listener_roots: list[int] | None = None, gov: Path | None = None,
                  which: Callable[[str], str | None] = shutil.which, now: dt.datetime | None = None) -> AgentStatus:
    """Separa: instalado / analise manual / vinculado ao orquestrador / revisando PR / falhou. O revisor AUTOMATICO so seria 'operacional'
    com registro de integracao (nao existe): enquanto o E2E Claude<->Codex nao for comprovado o detalhe diz isso explicitamente."""
    n = _now(now)
    installed = bool(which("codex"))
    note = "revisor automatico NAO operacional (E2E Claude<->Codex nao comprovado)"
    rec = read_codex_record(gov) if gov else None
    if rec and rec["status"] == "failed":
        return AgentStatus("Codex", Level.RED, "Falhou", f"PR #{rec.get('pr', '?')} {str(rec.get('sha', ''))[:7]}: {str(rec.get('error', 'sem detalhe'))[:100]}")
    if procs is None:
        return AgentStatus("Codex", Level.GRAY, "Indisponivel", "tabela de processos nao observavel")
    live = [p for p in procs if is_codex(p)]
    linked_ids = {p.pid for p in descendants(procs, set(listener_roots or []))} if listener_roots else set()
    linked = [p for p in live if p.pid in linked_ids]
    manual = [p for p in live if p.pid not in linked_ids]
    if linked:
        p = linked[0]
        reviewing = bool(re.search(r"\b(exec|review)\b", p.cmdline))
        return AgentStatus("Codex", Level.BLUE, "Revisando PR (vinculado)" if reviewing else "Vinculado ao orquestrador",
                           f"filho do executor, ha {_age(p.created, n)}s", p.pid, p.created, short_cmd(p.cmdline))
    if manual:
        p = manual[0]
        return AgentStatus("Codex", Level.BLUE, "Analise manual", f"fora do orquestrador, ha {_age(p.created, n)}s; {note}", p.pid, p.created,
                           short_cmd(p.cmdline))
    if rec and rec["status"] == "done":
        return AgentStatus("Codex", Level.YELLOW, "Ocioso", f"ultimo parecer: PR #{rec.get('pr', '?')} {rec.get('verdict', '?')}")
    return AgentStatus("Codex", Level.GRAY, "Nao integrado", ("CLI instalada; " if installed else "CLI nao encontrada; ") + note)


def lock_status(holder: str | None, procs: list[Proc] | None, roots: list[int]) -> str:
    """Correlaciona o PID do InstanceLock com o processo REAL: pertence a cadeia do executor? vivo? orfao?"""
    if holder is None:
        return "sem lock (ninguem consome a fila)" if procs is not None else "indisponivel"
    if procs is None:
        return f"pid {holder}: processo nao verificavel"
    try:
        pid = int(holder)
    except ValueError:
        return f"conteudo invalido: {holder!r}"
    by = {p.pid: p for p in procs}
    chain = set(roots) | {p.pid for p in descendants(procs, set(roots))}
    if pid in chain:
        return f"pid {pid} vivo e da cadeia do executor"
    if pid in by:
        return f"pid {pid} vivo mas FORA da cadeia do executor (reuso de PID?)"
    return f"pid {pid} NAO existe (lock velho; o SO libera o lock real)"


def executor_summary(bridge: dict | None, now: dt.datetime) -> tuple[str, str, str]:
    """(resumo de fila/tentativas/execucoes, trabalho, review/SHA atual). Tudo do event_bridge.json."""
    if not bridge:
        return "indisponivel", "indisponivel", ""
    q = [i for i in bridge.get("queue", []) if isinstance(i, dict)]
    runs = [parse_iso(r) for r in bridge.get("runs", [])]
    runs24 = sum(1 for r in runs if r and (now - r).total_seconds() <= 86400)
    states: dict[str, int] = {}
    for i in q:
        states[str(i.get("state"))] = states.get(str(i.get("state")), 0) + 1
    failed = [i for i in q if i.get("state") == "FAILED"]
    att = ", ".join(f"PR #{i.get('pr')} tentativa {i.get('attempts', 0)}/3" for i in failed[:3])
    parts = [f"fila {len(q)} ({', '.join(f'{k}={v}' for k, v in sorted(states.items())) or 'vazia'})", f"execucoes 24h: {runs24}/6"]
    if failed:
        parts.append(f"falhas: {att}")
    running = [i for i in q if i.get("state") == "RUNNING"]
    cur = (running or [i for i in q if i.get("state") in ("QUEUED", "FAILED")] or q or [None])[-1]
    ref = f"{cur.get('event_id', '?')} @ {str(cur.get('head_sha', ''))[:7]} (PR #{cur.get('pr')})" if cur else ""
    work = "TRABALHANDO (executando uma tarefa)" if running else "apenas monitorando (nenhuma tarefa em execucao)"
    return "; ".join(parts), work, ref


class GithubCache:
    """Cache com TTL para nao consultar o GitHub a cada ciclo local."""

    def __init__(self, ttl_s: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.clock, self._at, self._val = ttl_s, clock, None, None
        self.last_good = None

    def invalidate(self) -> None:
        self._at, self._val = None, None

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


ERROR_RE = re.compile(r"FAIL|FATAL|ERROR|BLOCKED|LOST|REFUSED|SUPERSEDED", re.I)
BACKLOG_COLUMNS = ("Ready", "In Progress", "GPT Review", "Blocked", "Done")
_UNUSED_JQ = "[.items[].status] | group_by(.) | map({key: (.[0] // \"(sem status)\"), value: length}) | from_entries"


def group_events(events: list[Event], limit: int = 20) -> list[GroupedEvent]:
    """`events` do mais novo para o mais antigo. Consecutivos identicos (acao/item/motivo) => 1 linha com contagem."""
    out: list[GroupedEvent] = []
    for e in events:
        if out and (out[-1].action, out[-1].item, out[-1].reason) == (e.action, e.item, e.reason):
            g = out[-1]
            out[-1] = GroupedEvent(e.at, g.last_at, g.action, g.item, g.reason, g.count + 1, g.error)     # first_at = mais antigo
        else:
            out.append(GroupedEvent(e.at, e.at, e.action, e.item, e.reason, 1, bool(ERROR_RE.search(f"{e.action} {e.reason}"))))
    return out[:limit]


def recent_events(gov: Path, n: int = 200) -> list[Event]:
    logs, _bad, _nul = read_log_tail(gov, n)
    ev = [Event(str(r.get("at", "?")), str(r.get("action") or ("FATAL" if r.get("fatal") else "ciclo")), str(r.get("item") or ""),
                str(r.get("reason") or r.get("fatal") or "")) for r in logs]
    return list(reversed(ev))


GRAPHQL = ("query($after:String){organization(login:\"%s\"){projectV2(number:%d){items(first:100,after:$after){"
           "pageInfo{hasNextPage endCursor} nodes{fieldValueByName(name:\"Status\"){... on ProjectV2ItemFieldSingleSelectValue{name}}}}}}}")


def collect_backlog(gh: Callable[[list[str]], tuple[int, str]] = run_gh, owner: str = "GFCDOTA", number: int = 1,
                    now: dt.datetime | None = None, max_pages: int = 10) -> tuple[dict[str, int | None], str | None, str | None]:
    """(contagens por coluna, erro tecnico especifico, sync ISO). Uma consulta GraphQL enxuta (so o campo Status, 100 itens/pagina:
    custa ~1 ponto, ao contrario de `gh project item-list` que baixa corpo de todas as Issues). Falha => erro explicito, nunca numero."""
    empty: dict[str, int | None] = {k: None for k in BACKLOG_COLUMNS}
    counts: dict[str, int] = {}
    after = None
    for _ in range(max_pages):
        args = ["api", "graphql", "-f", "query=" + GRAPHQL % (owner, number)] + (["-f", f"after={after}"] if after else [])
        rc, out = gh(args)
        if rc != 0:
            first = (out.splitlines() or ["sem saida"])[0]
            hint = " (token sem escopo 'read:project'? rode: gh auth refresh -s read:project)" if "scope" in out.lower() else ""
            return empty, f"gh api graphql rc={rc}: {first[:160]}{hint}", None
        try:
            data = json.loads(out)
            if data.get("errors"):
                return empty, "GraphQL: " + str(data["errors"][0].get("message", "erro"))[:160], None
            items = data["data"]["organization"]["projectV2"]["items"]
            for node in items["nodes"]:
                fv = (node or {}).get("fieldValueByName") or {}
                name = fv.get("name") or "(sem status)"
                counts[name] = counts.get(name, 0) + 1
            if not items["pageInfo"]["hasNextPage"]:
                break
            after = items["pageInfo"]["endCursor"]
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            return empty, f"resposta do GraphQL ilegivel: {type(exc).__name__}: {exc}"[:200], None
    else:
        return empty, f"Project com mais de {max_pages * 100} itens: contagem incompleta recusada", None
    return {k: counts.get(k, 0) for k in BACKLOG_COLUMNS}, None, _now(now).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_snapshot(gov: Path | None = None, procs_fn=list_processes, task_fn=task_state, gh=run_gh, cache: GithubCache | None = None,
                     backlog_cache: GithubCache | None = None, now: dt.datetime | None = None) -> Snapshot:
    """Uma coleta completa. Chamar FORA da thread de UI."""
    g = gov or default_gov_dir()
    n = _now(now)
    procs = procs_fn()
    listener, ex = collect_listener(g, procs, task_fn(), n)
    claude = collect_claude(procs, ex["roots"], g, n)
    codex = collect_codex(procs, ex["roots"], g, now=n)
    bridge = read_bridge(g)
    pr = current_pr(bridge)
    fetch = lambda: collect_github(pr, gh)  # noqa: E731
    github, gx = cache.get(f"pr{pr}", fetch) if cache else fetch()
    bfetch = lambda: collect_backlog(gh, now=n)  # noqa: E731
    counts, berr, bsync = backlog_cache.get("backlog", bfetch) if backlog_cache else bfetch()
    if backlog_cache is not None:
        if berr is None:
            backlog_cache.last_good = (counts, bsync)
        elif getattr(backlog_cache, "last_good", None):                         # erro agora, mas ha leitura anterior: mostra E sinaliza
            counts, bsync = backlog_cache.last_good
    summary, work, ref = executor_summary(bridge, n)
    log = _latest_log(g)
    return Snapshot(at=n.isoformat(), claude=claude, codex=codex, listener=listener, github=github, pr=pr,
                    pr_url=gx.get("pr_url"), mode=ex["mode"], heartbeat_age_s=ex["heartbeat_age_s"], kill_switch=ex["kill_switch"],
                    concurrent_instances=ex["concurrent_instances"], lock_holder=ex["lock_holder"],
                    lock_status=lock_status(ex["lock_holder"], procs, ex["roots"]), last_error=ex["last_error"],
                    events=group_events(recent_events(g)), backlog=counts, backlog_error=berr, backlog_synced=bsync,
                    github_checks=gx.get("checks", "indisponivel"), executor_summary=summary, work=work, review_ref=ref,
                    log_path=str(log) if log else None)


def _latest_log(gov: Path) -> Path | None:
    try:
        runs = sorted((gov / "executor").glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        runs = []
    if runs:
        return runs[0]
    cyc = gov / "event_bridge.log"
    return cyc if cyc.exists() else None
