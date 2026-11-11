# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import abc
import collections.abc as cabc
import enum
import os
import stat
import sys
import typing as t
import uuid
from datetime import datetime
from gettext import gettext as _
from gettext import ngettext
from ._compat import _get_argv_encoding
from ._compat import open_stream
from .exceptions import BadParameter
from .utils import _LazyFile
from .utils import _safecall
from .utils import format_filename
import typing_extensions as te
from .core import Context
from .core import Parameter
from .shell_completion import CompletionItem
_ValueT = t.TypeVar('_ValueT')
_ValueT_contra = t.TypeVar('_ValueT_contra', contravariant=True)
_ValueT_co = t.TypeVar('_ValueT_co', covariant=True)
_InputT_contra = te.TypeVar('_InputT_contra', contravariant=True, default=t.Any)
_FloatValueT = t.TypeVar('_FloatValueT', bound=float)
_FloatValueT_co = t.TypeVar('_FloatValueT_co', bound=float, covariant=True)
_PathT_co = te.TypeVar('_PathT_co', covariant=True, default='str | bytes | os.PathLike[str]')

class ParamTypeInfoDict(t.TypedDict):
    param_type: str
    name: str

class ParamType(t.Generic[_ValueT_co, _InputT_contra], abc.ABC):
    is_composite: t.ClassVar[bool]
    arity: int
    name: str
    envvar_list_splitter: t.ClassVar[str | None]

    def to_info_dict(self) -> ParamTypeInfoDict:
        ...

    @t.overload
    def __call__(self, value: None, param: Parameter | None=None, ctx: Context | None=None) -> None:
        ...

    @t.overload
    def __call__(self, value: _InputT_contra, param: Parameter | None=None, ctx: Context | None=None) -> _ValueT_co:
        ...

    def get_metavar(self, param: Parameter, ctx: Context) -> str | None:
        ...

    def get_missing_message(self, param: Parameter, ctx: Context | None) -> str | None:
        ...

    def convert(self, value: _InputT_contra, param: Parameter | None, ctx: Context | None) -> _ValueT_co:
        ...

    def split_envvar_value(self, rv: str) -> cabc.Sequence[str]:
        ...

    def fail(self, message: str, param: Parameter | None=None, ctx: Context | None=None) -> t.NoReturn:
        ...

    def shell_complete(self, ctx: Context, param: Parameter, incomplete: str) -> list[CompletionItem]:
        ...

class CompositeParamType(ParamType[_ValueT_co]):
    is_composite: t.ClassVar[bool]

    @property
    @abc.abstractmethod
    def arity(self) -> int:
        ...

class FuncParamTypeInfoDict(ParamTypeInfoDict, t.Generic[_ValueT_contra, _ValueT_co]):
    func: t.Callable[[_ValueT_contra], _ValueT_co]

class FuncParamType(ParamType[_ValueT_co], t.Generic[_ValueT_contra, _ValueT_co]):
    name: str
    func: t.Callable[[_ValueT_contra], _ValueT_co]

    def __init__(self, func: t.Callable[[_ValueT_contra], _ValueT_co]) -> None:
        ...

    def to_info_dict(self) -> FuncParamTypeInfoDict[_ValueT_contra, _ValueT_co]:
        ...

    def convert(self, value: _ValueT_contra, param: Parameter | None, ctx: Context | None) -> _ValueT_co:
        ...

class UnprocessedParamType(ParamType[t.Any]):
    name: str

    def convert(self, value: _ValueT, param: Parameter | None, ctx: Context | None) -> _ValueT:
        ...

    def __repr__(self) -> str:
        ...

class StringParamType(ParamType[str]):
    name: str

    def convert(self, value: t.Any, param: Parameter | None, ctx: Context | None) -> str:
        ...

    def __repr__(self) -> str:
        ...

class ChoiceInfoDict(ParamTypeInfoDict, t.Generic[_ValueT_co]):
    choices: tuple[_ValueT_co, ...]
    case_sensitive: bool

