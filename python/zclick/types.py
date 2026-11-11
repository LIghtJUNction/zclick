"""Python value adapters for the native command parser.

Conversions intentionally use Python objects: integers remain unbounded, user
converters remain virtual, and file ownership follows the context lifetime.
"""
from __future__ import annotations

import abc

import enum
import os
import stat
import sys
import typing as t
import uuid
from datetime import datetime

from .exceptions import BadParameter

V = t.TypeVar("V", covariant=True)
I = t.TypeVar("I", contravariant=True)
P = t.TypeVar("P", covariant=True)


class ParamTypeInfoDict(t.TypedDict):
    param_type: str
    name: str


class FuncParamTypeInfoDict(ParamTypeInfoDict):
    func: t.Callable[[t.Any], t.Any]


class ChoiceInfoDict(ParamTypeInfoDict):
    choices: tuple[t.Any, ...]
    case_sensitive: bool


class DateTimeInfoDict(ParamTypeInfoDict):
    formats: t.Sequence[str]


class NumberRangeInfoDict(ParamTypeInfoDict):
    min: t.Any | None
    max: t.Any | None
    min_open: bool
    max_open: bool
    clamp: bool


class FileInfoDict(ParamTypeInfoDict):
    mode: str
    encoding: str | None


class PathInfoDict(ParamTypeInfoDict):
    exists: bool
    file_okay: bool
    dir_okay: bool
    writable: bool
    readable: bool
    allow_dash: bool


class TupleInfoDict(ParamTypeInfoDict):
    types: t.Sequence[ParamTypeInfoDict]


class OptionHelpExtra(t.TypedDict, total=False):
    envvars: tuple[str, ...]
    default: str
    range: str
    required: str


class ParamType(t.Generic[V, I], abc.ABC):
    name: str
    is_composite = False
    arity = 1
    envvar_list_splitter: str | None = None

    @classmethod
    def __class_getitem__(cls, item: t.Any) -> t.Any:
        if len(getattr(cls, "__parameters__", ())) == 2 and not isinstance(item, tuple):
            item = (item, t.Any)
        return super().__class_getitem__(item)

    def __call__(self, value: I | None, param: t.Any = None, ctx: t.Any = None) -> V | None:
        return None if value is None else self.convert(value, param, ctx)

    def convert(self, value: I, param: t.Any, ctx: t.Any) -> V:
        return t.cast(V, value)

    def to_info_dict(self) -> dict[str, t.Any]:
        kind = self.__class__.__name__.removesuffix("ParamType").removesuffix("ParameterType")
        return {"param_type": kind, "name": getattr(self, "name", kind)}

    def get_metavar(self, param: t.Any, ctx: t.Any) -> str | None:
        return None

    def get_missing_message(self, param: t.Any, ctx: t.Any) -> str | None:
        return None

    def split_envvar_value(self, rv: str) -> list[str]:
        return rv.split(self.envvar_list_splitter)

    def fail(self, message: str, param: t.Any = None, ctx: t.Any = None) -> t.NoReturn:
        raise BadParameter(message, ctx=ctx, param=param)

    def shell_complete(self, ctx: t.Any, param: t.Any, incomplete: str) -> list[t.Any]:
        return []


class CompositeParamType(ParamType[V, I]):
    is_composite = True

    @property
    @abc.abstractmethod
    def arity(self) -> int:
        """The number of input values consumed by this composite type."""
        return t.cast(int, None)


class FuncParamType(ParamType[V, I]):
    def __init__(self, func: t.Callable[[I], V]) -> None:
        self.func = func
        self.name = getattr(func, "__name__", type(func).__name__)

    def to_info_dict(self) -> dict[str, t.Any]:
        return {**super().to_info_dict(), "func": self.func}

    def convert(self, value: I, param: t.Any, ctx: t.Any) -> V:
        try:
            return self.func(value)
        except ValueError as exc:
            self.fail(str(exc) or str(value), param, ctx)


class UnprocessedParamType(ParamType[t.Any, t.Any]):
    name = "text"

    def __repr__(self) -> str:
        return "UNPROCESSED"


class StringParamType(ParamType[str, t.Any]):
    name = "text"

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> str:
        if isinstance(value, bytes):
            for encoding in (sys.getfilesystemencoding(), "utf-8"):
                try:
                    return value.decode(encoding)
                except UnicodeError:
                    pass
            return value.decode("utf-8", "replace")
        return str(value)

    def __repr__(self) -> str:
        return "STRING"


