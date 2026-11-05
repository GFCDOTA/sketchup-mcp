"""Adapters that launch the REAL Claude Code and Codex CLIs as subprocesses.

Safety properties (asserted by tests/evidence, not just intended):
- No --dangerously-skip-permissions / --yolo / bypass flags (FORBIDDEN_FLAGS guard).
- Paid-API credentials are removed from the child env, so both CLIs must use
  their existing subscription login (Claude OAuth / ChatGPT login).
- GitHub credentials are removed: agents cannot push even if they tried.
- Claude: only Read/Write/Edit tools exist (no Bash, no web), no user/project
  settings or hooks, no MCP servers, and dontAsk mode denies anything not
  pre-approved.
- Codex: `codex exec --sandbox read-only`, ephemeral, structured output.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_FLAGS = ("--dangerously-skip-permissions", "--yolo", "--dangerously-bypass-approvals-and-sandbox",
                   "--full-auto", "bypassPermissions")
STRIPPED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY",
                "GH_TOKEN", "GITHUB_TOKEN", "GIT_ASKPASS", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                # nested-session markers of the parent Claude Code session
                "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")
_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                        r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,})")


def redact(text: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", text or "")


def resolve_bins() -> dict[str, list[str]]:
    """Resolve npm shims to the real executables so the recorded PID is the
    agent process itself, not a cmd.exe wrapper."""
    out: dict[str, list[str]] = {}
    claude = shutil.which("claude")
    if claude:
        native = Path(claude).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        out["claude"] = [str(native)] if native.exists() else [claude]
    codex = shutil.which("codex")
    if codex:
        js = Path(codex).parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        node = shutil.which("node")
        out["codex"] = [node, str(js)] if (js.exists() and node) else [codex]
    return out


def child_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED_ENV}
    env.update(extra or {})
    return env


@dataclass
class CliRun:
    argv: list[str]
    pid: int
    exit_code: int | None
    timed_out: bool
    duration_s: float
    stdout: str
    stderr: str


def run_cli(argv, stdin_text, cwd, timeout, stdout_path, stderr_path, on_start=None, env=None) -> CliRun:
    """Run one CLI process. `on_start(pid)` fires right after spawn so the
    caller can persist the PID before the (long) wait. On timeout the whole
    process tree is killed and the run is reported as timed_out, never ok."""
    for flag in FORBIDDEN_FLAGS:
        if any(flag in a for a in argv):
            raise ValueError(f"forbidden flag {flag} in argv")
    t0 = time.monotonic()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with open(stdout_path, "w", encoding="utf-8") as fo, open(stderr_path, "w", encoding="utf-8") as fe:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd=str(cwd), env=env or child_env(), text=True, encoding="utf-8",
                                errors="replace", creationflags=flags)
        if on_start:
            on_start(proc.pid)
        timed_out = False
        try:
            out, err = proc.communicate(stdin_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(proc.pid)
            out, err = proc.communicate()
        out, err = redact(out), redact(err)
        fo.write(out)
        fe.write(err)
    return CliRun(argv, proc.pid, proc.returncode, timed_out, round(time.monotonic() - t0, 2), out, err)


def kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:  # pragma: no cover - lab runs on Windows
        os.kill(pid, 9)


# --- argv builders ---------------------------------------------------------
def claude_argv(bins) -> list[str]:
    return [*bins["claude"], "-p",
            "--output-format", "json",
            "--permission-mode", "dontAsk",
            "--tools", "Read,Write,Edit",
            "--allowedTools", "Read,Write,Edit",
            "--setting-sources", "",
            "--strict-mcp-config",
            "--no-session-persistence"]


def codex_argv(bins, workspace, schema_path, out_path) -> list[str]:
    return [*bins["codex"], "exec",
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "-C", str(workspace),
            "--output-schema", str(schema_path),
            "--output-last-message", str(out_path),
            "-"]


def parse_claude_json(stdout: str) -> dict:
    """Claude -p --output-format json prints one JSON object. Raises on
    anything that is not an explicit success (auth error, max turns, ...)."""
    data = json.loads(stdout.strip())
    if data.get("is_error") or data.get("subtype") != "success":
        raise RuntimeError(f"claude reported failure: subtype={data.get('subtype')} "
                           f"api_error_status={data.get('api_error_status')} result={str(data.get('result'))[:300]}")
    return data
