# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import collections.abc as cabc
import inspect
import io
import itertools
import os
import re
import sys
import typing as t
from contextlib import AbstractContextManager
from contextlib import redirect_stdout
from gettext import gettext as _
from . import _compat
from ._compat import isatty
from ._compat import strip_ansi
from .exceptions import Abort
from .exceptions import UsageError
from .globals import resolve_color_default
from .types import Choice
from .types import convert_type
from .types import ParamType
from .utils import _LazyFile
from .utils import echo
from ._termui_impl import ProgressBar
V = t.TypeVar('V')
visible_prompt_func: t.Callable[[str], str]
_ansi_colors: dict[t.Any, t.Any]
_ansi_reset_all: str
_HIDDEN_INPUT_MASK: str

def _mask_hidden_input(message: str, value: str) -> str:
    ...

def hidden_prompt_func(prompt: str) -> str:
    ...

def _readline_prompt(func: t.Callable[[str], str], text: str, err: bool) -> str:
    ...

def _build_prompt(text: str, suffix: str, show_default: bool | str=False, default: object | None=None, show_choices: bool=True, type: object | None=None) -> str:
    ...

def _format_default(default: V) -> V | str:
    ...

@t.overload
def prompt(text: str, default: str | None=None, hide_input: bool=False, confirmation_prompt: bool | str=False, type: None=None, value_proc: None=None, prompt_suffix: str=': ', show_default: bool | str=True, err: bool=False, show_choices: bool=True) -> str:
    ...

@t.overload
def prompt(text: str, default: V | str | None=None, hide_input: bool=False, confirmation_prompt: bool | str=False, type: ParamType[V, str] | builtins.type[V] | None=None, value_proc: t.Callable[[str], V] | None=None, prompt_suffix: str=': ', show_default: bool | str=True, err: bool=False, show_choices: bool=True) -> V:
    ...

def confirm(text: str, default: bool | None=False, abort: bool=False, prompt_suffix: str=': ', show_default: bool=True, err: bool=False) -> bool:
    ...

def get_pager_file(color: bool | None=None) -> t.ContextManager[t.TextIO]:
    ...

def echo_via_pager(text_or_generator: cabc.Iterable[str] | t.Callable[[], cabc.Iterable[str]] | str, color: bool | None=None) -> None:
    ...

@t.overload
def progressbar(*, length: int, label: str | None=None, hidden: bool=False, show_eta: bool=True, show_percent: bool | None=None, show_pos: bool=False, fill_char: str='#', empty_char: str='-', bar_template: str='%(label)s  [%(bar)s]  %(info)s', info_sep: str='  ', width: int=36, file: t.TextIO | None=None, color: bool | None=None, update_min_steps: int=1) -> ProgressBar[int]:
    ...

@t.overload
def progressbar(iterable: cabc.Iterable[V] | None=None, length: int | None=None, label: str | None=None, hidden: bool=False, show_eta: bool=True, show_percent: bool | None=None, show_pos: bool=False, item_show_func: t.Callable[[V | None], str | None] | None=None, fill_char: str='#', empty_char: str='-', bar_template: str='%(label)s  [%(bar)s]  %(info)s', info_sep: str='  ', width: int=36, file: t.TextIO | None=None, color: bool | None=None, update_min_steps: int=1) -> ProgressBar[V]:
    ...

def clear() -> None:
    ...

def _interpret_color(color: int | tuple[int, int, int] | str, offset: int=0) -> str:
    ...

def style(text: t.Any, fg: int | tuple[int, int, int] | str | None=None, bg: int | tuple[int, int, int] | str | None=None, bold: bool | None=None, dim: bool | None=None, underline: bool | None=None, overline: bool | None=None, italic: bool | None=None, blink: bool | None=None, reverse: bool | None=None, strikethrough: bool | None=None, reset: bool=True) -> str:
    ...

def unstyle(text: str) -> str:
    ...

def secho(message: t.Any | None=None, file: t.IO[t.AnyStr] | None=None, nl: bool=True, err: bool=False, color: bool | None=None, **styles: t.Any) -> None:
    ...

@t.overload
def edit(text: bytes | bytearray, editor: str | None=None, env: cabc.Mapping[str, str] | None=None, require_save: bool=False, extension: str='.txt') -> bytes | None:
    ...

@t.overload
def edit(text: str, editor: str | None=None, env: cabc.Mapping[str, str] | None=None, require_save: bool=True, extension: str='.txt') -> str | None:
    ...

@t.overload
def edit(text: None=None, editor: str | None=None, env: cabc.Mapping[str, str] | None=None, require_save: bool=True, extension: str='.txt', filename: str | os.PathLike[str] | cabc.Iterable[str | os.PathLike[str]] | None=None) -> None:
    ...

def launch(url: str, wait: bool=False, locate: bool=False) -> int:
    ...
_getchar: t.Callable[[bool], str] | None

def getchar(echo: bool=False) -> str:
    ...

def raw_terminal() -> AbstractContextManager[int]:
    ...

def pause(info: str | None=None, err: bool=False) -> None:
    ...