class Choice(ParamType[V, t.Any]):
    name = "choice"

    def __init__(self, choices: t.Iterable[V], case_sensitive: bool = True) -> None:
        self.choices = tuple(choices)
        self.case_sensitive = case_sensitive

    def to_info_dict(self) -> dict[str, t.Any]:
        return {**super().to_info_dict(), "choices": self.choices, "case_sensitive": self.case_sensitive}

    def normalize_choice(self, choice: object, ctx: t.Any) -> str:
        result = choice.name if isinstance(choice, enum.Enum) else str(choice)
        normalize = getattr(ctx, "token_normalize_func", None)
        if normalize is not None:
            result = normalize(result)
        return result if self.case_sensitive else result.casefold()

    def _normalized_mapping(self, ctx: t.Any = None) -> dict[V, str]:
        return {item: self.normalize_choice(item, ctx) for item in self.choices}

    def get_metavar(self, param: t.Any, ctx: t.Any) -> str:
        if getattr(param, "param_type_name", None) == "option" and not getattr(param, "show_choices", True):
            names = list(dict.fromkeys(type(value).__name__.upper() if isinstance(value, enum.Enum) else convert_type(type(value)).name.upper() for value in self.choices))
            return "[" + "|".join(names) + "]"
        values = "|".join(self.normalize_choice(v, ctx) for v in self.choices)
        return f"{{{values}}}" if getattr(param, "required", False) and getattr(param, "param_type_name", None) == "argument" else f"[{values}]"

    def get_missing_message(self, param: t.Any, ctx: t.Any) -> str:
        return "Choose from:\n\t" + ",\n\t".join(self.normalize_choice(v, ctx) for v in self.choices)

    def get_invalid_choice_message(self, value: t.Any, ctx: t.Any) -> str:
        options = ", ".join(repr(self.normalize_choice(v, ctx)) for v in self.choices)
        if len(self.choices) == 1:
            return f"{value!r} is not {options}."
        return f"{value!r} is not one of {options}."

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> V:
        normalized = self.normalize_choice(value, ctx)
        for item in self.choices:
            if self.normalize_choice(item, ctx) == normalized:
                return item
        self.fail(self.get_invalid_choice_message(value, ctx), param, ctx)

    def shell_complete(self, ctx: t.Any, param: t.Any, incomplete: str) -> list[t.Any]:
        from .shell_completion import CompletionItem
        prefix = self.normalize_choice(incomplete, ctx)
        return [CompletionItem(self.normalize_choice(v, ctx)) for v in self.choices if self.normalize_choice(v, ctx).startswith(prefix)]

    def __repr__(self) -> str:
        return f"Choice({list(self.choices)!r})"


class DateTime(ParamType[datetime, t.Any]):
    name = "datetime"

    def __init__(self, formats: t.Sequence[str] | None = None) -> None:
        self.formats = formats if formats is not None else ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]

    def to_info_dict(self) -> dict[str, t.Any]:
        return {**super().to_info_dict(), "formats": self.formats}

    def get_metavar(self, param: t.Any, ctx: t.Any) -> str:
        return "[" + "|".join(self.formats) + "]"

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> datetime:
        if isinstance(value, datetime):
            return value
        for format in self.formats:
            try:
                return datetime.strptime(value, format)
            except ValueError:
                pass
        formats = ", ".join(repr(f) for f in self.formats)
        desc = "the format" if len(self.formats) == 1 else "the formats"
        self.fail(f"{value!r} does not match {desc} {formats}.", param, ctx)

    def __repr__(self) -> str:
        return "DateTime"


class IntParamType(ParamType[int, t.Any]):
    name = "integer"

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            self.fail(f"{value!r} is not a valid integer.", param, ctx)

    def __repr__(self) -> str:
        return "INT"


class FloatParamType(ParamType[float, t.Any]):
    name = "float"

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            self.fail(f"{value!r} is not a valid float.", param, ctx)

    def __repr__(self) -> str:
        return "FLOAT"


