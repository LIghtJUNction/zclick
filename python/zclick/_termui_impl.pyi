# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import collections.abc as cabc
import contextlib
import math
import os
import shlex
import sys
import time
import typing as t
from gettext import gettext as _
from io import StringIO
from pathlib import Path
from types import TracebackType
from ._compat import _default_text_stdout
from ._compat import CYGWIN
from ._compat import get_best_encoding
from ._compat import isatty
from ._compat import strip_ansi
from ._compat import term_len
from ._compat import WIN
from .exceptions import ClickException
from .utils import echo
V = t.TypeVar('V')

class ProgressBar(t.Generic[V]):
    label: str
    width: int
    autowidth: bool
    iter: cabc.Iterable[V]
    pos: int
    avg: list[float]
    last_eta: float
    start: float
    eta_known: bool
    finished: bool
    max_width: int | None
    entered: bool
    current_item: V | None
    _last_line: str | None

    def __init__(self, iterable: cabc.Iterable[V] | None, length: int | None=None, fill_char: str='#', empty_char: str=' ', bar_template: str='%(bar)s', info_sep: str='  ', hidden: bool=False, show_eta: bool=True, show_percent: bool | None=None, show_pos: bool=False, item_show_func: t.Callable[[V | None], str | None] | None=None, label: str | None=None, file: t.TextIO | None=None, color: bool | None=None, update_min_steps: int=1, width: int=30) -> None:
        ...

    def __enter__(self) -> ProgressBar[V]:
        ...

    def __exit__(self, exc_type: builtins.type[BaseException] | None, exc_value: BaseException | None, tb: TracebackType | None) -> None:
        ...

    def __iter__(self) -> cabc.Iterator[V]:
        ...

    def __next__(self) -> V:
        ...

    def render_finish(self) -> None:
        ...

    @property
    def pct(self) -> float:
        ...

    @property
    def time_per_iteration(self) -> float:
        ...

    @property
    def eta(self) -> float:
        ...

    def format_eta(self) -> str:
        ...

    def format_pos(self) -> str:
        ...

    def format_pct(self) -> str:
        ...

    def format_bar(self) -> str:
        ...

    def format_progress_line(self) -> str:
        ...

    def render_progress(self) -> None:
        ...

    def make_step(self, n_steps: int) -> None:
        ...

    def update(self, n_steps: int, current_item: V | None=None) -> None:
        ...

    def finish(self) -> None:
        ...

    def generator(self) -> cabc.Iterator[V]:
        ...

class _PagerWriter:

    def __init__(self, stream: t.TextIO, color: bool) -> None:
        ...

    def write(self, text: str) -> int:
        ...

    def writelines(self, lines: cabc.Iterable[str]) -> None:
        ...

    def flush(self) -> None:
        ...

    def close(self) -> None:
        ...

    def __getattr__(self, name: str) -> t.Any:
        ...

def _resolve_pager_command(cmd_parts: list[str]) -> tuple[Path, list[str]] | None:
    ...

def _pager_contextmanager(color: bool | None=None) -> t.ContextManager[tuple[t.TextIO, bool | None]]:
    ...

@contextlib.contextmanager
def get_pager_file(color: bool | None=None) -> t.Generator[t.TextIO, None, None]:
    ...

def _less_uses_raw_mode(less_env: str, cmd_params: list[str]) -> bool:
    ...

@contextlib.contextmanager
def _pipepager(cmd_path: Path, cmd_params: list[str], color: bool | None=None) -> t.Iterator[tuple[t.TextIO, bool | None]]:
    ...

@contextlib.contextmanager
def _tempfilepager(cmd_path: Path, cmd_params: list[str], color: bool | None=None) -> t.Iterator[tuple[t.TextIO, bool | None]]:
    ...

@contextlib.contextmanager
def _nullpager(stream: t.TextIO, color: bool | None=None) -> t.Iterator[tuple[t.TextIO, bool | None]]:
    ...

class Editor:

    def __init__(self, editor: str | None=None, env: cabc.Mapping[str, str] | None=None, require_save: bool=True, extension: str='.txt') -> None:
        ...

    def get_editor(self) -> str:
        ...

    def edit_files(self, filenames: cabc.Iterable[str | os.PathLike[str]]) -> None:
        ...

    @t.overload
    def edit(self, text: bytes | bytearray) -> bytes | None:
        ...

    @t.overload
    def edit(self, text: str | None) -> str | None:
        ...

def open_url(url: str, wait: bool=False, locate: bool=False) -> int:
    ...

def _translate_ch_to_exc(ch: str) -> None:
    ...
