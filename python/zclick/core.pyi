# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import collections.abc as cabc
import enum
import errno
import inspect
import os
import sys
import typing as t
from abc import ABC
from abc import abstractmethod
from collections import abc
from collections import Counter
from contextlib import AbstractContextManager
from contextlib import contextmanager
from contextlib import ExitStack
from functools import update_wrapper
from gettext import gettext as _
from gettext import ngettext
from itertools import repeat
from types import TracebackType
from . import types
from ._utils import FLAG_NEEDS_VALUE
from ._utils import UNSET
from .exceptions import Abort
from .exceptions import BadParameter
from .exceptions import ClickException
from .exceptions import Exit
from .exceptions import MissingParameter
from .exceptions import NoArgsIsHelpError
from .exceptions import NoSuchCommand
from .exceptions import UsageError
from .formatting import HelpFormatter
from .formatting import join_options
from .globals import pop_context
from .globals import push_context
from .parser import _OptionParser
from .parser import _split_opt
from .termui import confirm
from .termui import prompt
from .termui import style
from .utils import _detect_program_name
from .utils import _expand_args
from .utils import _make_default_short_help
from .utils import _PacifyFlushWrapper
from .utils import echo
from .utils import make_str
from typing_extensions import Self
from .shell_completion import CompletionItem
F = t.TypeVar('F', bound='t.Callable[..., t.Any]')
V = t.TypeVar('V')
_HELP_OPTION_STORAGE_NAME: str

def _complete_visible_commands(ctx: Context, incomplete: str) -> cabc.Iterator[tuple[str, Command]]:
    ...

def _check_nested_chain(base_command: Group, cmd_name: str, cmd: Command, register: bool=False) -> None:
    ...

def _echo_aborted() -> None:
    ...

def _format_deprecated_label(deprecated: bool | str) -> str:
    ...

def _format_deprecated_suffix(deprecated: bool | str) -> str:
    ...

def batch(iterable: cabc.Iterable[V], batch_size: int) -> list[tuple[V, ...]]:
    ...

@contextmanager
def augment_usage_errors(ctx: Context, param: Parameter | None=None) -> cabc.Generator[None]:
    ...

def iter_params_for_processing(invocation_order: cabc.Sequence[Parameter], declaration_order: cabc.Sequence[Parameter]) -> list[Parameter]:
    ...

class ParameterSource(enum.IntEnum):
    PROMPT = ...
    COMMANDLINE = ...
    ENVIRONMENT = ...
    DEFAULT_MAP = ...
    DEFAULT = ...

