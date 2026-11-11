# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import collections.abc as cabc
import typing as t
from gettext import gettext as _
from gettext import ngettext
from ._compat import get_text_stderr
from .globals import resolve_color_default
from .utils import echo
from .utils import format_filename
from .core import Command
from .core import Context
from .core import Parameter

def _join_param_hints(param_hint: cabc.Sequence[str] | str | None) -> str | None:
    ...

def _format_possibilities(possibilities: list[str]) -> str:
    ...

class ClickException(Exception):
    exit_code: t.ClassVar[int]
    show_color: t.Final[bool | None]
    message: t.Final[str]

    def __init__(self, message: str) -> None:
        ...

    def format_message(self) -> str:
        ...

    def __str__(self) -> str:
        ...

    def show(self, file: t.IO[t.Any] | None=None) -> None:
        ...

class UsageError(ClickException):
    exit_code: t.ClassVar[int]
    ctx: Context | None
    cmd: t.Final[Command | None]

    def __init__(self, message: str, ctx: Context | None=None) -> None:
        ...

    def show(self, file: t.IO[t.Any] | None=None) -> None:
        ...

class BadParameter(UsageError):
    param: Parameter | None
    param_hint: cabc.Sequence[str] | str | None

    def __init__(self, message: str, ctx: Context | None=None, param: Parameter | None=None, param_hint: cabc.Sequence[str] | str | None=None) -> None:
        ...

    def format_message(self) -> str:
        ...

class MissingParameter(BadParameter):
    param_type: t.Final[str | None]

    def __init__(self, message: str | None=None, ctx: Context | None=None, param: Parameter | None=None, param_hint: cabc.Sequence[str] | str | None=None, param_type: str | None=None) -> None:
        ...

    def format_message(self) -> str:
        ...

    def __str__(self) -> str:
        ...

class NoSuchOption(UsageError):
    option_name: t.Final[str]
    possibilities: t.Final[list[str] | None]

    def __init__(self, option_name: str, message: str | None=None, possibilities: cabc.Iterable[str] | None=None, ctx: Context | None=None) -> None:
        ...

    def format_message(self) -> str:
        ...

class NoSuchCommand(UsageError):
    command_name: t.Final[str]
    possibilities: t.Final[list[str] | None]

    def __init__(self, command_name: str, message: str | None=None, possibilities: cabc.Iterable[str] | None=None, ctx: Context | None=None) -> None:
        ...

    def format_message(self) -> str:
        ...

class BadOptionUsage(UsageError):
    option_name: t.Final[str]

    def __init__(self, option_name: str, message: str, ctx: Context | None=None) -> None:
        ...

class BadArgumentUsage(UsageError):
    ...

class NoArgsIsHelpError(UsageError):
    ctx: Context

    def __init__(self, ctx: Context) -> None:
        ...

    def show(self, file: t.IO[t.Any] | None=None) -> None:
        ...

class FileError(ClickException):
    ui_filename: t.Final[str]
    filename: t.Final[str]

    def __init__(self, filename: str, hint: str | None=None) -> None:
        ...

    def format_message(self) -> str:
        ...

class Abort(RuntimeError):
    ...

class Exit(RuntimeError):
    __slots__: tuple[t.Any, ...]
    exit_code: t.Final[int]

    def __init__(self, code: int=0) -> None:
        ...
