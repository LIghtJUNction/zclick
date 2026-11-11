# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import collections.abc as cabc
import io
import sys
import time
import typing as t
from ctypes import Array
from ctypes import byref
from ctypes import c_char
from ctypes import c_char_p
from ctypes import c_int
from ctypes import c_ssize_t
from ctypes import c_ulong
from ctypes import c_void_p
from ctypes import POINTER
from ctypes import py_object
from ctypes import Structure
from ctypes.wintypes import DWORD
from ctypes.wintypes import HANDLE
from ctypes.wintypes import LPCWSTR
from ctypes.wintypes import LPWSTR
from gettext import gettext as _
from ._compat import _NonClosingTextIOWrapper
import msvcrt
from ctypes import windll
from ctypes import WINFUNCTYPE
c_ssize_p: POINTER
kernel32: t.Any
GetStdHandle: t.Any
ReadConsoleW: t.Any
WriteConsoleW: t.Any
GetConsoleMode: t.Any
GetLastError: t.Any
CommandLineToArgvW: WINFUNCTYPE(POINTER(LPWSTR), LPCWSTR, POINTER(c_int))
LocalFree: WINFUNCTYPE(c_void_p, c_void_p)
STDIN_HANDLE: GetStdHandle
STDOUT_HANDLE: GetStdHandle
STDERR_HANDLE: GetStdHandle
PyBUF_SIMPLE: int
PyBUF_WRITABLE: int
ERROR_SUCCESS: int
ERROR_NOT_ENOUGH_MEMORY: int
ERROR_OPERATION_ABORTED: int
EOF: bytes
MAX_BYTES_WRITTEN: int

class _WindowsConsoleRawIOBase(io.RawIOBase):

    def __init__(self, handle: int | None) -> None:
        ...

    def isatty(self) -> t.Literal[True]:
        ...

class _WindowsConsoleReader(_WindowsConsoleRawIOBase):

    def readable(self) -> t.Literal[True]:
        ...

    def readinto(self, b: Buffer) -> int:
        ...

class _WindowsConsoleWriter(_WindowsConsoleRawIOBase):

    def writable(self) -> t.Literal[True]:
        ...

    @staticmethod
    def _get_error_message(errno: int) -> str:
        ...

    def write(self, b: Buffer) -> int:
        ...

class ConsoleStream:

    def __init__(self, text_stream: t.TextIO, byte_stream: t.BinaryIO) -> None:
        ...

    @property
    def name(self) -> str:
        ...

    def write(self, x: t.AnyStr) -> int:
        ...

    def writelines(self, lines: cabc.Iterable[t.AnyStr]) -> None:
        ...

    def __getattr__(self, name: str) -> t.Any:
        ...

    def isatty(self) -> bool:
        ...

    def __repr__(self) -> str:
        ...

def _get_text_stdin(buffer_stream: t.BinaryIO) -> t.TextIO:
    ...

def _get_text_stdout(buffer_stream: t.BinaryIO) -> t.TextIO:
    ...

def _get_text_stderr(buffer_stream: t.BinaryIO) -> t.TextIO:
    ...
_stream_factories: cabc.Mapping[int, t.Callable[[t.BinaryIO], t.TextIO]]

def _is_console(f: t.TextIO) -> bool:
    ...

def _get_windows_console_stream(f: t.TextIO, encoding: str | None, errors: str | None) -> t.TextIO | None:
    ...