class Context:
    formatter_class: builtins.type[HelpFormatter]
    parent: Context | None
    command: Command
    info_name: str | None
    params: dict[str, t.Any]
    args: list[str]
    _protected_args: list[str]
    _opt_prefixes: set[str]
    obj: t.Any
    _meta: dict[str, t.Any]
    default_map: cabc.MutableMapping[str, t.Any] | None
    invoked_subcommand: str | None
    terminal_width: int | None
    max_content_width: int | None
    allow_extra_args: bool
    allow_interspersed_args: bool
    ignore_unknown_options: bool
    help_option_names: list[str]
    token_normalize_func: t.Callable[[str], str] | None
    resilient_parsing: bool
    auto_envvar_prefix: str | None
    color: bool | None
    show_default: bool | None
    _close_callbacks: list[t.Callable[[], t.Any]]
    _depth: int
    _parameter_source: dict[str, ParameterSource]
    _param_default_explicit: dict[str, bool]
    _exit_stack: ExitStack

    def __init__(self, command: Command, parent: Context | None=None, info_name: str | None=None, obj: t.Any | None=None, auto_envvar_prefix: str | None=None, default_map: cabc.MutableMapping[str, t.Any] | None=None, terminal_width: int | None=None, max_content_width: int | None=None, resilient_parsing: bool=False, allow_extra_args: bool | None=None, allow_interspersed_args: bool | None=None, ignore_unknown_options: bool | None=None, help_option_names: list[str] | None=None, token_normalize_func: t.Callable[[str], str] | None=None, color: bool | None=None, show_default: bool | None=None) -> None:
        ...

    @property
    def protected_args(self) -> list[str]:
        ...

    def to_info_dict(self) -> dict[str, t.Any]:
        ...

    def __enter__(self) -> Self:
        ...

    def __exit__(self, exc_type: builtins.type[BaseException] | None, exc_value: BaseException | None, tb: TracebackType | None) -> bool | None:
        ...

    @contextmanager
    def scope(self, cleanup: bool=True) -> cabc.Generator[Context]:
        ...

    @property
    def meta(self) -> dict[str, t.Any]:
        ...

    def make_formatter(self) -> HelpFormatter:
        ...

    def with_resource(self, context_manager: AbstractContextManager[V]) -> V:
        ...

    def call_on_close(self, f: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
        ...

    def close(self) -> None:
        ...

    def _close_with_exception_info(self, exc_type: builtins.type[BaseException] | None, exc_value: BaseException | None, tb: TracebackType | None) -> bool | None:
        ...

    @property
    def command_path(self) -> str:
        ...

    def find_root(self) -> Context:
        ...

    def find_object(self, object_type: builtins.type[V]) -> V | None:
        ...

    def ensure_object(self, object_type: builtins.type[V]) -> V:
        ...

    def _default_map_has(self, name: str | None) -> bool:
        ...

    @t.overload
    def lookup_default(self, name: str, call: t.Literal[True]=True) -> t.Any | None:
        ...

    @t.overload
    def lookup_default(self, name: str, call: t.Literal[False]=...) -> t.Any | t.Callable[[], t.Any] | None:
        ...

    def fail(self, message: str) -> t.NoReturn:
        ...

    def abort(self) -> t.NoReturn:
        ...

    def exit(self, code: int=0) -> t.NoReturn:
        ...

    def get_usage(self) -> str:
        ...

    def get_help(self) -> str:
        ...

    def _make_sub_context(self, command: Command) -> Context:
        ...

    @t.overload
    def invoke(self, callback: t.Callable[..., V], /, *args: t.Any, **kwargs: t.Any) -> V:
        ...

    @t.overload
    def invoke(self, callback: Command, /, *args: t.Any, **kwargs: t.Any) -> t.Any:
        ...

    def forward(self, cmd: Command, /, *args: t.Any, **kwargs: t.Any) -> t.Any:
        ...

    def set_parameter_source(self, name: str, source: ParameterSource) -> None:
        ...

    def get_parameter_source(self, name: str) -> ParameterSource | None:
        ...

class Command:
    context_class: builtins.type[Context]
    allow_extra_args: bool
    allow_interspersed_args: bool
    ignore_unknown_options: bool
    name: str | None
    context_settings: cabc.MutableMapping[str, t.Any]
    callback: t.Callable[..., t.Any] | None
    params: list[Parameter]
    help: str | None
    epilog: str | None
    options_metavar: str | None
    short_help: str | None
    add_help_option: bool
    _help_option: Option | None
    no_args_is_help: bool
    hidden: bool
    deprecated: bool | str

    def __init__(self, name: str | None, context_settings: cabc.MutableMapping[str, t.Any] | None=None, callback: t.Callable[..., t.Any] | None=None, params: list[Parameter] | None=None, help: str | None=None, epilog: str | None=None, short_help: str | None=None, options_metavar: str | None='[OPTIONS]', add_help_option: bool=True, no_args_is_help: bool=False, hidden: bool=False, deprecated: bool | str=False) -> None:
        ...

    def to_info_dict(self, ctx: Context) -> dict[str, t.Any]:
        ...

    def __repr__(self) -> str:
        ...

    def get_usage(self, ctx: Context) -> str:
        ...

    def get_params(self, ctx: Context) -> list[Parameter]:
        ...

    def format_usage(self, ctx: Context, formatter: HelpFormatter) -> None:
        ...

    def collect_usage_pieces(self, ctx: Context) -> list[str]:
        ...

    def get_help_option_names(self, ctx: Context) -> list[str]:
        ...

    def get_help_option(self, ctx: Context) -> Option | None:
        ...

    def make_parser(self, ctx: Context) -> _OptionParser:
        ...

    def get_help(self, ctx: Context) -> str:
        ...

    def get_short_help_str(self, limit: int=45) -> str:
        ...

    def format_help(self, ctx: Context, formatter: HelpFormatter) -> None:
        ...

    def format_help_text(self, ctx: Context, formatter: HelpFormatter) -> None:
        ...

    def format_options(self, ctx: Context, formatter: HelpFormatter) -> None:
        ...

    def format_arguments(self, ctx: Context, formatter: HelpFormatter) -> None:
        ...

    def format_epilog(self, ctx: Context, formatter: HelpFormatter) -> None:
        ...

    def make_context(self, info_name: str | None, args: list[str], parent: Context | None=None, **extra: t.Any) -> Context:
        ...

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        ...

    def invoke(self, ctx: Context) -> t.Any:
        ...

    def shell_complete(self, ctx: Context, incomplete: str) -> list[CompletionItem]:
        ...

    @t.overload
    def main(self, args: cabc.Sequence[str] | None=None, prog_name: str | None=None, complete_var: str | None=None, standalone_mode: t.Literal[True]=True, **extra: t.Any) -> t.NoReturn:
        ...

    @t.overload
    def main(self, args: cabc.Sequence[str] | None=None, prog_name: str | None=None, complete_var: str | None=None, standalone_mode: bool=..., **extra: t.Any) -> t.Any:
        ...

    def _main_shell_completion(self, ctx_args: cabc.MutableMapping[str, t.Any], prog_name: str, complete_var: str | None=None) -> None:
        ...

    def __call__(self, *args: t.Any, **kwargs: t.Any) -> t.Any:
        ...

class _FakeSubclassCheck(type):

    def __subclasscheck__(cls, subclass: type) -> bool:
        ...

    def __instancecheck__(cls, instance: t.Any) -> bool:
        ...

class _BaseCommand(Command, metaclass=_FakeSubclassCheck):
    ...

class Group(Command):
    allow_extra_args: bool
    allow_interspersed_args: bool
    command_class: builtins.type[Command] | None
    group_class: builtins.type[Group | type] | None
    commands: cabc.MutableMapping[str, Command]
    invoke_without_command: bool
    subcommand_metavar: str
    chain: bool
    _result_callback: t.Callable[..., t.Any] | None

    def __init__(self, name: str | None=None, commands: cabc.MutableMapping[str, Command] | cabc.Sequence[Command] | None=None, invoke_without_command: bool=False, no_args_is_help: bool | None=None, subcommand_metavar: str | None=None, chain: bool=False, result_callback: t.Callable[..., t.Any] | None=None, **kwargs: t.Any) -> None:
        ...

    def to_info_dict(self, ctx: Context) -> dict[str, t.Any]:
        ...

    def add_command(self, cmd: Command, name: str | None=None) -> None:
        ...

    @t.overload
    def command(self, __func: t.Callable[..., t.Any]) -> Command:
        ...

    @t.overload
    def command(self, *args: t.Any, **kwargs: t.Any) -> t.Callable[[t.Callable[..., t.Any]], Command]:
        ...

    @t.overload
    def group(self, __func: t.Callable[..., t.Any]) -> Group:
        ...

    @t.overload
    def group(self, *args: t.Any, **kwargs: t.Any) -> t.Callable[[t.Callable[..., t.Any]], Group]:
        ...

    def result_callback(self, replace: bool=False) -> t.Callable[[F], F]:
        ...

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        ...

    def list_commands(self, ctx: Context) -> list[str]:
        ...

    def collect_usage_pieces(self, ctx: Context) -> list[str]:
        ...

    def format_options(self, ctx: Context, formatter: HelpFormatter) -> None:
        ...

    def format_commands(self, ctx: Context, formatter: HelpFormatter) -> None:
        ...

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        ...

    def invoke(self, ctx: Context) -> t.Any:
        ...

    def resolve_command(self, ctx: Context, args: list[str]) -> tuple[str | None, Command | None, list[str]]:
        ...

    def shell_complete(self, ctx: Context, incomplete: str) -> list[CompletionItem]:
        ...

class _MultiCommand(Group, metaclass=_FakeSubclassCheck):
    ...

class CommandCollection(Group):
    sources: list[Group]

    def __init__(self, name: str | None=None, sources: list[Group] | None=None, **kwargs: t.Any) -> None:
        ...

    def add_source(self, group: Group) -> None:
        ...

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        ...

    def list_commands(self, ctx: Context) -> list[str]:
        ...

def _check_iter(value: cabc.Iterable[V]) -> cabc.Iterator[V]:
    ...

class Parameter(ABC):
    param_type_name: str
    name: str
    opts: list[str]
    secondary_opts: list[str]
    required: bool
    callback: t.Callable[[Context, Parameter, t.Any], t.Any] | None
    nargs: int
    multiple: bool
    expose_value: bool
    default: t.Any | t.Callable[[], t.Any] | None
    _default_explicit: bool
    is_eager: bool
    metavar: str | None
    envvar: str | cabc.Sequence[str] | None
    _custom_shell_complete: t.Callable[[Context, Parameter, str], list[CompletionItem] | list[str]] | None
    deprecated: bool | str
    help: str | None
    type: types.ParamType[t.Any]

    def __init__(self, param_decls: cabc.Sequence[str] | None=None, type: types.ParamType[t.Any] | t.Any | None=None, required: bool=False, default: t.Any | t.Callable[[], t.Any] | None=UNSET, callback: t.Callable[[Context, Parameter, t.Any], t.Any] | None=None, nargs: int | None=None, multiple: bool=False, metavar: str | None=None, expose_value: bool=True, is_eager: bool=False, envvar: str | cabc.Sequence[str] | None=None, shell_complete: t.Callable[[Context, Parameter, str], list[CompletionItem] | list[str]] | None=None, deprecated: bool | str=False, help: str | None=None) -> None:
        ...

    @staticmethod
    def _hide_unset(value: t.Any) -> t.Any:
        ...

    def to_info_dict(self) -> dict[str, t.Any]:
        ...

    def __repr__(self) -> str:
        ...

    @abstractmethod
    def _parse_decls(self, decls: cabc.Sequence[str], expose_value: bool) -> tuple[str, list[str], list[str]]:
        ...

    @property
    def human_readable_name(self) -> str:
        ...

    def make_metavar(self, ctx: Context) -> str:
        ...

    @t.overload
    def get_default(self, ctx: Context, call: t.Literal[True]=True) -> t.Any | None:
        ...

    @t.overload
    def get_default(self, ctx: Context, call: bool=...) -> t.Any | t.Callable[[], t.Any] | None:
        ...

    @abstractmethod
    def add_to_parser(self, parser: _OptionParser, ctx: Context) -> None:
        ...

    def consume_value(self, ctx: Context, opts: cabc.Mapping[str, t.Any]) -> tuple[t.Any, ParameterSource]:
        ...

    def type_cast_value(self, ctx: Context, value: t.Any) -> t.Any:
        ...

    def value_is_missing(self, value: t.Any) -> bool:
        ...

    def process_value(self, ctx: Context, value: t.Any) -> t.Any:
        ...

    def resolve_envvar_value(self, ctx: Context) -> str | None:
        ...

    def value_from_envvar(self, ctx: Context) -> str | cabc.Sequence[str] | None:
        ...

    def handle_parse_result(self, ctx: Context, opts: cabc.Mapping[str, t.Any], args: list[str]) -> tuple[t.Any, list[str]]:
        ...

    def get_help_record(self, ctx: Context) -> tuple[str, str] | None:
        ...

    def get_usage_pieces(self, ctx: Context) -> list[str]:
        ...

    def get_error_hint(self, ctx: Context | None) -> str:
        ...

    def shell_complete(self, ctx: Context, incomplete: str) -> list[CompletionItem]:
        ...

class Option(Parameter):
    param_type_name: str
    prompt: str | None
    confirmation_prompt: bool | str
    prompt_required: bool
    hide_input: bool
    hidden: bool
    _flag_needs_value: bool
    is_flag: bool
    flag_value: t.Any
    type: types.ParamType[t.Any]
    default: t.Any | t.Callable[[], t.Any] | None
    count: bool
    allow_from_autoenv: bool
    show_default: bool | str | None
    show_choices: bool
    show_envvar: bool

    def __init__(self, param_decls: cabc.Sequence[str] | None=None, show_default: bool | str | None=None, prompt: bool | str=False, confirmation_prompt: bool | str=False, prompt_required: bool=True, hide_input: bool=False, is_flag: bool | None=None, flag_value: t.Any=UNSET, multiple: bool=False, count: bool=False, allow_from_autoenv: bool=True, type: types.ParamType[t.Any] | t.Any | None=None, help: str | None=None, hidden: bool=False, show_choices: bool=True, show_envvar: bool=False, deprecated: bool | str=False, **attrs: t.Any) -> None:
        ...

    @property
    def is_bool_flag(self) -> bool:
        ...

    @property
    def flag_activation_value(self) -> t.Any:
        ...

    def _infer_flag_kind(self, is_flag: bool | None, flag_value: t.Any) -> tuple[bool, bool]:
        ...

    def _pick_type(self, type_arg: t.Any, flag_value: t.Any, count: bool, is_flag: bool) -> types.ParamType[t.Any]:
        ...

    def _resolve_lazy_default(self, value: t.Any) -> t.Any:
        ...

    def _validate(self, prompt: bool | str, deprecated: bool | str) -> None:
        ...

    def to_info_dict(self) -> dict[str, t.Any]:
        ...

    def get_default(self, ctx: Context, call: bool=True) -> t.Any | t.Callable[[], t.Any] | None:
        ...

    def get_error_hint(self, ctx: Context | None) -> str:
        ...

    def _parse_decls(self, decls: cabc.Sequence[str], expose_value: bool) -> tuple[str, list[str], list[str]]:
        ...

    def add_to_parser(self, parser: _OptionParser, ctx: Context) -> None:
        ...

    def get_help_spec(self, ctx: Context) -> str:
        ...

    def get_help_record(self, ctx: Context) -> tuple[str, str] | None:
        ...

    def get_help_extra(self, ctx: Context) -> types.OptionHelpExtra:
        ...

    def prompt_for_value(self, ctx: Context) -> t.Any:
        ...

    def resolve_envvar_value(self, ctx: Context) -> str | None:
        ...

    def value_from_envvar(self, ctx: Context) -> t.Any:
        ...

    def consume_value(self, ctx: Context, opts: cabc.Mapping[str, Parameter]) -> tuple[t.Any, ParameterSource]:
        ...

    def process_value(self, ctx: Context, value: t.Any) -> t.Any:
        ...

class Argument(Parameter):
    param_type_name: str

    def __init__(self, param_decls: cabc.Sequence[str], required: bool | None=None, help: str | None=None, **attrs: t.Any) -> None:
        ...

    @property
    def human_readable_name(self) -> str:
        ...

    def make_metavar(self, ctx: Context) -> str:
        ...

    def _parse_decls(self, decls: cabc.Sequence[str], expose_value: bool) -> tuple[str, list[str], list[str]]:
        ...

    def get_usage_pieces(self, ctx: Context) -> list[str]:
        ...

    def get_help_record(self, ctx: Context) -> tuple[str, str]:
        ...

    def get_error_hint(self, ctx: Context | None) -> str:
        ...

    def add_to_parser(self, parser: _OptionParser, ctx: Context) -> None:
        ...

def __getattr__(name: str) -> object:
    ...
