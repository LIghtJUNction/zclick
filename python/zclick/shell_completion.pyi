# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import collections.abc as cabc
import os
import re
import typing as t
from gettext import gettext as _
from .core import Argument
from .core import Command
from .core import Context
from .core import Group
from .core import Option
from .core import Parameter
from .core import ParameterSource
from .utils import echo

def shell_complete(cli: Command, ctx_args: cabc.MutableMapping[str, t.Any], prog_name: str, complete_var: str, instruction: str) -> t.Literal[0, 1]:
    ...
from typing_extensions import TypeVar
_ValueT_co = TypeVar('_ValueT_co', covariant=True, default=t.Any)

class CompletionItem(t.Generic[_ValueT_co]):
    __slots__: tuple[t.Any, ...]
    value: _ValueT_co
    type: str
    help: str | None

    def __init__(self, value: _ValueT_co, type: str='plain', help: str | None=None, **kwargs: t.Any) -> None:
        ...

    def __getattr__(self, name: str) -> t.Any:
        ...
_SOURCE_BASH: str
_SOURCE_ZSH: str
_SOURCE_FISH: str
_SOURCE_POWERSHELL: str

class _SourceVarsDict(t.TypedDict):
    complete_func: str
    complete_var: str
    prog_name: str

class ShellComplete:
    name: t.ClassVar[str]
    source_template: t.ClassVar[str]
    cli: Command
    ctx_args: cabc.MutableMapping[str, t.Any]
    prog_name: str
    complete_var: str

    def __init__(self, cli: Command, ctx_args: cabc.MutableMapping[str, t.Any], prog_name: str, complete_var: str) -> None:
        ...

    @property
    def func_name(self) -> str:
        ...

    def source_vars(self) -> _SourceVarsDict:
        ...

    def source(self) -> str:
        ...

    def get_completion_args(self) -> tuple[list[str], str]:
        ...

    def get_completions(self, args: list[str], incomplete: str) -> list[CompletionItem[str]]:
        ...

    def format_completion(self, item: CompletionItem[str]) -> str:
        ...

    def complete(self) -> str:
        ...

class BashComplete(ShellComplete):
    name: t.ClassVar[str]
    source_template: t.ClassVar[str]

    @staticmethod
    def _check_version() -> None:
        ...

    def source(self) -> str:
        ...

    def get_completion_args(self) -> tuple[list[str], str]:
        ...

    def format_completion(self, item: CompletionItem[t.Any]) -> str:
        ...

class ZshComplete(ShellComplete):
    name: t.ClassVar[str]
    source_template: t.ClassVar[str]

    def get_completion_args(self) -> tuple[list[str], str]:
        ...

    def format_completion(self, item: CompletionItem[str]) -> str:
        ...

class FishComplete(ShellComplete):
    name: t.ClassVar[str]
    source_template: t.ClassVar[str]

    def get_completion_args(self) -> tuple[list[str], str]:
        ...

    def format_completion(self, item: CompletionItem[str]) -> str:
        ...

class PowerShellComplete(ShellComplete):
    name: t.ClassVar[str]
    source_template: t.ClassVar[str]

    def get_completion_args(self) -> tuple[list[str], str]:
        ...

    def format_completion(self, item: CompletionItem[str]) -> str:
        ...
_available_shells: t.Final[dict[str, builtins.type[ShellComplete]]]
_ShellCompleteT = t.TypeVar('_ShellCompleteT', bound='ShellComplete')

def add_completion_class(cls: builtins.type[_ShellCompleteT], name: str | None=None) -> builtins.type[_ShellCompleteT]:
    ...

@t.overload
def get_completion_class(shell: t.Literal['bash']) -> builtins.type[BashComplete]:
    ...

@t.overload
def get_completion_class(shell: t.Literal['fish']) -> builtins.type[FishComplete]:
    ...

@t.overload
def get_completion_class(shell: t.Literal['zsh']) -> builtins.type[ZshComplete]:
    ...

@t.overload
def get_completion_class(shell: str) -> builtins.type[ShellComplete] | None:
    ...

def split_arg_string(string: str) -> list[str]:
    ...

def _is_incomplete_argument(ctx: Context, param: Parameter) -> bool:
    ...

def _start_of_option(ctx: Context, value: str) -> bool:
    ...

def _is_incomplete_option(ctx: Context, args: list[str], param: Parameter) -> bool:
    ...

def _resolve_context(cli: Command, ctx_args: cabc.MutableMapping[str, t.Any], prog_name: str, args: list[str]) -> Context:
    ...

def _resolve_incomplete(ctx: Context, args: list[str], incomplete: str) -> tuple[Command | Parameter, str]:
    ...
