"""Real Windows AppContainer negative isolation tests with synthetic files.

These tests do not authorize execution of agents or untrusted PR code.
"""
from __future__ import annotations

import base64
import ctypes
import os
import subprocess
from ctypes import wintypes
from pathlib import Path

import pytest

from tools.orchestration import appcontainer
from tools.orchestration import process_supervisor as ps
from tools.orchestration.appcontainer import AppContainerError, AppContainerProfile
from tools.orchestration.event_store import EventStore

pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires real Windows AppContainer")


def _child_env():
    env_keep = {"SYSTEMROOT", "WINDIR", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP",
                "COMSPEC", "PATHEXT", "ALLUSERSPROFILE", "PROGRAMDATA"}
    env = {key: value for key, value in os.environ.items() if key.upper() in env_keep}
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    return env


def test_appcontainer_limits_file_access_and_has_no_capabilities(tmp_path):
    allowed, outside = tmp_path / "allowed test", tmp_path / "outside test"
    allowed.mkdir()
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("synthetic sentinel", encoding="utf-8")

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    sid_to_string = advapi.ConvertSidToStringSidW
    sid_to_string.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    sid_to_string.restype = wintypes.BOOL
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [ctypes.c_void_p], ctypes.c_void_p
    open_token = advapi.OpenProcessToken
    open_token.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    open_token.restype = wintypes.BOOL
    get_token = advapi.GetTokenInformation
    get_token.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD)]
    get_token.restype = wintypes.BOOL

    with AppContainerProfile() as profile:
        text = wintypes.LPWSTR()
        assert sid_to_string(profile.sid, ctypes.byref(text))
        sid_string = text.value
        kernel.LocalFree(text)
        # Grant only this synthetic, newly created test directory.
        icacls = str(Path(os.environ["SystemRoot"]) / "System32" / "icacls.exe")
        for args in ([icacls, str(allowed), "/grant", f"*{sid_string}:(OI)(CI)M"],
                     [icacls, str(allowed), "/setintegritylevel", "(OI)(CI)L"]):
            proc = subprocess.run(args, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            assert proc.returncode == 0, proc.stderr

        writable = str(allowed / "allowed.txt").replace("'", "''")
        blocked = str(sentinel).replace("'", "''")
        script = (f"$ErrorActionPreference='Stop'; try {{ Set-Content -LiteralPath '{writable}' -Value 'allowed' -Encoding UTF8; "
                  f"try {{ Get-Content -LiteralPath '{blocked}' | Out-Null; exit 23 }} catch {{ exit 24 }} "
                  "} catch { exit 31 }")
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        executable = str(Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
        env = _child_env()
        argv = [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
        with ps.WindowsJob(argv, cwd=Path(executable).parent, env=env, suspended=True, profile=profile) as job:
            token = wintypes.HANDLE()
            assert open_token(job._process, 0x0008, ctypes.byref(token))
            try:
                result_value, length = wintypes.DWORD(), wintypes.DWORD()
                assert get_token(token, 29, ctypes.byref(result_value), ctypes.sizeof(result_value), ctypes.byref(length))
                assert result_value.value == 1  # TokenIsAppContainer
                get_token(token, 30, None, 0, ctypes.byref(length))
                buffer = ctypes.create_string_buffer(length.value)
                assert get_token(token, 30, buffer, length, ctypes.byref(length))
                assert ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value == 0
            finally:
                ps._close(token)
            job.resume()
            assert job.wait(15) == 24  # denied reading the sentinel outside the granted folder
            assert (allowed / "allowed.txt").read_text(encoding="utf-8-sig").strip() == "allowed"

    with pytest.raises(AppContainerError, match="closed"):
        _ = profile.sid


def test_security_attribute_failure_does_not_launch_uncontained_process(tmp_path, monkeypatch):
    executable = str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe")
    original = ps._update_attrs
    attempted_launch = []

    def record_launch(*args):
        attempted_launch.append(True)
        raise AssertionError("uncontained process launch attempted")

    def reject_security_attribute(*args):
        if args[2] == 0x00020009:
            return 0
        return original(*args)

    monkeypatch.setattr(ps, "_update_attrs", reject_security_attribute)
    monkeypatch.setattr(ps, "_create_process", record_launch)
    with AppContainerProfile() as profile:
        with pytest.raises(ps.ProcessSupervisorError, match="SECURITY_CAPABILITIES"):
            ps.WindowsJob([executable, "/d", "/c", "echo unexpected"], cwd=tmp_path,
                          env={"SystemRoot": os.environ["SystemRoot"]}, profile=profile)
    assert not attempted_launch


def test_leased_process_can_run_inside_zero_capability_profile(tmp_path):
    store = EventStore(tmp_path / "events.db")
    store.publish("IMPLEMENT_REQUESTED", "key", "pr:7", {})
    event = store.claim("IMPLEMENT_REQUESTED", "worker", 10)
    executable = str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe")
    with AppContainerProfile() as profile:
        result = ps.run_claimed(store, event, [executable, "/d", "/c", "exit", "7"],
                                cwd=Path(executable).parent, env=_child_env(),
                                lease_seconds=10, timeout=15, interval=.2, profile=profile)
    assert result == ("finished", 7)
    store.complete(event, {"exit": 7})


def test_existing_profile_is_never_reused_or_deleted(monkeypatch):
    deleted = []
    monkeypatch.setattr(appcontainer, "_create", lambda *_: -2147024713)  # HRESULT_FROM_WIN32(ERROR_ALREADY_EXISTS)
    monkeypatch.setattr(appcontainer, "_delete", lambda name: deleted.append(name))
    with pytest.raises(AppContainerError, match="CreateAppContainerProfile"):
        AppContainerProfile()
    assert deleted == []


def test_profile_cleanup_failure_is_reported_and_can_be_retried(monkeypatch):
    with AppContainerProfile() as profile:
        with monkeypatch.context() as patch:
            patch.setattr(appcontainer, "_delete", lambda _: -1)
            with pytest.raises(AppContainerError, match="DeleteAppContainerProfile"):
                profile.close()
            assert profile.sid
        # Context exit retries the real deletion after the simulated failure.