class Choice(ParamType[_ValueT_co], t.Generic[_ValueT_co]):
    name: str
    choices: tuple[_ValueT_co, ...]
    case_sensitive: bool

    def __init__(self, choices: cabc.Iterable[_ValueT_co], case_sensitive: bool=True) -> None:
        ...

    def to_info_dict(self) -> ChoiceInfoDict[_ValueT_co]:
        ...

    def _normalized_mapping(self, ctx: Context | None=None) -> cabc.Mapping[_ValueT_co, str]:
        ...

    def normalize_choice(self, choice: object, ctx: Context | None) -> str:
        ...

    def get_metavar(self, param: Parameter, ctx: Context) -> str | None:
        ...

    def get_missing_message(self, param: Parameter, ctx: Context | None) -> str:
        ...

    def convert(self, value: t.Any, param: Parameter | None, ctx: Context | None) -> _ValueT_co:
        ...

    def get_invalid_choice_message(self, value: t.Any, ctx: Context | None) -> str:
        ...

    def __repr__(self) -> str:
        ...

    def shell_complete(self, ctx: Context, param: Parameter, incomplete: str) -> list[CompletionItem]:
        ...

class DateTimeInfoDict(ParamTypeInfoDict):
    formats: cabc.Sequence[str]

class DateTime(ParamType[datetime]):
    name: str
    formats: cabc.Sequence[str]

    def __init__(self, formats: cabc.Sequence[str] | None=None):
        ...

    def to_info_dict(self) -> DateTimeInfoDict:
        ...

    def get_metavar(self, param: Parameter, ctx: Context) -> str:
        ...

    def _try_to_convert_date(self, value: t.Any, format: str) -> datetime | None:
        ...

    def convert(self, value: t.Any, param: Parameter | None, ctx: Context | None) -> datetime:
        ...

    def __repr__(self) -> str:
        ...

class _NumberParamTypeBase(ParamType[_ValueT_co], t.Generic[_ValueT_contra, _ValueT_co]):
    _number_class: t.Callable[[_ValueT_contra], _ValueT_co]

    def convert(self, value: _ValueT_contra, param: Parameter | None, ctx: Context | None) -> _ValueT_co:
        ...

class NumberRangeInfoDict(ParamTypeInfoDict, t.Generic[_FloatValueT_co]):
    min: _FloatValueT_co | None
    max: _FloatValueT_co | None
    min_open: bool
    max_open: bool
    clamp: bool

class _NumberRangeBase(_NumberParamTypeBase[_ValueT_contra, _FloatValueT_co], t.Generic[_ValueT_contra, _FloatValueT_co]):
    min: _FloatValueT_co | None
    max: _FloatValueT_co | None
    min_open: bool
    max_open: bool
    clamp: bool

    def __init__(self, min: _FloatValueT_co | None=None, max: _FloatValueT_co | None=None, min_open: bool=False, max_open: bool=False, clamp: bool=False) -> None:
        ...

    def to_info_dict(self) -> NumberRangeInfoDict[_FloatValueT_co]:
        ...

    def convert(self, value: _ValueT_contra, param: Parameter | None, ctx: Context | None) -> _FloatValueT_co:
        ...

    @abc.abstractmethod
    def _clamp(self: _NumberRangeBase[t.Any, _FloatValueT], bound: _FloatValueT, dir: t.Literal[1, -1], open: bool) -> _FloatValueT:
        ...

    def _describe_range(self) -> str:
        ...

    def __repr__(self) -> str:
        ...

class IntParamType(_NumberParamTypeBase[t.SupportsInt | t.SupportsIndex, int]):
    name: str
    _number_class = int

    def __repr__(self) -> str:
        ...

class IntRange(_NumberRangeBase[int, int], IntParamType):
    name: str

    def _clamp(self, bound: int, dir: t.Literal[1, -1], open: bool) -> int:
        ...

class FloatParamType(_NumberParamTypeBase[t.SupportsFloat | t.SupportsIndex, float]):
    name: str
    _number_class = float

    def __repr__(self) -> str:
        ...

class FloatRange(_NumberRangeBase[float, float], FloatParamType):
    name: str

    def __init__(self, min: float | None=None, max: float | None=None, min_open: bool=False, max_open: bool=False, clamp: bool=False) -> None:
        ...

    def _clamp(self, bound: float, dir: t.Literal[1, -1], open: bool) -> float:
        ...

class BoolParamType(ParamType[bool]):
    name: str
    bool_states: dict[str, bool]

    @staticmethod
    def str_to_bool(value: str | bool) -> bool | None:
        ...

    def convert(self, value: t.Any, param: Parameter | None, ctx: Context | None) -> bool:
        ...

    def __repr__(self) -> str:
        ...

