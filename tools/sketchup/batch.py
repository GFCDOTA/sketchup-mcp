"""Rodar Ruby num SketchUp em lote: `SketchUp.exe <in.skp> -RubyStartup <job.rb>`.

Por que `-RubyStartup` e não o `autorun_consume.rb`: o plugin de autorun não é
versionado e deixa estado no `Plugins` (um `*_control.txt` esquecido já fez o
SketchUp do Felipe apagar e salvar por cima do arquivo aberto — 2026-05-20).
`-RubyStartup` vale para AQUELE processo e mais nenhum.

Contrato com o job Ruby (`tools/sketchup/ruby/skmcp_runtime.rb`):
  SKMCP_PARAMS  caminho do JSON de parâmetros (escrito aqui)
  SKMCP_RESULT  caminho do JSON de resultado (escrito pelo Ruby, atômico)
  SKMCP_QUIT    "1" → o Ruby fecha o PRÓPRIO SketchUp depois de escrever

O resultado existir é a prova de que ESTA execução terminou: ele é apagado
antes de subir. Modo (`su_runner_safety`): `interactive` (default local) deixa
o SketchUp aberto para inspeção; `headless` (default no CI) fecha — e só o
processo que nós mesmos subimos, nunca outro.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tools.sketchup.process import SketchUp
from tools.sketchup.runner_safety import MODES, parse_mode, should_terminate

RUBY_DIR = Path(__file__).resolve().parent / "ruby"
# Carrega um script Ruby neste processo (substitui o control file do autorun no Plugins global).
LAUNCHER = RUBY_DIR / "skmcp_launch.rb"


def launch_env(script: Path, error_file: Path | None = None, defer_s: float | None = None) -> dict[str, str]:
    """Env que faz o `skmcp_launch.rb` carregar `script` (use com `-RubyStartup LAUNCHER`)."""
    env = {"SKMCP_LAUNCH_SCRIPT": _slash(script)}
    if error_file is not None:
        env["SKMCP_LAUNCH_ERROR"] = _slash(error_file)
    if defer_s is not None:
        env["SKMCP_LAUNCH_DEFER"] = str(defer_s)
    return env


def resolve_mode(mode: str | None = None, env: dict[str, str] | None = None) -> str:
    """Modo explícito vence; senão RUN_MODE; senão headless no CI, interactive fora.
    `argv=[]`: o argv do processo do MCP não é do usuário e não pode decidir."""
    env = os.environ if env is None else env
    if mode is not None:
        if mode not in MODES:
            raise ValueError(f"mode inválido: {mode!r} (válidos: {', '.join(MODES)})")
        return mode
    ci = (env.get("CI", "").lower() == "true" or env.get("GITHUB_ACTIONS", "").lower() == "true")
    return parse_mode(argv=[], env=env, default="headless" if ci else "interactive")


def _slash(p: Path) -> str:
    return str(Path(p).resolve()).replace("\\", "/")


def run_script(su: SketchUp, *, script: Path, done_marker: Path,
               skp_in: Path | None = None, env_extra: dict[str, str] | None = None,
               timeout_s: int = 240, mode: str | None = None) -> dict[str, Any]:
    """Sobe o SketchUp com `script` e espera `done_marker` aparecer."""
    mode = resolve_mode(mode)
    why = su.unavailable()
    if why:
        return {"status": "UNAVAILABLE", "reason": why, "mode": mode}
    if mode in ("attach", "manual"):
        return {"status": "UNAVAILABLE", "mode": mode,
                "reason": f"mode={mode} não sobe SketchUp (só lê arquivos)"}
    for what, p in (("script Ruby", script), ("skp de entrada", skp_in)):
        if p is not None and not su.system.exists(Path(p)):
            return {"status": "ERROR", "reason": f"{what} não encontrado: {p}", "mode": mode}

    done_marker = Path(done_marker)
    if done_marker.exists():
        done_marker.unlink()
    env = os.environ.copy()
    env.update(env_extra or {})
    cmd = [str(su.loc.exe)]
    if skp_in is not None:
        cmd.append(str(Path(skp_in).resolve()))  # posicional ANTES de -RubyStartup
    cmd += ["-RubyStartup", str(Path(script).resolve())]

    started = su.system.now()
    handle = su.system.popen(cmd, env)
    status = "TIMEOUT"
    while su.system.now() - started < timeout_s:
        if done_marker.exists():
            status = "DONE"
            break
        if handle.poll() is not None:
            # pode ter escrito e saído (SKMCP_QUIT) no mesmo intervalo
            status = "DONE" if done_marker.exists() else "SU_EXITED"
            break
        su.system.sleep(1)

    alive = handle.poll() is None
    terminated = False
    if alive and should_terminate(mode):
        handle.terminate()  # SÓ o filho que nós subimos
        terminated = True
    return {
        "status": status,
        "mode": mode,
        "pid": getattr(handle, "pid", None),
        "elapsed_s": round(su.system.now() - started, 2),
        "su_left_running": alive and not terminated,
        "command": cmd,
    }


def run_job(su: SketchUp, job: str, *, out_dir: Path, params: dict[str, Any],
            skp_in: Path | None = None, timeout_s: int = 240,
            mode: str | None = None, script: Path | None = None) -> dict[str, Any]:
    """Roda `ruby/<job>.rb` (ou `script`, para jobs de capacidade fora de tools/sketchup/ruby) com `params` e devolve o
    JSON que o Ruby escreveu."""
    try:
        mode = resolve_mode(mode)
    except ValueError as e:
        return {"status": "ERROR", "reason": str(e)}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    params_p = out_dir / f"{job}_params.json"
    result_p = out_dir / f"{job}_result.json"
    params_p.write_text(json.dumps({**params, "out_dir": _slash(out_dir)}, indent=2),
                        encoding="utf-8")
    run = run_script(
        su, script=script or RUBY_DIR / f"{job}.rb", done_marker=result_p, skp_in=skp_in,
        timeout_s=timeout_s, mode=mode,
        env_extra={
            "SKMCP_PARAMS": _slash(params_p),
            "SKMCP_RESULT": _slash(result_p),
            "SKMCP_QUIT": "1" if should_terminate(mode) else "0",
        },
    )
    out: dict[str, Any] = {"job": job, "out_dir": str(out_dir), **run}
    if run["status"] != "DONE":
        if run["status"] == "SU_EXITED":
            out["reason"] = "o SketchUp fechou antes de escrever o resultado"
        elif run["status"] == "TIMEOUT":
            out["reason"] = f"sem resultado em {timeout_s}s"
        return out
    try:
        result = json.loads(result_p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        out.update(status="ERROR", reason=f"resultado ilegível ({result_p}): {e}")
        return out
    out["status"] = "OK" if result.get("ok") else "FAILED"
    out["result"] = result
    return out
