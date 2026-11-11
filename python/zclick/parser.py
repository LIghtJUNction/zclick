"""Legacy parser adapter over the Rust/zclap token engine.

Definitions are rebuilt on every call so mutation and Python subclass hooks stay
observable. No Click implementation is loaded by this module.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING, TypeVar

from .exceptions import BadArgumentUsage, BadOptionUsage, NoSuchOption
from ._utils import FLAG_NEEDS_VALUE

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
    return prefix + ctx.token_normalize_func(name)


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
        self.action, self.nargs, self.const = action or "store", nargs, const
        self._short_opts = [x for x in opts if len(_split_opt(x)[0]) == 1 and len(_split_opt(x)[1]) == 1]
        self._long_opts = [x for x in opts if x not in self._short_opts]
        self.prefixes = {_split_opt(x)[0] for x in opts}

    @property
    def takes_value(self) -> bool:
        return self.action in ("store", "append")

    def process(self, value: Any, state: _ParsingState) -> None:
        if self.action in ("store_const", "append_const"):
            value = self.const
        if self.action.startswith("append"):
            state.opts.setdefault(self.dest, []).append(value)
        elif self.action == "count":
            state.opts[self.dest] = state.opts.get(self.dest, 0) + 1
        else:
            state.opts[self.dest] = value
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
        state.opts[self.dest] = UNSET if self.nargs == -1 and value == () else value
        state.order.append(self.obj)


class _OptionParser:
    def __init__(self, ctx: Context | None = None) -> None:
        self.ctx = ctx
        self.allow_interspersed_args = ctx.allow_interspersed_args if ctx else True
        self.ignore_unknown_options = ctx.ignore_unknown_options if ctx else False
        self._opt_prefixes = {"-", "--"}
        self._short_opt: dict[str, _Option] = {}
        self._long_opt: dict[str, _Option] = {}
        self._args: list[_Argument] = []
        self._options: list[_Option] = []

    def add_option(self, obj: Any, opts: list[str], dest: str | None,
                   action: str | None = None, nargs: int = 1, const: Any = None) -> None:
        option = _Option(obj, [_normalize_opt(o, self.ctx) for o in opts], dest, action, nargs, const)
        self._options.append(option)
        self._opt_prefixes.update(option.prefixes)
        self._short_opt.update((o, option) for o in option._short_opts)
        self._long_opt.update((o, option) for o in option._long_opts)

    def add_argument(self, obj: Any, dest: str | None, nargs: int = 1) -> None:
        self._args.append(_Argument(obj, dest, nargs))

    def parse_args(self, args: list[str]) -> tuple[dict[str, Any], list[str], list[Any]]:
        from . import _native
        from ._utils import UNSET
        definitions: list[Any] = self._options + self._args
        specs = [(i, p.opts if isinstance(p, _Option) else [], p.nargs,
                  isinstance(p, _Option) and not p.takes_value,
                  bool(getattr(p.obj, "_flag_needs_value", False)))
                 for i, p in enumerate(definitions)]
        normalized = args
        if self.ctx and self.ctx.token_normalize_func:
            # Normalize option spellings, never their attached values or positional tokens.
            normalized = []
            pending = 0
            ended = False
            for token in args:
                if pending or ended:
                    normalized.append(token)
                    pending = max(0, pending - 1)
                    continue
                if token == "--":
                    ended = True
                    normalized.append(token)
                    continue
                head, sep, tail = token.partition("=")
                if _split_opt(head)[0] in self._opt_prefixes:
                    head = _normalize_opt(head, self.ctx)
                    found = self._long_opt.get(head) or self._short_opt.get(head)
                    if found and found.takes_value and not sep:
                        pending = found.nargs
                    token = head + sep + tail
                normalized.append(token)
        values, leftovers, order, error = _native.parse(
            specs, normalized, self.allow_interspersed_args, self.ignore_unknown_options)
        state = _ParsingState([])
        occurrence = {}
        for index in order:
            p = definitions[index]
            position = occurrence.get(index, 0)
            occurrence[index] = position + 1
            items = values.get(index, [()])[position]
            if isinstance(p, _Option):
                value = (_flag_needs_value if not items and p.takes_value else
                         items[0] if p.nargs == 1 and items else tuple(items))
            else:
                value = items[0] if p.nargs == 1 and items else tuple(items) if items or p.nargs < 0 else UNSET
            p.process(value, state)
        if error and not (self.ctx and self.ctx.resilient_parsing):
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
