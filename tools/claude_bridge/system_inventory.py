#!/usr/bin/env python3
"""System inventory for the cockpit Explorer / git-state / cost pages.

Extracted from server.py (SRP): top-level dir classification + size,
per-repo git state, and live claude.exe process accounting. All read-only
(filesystem walk + `git` + a PowerShell CIM query). server.py re-exports
system_map / git_inventory / live_processes for its route table.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _dir_size_mb(p: Path, cap: int = 8000):
    """Best-effort dir size in MB, bounded by `cap` files so big trees (.git) don't
    hang the endpoint. Returns (mb, capped)."""
    total = n = 0
    try:
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
                    n += 1
                    if n >= cap:
                        return round(total / 1e6, 1), True
            except OSError:
                pass
    except OSError:
        pass
    return round(total / 1e6, 1), False


def _classify_dir(p: Path) -> dict:
    """Human classification of a top-level E:\\Claude directory."""
    name = p.name
    known = {
        "sketchup-mcp": ("CANONICAL_REPO", "repo principal canônico (pipeline PDF→SKP + gate + .claude/)", "baixo", "não"),
        "claude-bridge": ("BRIDGE_SERVICE", "bridge standalone original (broker + server + .oauth_token + LIGAR-BRIDGE) — fallback/legado", "médio (contém o token)", "não — guarda o .oauth_token"),
        ".claude": ("CONFIG", "config/memória do projeto E:\\Claude (onde o chat roda)", "baixo", "não"),
    }
    if name in known:
        t, expl, risk, dele = known[name]
    elif name.startswith("wt-"):
        t, expl, risk, dele = ("WORKTREE", "git worktree (checkout isolado de um branch)", "baixo", "sim (git worktree remove)")
    elif name in (".venv", "venv", "env"):
        t, expl, risk, dele = ("VENV", "ambiente virtual Python", "baixo", "sim (recriável)")
    elif name == ".git":
        t, expl, risk, dele = ("GIT_INTERNAL", "interno do git", "ALTO", "NÃO")
    elif name in ("runs", "__pycache__", ".pytest_cache", "node_modules"):
        t, expl, risk, dele = ("RUNS_SCRATCH", "scratch / build output (gitignored)", "baixo", "sim")
    elif name == "artifacts":
        t, expl, risk, dele = ("ARTIFACTS", "deliverables versionados", "médio", "não")
    else:
        t, expl, risk, dele = ("UNKNOWN", "não classificado — investigar", "?", "?")
    return {"type": t, "expl": expl, "risk": risk, "can_delete": dele}


def system_map() -> dict:
    """Scan E:\\Claude top-level and explain each dir (the Explorer page)."""
    root = REPO_ROOT.parent
    items = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        entries = []
    for p in entries:
        if not p.is_dir():
            continue
        mb, capped = _dir_size_mb(p)
        try:
            mod = round(time.time() - p.stat().st_mtime)
        except OSError:
            mod = None
        items.append({"name": p.name, **_classify_dir(p), "mb": mb,
                      "mb_capped": capped, "modified_sec": mod,
                      "has_git": (p / ".git").exists(),
                      "is_worktree": (p / ".git").is_file()})
    return {"root": str(root), "items": items,
            "unknown": [i["name"] for i in items if i["type"] == "UNKNOWN"]}


def git_inventory() -> dict:
    """Read-only git state for every repo/worktree under E:\\Claude. Mutates nothing."""
    root = REPO_ROOT.parent

    def g(p, *args):
        try:
            r = subprocess.run(["git", "-C", str(p), *args], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=10)
            return (r.stdout or "").strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    repos = []
    try:
        candidates = sorted(x for x in root.iterdir() if x.is_dir())
    except OSError:
        candidates = []
    for p in candidates:
        if not (p / ".git").exists():
            continue
        lines = [ln for ln in g(p, "status", "--porcelain").splitlines() if ln.strip()]
        untracked = sum(1 for ln in lines if ln.startswith("??"))
        repos.append({"path": p.name, "is_worktree": (p / ".git").is_file(),
                      "branch": g(p, "rev-parse", "--abbrev-ref", "HEAD"),
                      "head": g(p, "rev-parse", "--short", "HEAD"),
                      "remote": g(p, "remote", "get-url", "origin"),
                      "last_commit": g(p, "log", "-1", "--oneline"),
                      "dirty": len(lines) > 0, "untracked": untracked,
                      "changed": len(lines) - untracked})
    return {"repos": repos, "dirty": [r["path"] for r in repos if r["dirty"]]}


def _classify_processes(procs: list) -> dict:
    """Separa os processos 'claude.exe' em APP DESKTOP (Electron: renderer/gpu/utility —
    so RAM) vs SESSOES CLI (claude-code, stream-json — as que PODEM custar, e so quando
    geram). Logica pura pra ser testavel sem enumerar processos de verdade."""
    desktop_ram = desktop_n = 0
    cli = []
    for p in procs:
        cl = p.get("CommandLine") or ""
        ram = int((p.get("WorkingSetSize") or 0) / (1024 * 1024))
        if "claude-code" in cl or "stream-json" in cl:
            cpu = int(((p.get("KernelModeTime") or 0) + (p.get("UserModeTime") or 0)) / 1e7)
            cli.append({"pid": p.get("ProcessId"), "ram_mb": ram, "cpu_sec": cpu,
                        "effort": "max" if "--effort max" in cl else "?"})
        else:
            desktop_ram += ram
            desktop_n += 1
    cli.sort(key=lambda x: x.get("cpu_sec", 0), reverse=True)
    return {"cli_sessions": cli, "cli_count": len(cli),
            "desktop_app": {"processes": desktop_n, "ram_mb": desktop_ram}}


def live_processes() -> dict:
    """A VERDADE sobre 'esta gastando dinheiro?'. Token so queima durante geracao ativa:
    sessao CLI idle = R$0; app desktop aberto = so RAM; transcript parado no disco =
    historico, R$0. Read-only — nao mata nada."""
    ps = ("Get-CimInstance Win32_Process -Filter \"name='claude.exe'\" | "
          "Select-Object ProcessId,WorkingSetSize,KernelModeTime,UserModeTime,CommandLine | "
          "ConvertTo-Json -Compress")
    procs = []
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=15)
        data = json.loads(r.stdout or "[]")
        procs = data if isinstance(data, list) else [data]
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        procs = []
    out = _classify_processes(procs)
    n = out["cli_count"]
    out["verdict"] = ("Nenhuma sessao CLI viva — nada pode estar custando."
                      if n == 0 else
                      f"{n} sessao(oes) CLI viva(s), todas idle = R$0. Token so queima gerando.")
    out["nota"] = ("App Desktop aberto usa RAM (~{} MB), nao dinheiro. Sessao parada e "
                   "transcript no disco = historico, R$0."
                   ).format(out["desktop_app"]["ram_mb"])
    return out
