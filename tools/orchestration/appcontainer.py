"""Temporary Windows AppContainer identity and workspace experiments.

A profile with no capabilities is only one layer of containment. Process
lifetime, indirect effects, workspace inputs and cleanup need separate controls.
This module does not activate a worker or authorize execution of untrusted code.
"""
from __future__ import annotations

import ctypes
import os
import uuid
from ctypes import wintypes
from pathlib import Path


class AppContainerError(RuntimeError):
    """AppContainer identity creation, use, or cleanup failed."""


if os.name == "nt":
    _userenv = ctypes.WinDLL("userenv", use_last_error=True)
    _advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _create = _userenv.CreateAppContainerProfile
    _create.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
                        wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    _create.restype = ctypes.c_long
    _delete = _userenv.DeleteAppContainerProfile
    _delete.argtypes, _delete.restype = [wintypes.LPCWSTR], ctypes.c_long
    _free_sid = _advapi.FreeSid
    _free_sid.argtypes, _free_sid.restype = [ctypes.c_void_p], ctypes.c_void_p
    _sid_string = _advapi.ConvertSidToStringSidW
    _sid_string.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    _sid_string.restype = wintypes.BOOL
    _open_token = _advapi.OpenProcessToken
    _open_token.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    _open_token.restype = wintypes.BOOL
    _token_info = _advapi.GetTokenInformation
    _token_info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                            ctypes.POINTER(wintypes.DWORD)]
    _token_info.restype = wintypes.BOOL
    _sddl_to_sd = _advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    _sddl_to_sd.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    _sddl_to_sd.restype = wintypes.BOOL
    _kernel.GetCurrentProcess.argtypes, _kernel.GetCurrentProcess.restype = [], wintypes.HANDLE
    _kernel.CloseHandle.argtypes, _kernel.CloseHandle.restype = [wintypes.HANDLE], wintypes.BOOL
    _kernel.LocalFree.argtypes, _kernel.LocalFree.restype = [ctypes.c_void_p], ctypes.c_void_p
    _kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel.OpenProcess.restype = wintypes.HANDLE

    class _SecurityAttributes(ctypes.Structure):
        _fields_ = [("length", wintypes.DWORD), ("descriptor", ctypes.c_void_p), ("inheritable", wintypes.BOOL)]

    _mkdir = _kernel.CreateDirectoryW
    _mkdir.argtypes, _mkdir.restype = [wintypes.LPCWSTR, ctypes.POINTER(_SecurityAttributes)], wintypes.BOOL


def _windows_error(operation):
    return AppContainerError(f"{operation} failed: Windows error {ctypes.get_last_error()}")


def _to_sid_string(sid):
    value = wintypes.LPWSTR()
    if not _sid_string(sid, ctypes.byref(value)):
        raise _windows_error("ConvertSidToStringSidW")
    try:
        return value.value
    finally:
        _kernel.LocalFree(value)


def _current_user_sid():
    token = wintypes.HANDLE()
    if not _open_token(_kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise _windows_error("OpenProcessToken")
    try:
        size = wintypes.DWORD()
        _token_info(token, 1, None, 0, ctypes.byref(size))  # TokenUser
        if not size.value:
            raise _windows_error("GetTokenInformation size")
        buffer = ctypes.create_string_buffer(size.value)
        if not _token_info(token, 1, buffer, size, ctypes.byref(size)):
            raise _windows_error("GetTokenInformation")
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
        return _to_sid_string(sid)
    finally:
        _kernel.CloseHandle(token)


def token_facts(pid: int) -> dict:
    """Ask the kernel whether a live process runs in an AppContainer and how many capabilities its token holds.

    This reads the token of the process that was actually created; it is not derived
    from the arguments used to create it. It says nothing about file ACLs.
    """
    if os.name != "nt":
        raise AppContainerError("Windows AppContainer is required")
    process = _kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not process:
        raise _windows_error("OpenProcess")
    try:
        token = wintypes.HANDLE()
        if not _open_token(process, 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
            raise _windows_error("OpenProcessToken")
        try:
            flag, size = wintypes.DWORD(), wintypes.DWORD()
            if not _token_info(token, 29, ctypes.byref(flag), ctypes.sizeof(flag), ctypes.byref(size)):  # TokenIsAppContainer
                raise _windows_error("GetTokenInformation TokenIsAppContainer")
            _token_info(token, 30, None, 0, ctypes.byref(size))  # TokenCapabilities
            if not size.value:
                raise _windows_error("GetTokenInformation TokenCapabilities size")
            buffer = ctypes.create_string_buffer(size.value)
            if not _token_info(token, 30, buffer, size, ctypes.byref(size)):
                raise _windows_error("GetTokenInformation TokenCapabilities")
            count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
            return {"is_appcontainer": flag.value == 1, "capabilities": count}
        finally:
            _kernel.CloseHandle(token)
    finally:
        _kernel.CloseHandle(process)


class AppContainerProfile:
    """Own a unique temporary profile with no capabilities; use as a context manager.

    Existing profiles are never reused or deleted. The caller must stop all
    contained processes before leaving the context and must not grant access to
    sensitive resources through ACLs. Cleanup failure is reported, never ignored.
    """

    def __init__(self):
        if os.name != "nt":
            raise AppContainerError("Windows AppContainer is required")
        self.name = "SketchUpMCP_" + uuid.uuid4().hex
        self._sid = ctypes.c_void_p()
        result = _create(self.name, self.name, "Temporary SketchUp MCP test profile", None, 0, ctypes.byref(self._sid))
        if result != 0:
            raise AppContainerError(f"CreateAppContainerProfile failed: 0x{result & 0xffffffff:08x}")
        self._active = True

    @property
    def sid(self):
        if not self._active:
            raise AppContainerError("AppContainer profile is closed")
        return self._sid

    def close(self):
        if not self._active:
            return
        result = _delete(self.name)
        if result != 0:
            raise AppContainerError(f"DeleteAppContainerProfile {self.name} failed: 0x{result & 0xffffffff:08x}")
        _free_sid(self._sid)
        self._active = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def create_workspace(profile: AppContainerProfile, root: str | Path) -> Path:
    """Create a new empty low-integrity directory with an explicit protected DACL.

    Only the current user, SYSTEM and this profile get access in the new DACL.
    Existing paths are never modified or reused; no content is copied or deleted.
    The root must be trusted: this function is not safe against concurrent
    replacement of the root by another process with equivalent user privileges.
    The caller owns eventual cleanup and must check the resolved path first.
    """
    if os.name != "nt":
        raise AppContainerError("Windows AppContainer is required")
    if not isinstance(profile, AppContainerProfile):
        raise TypeError("profile must be an AppContainerProfile")
    container_sid = _to_sid_string(profile.sid)
    user_sid = _current_user_sid()
    parent = Path(root).resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("workspace root must be an existing directory")
    target = parent / ("sandbox-" + uuid.uuid4().hex)
    # A protected DACL prevents inherited grants. The profile gets Modify,
    # not WRITE_DAC or WRITE_OWNER. Low integrity permits writing within it.
    sddl = f"D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{user_sid})(A;OICI;0x001301bf;;;{container_sid})S:(ML;OICI;NW;;;LW)"
    descriptor = ctypes.c_void_p()
    if not _sddl_to_sd(sddl, 1, ctypes.byref(descriptor), None):
        raise _windows_error("ConvertStringSecurityDescriptorToSecurityDescriptorW")
    try:
        attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
        if not _mkdir(str(target), ctypes.byref(attributes)):
            raise _windows_error("CreateDirectoryW")
    finally:
        _kernel.LocalFree(descriptor)
    return target
