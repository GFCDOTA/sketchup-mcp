"""Real Windows AppContainer negative isolation tests with synthetic files.

These tests do not authorize execution of agents or untrusted PR code.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import uuid
from ctypes import wintypes
from pathlib import Path

import pytest

from tools.orchestration import appcontainer
from tools.orchestration import process_supervisor as ps
from tools.orchestration.appcontainer import (
    AppContainerError,
    AppContainerProfile,
    create_workspace,
)
from tools.orchestration.event_store import EventStore

pytestmark = pytest.mark.skipif(os.name != "nt", reason="requires real Windows AppContainer")


def _child_env():
    env_keep = {"SYSTEMROOT", "WINDIR", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP",
                "COMSPEC", "PATHEXT", "ALLUSERSPROFILE", "PROGRAMDATA"}
    env = {key: value for key, value in os.environ.items() if key.upper() in env_keep}
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    return env


def test_appcontainer_limits_file_access_and_has_no_capabilities(tmp_path):
    outside = tmp_path / "outside test"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("synthetic sentinel", encoding="utf-8")

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    open_token = advapi.OpenProcessToken
    open_token.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    open_token.restype = wintypes.BOOL
    get_token = advapi.GetTokenInformation
    get_token.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD)]
    get_token.restype = wintypes.BOOL

    with AppContainerProfile() as profile:
        allowed = create_workspace(profile, tmp_path)

        executable = str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe")
        env = _child_env()
        env["SANDBOX_OUTPUT"] = f'"{allowed / "allowed.txt"}"'
        env["SANDBOX_COPY"] = f'"{allowed / "copy.txt"}"'
        env["SANDBOX_BLOCKED"] = f'"{sentinel}"'
        # Quoted paths are expanded from variables after cmd parses the command.
        command = "echo allowed>%SANDBOX_OUTPUT%&type %SANDBOX_BLOCKED%>%SANDBOX_COPY% 2>NUL&&exit 23||exit 24"
        argv = [executable, "/d", "/c", command]
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


def test_workspace_isolates_profiles_from_each_other(tmp_path):
    """Owner's file inside a workspace is not readable by a different profile."""
    executable = str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe")
    with AppContainerProfile() as owner, AppContainerProfile() as other:
        ws = create_workspace(owner, tmp_path)
        env = _child_env()
        env["SANDBOX_FILE"] = f'"{ws / "secret.txt"}"'
        # Owner creates a file — proven pattern (same as first test's echo).
        with ps.WindowsJob([executable, "/d", "/c", "echo secret>%SANDBOX_FILE%"],
                           cwd=Path(executable).parent, env=env, profile=owner) as job:
            assert job.wait(15) == 0
        assert (ws / "secret.txt").read_text(encoding="utf-8-sig").strip() == "secret"
        # A different profile cannot read that file.
        with ps.WindowsJob(
            [executable, "/d", "/c", "type %SANDBOX_FILE%>NUL 2>NUL&&exit 23||exit 24"],
            cwd=Path(executable).parent, env=env, profile=other,
        ) as job:
            assert job.wait(15) == 24


def test_workspace_never_reuses_existing_path(tmp_path, monkeypatch):
    fixed = uuid.UUID("00112233-4455-6677-8899-aabbccddeeff")
    target = tmp_path / ("sandbox-" + fixed.hex)
    target.mkdir()
    marker = target / "preserve.txt"
    marker.write_text("keep", encoding="utf-8")
    with AppContainerProfile() as profile:
        monkeypatch.setattr(appcontainer.uuid, "uuid4", lambda: fixed)
        with pytest.raises(AppContainerError, match="CreateDirectoryW"):
            create_workspace(profile, tmp_path)
    assert marker.read_text(encoding="utf-8") == "keep"


def test_workspace_security_descriptor_failure_creates_nothing(tmp_path, monkeypatch):
    with AppContainerProfile() as profile:
        monkeypatch.setattr(appcontainer, "_sddl_to_sd", lambda *_: 0)
        with pytest.raises(AppContainerError, match="ConvertStringSecurityDescriptor"):
            create_workspace(profile, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_token_facts_tell_a_contained_process_from_an_ordinary_one():
    executable = str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe")
    assert appcontainer.token_facts(os.getpid())["is_appcontainer"] is False
    with AppContainerProfile() as profile:
        with ps.WindowsJob([executable, "/d", "/c", "exit", "0"], cwd=Path(executable).parent, env=_child_env(),
                           suspended=True, profile=profile) as job:
            assert appcontainer.token_facts(job.pid) == {"is_appcontainer": True, "capabilities": 0}


def test_token_facts_of_a_process_that_cannot_be_opened_is_an_error_not_a_guess():
    with pytest.raises(AppContainerError, match="OpenProcess"):
        appcontainer.token_facts(0)
