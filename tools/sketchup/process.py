"""Ciclo de vida do SketchUp.exe — achar, listar, abrir, fechar.

Regra que este módulo existe para impor (FP-019, LL-015, `su_runner_safety`):
**nunca `taskkill /IM SketchUp.exe`.** Isso mata TODAS as janelas, inclusive a
do Felipe com trabalho não salvo. Fechar é sempre por PID, e só com
`confirm=True`. Sem confirmação, `close()` só diz o que fecharia.

Fechamento padrão é GRACIOSO (`taskkill /PID` sem `/F` = WM_CLOSE): o
SketchUp pergunta se quer salvar. Forçar (`/F`) é pedido explícito à parte.

Tudo que toca processo passa por `System`, dublado inteiro nos testes — a
suíte roda sem Windows e sem SketchUp.
"""
from __future__ import annotations

import csv
import io
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

IMAGE = "SketchUp.exe"
EXE_DEFAULT = r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
PLUGINS_DEFAULT = r"%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins"
VRAY_EXE_DEFAULT = (r"C:\Program Files\Chaos\V-Ray\V-Ray for SketchUp"
                    r"\extension\vray\bin\vray.exe")
# Plugin de autorun LEGADO (não versionado, mora só no Plugins da máquina). Nada neste repositório depende mais dele:
# o build do shell e o render do quadrado rodam no próprio processo (-RubyStartup skmcp_launch.rb). status() só
# informa se ele existe, porque um control file esquecido ainda o faria rodar em qualquer SketchUp aberto.
AUTORUN_PLUGIN = "autorun_consume.rb"


def job_info() -> dict[str, Any]:
    """Como ESTE processo está preso a um Job Object do Windows (diagnóstico, só leitura).

    Clientes MCP no Windows costumam pôr o servidor num job `KILL_ON_JOB_CLOSE`: fechar o cliente mata a árvore, SketchUp
    incluso, a menos que o job permita breakaway. `sketchup_survives_server_exit` diz se uma instância aberta por
    `spawn_detached` sobreviveria ao servidor; `None` quando não dá para saber (não Windows / consulta falhou).

    LIMITE (L2 P3b): isto lê o job visível a este processo, não o que o CLIENTE faz depois. O cliente Python do `mcp` cria o
    próprio job e o termina ao fechar — filhos de `spawn_detached` morrem mesmo com `sketchup_survives_server_exit=True`.
    Por isso `su_open` usa `spawn_outside_job` (WMI); os jobs em lote seguem o job do cliente de propósito."""
    if sys.platform != "win32":
        return {"supported": False, "sketchup_survives_server_exit": None}
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    kernel32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                                   ctypes.POINTER(wintypes.DWORD)]
    in_job = wintypes.BOOL()
    if not kernel32.IsProcessInJob(kernel32.GetCurrentProcess(), None, ctypes.byref(in_job)):
        return {"supported": True, "in_job": None, "sketchup_survives_server_exit": None}
    if not in_job.value:
        return {"supported": True, "in_job": False, "sketchup_survives_server_exit": True}

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("Basic", Basic), ("IoInfo", ctypes.c_ulonglong * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    info = Extended()
    ok = kernel32.QueryInformationJobObject(None, 9, ctypes.byref(info), ctypes.sizeof(info), None)  # 9 = ExtendedLimit
    if not ok:
        return {"supported": True, "in_job": True, "sketchup_survives_server_exit": None}
    flags = info.Basic.LimitFlags
    kill, brk, silent = bool(flags & 0x2000), bool(flags & 0x800), bool(flags & 0x1000)
    return {"supported": True, "in_job": True, "kill_on_job_close": kill, "breakaway_ok": brk,
            "silent_breakaway_ok": silent, "sketchup_survives_server_exit": (not kill) or brk or silent}


def spawn_detached(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.Popen:
    """Sobe o SketchUp DESANEXADO de quem chamou.

    stdin=DEVNULL é obrigatório (L2 2026-10-19): dentro do servidor MCP stdio o
    stdin é o pipe do JSON-RPC, com uma leitura síncrona sempre pendente. O
    SketchUp herdava esse handle, bloqueava no I/O do stdin atrás daquela leitura
    e nunca abria o modelo ("Sem nome", sem resposta) — todo su_* via MCP dava
    TIMEOUT, enquanto o mesmo job chamado direto terminava em ~10 s.

    CREATE_BREAKAWAY_FROM_JOB: clientes MCP no Windows põem o servidor num Job
    Object KILL_ON_JOB_CLOSE; sem sair do job, o SketchUp morre quando o servidor
    fecha. Se o job não permite breakaway, o CreateProcess recusa — tenta de novo
    sem a flag (o SketchUp abre, mas segue o ciclo de vida do job)."""
    base = getattr(subprocess, "DETACHED_PROCESS", 0)
    breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    kw = dict(env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, close_fds=True)
    if breakaway:
        try:
            return subprocess.Popen(cmd, creationflags=base | breakaway, **kw)  # noqa: S603
        except OSError:
            pass  # job sem JOB_OBJECT_LIMIT_BREAKAWAY_OK
    return subprocess.Popen(cmd, creationflags=base, **kw)  # noqa: S603


class Handle(Protocol):
    pid: int

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...


class PidHandle:
    """Handle de um processo que NAO e nosso filho (criado via WMI): so PID, `poll` por tasklist, `terminate` por PID."""

    def __init__(self, pid: int):
        self.pid = int(pid)

    def poll(self) -> int | None:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH", "/FI", f"PID eq {self.pid}"],  # noqa: S603,S607
                             capture_output=True, text=True).stdout
        return None if f'"{self.pid}"' in out else 0

    def terminate(self) -> None:
        subprocess.run(["taskkill", "/PID", str(self.pid)], capture_output=True)  # noqa: S603,S607 — so o PID dele


def spawn_outside_job(cmd: list[str]) -> Handle | None:
    """Sobe o processo FORA do Job Object de quem chamou (L2 P3b, 2026-10-19).

    O cliente MCP em Python (mcp 1.28) poe o servidor num Job Object e o encerra com `TerminateJobObject` ao fechar: um
    SketchUp aberto por `su_open` morria junto, apesar de `spawn_detached` tentar o breakaway (o job do cliente nao o
    permite e o fallback entra no job). `su_open` abre uma janela PARA O HUMANO, que nao pode acompanhar o ciclo de vida
    do cliente. Um processo criado por `Win32_Process.Create` (WMI) e filho do servico WMI, nao do servidor: fica fora
    do job. Devolve None quando nao da (nao Windows, WMI recusou, PID nao veio) — o chamador cai no `spawn_detached`.
    Sem env customizado: o processo herda o ambiente do servico WMI, nao o do servidor."""
    if sys.platform != "win32":
        return None
    line = subprocess.list2cmdline(cmd).replace("'", "''")
    script = ("$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='" + line + "'}; "
              "if ($r.ReturnValue -ne 0) { exit 2 }; Write-Output $r.ProcessId")
    try:
        done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],  # noqa: S603,S607
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    pid = (done.stdout or "").strip().splitlines()[-1:] or [""]
    return PidHandle(int(pid[0])) if done.returncode == 0 and pid[0].isdigit() else None


