# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import codecs
import collections.abc as cabc
import io
import os
import re
import sys
import typing as t
from types import TracebackType
from weakref import WeakKeyDictionary
CYGWIN: sys.platform.startswith
WIN: sys.platform.startswith
_ansi_re: re.compile

def _make_text_stream(stream: t.BinaryIO, encoding: str | None, errors: str | None, force_readable: bool=False, force_writable: bool=False) -> t.TextIO:
    ...

def is_ascii_encoding(encoding: str) -> bool:
    ...

def get_best_encoding(stream: t.IO[t.Any]) -> str:
    ...

class _NonClosingTextIOWrapper(io.TextIOWrapper):

    def __init__(self, stream: t.BinaryIO, encoding: str | None, errors: str | None, force_readable: bool=False, force_writable: bool=False, **extra: t.Any) -> None:
        ...

    def __del__(self) -> None:
        ...

    def isatty(self) -> bool:
        ...

class _FixupStream:

    def __init__(self, stream: t.BinaryIO, force_readable: bool=False, force_writable: bool=False):
        ...

    def __getattr__(self, name: str) -> t.Any:
        ...

    def read1(self, size: int) -> bytes:
        ...

    def readable(self) -> bool:
        ...

    def writable(self) -> bool:
        ...

    def seekable(self) -> bool:
        ...

def _is_binary_reader(stream: t.IO[t.Any], default: bool=False) -> bool:
    ...

def _is_binary_writer(stream: t.IO[t.Any], default: bool=False) -> bool:
    ...

def _find_binary_reader(stream: t.IO[t.Any]) -> t.BinaryIO | None:
    ...

def _find_binary_writer(stream: t.IO[t.Any]) -> t.BinaryIO | None:
    ...

def _stream_is_misconfigured(stream: t.TextIO) -> bool:
    ...

def _is_compat_stream_attr(stream: t.TextIO, attr: str, value: str | None) -> bool:
    ...

def _is_compatible_text_stream(stream: t.TextIO, encoding: str | None, errors: str | None) -> bool:
    ...

def _force_correct_text_stream(text_stream: t.IO[t.Any], encoding: str | None, errors: str | None, is_binary: t.Callable[[t.IO[t.Any], bool], bool], find_binary: t.Callable[[t.IO[t.Any]], t.BinaryIO | None], force_readable: bool=False, force_writable: bool=False) -> t.TextIO:
    ...

def _force_correct_text_reader(text_reader: t.IO[t.Any], encoding: str | None, errors: str | None, force_readable: bool=False) -> t.TextIO:
    ...

def _force_correct_text_writer(text_writer: t.IO[t.Any], encoding: str | None, errors: str | None, force_writable: bool=False) -> t.TextIO:
    ...

def get_binary_stdin() -> t.BinaryIO:
    ...

def get_binary_stdout() -> t.BinaryIO:
    ...

def get_binary_stderr() -> t.BinaryIO:
    ...

def get_text_stdin(encoding: str | None=None, errors: str | None=None) -> t.TextIO:
    ...

def get_text_stdout(encoding: str | None=None, errors: str | None=None) -> t.TextIO:
    ...

def get_text_stderr(encoding: str | None=None, errors: str | None=None) -> t.TextIO:
    ...

def _wrap_io_open(file: str | os.PathLike[str] | int, mode: str, encoding: str | None, errors: str | None) -> t.IO[t.Any]:
    ...

def open_stream(filename: str | os.PathLike[str], mode: str='r', encoding: str | None=None, errors: str | None='strict', atomic: bool=False) -> tuple[t.IO[t.Any], bool]:
    ...

class _AtomicFile:

    def __init__(self, f: t.IO[t.Any], tmp_filename: str, real_filename: str) -> None:
        ...

    @property
    def name(self) -> str:
        ...

    def close(self, delete: bool=False) -> None:
        ...

    def __getattr__(self, name: str) -> t.Any:
        ...

    def __enter__(self) -> _AtomicFile:
        ...

    def __exit__(self, exc_type: builtins.type[BaseException] | None, exc_value: BaseException | None, tb: TracebackType | None) -> None:
        ...

    def __repr__(self) -> str:
        ...

def strip_ansi(value: str) -> str:
    ...

def _is_jupyter_kernel_output(stream: t.IO[t.Any]) -> bool:
    ...

def should_strip_ansi(stream: t.IO[t.Any] | None=None, color: bool | None=None) -> bool:
    ...

def term_len(x: str) -> int:
    ...

def isatty(stream: t.IO[t.Any]) -> bool:
    ...

def _make_cached_stream_func(src_func: t.Callable[[], t.TextIO | None], wrapper_func: t.Callable[[], t.TextIO]) -> t.Callable[[], t.TextIO | None]:
    ...
_default_text_stdin: _make_cached_stream_func
_default_text_stdout: _make_cached_stream_func
_default_text_stderr: _make_cached_stream_func
binary_streams: cabc.Mapping[str, t.Callable[[], t.BinaryIO]]
text_streams: cabc.Mapping[str, t.Callable[[str | None, str | None], t.TextIO]]
