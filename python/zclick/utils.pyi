# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import collections.abc as cabc
import os
import re
import sys
import typing as t
from functools import update_wrapper
from gettext import gettext as _
from types import ModuleType
from types import TracebackType
from ._compat import _default_text_stderr
from ._compat import _default_text_stdout
from ._compat import _find_binary_writer
from ._compat import binary_streams
from ._compat import open_stream
from ._compat import should_strip_ansi
from ._compat import strip_ansi
from ._compat import text_streams
from ._compat import WIN
from .globals import resolve_color_default
import typing_extensions as te
P = te.ParamSpec('P')
R = t.TypeVar('R')

def _posixify(name: str) -> str:
    ...

def _safecall(func: t.Callable[P, R]) -> t.Callable[P, R | None]:
    ...

def make_str(value: t.Any) -> str:
    ...

def _make_default_short_help(help: str, max_length: int=45) -> str:
    ...

class _LazyFile:
    name: str
    mode: str
    encoding: str | None
    errors: str | None
    atomic: bool
    _f: t.IO[t.Any] | None
    should_close: bool

    def __init__(self, filename: str | os.PathLike[str], mode: str='r', encoding: str | None=None, errors: str | None='strict', atomic: bool=False) -> None:
        ...

    def __getattr__(self, name: str) -> t.Any:
        ...

    def __repr__(self) -> str:
        ...

    def open(self) -> t.IO[t.Any]:
        ...

    def close(self) -> None:
        ...

    def close_intelligently(self) -> None:
        ...

    def __enter__(self) -> _LazyFile:
        ...

    def __exit__(self, exc_type: builtins.type[BaseException] | None, exc_value: BaseException | None, tb: TracebackType | None) -> None:
        ...

    def __iter__(self) -> cabc.Iterator[t.AnyStr]:
        ...

class _KeepOpenFile:
    _file: t.IO[t.Any]

    def __init__(self, file: t.IO[t.Any]) -> None:
        ...

    def __getattr__(self, name: str) -> t.Any:
        ...

    def __enter__(self) -> _KeepOpenFile:
        ...

    def __exit__(self, exc_type: builtins.type[BaseException] | None, exc_value: BaseException | None, tb: TracebackType | None) -> None:
        ...

    def __repr__(self) -> str:
        ...

    def __iter__(self) -> cabc.Iterator[t.AnyStr]:
        ...

def echo(message: object=None, file: t.IO[t.Any] | None=None, nl: bool=True, err: bool=False, color: bool | None=None) -> None:
    ...

def _get_binary_stream(name: t.Literal['stdin', 'stdout', 'stderr']) -> t.BinaryIO:
    ...

def _get_text_stream(name: t.Literal['stdin', 'stdout', 'stderr'], encoding: str | None=None, errors: str | None='strict') -> t.TextIO:
    ...

def open_file(filename: str | os.PathLike[str], mode: str='r', encoding: str | None=None, errors: str | None='strict', lazy: bool=False, atomic: bool=False) -> t.IO[t.Any]:
    ...

def format_filename(filename: str | bytes | os.PathLike[str] | os.PathLike[bytes], shorten: bool=False) -> str:
    ...

def get_app_dir(app_name: str, roaming: bool=True, force_posix: bool=False) -> str:
    ...

class _PacifyFlushWrapper:
    wrapped: t.IO[t.Any]

    def __init__(self, wrapped: t.IO[t.Any]) -> None:
        ...

    def flush(self) -> None:
        ...

    def __getattr__(self, attr: str) -> t.Any:
        ...

def _detect_program_name(path: str | None=None, _main: ModuleType | None=None) -> str:
    ...

def _expand_args(args: cabc.Iterable[str], *, user: bool=True, env: bool=True, glob_recursive: bool=True) -> list[str]:
    ...

def __getattr__(name: str) -> object:
    ...
