"""Run a Windows process on a fresh desktop without switching to it."""

import _winapi
import ctypes
from ctypes import wintypes
import subprocess
from uuid import uuid4


class StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", wintypes.LPVOID),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("process", wintypes.HANDLE),
        ("thread", wintypes.HANDLE),
        ("process_id", wintypes.DWORD),
        ("thread_id", wintypes.DWORD),
    ]


def run(executable, cwd, environment, timeout):
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.CreateDesktopW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
    ]
    user.CreateDesktopW.restype = wintypes.HANDLE
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    user.CloseDesktop.restype = wintypes.BOOL
    kernel.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPVOID, wintypes.LPVOID,
        wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID, wintypes.LPCWSTR,
        ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInformation),
    ]
    kernel.CreateProcessW.restype = wintypes.BOOL

    desktop_name = f"PoB-Capture-{uuid4().hex}"
    desktop = user.CreateDesktopW(desktop_name, None, None, 0, 0x10000000, None)  # GENERIC_ALL
    if not desktop:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        startup = StartupInfo(cb=ctypes.sizeof(StartupInfo), lpDesktop=desktop_name)
        handles = ProcessInformation()
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(executable)]))
        # CreateProcessW requires a sorted, double-null-terminated environment block.
        variables = (f"{key}={environment[key]}" for key in sorted(environment, key=str.upper))
        block = ctypes.create_unicode_buffer("\0".join(variables) + "\0")
        flags = 0x400 | subprocess.BELOW_NORMAL_PRIORITY_CLASS  # CREATE_UNICODE_ENVIRONMENT
        if not kernel.CreateProcessW(
            str(executable), command, None, None, False, flags, block, str(cwd),
            ctypes.byref(startup), ctypes.byref(handles),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        _winapi.CloseHandle(handles.thread)
        try:
            result = _winapi.WaitForSingleObject(handles.process, int(timeout * 1000))
            if result == _winapi.WAIT_TIMEOUT:
                raise subprocess.TimeoutExpired(str(executable), timeout)
            return _winapi.GetExitCodeProcess(handles.process)
        finally:
            if _winapi.WaitForSingleObject(handles.process, 0) == _winapi.WAIT_TIMEOUT:
                _winapi.TerminateProcess(handles.process, 1)
                _winapi.WaitForSingleObject(handles.process, _winapi.INFINITE)
            _winapi.CloseHandle(handles.process)
    finally:
        user.CloseDesktop(desktop)