class UUIDParameterType(ParamType[uuid.UUID]):
    name: str

    def convert(self, value: uuid.UUID | str, param: Parameter | None, ctx: Context | None) -> uuid.UUID:
        ...

    def __repr__(self) -> str:
        ...

class FileInfoDict(ParamTypeInfoDict):
    mode: str
    encoding: str | None

class File(ParamType[t.IO[t.Any]]):
    name: str
    envvar_list_splitter: t.ClassVar[str]
    mode: str
    encoding: str | None
    errors: str | None
    lazy: bool | None
    atomic: bool

    def __init__(self, mode: str='r', encoding: str | None=None, errors: str | None='strict', lazy: bool | None=None, atomic: bool=False) -> None:
        ...

    def to_info_dict(self) -> FileInfoDict:
        ...

    def resolve_lazy_flag(self, value: str | os.PathLike[str]) -> bool:
        ...

    def convert(self, value: str | os.PathLike[str] | t.IO[t.Any], param: Parameter | None, ctx: Context | None) -> t.IO[t.Any]:
        ...

    def shell_complete(self, ctx: Context, param: Parameter, incomplete: str) -> list[CompletionItem]:
        ...

def _is_file_like(value: t.Any) -> te.TypeIs[t.IO[t.Any]]:
    ...

class PathInfoDict(ParamTypeInfoDict):
    exists: bool
    file_okay: bool
    dir_okay: bool
    writable: bool
    readable: bool
    allow_dash: bool

class Path(ParamType[_PathT_co, str | os.PathLike[str]], t.Generic[_PathT_co]):
    envvar_list_splitter: t.ClassVar[str]
    exists: bool
    file_okay: bool
    dir_okay: bool
    readable: bool
    writable: bool
    executable: bool
    resolve_path: bool
    allow_dash: bool
    name: str
    type: builtins.type[_PathT_co] | None

    def __init__(self, exists: bool=False, file_okay: bool=True, dir_okay: bool=True, writable: bool=False, readable: bool=True, resolve_path: bool=False, allow_dash: bool=False, path_type: builtins.type[_PathT_co] | None=None, executable: bool=False) -> None:
        ...

    def to_info_dict(self) -> PathInfoDict:
        ...

    def coerce_path_result(self, value: str | os.PathLike[str]) -> _PathT_co:
        ...

    def convert(self, value: str | os.PathLike[str], param: Parameter | None, ctx: Context | None) -> _PathT_co:
        ...

    def shell_complete(self, ctx: Context, param: Parameter, incomplete: str) -> list[CompletionItem]:
        ...

class TupleInfoDict(ParamTypeInfoDict):
    types: cabc.Sequence[ParamTypeInfoDict]

class Tuple(CompositeParamType[tuple[t.Any, ...]]):
    types: cabc.Sequence[ParamType[t.Any]]

    def __init__(self, types: cabc.Sequence[builtins.type[t.Any] | ParamType[t.Any]]) -> None:
        ...

    def to_info_dict(self) -> TupleInfoDict:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def arity(self) -> int:
        ...

    def convert(self, value: t.Any, param: Parameter | None, ctx: Context | None) -> tuple[t.Any, ...]:
        ...

def _guess_type(ty: builtins.type[t.Any] | ParamType[t.Any] | None, default: t.Any | None) -> builtins.type[t.Any] | tuple[builtins.type[t.Any], ...] | ParamType[t.Any] | None:
    ...

@t.overload
def convert_type(ty: None, default: None=None) -> StringParamType:
    ...

@t.overload
def convert_type(ty: type | ParamType[t.Any], default: t.Any | None=None) -> ParamType[t.Any]:
    ...

@t.overload
def convert_type(ty: t.Any | None, default: t.Any | None=None) -> ParamType[t.Any]:
    ...
UNPROCESSED: t.Final[UnprocessedParamType]
STRING: t.Final[StringParamType]
INT: t.Final[IntParamType]
FLOAT: t.Final[FloatParamType]
BOOL: t.Final[BoolParamType]
UUID: t.Final[UUIDParameterType]

class OptionHelpExtra(t.TypedDict, total=False):
    envvars: tuple[str, ...]
    default: str
    range: str
    required: str