class System:
    """Tudo que toca SO, processo e relógio de verdade."""

    def platform(self) -> str:
        return sys.platform

    def exists(self, path: Path) -> bool:
        return Path(path).exists()

    def tasklist(self) -> str:
        out = subprocess.run(  # noqa: S603,S607 — comando fixo, sem entrada do usuário
            ["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {IMAGE}"],
            capture_output=True, text=True,
        )
        return out.stdout or ""

    def taskkill_pid(self, pid: int, *, force: bool) -> int:
        cmd = ["taskkill", "/PID", str(int(pid))]
        if force:
            cmd.append("/F")
        return subprocess.run(cmd, capture_output=True).returncode  # noqa: S603

    def popen(self, cmd: list[str], env: dict[str, str] | None = None) -> Handle:
        return spawn_detached(cmd, env)  # comando montado aqui, caminhos validados

    def popen_outside_job(self, cmd: list[str]) -> Handle | None:
        return spawn_outside_job(cmd)

    def now(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True)
class Locations:
    exe: Path
    plugins_dir: Path
    vray_exe: Path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Locations":
        env = os.environ if env is None else env
        return cls(
            exe=Path(env.get("SKETCHUP_EXE") or EXE_DEFAULT),
            plugins_dir=Path(os.path.expandvars(env.get("SKETCHUP_PLUGINS") or PLUGINS_DEFAULT)),
            vray_exe=Path(env.get("VRAY_EXE") or VRAY_EXE_DEFAULT),
        )


def parse_tasklist(raw: str) -> list[dict[str, Any]]:
    """`tasklist /FO CSV /NH` → [{pid, mem_kb}]. Sem instância, o tasklist
    imprime uma linha "INFO: ..." — que não é CSV de processo e é ignorada."""
    rows = []
    for rec in csv.reader(io.StringIO(raw)):
        if len(rec) < 2 or rec[0].strip().lower() != IMAGE.lower():
            continue
        try:
            pid = int(rec[1])
        except ValueError:
            continue
        mem = None
        if len(rec) >= 5:
            digits = "".join(ch for ch in rec[4] if ch.isdigit())
            mem = int(digits) if digits else None
        rows.append({"pid": pid, "mem_kb": mem})
    return rows


