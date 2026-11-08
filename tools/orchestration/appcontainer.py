"""Temporary Windows AppContainer identity for isolated process experiments.

A profile with no capabilities is only one layer of containment. Resource ACLs,
process lifetime, allowed filesystem access, and cleanup need separate controls.
This module does not activate a worker or authorize execution of untrusted code.
"""
from __future__ import annotations

import ctypes
import os
import uuid
from ctypes import wintypes


class AppContainerError(RuntimeError):
    """AppContainer identity creation, use, or cleanup failed."""


if os.name == "nt":
    _userenv = ctypes.WinDLL("userenv", use_last_error=True)
    _advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    _create = _userenv.CreateAppContainerProfile
    _create.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
                        wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    _create.restype = ctypes.c_long
    _delete = _userenv.DeleteAppContainerProfile
    _delete.argtypes, _delete.restype = [wintypes.LPCWSTR], ctypes.c_long
    _free_sid = _advapi.FreeSid
    _free_sid.argtypes, _free_sid.restype = [ctypes.c_void_p], ctypes.c_void_p


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
