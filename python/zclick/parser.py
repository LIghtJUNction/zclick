"""Legacy parser adapter over the Rust/zclap token engine.

Every call validates the live definitions before reusing an immutable native
schema. Invocation state and Python actions are never cached. No Click
implementation is loaded by this module.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING, TypeVar

from .exceptions import BadArgumentUsage, BadOptionUsage, NoSuchOption
from ._utils import FLAG_NEEDS_VALUE
from . import _native

if TYPE_CHECKING:
    from .core import Context

_flag_needs_value = FLAG_NEEDS_VALUE
V = TypeVar("V")


def _split_opt(opt: str) -> tuple[str, str]:
    if not opt or opt[0].isalnum():
        return "", opt
    size = 2 if len(opt) > 1 and opt[:1] == opt[1:2] else 1
    return opt[:size], opt[size:]


def _normalize_opt(opt: str, ctx: Context | None) -> str:
    if ctx is None or ctx.token_normalize_func is None:
        return opt
    prefix, name = _split_opt(opt)
    return f"{prefix}{ctx.token_normalize_func(name)}"


class _ParsingState:
    def __init__(self, rargs: list[str]) -> None:
        self.opts: dict[str, Any] = {}
        self.largs: list[str] = []
        self.rargs = rargs
        self.order: list[Any] = []


class _Option:
    def __init__(self, obj: Any, opts: list[str], dest: str | None,
                 action: str | None = None, nargs: int = 1, const: Any = None) -> None:
        self.obj, self.opts, self.dest = obj, list(opts), dest
        self.action, self.nargs, self.const = "store" if action is None else action, nargs, const
        self._short_opts, self._long_opts, self.prefixes = [], [], set()
        for spelling in opts:
            prefix, suffix = _split_opt(spelling)
            if not prefix:
                raise ValueError(f"Invalid start character for option ({spelling})")
            self.prefixes.add(prefix[0])
            if len(prefix) == len(suffix) == 1:
                self._short_opts.append(spelling)
            else:
                self._long_opts.append(spelling)
                self.prefixes.add(prefix)

    @property
    def takes_value(self) -> bool:
        return self.action in ("store", "append")

    def process(self, value: Any, state: _ParsingState) -> None:
        if self.action in ("store_const", "append_const"):
            value = self.const
        if self.action in ("append", "append_const"):
            state.opts.setdefault(self.dest, []).append(value)
        elif self.action == "count":
            state.opts[self.dest] = state.opts.get(self.dest, 0) + 1
        elif self.action in ("store", "store_const"):
            state.opts[self.dest] = value
        else:
            raise ValueError(f"unknown action '{self.action}'")
        state.order.append(self.obj)


class _Argument:
    def __init__(self, obj: Any, dest: str | None, nargs: int = 1) -> None:
        self.obj, self.dest, self.nargs = obj, dest, nargs

    def process(self, value: Any, state: _ParsingState) -> None:
        from ._utils import UNSET
        if self.nargs > 1 and value is not UNSET and value and any(v is UNSET for v in value):
            if not all(v is UNSET for v in value):
                raise BadArgumentUsage(f"Argument {self.dest!r} takes {self.nargs} values.")
            value = UNSET
        state.opts[self.dest] = UNSET if value == () else value
        state.order.append(self.obj)


class _OptionParser:
    def __init__(self, ctx: Context | None = None) -> None:
        self.ctx = ctx
        self.allow_interspersed_args = ctx.allow_interspersed_args if ctx is not None else True
        self.ignore_unknown_options = ctx.ignore_unknown_options if ctx is not None else False
        self._opt_prefixes = {"-", "--"}
        self._short_opt: dict[str, _Option] = {}
        self._long_opt: dict[str, _Option] = {}
        self._args: list[_Argument] = []
        self._options: list[_Option] = []
        self._plan: _native.ParserPlan | None = None

    def add_option(self, obj: Any, opts: list[str], dest: str | None,
                   action: str | None = None, nargs: int = 1, const: Any = None) -> None:
        normalized = [_normalize_opt(o, self.ctx) for o in opts] if self.ctx is not None and self.ctx.token_normalize_func is not None else opts
        option = _Option(obj, normalized, dest, action, nargs, const)
        self._options.append(option)
        self._opt_prefixes.update(option.prefixes)
        for spelling in option._short_opts:
            self._short_opt[spelling] = option
        for spelling in option._long_opts:
            self._long_opt[spelling] = option

    def add_argument(self, obj: Any, dest: str | None, nargs: int = 1) -> None:
        self._args.append(_Argument(obj, dest, nargs))

    def parse_args(self, args: list[str]) -> tuple[dict[str, Any], list[str], list[Any]]:
        from ._utils import UNSET
        definitions: list[Any] = self._options + self._args
        plan = _native.ParserPlan.from_definitions(definitions, _Option, self._plan)
        self._plan = plan
        normalize = None
        if self.ctx is not None and self.ctx.token_normalize_func is not None:
            normalize = lambda spelling: _normalize_opt(spelling, self.ctx)
        state = _ParsingState([])
        leftovers, error = plan.parse_into(
            args, definitions, state, UNSET, _flag_needs_value,
            bool(self.allow_interspersed_args), bool(self.ignore_unknown_options),
            normalizer=normalize, original_args=args)
        if error and not (self.ctx is not None and self.ctx.resilient_parsing):
            kind, spelling = error["kind"], error.get("option", "")
            if kind == "unknown_option":
                import difflib
                raise NoSuchOption(spelling, possibilities=difflib.get_close_matches(spelling, self._long_opt), ctx=self.ctx)
            if kind in ("missing_argument", "argument_arity"):
                p = definitions[error["id"]]
                raise BadArgumentUsage(f"Argument {p.dest!r} takes {p.nargs} values.")
            if kind == "definition":
                raise TypeError(error["message"])
            raise BadOptionUsage(spelling, error["message"])
        return state.opts, leftovers, state.order


def __getattr__(name: str) -> Any:
    import warnings
    aliases = {"OptionParser": _OptionParser, "Option": _Option,
               "Argument": _Argument, "ParsingState": _ParsingState,
               "split_opt": _split_opt, "normalize_opt": _normalize_opt}
    if name == "split_arg_string":
        from .shell_completion import split_arg_string
        value = split_arg_string
    elif name in aliases:
        value = aliases[name]
    else:
        raise AttributeError(name)
    warnings.warn(f"'{name}' is deprecated and will be removed in Click 9.0.", DeprecationWarning, stacklevel=2)
    return value