class _NumberRange:
    def __init__(self, min: float | None = None, max: float | None = None, min_open: bool = False, max_open: bool = False, clamp: bool = False) -> None:
        self.min, self.max, self.min_open, self.max_open, self.clamp = min, max, min_open, max_open, clamp

    def to_info_dict(self) -> dict[str, t.Any]:
        return {**super().to_info_dict(), **{k: getattr(self, k) for k in ("min", "max", "min_open", "max_open", "clamp")}}

    def _describe_range(self) -> str:
        left = "<" if self.min_open else "<="
        right = "<" if self.max_open else "<="
        if self.min is None:
            return f"x{right}{self.max}" if self.max is not None else "any"
        if self.max is None:
            return f"x{'>' if self.min_open else '>='}{self.min}"
        return f"{self.min}{left}x{right}{self.max}"

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> t.Any:
        result = super().convert(value, param, ctx)
        low = self.min is not None and (result < self.min or self.min_open and result == self.min)
        high = self.max is not None and (result > self.max or self.max_open and result == self.max)
        if low or high:
            if self.clamp:
                if isinstance(self, FloatRange) and (self.min_open or self.max_open):
                    raise RuntimeError("Clamping is not supported for open bounds.")
                return (self.min + int(self.min_open)) if low else (self.max - int(self.max_open))
            self.fail(f"{result} is not in the range {self._describe_range()}.", param, ctx)
        return result

    def __repr__(self) -> str:
        suffix = " clamped" if self.clamp else ""
        return f"<{self.__class__.__name__} {self._describe_range()}{suffix}>"


class IntRange(_NumberRange, IntParamType):
    name = "integer range"


class FloatRange(_NumberRange, FloatParamType):
    name = "float range"

    def __init__(self, min: float | None = None, max: float | None = None, min_open: bool = False, max_open: bool = False, clamp: bool = False) -> None:
        if clamp and (min_open or max_open):
            raise TypeError("Clamping is not supported for open bounds.")
        super().__init__(min, max, min_open, max_open, clamp)


class BoolParamType(ParamType[bool, t.Any]):
    name = "boolean"
    bool_states = {value: True for value in ("1", "true", "t", "yes", "y", "on")} | {value: False for value in ("", "0", "false", "f", "no", "n", "off")}

    @staticmethod
    def str_to_bool(value: str | bool) -> bool | None:
        if isinstance(value, bool):
            return value
        lowered = str(value).strip().casefold()
        return BoolParamType.bool_states.get(lowered)

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> bool:
        result = self.str_to_bool(value)
        if result is None:
            self.fail(f"{value!r} is not a valid boolean.", param, ctx)
        return result

    def __repr__(self) -> str:
        return "BOOL"


class UUIDParameterType(ParamType[uuid.UUID, t.Any]):
    name = "uuid"

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> uuid.UUID:
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(value.strip())
        except (ValueError, AttributeError):
            self.fail(f"{value!r} is not a valid UUID.", param, ctx)

    def __repr__(self) -> str:
        return "UUID"


class File(ParamType[t.IO[t.Any], t.Any]):
    name = "filename"
    envvar_list_splitter = os.path.pathsep

    def __init__(self, mode: str = "r", encoding: str | None = None, errors: str | None = "strict", lazy: bool | None = None, atomic: bool = False) -> None:
        self.mode, self.encoding, self.errors, self.lazy, self.atomic = mode, encoding, errors, lazy, atomic

    def to_info_dict(self) -> dict[str, t.Any]:
        return {**super().to_info_dict(), "mode": self.mode, "encoding": self.encoding}

    def resolve_lazy_flag(self, value: t.Any) -> bool:
        if self.lazy is not None:
            return self.lazy
        path = os.fspath(value)
        return path != (b"-" if isinstance(path, bytes) else "-") and "w" in self.mode

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> t.Any:
        if hasattr(value, "read") or hasattr(value, "write"):
            return value
        from .utils import _LazyFile, _open_stream, format_filename
        try:
            if self.resolve_lazy_flag(value):
                stream = _LazyFile(value, self.mode, self.encoding, self.errors, atomic=self.atomic)
                if ctx is not None:
                    ctx.call_on_close(stream.close_intelligently)
                return stream
            stream, owned = _open_stream(value, self.mode, self.encoding, self.errors, atomic=self.atomic)
            if ctx is not None:
                ctx.call_on_close(stream.close if owned else stream.flush)
            return stream
        except OSError as exc:
            self.fail(f"'{format_filename(value)}': {exc.strerror}", param, ctx)

    def shell_complete(self, ctx: t.Any, param: t.Any, incomplete: str) -> list[t.Any]:
        from .shell_completion import CompletionItem
        return [CompletionItem(incomplete, type="file")]