class SketchUp:
    def __init__(self, system: System | None = None, locations: Locations | None = None):
        self.system = system or System()
        self.loc = locations or Locations.from_env()

    # -- leitura -----------------------------------------------------------
    def supported(self) -> bool:
        return self.system.platform().startswith("win")

    def instances(self) -> list[dict[str, Any]]:
        if not self.supported():
            return []
        return parse_tasklist(self.system.tasklist())

    def status(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "platform": self.system.platform(),
            "platform_supported": self.supported(),
            "exe": str(self.loc.exe),
            "exe_found": self.system.exists(self.loc.exe),
            "plugins_dir": str(self.loc.plugins_dir),
            "autorun_plugin_present": self.system.exists(self.loc.plugins_dir / AUTORUN_PLUGIN),
            "vray_exe_found": self.system.exists(self.loc.vray_exe),
            "instances": self.instances(),
            "server_job": job_info(),
        }
        if not out["platform_supported"]:
            out["note"] = ("SketchUp só roda no Windows. As tools puras (gates, "
                           "classes, inventário) seguem funcionando; as su_* que "
                           "sobem o SketchUp respondem UNAVAILABLE.")
        elif not out["exe_found"]:
            out["note"] = "SketchUp.exe não encontrado — ajuste a env SKETCHUP_EXE."
        return out

    def unavailable(self) -> str | None:
        """Motivo de não dar para subir o SketchUp agora, ou None."""
        if not self.supported():
            return f"SketchUp exige Windows (plataforma: {self.system.platform()})"
        if not self.system.exists(self.loc.exe):
            return f"SketchUp.exe não encontrado em {self.loc.exe} (env SKETCHUP_EXE)"
        return None

    # -- ação --------------------------------------------------------------
    def open(self, skp: Path) -> dict[str, Any]:
        """Abre um .skp numa janela nova, DESANEXADA: é app que o Felipe vai usar,
        não filho a vigiar — fechar o MCP não pode fechar o SketchUp."""
        why = self.unavailable()
        if why:
            return {"status": "UNAVAILABLE", "reason": why}
        skp = Path(skp)
        if skp.suffix.lower() != ".skp" or not self.system.exists(skp):
            return {"status": "ERROR", "reason": f"não é um .skp existente: {skp}"}
        # absoluto: o processo criado via WMI nasce em outro diretório de trabalho (um caminho relativo abriria "Sem nome")
        cmd = [str(self.loc.exe), str(skp.resolve())]
        outside = getattr(self.system, "popen_outside_job", None)
        h = outside(cmd) if outside else None
        escaped = h is not None
        if h is None:                                   # sem WMI / nao Windows / dublê: filho desanexado, que pode seguir o job do cliente
            h = self.system.popen(cmd)
        return {"status": "OPENED", "pid": getattr(h, "pid", None), "skp": str(skp), "outside_job": escaped}

    def close(self, *, pid: int | None = None, all_instances: bool = False,
              force: bool = False, confirm: bool = False,
              grace_s: float = 5.0) -> dict[str, Any]:
        if not self.supported():
            return {"status": "UNAVAILABLE",
                    "reason": f"SketchUp exige Windows (plataforma: {self.system.platform()})"}
        running = {r["pid"] for r in self.instances()}
        if pid is not None:
            if pid not in running:
                return {"status": "ERROR", "reason": f"PID {pid} não é um SketchUp rodando",
                        "running": sorted(running)}
            targets = [pid]
        elif all_instances:
            targets = sorted(running)
        else:
            return {"status": "ERROR",
                    "reason": "diga qual: pid=<n> ou all_instances=true",
                    "running": sorted(running)}
        if not targets:
            return {"status": "NOTHING_TO_CLOSE", "running": []}
        if not confirm:
            return {
                "status": "CONFIRMATION_REQUIRED",
                "would_close": targets,
                "force": force,
                "warning": ("fechar pode descartar trabalho não salvo nessas janelas. "
                            "Chame de novo com confirm=true para autorizar."
                            + (" force=true mata sem perguntar se quer salvar." if force else "")),
            }
        for t in targets:
            self.system.taskkill_pid(t, force=force)
        deadline = self.system.now() + grace_s
        still = set(targets)
        while still and self.system.now() < deadline:
            self.system.sleep(0.5)
            still &= {r["pid"] for r in self.instances()}
        return {
            "status": "CLOSED" if not still else "PARTIAL",
            "closed": sorted(set(targets) - still),
            "still_running": sorted(still),
            **({"hint": "o SketchUp provavelmente está perguntando se quer salvar; "
                        "responda na janela, ou repita com force=true"} if still and not force else {}),
        }
