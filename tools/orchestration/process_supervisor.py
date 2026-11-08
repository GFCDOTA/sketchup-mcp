"""Windows process-tree lifetime primitive for FP-060 P2.

A Job Object is not a sandbox: it does not deny network, filesystem, credentials,
indirect process creation, or already-issued effects. This primitive is for
trusted, explicitly launched processes only; it does not enable PR code execution.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path

from tools.orchestration.appcontainer import AppContainerProfile


class ProcessSupervisorError(RuntimeError):
    """A supervised process could not be safely launched or observed."""


if os.name == "nt":
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _HANDLE = wintypes.HANDLE
    _SIZE = ctypes.c_size_t

    class _BasicLimits(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", _SIZE),
                    ("MaximumWorkingSetSize", _SIZE), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", _SIZE), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount",
            "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", _SIZE), ("JobMemoryLimit", _SIZE),
                    ("PeakProcessMemoryUsed", _SIZE), ("PeakJobMemoryUsed", _SIZE)]

    class _StartupInfo(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                    ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                    ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                    ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                    ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                    ("lpReserved2", ctypes.c_void_p), ("hStdInput", _HANDLE),
                    ("hStdOutput", _HANDLE), ("hStdError", _HANDLE)]

    class _StartupInfoEx(ctypes.Structure):
        _fields_ = [("startup", _StartupInfo), ("attributes", ctypes.c_void_p)]

    class _SecurityCapabilities(ctypes.Structure):
        _fields_ = [("sid", ctypes.c_void_p), ("capabilities", ctypes.c_void_p),
                    ("count", wintypes.DWORD), ("reserved", wintypes.DWORD)]

    class _ProcessInfo(ctypes.Structure):
        _fields_ = [("process", _HANDLE), ("thread", _HANDLE),
                    ("pid", wintypes.DWORD), ("tid", wintypes.DWORD)]

    def _bind(name, args, result):
        fn = getattr(_k32, name)
        fn.argtypes, fn.restype = args, result
        return fn

    _create_job = _bind("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], _HANDLE)
    _set_job = _bind("SetInformationJobObject", [_HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL)
    _init_attrs = _bind("InitializeProcThreadAttributeList", [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                                               ctypes.POINTER(_SIZE)], wintypes.BOOL)
    _update_attrs = _bind("UpdateProcThreadAttribute", [ctypes.c_void_p, wintypes.DWORD, _SIZE, ctypes.c_void_p,
                                                        _SIZE, ctypes.c_void_p, ctypes.c_void_p], wintypes.BOOL)
    _delete_attrs = _bind("DeleteProcThreadAttributeList", [ctypes.c_void_p], None)
    _create_process = _bind("CreateProcessW", [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                               wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
                                               ctypes.POINTER(_StartupInfoEx), ctypes.POINTER(_ProcessInfo)],
                            wintypes.BOOL)
    _close = _bind("CloseHandle", [_HANDLE], wintypes.BOOL)
    _wait = _bind("WaitForSingleObject", [_HANDLE, wintypes.DWORD], wintypes.DWORD)
    _exit_code = _bind("GetExitCodeProcess", [_HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL)
    _terminate_job = _bind("TerminateJobObject", [_HANDLE, wintypes.UINT], wintypes.BOOL)
    _resume_thread = _bind("ResumeThread", [_HANDLE], wintypes.DWORD)


def _error(action):
    return ProcessSupervisorError(f"{action}: Windows error {ctypes.get_last_error()}")


class WindowsJob:
    """Launch one trusted process already assigned to a kill-on-close Job Object.

    Closing this object kills the job tree, even after the root exits. A supervisor
    crash closes its non-inheritable job handle. Child handles are never inherited.
    No fallback launches an uncontained process when the job API is unavailable.
    An optional AppContainer profile adds a zero-capability token; by itself it
    does not establish safe workspace ACLs or authorize untrusted execution.
    """

    def __init__(self, argv: list[str], *, cwd: str | Path, env: dict[str, str], suspended: bool = False,
                 profile: AppContainerProfile | None = None):
        if os.name != "nt":
            raise ProcessSupervisorError("Windows Job Objects are required")
        if profile is not None and not isinstance(profile, AppContainerProfile):
            raise TypeError("profile must be an AppContainerProfile")
        profile_sid = profile.sid if profile is not None else None
        if not argv or not Path(argv[0]).is_absolute():
            raise ValueError("argv[0] must be an absolute executable path")
        if not Path(cwd).is_dir():
            raise ValueError("cwd must be an existing directory")
        if not env or any(not k or "=" in k or "\0" in k or "\0" in v for k, v in env.items()):
            raise ValueError("an explicit valid environment is required")
        self._job = self._process = self._thread = None
        self.pid = None
        job = _create_job(None, None)
        if not job:
            raise _error("CreateJobObjectW")
        self._job = job
        attrs_initialized = False
        try:
            limits = _ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not _set_job(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise _error("SetInformationJobObject")
            size = _SIZE()
            attribute_count = 2 if profile_sid is not None else 1
            _init_attrs(None, attribute_count, 0, ctypes.byref(size))
            if not size.value:
                raise _error("InitializeProcThreadAttributeList size")
            attrs = ctypes.create_string_buffer(size.value)
            if not _init_attrs(attrs, attribute_count, 0, ctypes.byref(size)):
                raise _error("InitializeProcThreadAttributeList")
            attrs_initialized = True
            job_list = (_HANDLE * 1)(job)
            # PROC_THREAD_ATTRIBUTE_JOB_LIST: assignment is part of process creation.
            if not _update_attrs(attrs, 0, 0x0002000D, job_list, ctypes.sizeof(job_list), None, None):
                raise _error("UpdateProcThreadAttribute JOB_LIST")
            if profile_sid is not None:
                caps = _SecurityCapabilities(profile_sid, None, 0, 0)
                if not _update_attrs(attrs, 0, 0x00020009, ctypes.byref(caps), ctypes.sizeof(caps), None, None):
                    raise _error("UpdateProcThreadAttribute SECURITY_CAPABILITIES")
            startup = _StartupInfoEx()
            startup.startup.cb = ctypes.sizeof(startup)
            startup.attributes = ctypes.cast(attrs, ctypes.c_void_p)
            info = _ProcessInfo()
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
            block = ctypes.create_unicode_buffer("\0".join(f"{k}={v}" for k, v in sorted(env.items(), key=lambda x: x[0].upper())) + "\0\0")
            flags = 0x00080000 | 0x00000400 | 0x08000000  # EXTENDED_STARTUPINFO, UNICODE_ENV, NO_WINDOW
            if suspended:
                flags |= 0x00000004  # CREATE_SUSPENDED
            if not _create_process(argv[0], command, None, None, False, flags, block, str(cwd),
                                   ctypes.byref(startup), ctypes.byref(info)):
                raise _error("CreateProcessW")
            self._process, self.pid = info.process, info.pid
            if suspended:
                self._thread = info.thread
            else:
                _close(info.thread)
        except BaseException:
            self.close()
            raise
        finally:
            if attrs_initialized:
                _delete_attrs(attrs)

    def resume(self):
        """Resume a process created suspended; failure leaves it in the job."""
        if not self._thread:
            raise ProcessSupervisorError("process is not suspended")
        if _resume_thread(self._thread) == 0xFFFFFFFF:
            raise _error("ResumeThread")
        _close(self._thread)
        self._thread = None

    def wait(self, timeout: float | None = None) -> int | None:
        """Return the root exit code, or None on timeout; children may still exist."""
        if not self._process:
            raise ProcessSupervisorError("job is closed")
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be nonnegative")
        ms = 0xFFFFFFFF if timeout is None else min(int(timeout * 1000), 0xFFFFFFFE)
        state = _wait(self._process, ms)
        if state == 0x102:
            return None
        if state != 0:
            raise _error("WaitForSingleObject")
        code = wintypes.DWORD()
        if not _exit_code(self._process, ctypes.byref(code)):
            raise _error("GetExitCodeProcess")
        return code.value

    def terminate(self):
        if self._job and not _terminate_job(self._job, 1):
            raise _error("TerminateJobObject")

    def close(self):
        if self._thread:
            _close(self._thread)
            self._thread = None
        if self._job:
            _close(self._job)
            self._job = None
        if self._process:
            _close(self._process)
            self._process = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def run_claimed(store, event: dict, argv: list[str], *, cwd: str | Path, env: dict[str, str],
                lease_seconds: float, timeout: float, interval: float = 0.2,
                profile: AppContainerProfile | None = None) -> tuple[str, int | None]:
    """Run a trusted process while renewing its EventStore lease.

    A watchdog independently kills the job at a conservative local deadline even
    if SQLite is blocked. Loss detected on renewal also kills the job. This is
    not a sandbox and cannot retract an external call or prevent indirect process
    creation; callers must not give the child publishing credentials. Results must
    still be committed through EventStore.complete() using the original token.
    Requires EventStore to validate lease time *after* acquiring its write lock.
    A profile adds a zero-capability AppContainer, but does not verify ACLs,
    prevent every escape, or authorize execution of untrusted code.
    """
    if lease_seconds <= 0 or timeout <= 0 or interval <= 0 or interval * 4 >= lease_seconds:
        raise ValueError("lease_seconds, timeout and interval must be positive; interval must be < lease/4")
    started = time.monotonic()
    if not store.renew(event, lease_seconds):
        return "lease_lost", None
    deadline = [started + lease_seconds - interval]
    lock = threading.Lock()
    stopped = threading.Event()
    lost = threading.Event()
    if time.monotonic() >= deadline[0]:
        return "lease_lost", None

    with WindowsJob(argv, cwd=cwd, env=env, suspended=True, profile=profile) as job:
        def watch():
            while not stopped.wait(min(interval, 0.05)):
                with lock:
                    if time.monotonic() < deadline[0]:
                        continue
                    lost.set()
                    job.terminate()
                    return

        watcher = threading.Thread(target=watch, name="lease-watchdog", daemon=True)
        watcher.start()
        try:
            with lock:
                if time.monotonic() >= deadline[0]:
                    lost.set()
                else:
                    job.resume()
            end = started + timeout
            next_renewal = time.monotonic() + interval
            while not lost.is_set():
                remaining = end - time.monotonic()
                if remaining <= 0:
                    job.terminate()
                    return "timeout", None
                code = job.wait(min(interval, remaining))
                if code is not None:
                    # Close the job before returning, including descendants left by root.
                    job.terminate()
                    renewed = store.renew(event, lease_seconds)
                    with lock:
                        if lost.is_set() or not renewed or time.monotonic() >= deadline[0]:
                            lost.set()
                            return "lease_lost", None
                        # No watchdog expiry can race the final ownership decision.
                        stopped.set()
                    return "finished", code
                if time.monotonic() >= next_renewal:
                    renewal_start = time.monotonic()
                    renewed = store.renew(event, lease_seconds)
                    with lock:
                        if not renewed or lost.is_set() or time.monotonic() >= deadline[0]:
                            lost.set()
                        else:
                            deadline[0] = renewal_start + lease_seconds - interval
                    if lost.is_set():
                        job.terminate()
                        break
                    next_renewal = time.monotonic() + interval
            job.terminate()
            return "lease_lost", None
        finally:
            stopped.set()
            watcher.join()
            # TerminateJobObject requests termination asynchronously. Never
            # report an outcome until the root process handle is signalled.
            # This alone does not establish that every descendant has exited.
            job.terminate()
            if job.wait(5.0) is None:
                raise ProcessSupervisorError("root process did not signal termination")
