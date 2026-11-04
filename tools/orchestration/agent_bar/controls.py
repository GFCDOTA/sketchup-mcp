"""controls.py — operacoes seguras da barra (FP-058). Sem Qt. A barra NAO e um segundo orquestrador: nada de commit/push/branch,
nada de matar processo por nome, nada de iniciar Claude, nenhum modo de execucao. Parar/reiniciar usa a Tarefa Agendada (mecanismo existente);
o `--watch-pid` do executor (#594) encerra a cadeia python quando o launcher morre."""
from __future__ import annotations

import os
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tools.orchestration.agent_bar import collectors as col
from tools.orchestration.agent_bar.models import Snapshot

REPO_URL = "https://github.com/GFCDOTA/sketchup-mcp"
PROJECT_URL = "https://github.com/orgs/GFCDOTA/projects/1"


@dataclass(frozen=True)
class Result:
    ok: bool
    message: str


def run_ps(script: str, timeout: float = 30.0) -> tuple[int, str]:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, creationflags=col.NO_WINDOW)
    return r.returncode, (r.stdout + r.stderr).strip()


def active_execution(procs: list[col.Proc] | None) -> str | None:
    """Motivo para NAO parar (execucao ativa ou estado nao observavel), ou None se parar e seguro."""
    if procs is None:
        return "tabela de processos indisponivel: nao da para provar que nao ha execucao ativa"
    roots = {p.pid for p in col.executor_roots(procs)}
    live = [p for p in col.descendants(procs, roots) if p.name.lower() in ("claude.exe", "claude")]
    if live:
        return f"execucao ativa: Claude pid {live[0].pid} e filho do executor; espere terminar (diagnostico copiavel)"
    return None


def task_has_execute(run: Callable[[str], tuple[int, str]] = run_ps) -> bool | None:
    """A acao da tarefa tem `-Execute`? None = nao observavel. Se tiver, a barra RECUSA reiniciar (nada de execucao pela barra)."""
    rc, out = run(f"(Get-ScheduledTask -TaskName '{col.TASK_NAME}' -ErrorAction Stop).Actions | ForEach-Object {{ $_.Arguments }}")
    if rc != 0:
        return None
    return "-execute" in out.lower()


def stop_listener(procs_fn=col.list_processes, run: Callable[[str], tuple[int, str]] = run_ps, confirmed: bool = False) -> Result:
    if not confirmed:
        return Result(False, "confirmacao necessaria para parar o listener")
    why = active_execution(procs_fn())
    if why:
        return Result(False, f"parada recusada: {why}")
    rc, out = run(f"Stop-ScheduledTask -TaskName '{col.TASK_NAME}' -ErrorAction Stop")
    return Result(rc == 0, "tarefa parada" if rc == 0 else f"Stop-ScheduledTask falhou: {out[:200]}")


def restart_listener_dry_run(procs_fn=col.list_processes, run: Callable[[str], tuple[int, str]] = run_ps, confirmed: bool = False) -> Result:
    if not confirmed:
        return Result(False, "confirmacao necessaria para reiniciar o listener")
    ex = task_has_execute(run)
    if ex is None:
        return Result(False, "reinicio recusado: nao foi possivel ler a acao da tarefa (nao provo que e DRY_RUN)")
    if ex:
        return Result(False, "reinicio recusado: a tarefa tem -Execute; a barra so reinicia em DRY_RUN")
    stopped = stop_listener(procs_fn, run, confirmed=True)
    if not stopped.ok and "recusada" in stopped.message:
        return stopped
    rc, out = run(f"Start-ScheduledTask -TaskName '{col.TASK_NAME}' -ErrorAction Stop")
    return Result(rc == 0, "tarefa reiniciada em DRY_RUN" if rc == 0 else f"Start-ScheduledTask falhou: {out[:200]}")


def open_url(url: str | None, opener: Callable[[str], object] = webbrowser.open) -> Result:
    if not url or not url.startswith("https://github.com/"):
        return Result(False, "URL indisponivel ou fora de github.com")
    opener(url)
    return Result(True, url)


def open_path(path: Path, opener: Callable[[str], object] | None = None) -> Result:
    if not path.exists():
        return Result(False, f"nao existe: {path}")
    (opener or os.startfile)(str(path))  # type: ignore[attr-defined]  # Windows
    return Result(True, str(path))


def latest_log(gov: Path) -> Path | None:
    """Log mais util: o ultimo log de execucao do executor, senao o log de ciclos do bridge."""
    try:
        runs = sorted((gov / "executor").glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        runs = []
    if runs:
        return runs[0]
    cyc = gov / "event_bridge.log"
    return cyc if cyc.exists() else None


def diagnostic_text(snap: Snapshot) -> str:
    return snap.diagnostic()
