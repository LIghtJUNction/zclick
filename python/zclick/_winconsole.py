"""Borrowed Windows console streams using the wide-character Win32 API.

The buffers passed to Win32 belong to ctypes for the duration of each call.
No CPython object addresses, buffer internals, or reference counts are accessed.
"""
from __future__ import annotations

import ctypes
import io
import sys
import typing as t
from ctypes import wintypes

from ._compat import _NonClosingTextIOWrapper

if sys.platform != "win32":
    raise ImportError("Windows console streams are only available on Windows")

import msvcrt

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _bind(name: str, args: list[t.Any], result: t.Any) -> t.Any:
    function = getattr(kernel32, name)
    function.argtypes = args
    function.restype = result
    return function


GetStdHandle = _bind("GetStdHandle", [wintypes.DWORD], wintypes.HANDLE)
GetConsoleMode = _bind("GetConsoleMode", [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL)
ReadConsoleW = _bind("ReadConsoleW", [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID], wintypes.BOOL)
WriteConsoleW = _bind("WriteConsoleW", [wintypes.HANDLE, wintypes.LPCVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID], wintypes.BOOL)
GetLastError = kernel32.GetLastError
STDIN_HANDLE, STDOUT_HANDLE, STDERR_HANDLE = (GetStdHandle(value) for value in (-10, -11, -12))
ERROR_SUCCESS, ERROR_NOT_ENOUGH_MEMORY, ERROR_OPERATION_ABORTED = 0, 8, 995
EOF = b"\x1a"
MAX_BYTES_WRITTEN = 32767


class _WindowsConsoleRawIOBase(io.RawIOBase):
    def __init__(self, handle: int | None) -> None:
        super().__init__()
        self.handle = handle

    def isatty(self) -> t.Literal[True]:
        return True


class _WindowsConsoleReader(_WindowsConsoleRawIOBase):
    def readable(self) -> t.Literal[True]:
        return True

    def readinto(self, b: t.Any) -> int:
        self._checkClosed()
        view = memoryview(b).cast("B")
        if view.readonly:
            raise TypeError("readinto() argument must be a writable bytes-like object")
        if not view:
            return 0
        if len(view) < 2:
            raise ValueError("Windows console reads require room for a UTF-16 code unit")
        units = min(len(view) // 2, 32767)
        storage = ctypes.create_string_buffer(units * 2)
        actual = wintypes.DWORD()
        if not ReadConsoleW(self.handle, storage, units, ctypes.byref(actual), None):
            error = ctypes.get_last_error()
            if error == ERROR_OPERATION_ABORTED:
                raise KeyboardInterrupt()
            raise ctypes.WinError(error)
        size = actual.value * 2
        value = storage.raw[:size]
        if value.startswith(b"\x1a\x00"):
            return 0
        view[:size] = value
        return size


class _WindowsConsoleWriter(_WindowsConsoleRawIOBase):
    def writable(self) -> t.Literal[True]:
        return True

    @staticmethod
    def _get_error_message(errno: int) -> str:
        return ctypes.FormatError(errno).strip()

    def write(self, b: t.Any) -> int:
        self._checkClosed()
        value = bytes(b)
        if len(value) % 2:
            raise ValueError("Windows console writes require complete UTF-16 code units")
        if not value:
            return 0
        size = min(len(value), MAX_BYTES_WRITTEN & ~1)
        # Keep a surrogate pair together at an internal chunk boundary.
        if size < len(value):
            last = int.from_bytes(value[size - 2:size], "little")
            following = int.from_bytes(value[size:size + 2], "little")
            if 0xD800 <= last <= 0xDBFF and 0xDC00 <= following <= 0xDFFF:
                size -= 2
        storage = ctypes.create_string_buffer(value[:size], size)
        actual = wintypes.DWORD()
        if not WriteConsoleW(self.handle, storage, size // 2, ctypes.byref(actual), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return actual.value * 2


class ConsoleStream:
    def __init__(self, text_stream: t.TextIO, byte_stream: t.BinaryIO) -> None:
        self._text_stream, self.buffer = text_stream, byte_stream

    @property
    def name(self) -> str:
        return self.buffer.name

    def write(self, x: t.AnyStr) -> int:
        if isinstance(x, str):
            return self._text_stream.write(x)
        self._text_stream.flush()
        return self.buffer.write(x)

    def writelines(self, lines: t.Iterable[t.AnyStr]) -> None:
        for line in lines:
            self.write(line)

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self._text_stream, name)

    def isatty(self) -> bool:
        return self._text_stream.isatty()

    def __repr__(self) -> str:
        return f"<ConsoleStream name={self.name!r}>"


def _wrap_console(handle: int | None, buffer_stream: t.BinaryIO, reading: bool) -> t.TextIO:
    raw = _WindowsConsoleReader(handle) if reading else _WindowsConsoleWriter(handle)
    buffered = io.BufferedReader(raw) if reading else io.BufferedWriter(raw)
    text = _NonClosingTextIOWrapper(buffered, encoding="utf-16-le", errors="strict", line_buffering=True)
    return t.cast(t.TextIO, ConsoleStream(text, buffer_stream))


def _get_text_stdin(buffer_stream: t.BinaryIO) -> t.TextIO:
    return _wrap_console(STDIN_HANDLE, buffer_stream, True)


def _get_text_stdout(buffer_stream: t.BinaryIO) -> t.TextIO:
    return _wrap_console(STDOUT_HANDLE, buffer_stream, False)


def _get_text_stderr(buffer_stream: t.BinaryIO) -> t.TextIO:
    return _wrap_console(STDERR_HANDLE, buffer_stream, False)


_stream_factories = {0: _get_text_stdin, 1: _get_text_stdout, 2: _get_text_stderr}


def _is_console(f: t.TextIO) -> bool:
    try:
        handle = msvcrt.get_osfhandle(f.fileno())
        return bool(GetConsoleMode(handle, ctypes.byref(wintypes.DWORD())))
    except (AttributeError, OSError, ValueError):
        return False


def _get_windows_console_stream(f: t.TextIO, encoding: str | None, errors: str | None) -> t.TextIO | None:
    if encoding not in (None, "utf-16-le") or errors not in (None, "strict") or not _is_console(f):
        return None
    create = _stream_factories.get(f.fileno())
    buffer = getattr(f, "buffer", None)
    return create(buffer) if create is not None and buffer is not None else None
