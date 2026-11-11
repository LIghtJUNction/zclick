# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import collections.abc as cabc
import typing as t
from collections import deque
from gettext import gettext as _
from gettext import ngettext
from ._utils import FLAG_NEEDS_VALUE
from ._utils import UNSET
from .exceptions import BadArgumentUsage
from .exceptions import BadOptionUsage
from .exceptions import NoSuchOption
from .exceptions import UsageError
from ._utils import T_FLAG_NEEDS_VALUE
from ._utils import T_UNSET
from .core import Argument as CoreArgument
from .core import Context
from .core import Option as CoreOption
from .core import Parameter as CoreParameter
V = t.TypeVar('V')

def _unpack_args(args: cabc.Sequence[str], nargs_spec: cabc.Sequence[int]) -> tuple[cabc.Sequence[str | cabc.Sequence[str | T_UNSET] | T_UNSET], list[str]]:
    ...

def _split_opt(opt: str) -> tuple[str, str]:
    ...

def _normalize_opt(opt: str, ctx: Context | None) -> str:
    ...

class _Option:
    prefixes: set[str]

    def __init__(self, obj: CoreOption, opts: cabc.Sequence[str], dest: str | None, action: str | None=None, nargs: int=1, const: t.Any | None=None):
        ...

    @property
    def takes_value(self) -> bool:
        ...

    def process(self, value: t.Any, state: _ParsingState) -> None:
        ...

class _Argument:

    def __init__(self, obj: CoreArgument, dest: str | None, nargs: int=1):
        ...

    def process(self, value: str | cabc.Sequence[str | T_UNSET] | T_UNSET, state: _ParsingState) -> None:
        ...

class _ParsingState:
    opts: dict[str, t.Any]
    largs: list[str]
    order: list[CoreParameter]

    def __init__(self, rargs: list[str]) -> None:
        ...

class _OptionParser:
    allow_interspersed_args: bool
    ignore_unknown_options: bool
    _short_opt: dict[str, _Option]
    _long_opt: dict[str, _Option]
    _args: list[_Argument]

    def __init__(self, ctx: Context | None=None) -> None:
        ...

    def add_option(self, obj: CoreOption, opts: cabc.Sequence[str], dest: str | None, action: str | None=None, nargs: int=1, const: t.Any | None=None) -> None:
        ...

    def add_argument(self, obj: CoreArgument, dest: str | None, nargs: int=1) -> None:
        ...

    def parse_args(self, args: list[str]) -> tuple[dict[str, t.Any], list[str], list[CoreParameter]]:
        ...

    def _process_args_for_args(self, state: _ParsingState) -> None:
        ...

    def _process_args_for_options(self, state: _ParsingState) -> None:
        ...

    def _match_long_opt(self, opt: str, explicit_value: str | None, state: _ParsingState) -> None:
        ...

    def _match_short_opt(self, arg: str, state: _ParsingState) -> None:
        ...

    def _get_value_from_state(self, option_name: str, option: _Option, state: _ParsingState) -> str | cabc.Sequence[str] | T_UNSET | T_FLAG_NEEDS_VALUE:
        ...

    def _process_opts(self, arg: str, state: _ParsingState) -> None:
        ...

def __getattr__(name: str) -> object:
    ...
