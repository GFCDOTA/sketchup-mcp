"""P3: ponte para CLIs legadas que precisam de Start-Process no desktop.

Não usar /IM nem terminar processo descoberto globalmente. O PID é retornado
pelo próprio Start-Process -PassThru e só esse PID pode receber close gracioso.
Para jobs novos, preferir tools.sketchup.batch.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _ps_literal(value: object) -> str:
    """Escapa uma string literal PowerShell sem interpolação de comando."""
    return "'" + str(value).replace("'", "''") + "'"


def launch_owned(executable: str | Path, input_skp: str | Path,
                 ruby_script: str | Path, *, env: dict[str, str],
                 timeout_s: int = 60) -> int:
    """Lança SketchUp pela instância interativa e devolve EXCLUSIVAMENTE o PID criado.

    Se o PowerShell não devolver um PID válido, falha; não faz fallback
    para buscas por nome e não encerra nenhuma janela já aberta.
    """
    args = ", ".join((
        _ps_literal('"' + str(input_skp) + '"'),
        _ps_literal("-RubyStartup"),
        _ps_literal('"' + str(ruby_script) + '"'),
    ))
    command = (
        "$ErrorActionPreference='Stop'; "
        f"$p = Start-Process -FilePath {_ps_literal(executable)} "
        f"-ArgumentList {args} -PassThru; "
        "[Console]::Out.WriteLine($p.Id)"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        env=env, capture_output=True, text=True, check=True, timeout=timeout_s,
    )
    output = (result.stdout or "").strip().splitlines()
    if not output or not output[-1].strip().isdigit() or int(output[-1]) <= 0:
        raise RuntimeError("Start-Process não retornou o PID próprio do SketchUp")
    return int(output[-1])


def terminate_owned(pid: int) -> bool:
    """Encerra (`taskkill /PID <pid> /F`) SO o processo que o PROPRIO script subiu — para scripts de render/prova que nao
    salvam e nao podem ficar presos num "salvar alteracoes?". Nunca por nome de imagem, nunca um PID descoberto."""
    if type(pid) is not int or pid <= 0:
        raise ValueError("PID proprio invalido")
    return subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True).returncode == 0


def close_owned(pid: int) -> bool:
    """Solicita fechamento SEM /F e SEM /IM. SketchUp decide sobre salvar."""
    if type(pid) is not int or pid <= 0:
        raise ValueError("PID próprio inválido")
    result = subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True)
    return result.returncode == 0