class Path(ParamType[P, t.Any]):
    envvar_list_splitter = os.path.pathsep

    def __init__(self, exists: bool = False, file_okay: bool = True, dir_okay: bool = True, writable: bool = False, readable: bool = True, resolve_path: bool = False, allow_dash: bool = False, path_type: type[P] | None = None, executable: bool = False) -> None:
        self.exists, self.file_okay, self.dir_okay = exists, file_okay, dir_okay
        self.writable, self.readable, self.resolve_path = writable, readable, resolve_path
        self.allow_dash, self.type, self.executable = allow_dash, path_type, executable
        self.name = "file" if file_okay and not dir_okay else "directory" if dir_okay and not file_okay else "path"

    def to_info_dict(self) -> dict[str, t.Any]:
        return {**super().to_info_dict(), **{k: getattr(self, k) for k in ("exists", "file_okay", "dir_okay", "writable", "readable", "allow_dash")}}

    def coerce_path_result(self, value: t.Any) -> P:
        if self.type is str:
            return os.fsdecode(value)
        if self.type is bytes:
            return os.fsencode(value)
        return self.type(value) if self.type is not None else value

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> P:
        from .utils import format_filename
        path = os.fspath(value)
        dash = path == (b"-" if isinstance(path, bytes) else "-")
        if self.allow_dash and self.file_okay and dash:
            return self.coerce_path_result(value)
        if self.resolve_path:
            value = os.path.realpath(value)
        def fail(reason: str) -> t.NoReturn:
            self.fail(f"{self.name.title()} {format_filename(value)!r} {reason}.", param, ctx)
        try:
            mode = os.stat(value).st_mode
        except OSError:
            if self.exists:
                fail("does not exist")
            return self.coerce_path_result(value)
        if not self.file_okay and stat.S_ISREG(mode):
            fail("is a file")
        if not self.dir_okay and stat.S_ISDIR(mode):
            fail("is a directory")
        for enabled, mode, reason in ((self.readable, os.R_OK, "readable"), (self.writable, os.W_OK, "writable"), (self.executable, os.X_OK, "executable")):
            if enabled and not os.access(value, mode):
                fail(f"is not {reason}")
        return self.coerce_path_result(value)

    def shell_complete(self, ctx: t.Any, param: t.Any, incomplete: str) -> list[t.Any]:
        from .shell_completion import CompletionItem
        return [CompletionItem(incomplete, type="file" if self.file_okay else "dir")]


class Tuple(CompositeParamType[tuple[t.Any, ...], t.Any]):
    def __init__(self, types: t.Sequence[t.Any]) -> None:
        self.types = [convert_type(tp) for tp in types]

    @property
    def name(self) -> str:
        return "<" + " ".join(tp.name for tp in self.types) + ">"

    @property
    def arity(self) -> int:
        return len(self.types)

    def to_info_dict(self) -> dict[str, t.Any]:
        return {**super().to_info_dict(), "types": [tp.to_info_dict() for tp in self.types]}

    def convert(self, value: t.Any, param: t.Any, ctx: t.Any) -> tuple[t.Any, ...]:
        if len(value) != self.arity:
            self.fail(f"{self.arity} values are required, but {len(value)} was given." if len(value) == 1 else f"{self.arity} values are required, but {len(value)} were given.", param, ctx)
        return tuple(tp(item, param, ctx) for tp, item in zip(self.types, value))


def convert_type(ty: t.Any = None, default: t.Any = None) -> ParamType[t.Any]:
    inferred = ty is None
    if inferred:
        if isinstance(default, (list, tuple)):
            if default and isinstance(default[0], (list, tuple)):
                return Tuple([type(v) for v in default[0]])
            default = default[0] if default else None
        ty = type(default)
    if isinstance(ty, ParamType):
        return ty
    if isinstance(ty, tuple):
        return Tuple(ty)
    known = {str: STRING, int: INT, float: FLOAT, bool: BOOL, type(None): STRING}
    if ty in known:
        return known[ty]
    if inferred:
        return STRING
    if isinstance(ty, type) and issubclass(ty, ParamType):
        raise AssertionError("Attempted to use an uninstantiated parameter type.")
    return FuncParamType(ty)


UNPROCESSED = UnprocessedParamType()
STRING = StringParamType()
INT = IntParamType()
FLOAT = FloatParamType()
BOOL = BoolParamType()
UUID = UUIDParameterType()
