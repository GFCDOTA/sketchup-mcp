"""Issue #589: o log do launcher e UTF-8 consistente. Roda o Windows PowerShell 5.1 REAL (o que o Agendador usa); pulado fora do Windows."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOGPS = ROOT / "tools/orchestration/event_bridge_log.ps1"
LAUNCHER = ROOT / "tools/orchestration/run_event_bridge.ps1"
PS = shutil.which("powershell")
needs_ps = pytest.mark.skipif(sys.platform != "win32" or not PS, reason="Windows PowerShell 5.1 real so existe no Windows")


def run_ps(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / "t.ps1"
    script.write_text(f'$ErrorActionPreference = "Stop"\n. "{LOGPS}"\n{body}\n', encoding="ascii")
    return subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, text=True, timeout=120)


def test_helper_and_launcher_are_ascii_only_and_the_launcher_no_longer_uses_tee_object():
    for p in (LOGPS, LAUNCHER):
        assert all(b < 128 for b in p.read_bytes()), p.name                   # PS 5.1 sem BOM le ANSI: acento quebra
    ps1 = LAUNCHER.read_text(encoding="ascii")
    code = "\n".join(line for line in ps1.splitlines() if not line.lstrip().startswith("#"))
    assert "Tee-Object" not in code and "Write-BridgeLog" in code and "Initialize-BridgeLog" in code
    assert "event_bridge_log.ps1" in code and "PYTHONUTF8" in code
    assert "api user" in ps1 and "exit 3" in ps1 and "if ($Execute)" in ps1   # identidade e opt-in de -Execute intactos


@needs_ps
def test_child_output_incl_accents_and_stderr_is_logged_as_strict_utf8_without_bom_or_nul(tmp_path):
    child = tmp_path / "child.py"
    child.write_text('import sys\nprint(\'{"msg": "a\\u00e7\\u00e3o \\u00e9 ok"}\')\nsys.stderr.write("erro no stderr\\n")\n', encoding="utf-8")
    log = tmp_path / "logs" / "event_bridge.log"
    body = f'''
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Initialize-BridgeLog -Path "{log}"
$ErrorActionPreference = "Continue"
& "{sys.executable}" "{child}" 2>&1 | ForEach-Object {{ Write-BridgeLog -Path "{log}" -Line "$_" }}
'''
    r = run_ps(tmp_path, body)
    assert r.returncode == 0, r.stderr
    raw = log.read_bytes()
    assert not raw.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")) and b"\x00" not in raw and b"\r" not in raw
    text = raw.decode("utf-8")                                               # estrito: levanta se nao for UTF-8 valido
    assert "ação é ok" in text and "erro no stderr" in text and text.endswith("\n")


@needs_ps
def test_legacy_utf16_or_mixed_log_is_preserved_byte_for_byte_and_a_clean_utf8_log_starts(tmp_path):
    log = tmp_path / "event_bridge.log"
    legacy = '{"at": "antigo-utf8"}\n'.encode() + '{"at": "novo-utf16"}\r\n'.encode("utf-16-le")
    log.write_bytes(legacy)
    r = run_ps(tmp_path, f'Initialize-BridgeLog -Path "{log}"\nWrite-BridgeLog -Path "{log}" -Line \'{{"at": "depois"}}\'')
    assert r.returncode == 0, r.stderr
    kept = list(tmp_path.glob("event_bridge.log.legacy-utf16-*"))
    assert len(kept) == 1 and kept[0].read_bytes() == legacy                 # preservado, nunca convertido nem apagado
    assert log.read_bytes() == b'{"at": "depois"}\n'


@needs_ps
def test_utf8_log_is_kept_when_small_and_rotated_to_dot_1_when_over_the_limit(tmp_path):
    log = tmp_path / "event_bridge.log"
    log.write_bytes(b'{"a": 1}\n')
    run_ps(tmp_path, f'Initialize-BridgeLog -Path "{log}" -MaxBytes 1000')
    assert log.read_bytes() == b'{"a": 1}\n' and not (tmp_path / "event_bridge.log.1").exists()
    log.write_bytes(b"x" * 200 + b"\n")
    (tmp_path / "event_bridge.log.1").write_bytes(b"velho")
    r = run_ps(tmp_path, f'Initialize-BridgeLog -Path "{log}" -MaxBytes 100')
    assert r.returncode == 0, r.stderr
    assert not log.exists() and (tmp_path / "event_bridge.log.1").read_bytes() == b"x" * 200 + b"\n"
