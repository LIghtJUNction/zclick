"""Dynamic Python command objects backed by the native Rust parsing engine.

Python retains ownership of user objects and virtual calls. A fresh native plan
is made for each invocation; mutation, recursion and nested calls do not share
mutable parser state.
"""
from __future__ import annotations

import abc
import inspect
import os
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from contextlib import ExitStack, contextmanager
from enum import Enum, IntEnum
from functools import update_wrapper
from gettext import gettext as _
from itertools import islice
from typing import Any, TypeVar

from . import types
from ._utils import UNSET, FLAG_NEEDS_VALUE
from ._native import (invoke_group as _invoke_group, processing_order as _processing_order,
                      select_parameter_value as _select_parameter_value)
from .exceptions import (Abort, BadParameter, ClickException, Exit, MissingParameter,
                         NoArgsIsHelpError, NoSuchCommand, UsageError)
from .formatting import HelpFormatter
from .globals import get_current_context, pop_context, push_context
from .parser import _OptionParser, _split_opt, _flag_needs_value
from .utils import echo

V = TypeVar("V")
F = TypeVar("F", bound=Callable[..., Any])


def batch(iterable: Iterable[V], batch_size: int) -> list[tuple[V, ...]]:
    iterator = iter(iterable)
    return list(iter(lambda: tuple(islice(iterator, batch_size)), ()))


@contextmanager
def augment_usage_errors(ctx: Context, param: Parameter | None = None):
    try:
        yield
    except BadParameter as exc:
        if exc.ctx is None:
            exc.ctx = ctx
        if exc.param is None:
            exc.param = param
        raise
    except UsageError as exc:
        if exc.ctx is None:
            exc.ctx = ctx
        raise


def iter_params_for_processing(invocation_order: Sequence[Parameter], declaration_order: Sequence[Parameter]) -> list[Parameter]:
    indices = {id(p): n for n, p in enumerate(declaration_order)}
    order = [indices[id(p)] for p in invocation_order if id(p) in indices]
    return [declaration_order[i] for i in _processing_order([p.is_eager for p in declaration_order], order)]


def _format_deprecated_label(value: bool | str) -> str:
    return f"({_('DEPRECATED')}: {value})" if isinstance(value, str) else _("(DEPRECATED)") if value else ""


def _format_deprecated_suffix(value: bool | str) -> str:
    return f" {value}" if isinstance(value, str) else ""


def _invoke_context(ctx: Context, callback: Callable[[], Any]) -> tuple[bool, Any]:
    """Keep Python's handled-exception state while Rust drives dispatch."""
    with ctx:
        return True, callback()
    return False, None


class ParameterSource(IntEnum):
    PROMPT = 1
    COMMANDLINE = 2
    ENVIRONMENT = 3
    DEFAULT_MAP = 4
    DEFAULT = 5


class Context:
    formatter_class = HelpFormatter

    def __init__(self, command: Command, parent: Context | None = None,
                 info_name: str | None = None, obj: Any | None = None,
                 auto_envvar_prefix: str | None = None,
                 default_map: MutableMapping[str, Any] | None = None,
                 terminal_width: int | None = None, max_content_width: int | None = None,
                 resilient_parsing: bool = False, allow_extra_args: bool | None = None,
                 allow_interspersed_args: bool | None = None, ignore_unknown_options: bool | None = None,
                 help_option_names: list[str] | None = None,
                 token_normalize_func: Callable[[str], str] | None = None,
                 color: bool | None = None, show_default: bool | None = None) -> None:
        self.parent, self.command, self.info_name = parent, command, info_name
        self.params: dict[str, Any] = {}
        self.args: list[str] = []
        self._protected_args: list[str] = []
        self._opt_prefixes: set[str] = set(parent._opt_prefixes) if parent else set()
        self.obj = parent.obj if obj is None and parent else obj
        self._meta = parent.meta if parent else {}
        self.default_map = (parent.default_map.get(info_name) if default_map is None and parent and parent.default_map is not None and info_name else default_map)
        self.invoked_subcommand: str | None = None
        self.terminal_width = parent.terminal_width if terminal_width is None and parent else terminal_width
        self.max_content_width = parent.max_content_width if max_content_width is None and parent else max_content_width
        self.allow_extra_args = command.allow_extra_args if allow_extra_args is None else allow_extra_args
        self.allow_interspersed_args = command.allow_interspersed_args if allow_interspersed_args is None else allow_interspersed_args
        self.ignore_unknown_options = command.ignore_unknown_options if ignore_unknown_options is None else ignore_unknown_options
        self.help_option_names = (parent.help_option_names if parent else ["--help"]) if help_option_names is None else help_option_names
        self.token_normalize_func = parent.token_normalize_func if token_normalize_func is None and parent else token_normalize_func
        self.resilient_parsing = resilient_parsing
        self.color = parent.color if color is None and parent else color
        self.show_default = parent.show_default if show_default is None and parent else show_default
        if auto_envvar_prefix is None and parent and parent.auto_envvar_prefix and info_name:
            auto_envvar_prefix = f"{parent.auto_envvar_prefix}_{info_name.upper()}"
        self.auto_envvar_prefix = auto_envvar_prefix.upper().replace("-", "_") if auto_envvar_prefix else None
        self._depth = 0
        self._parameter_source: dict[str, ParameterSource] = {}
        self._param_default_explicit: dict[str, bool] = {}
        self._exit_stack = ExitStack()

    @property
    def protected_args(self) -> list[str]:
        import warnings
        warnings.warn("'protected_args' is deprecated and will be removed in Click 9.0. 'args' will contain remaining unparsed tokens.", DeprecationWarning, stacklevel=2)
        return self._protected_args

    def to_info_dict(self) -> dict[str, Any]:
        with self.scope(cleanup=False):
            return {"command": self.command.to_info_dict(self), "info_name": self.info_name,
                    "allow_extra_args": self.allow_extra_args, "allow_interspersed_args": self.allow_interspersed_args,
                    "ignore_unknown_options": self.ignore_unknown_options, "auto_envvar_prefix": self.auto_envvar_prefix}

    def __enter__(self) -> Context:
        self._depth += 1
        push_context(self)
        return self

    def __exit__(self, exc_type, exc_value, tb) -> bool | None:
        self._depth -= 1
        try:
            if self._depth == 0:
                return self._close_with_exception_info(exc_type, exc_value, tb)
        finally:
            pop_context()

    @contextmanager
    def scope(self, cleanup: bool = True):
        if not cleanup:
            self._depth += 1
        try:
            with self:
                yield self
        finally:
            if not cleanup:
                self._depth -= 1

    @property
    def meta(self) -> dict[str, Any]:
        return self._meta

    def make_formatter(self) -> HelpFormatter:
        return self.formatter_class(width=self.terminal_width, max_width=self.max_content_width)

    def with_resource(self, context_manager):
        return self._exit_stack.enter_context(context_manager)

    def call_on_close(self, f: Callable[..., Any]) -> Callable[..., Any]:
        return self._exit_stack.callback(f)

    def close(self) -> None:
        self._close_with_exception_info(None, None, None)

    def _close_with_exception_info(self, exc_type, exc_value, tb) -> bool:
        try:
            return self._exit_stack.__exit__(exc_type, exc_value, tb)
        finally:
            self._exit_stack = ExitStack()

    @property
    def command_path(self) -> str:
        if self.parent is None:
            return self.info_name or ""
        pieces = [self.parent.command_path]
        for param in self.parent.command.get_params(self.parent):
            pieces.extend(param.get_usage_pieces(self))
        pieces.append(self.info_name or "")
        return " ".join(pieces).strip()

    def find_root(self) -> Context:
        root = self
        while root.parent is not None:
            root = root.parent
        return root

    def find_object(self, object_type: type[V]) -> V | None:
        ctx: Context | None = self
        while ctx is not None:
            if isinstance(ctx.obj, object_type):
                return ctx.obj
            ctx = ctx.parent
        return None

    def ensure_object(self, object_type: type[V]) -> V:
        obj = self.find_object(object_type)
        if obj is None:
            self.obj = obj = object_type()
        return obj

    def _default_map_has(self, name: str | None) -> bool:
        return name is not None and self.default_map is not None and self.default_map.get(name, UNSET) is not UNSET

    def lookup_default(self, name: str, call: bool = True) -> Any:
        value = self.default_map.get(name) if self.default_map is not None else None
        if value is UNSET:
            return None
        return value() if call and callable(value) else value

    def fail(self, message: str):
        raise UsageError(message, self)

    def abort(self):
        raise Abort()

    def exit(self, code: int = 0):
        self.close()
        raise Exit(code)

    def get_usage(self) -> str:
        return self.command.get_usage(self)

    def get_help(self) -> str:
        return self.command.get_help(self)

    def _make_sub_context(self, command: Command) -> Context:
        return type(self)(command, info_name=command.name, parent=self)

    def invoke(self, callback: Command | Callable[..., V], /, *args: Any, **kwargs: Any) -> V:
        ctx = self
        if isinstance(callback, Command):
            command = callback
            if command.callback is None:
                raise TypeError("The given command does not have a callback that can be invoked.")
            callback = command.callback
            ctx = self._make_sub_context(command)
            for param in command.params:
                if param.expose_value and param.name not in kwargs:
                    value = param.type_cast_value(ctx, param.get_default(ctx))
                    kwargs[param.name] = param._hide_unset(value)
            ctx.params.update(kwargs)
        with augment_usage_errors(ctx):
            with ctx:
                return callback(*args, **kwargs)

    def forward(self, cmd: Command, /, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(cmd, Command):
            raise TypeError("Callback is not a command.")
        for key, value in self.params.items():
            kwargs.setdefault(key, value)
        return self.invoke(cmd, *args, **kwargs)

    def set_parameter_source(self, name: str, source: ParameterSource) -> None:
        self._parameter_source[name] = source

    def get_parameter_source(self, name: str) -> ParameterSource | None:
        return self._parameter_source.get(name)


class Command:
    context_class = Context
    allow_extra_args = False
    allow_interspersed_args = True
    ignore_unknown_options = False

    def __init__(self, name: str | None, context_settings: MutableMapping[str, Any] | None = None,
                 callback: Callable[..., Any] | None = None, params: list[Parameter] | None = None,
                 help: str | None = None, epilog: str | None = None, short_help: str | None = None,
                 options_metavar: str | None = "[OPTIONS]", add_help_option: bool = True,
                 no_args_is_help: bool = False, hidden: bool = False, deprecated: bool | str = False) -> None:
        self.name, self.context_settings, self.callback = name, context_settings or {}, callback
        self.params = params if params is not None else []
        self.help, self.epilog, self.short_help = help, epilog, short_help
        self.options_metavar, self.add_help_option = options_metavar, add_help_option
        self.no_args_is_help, self.hidden, self.deprecated = no_args_is_help, hidden, deprecated
        self._help_option: Option | None = None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name}>"

    def to_info_dict(self, ctx: Context) -> dict[str, Any]:
        return {"name": self.name, "params": [p.to_info_dict() for p in self.get_params(ctx)],
                "help": self.help, "epilog": self.epilog, "short_help": self.short_help,
                "hidden": self.hidden, "deprecated": self.deprecated}

    def get_usage(self, ctx: Context) -> str:
        formatter = ctx.make_formatter()
        self.format_usage(ctx, formatter)
        return formatter.getvalue().rstrip("\n")

    def get_params(self, ctx: Context) -> list[Parameter]:
        params = self.params[:]
        help_option = self.get_help_option(ctx)
        if help_option is not None:
            params.append(help_option)
        counts = Counter(o for p in params for o in p.opts + p.secondary_opts)
        for name, count in counts.items():
            if count > 1:
                import warnings
                warnings.warn(f"The parameter {name} is used more than once. Remove its duplicate as parameters should be unique.", UserWarning, stacklevel=3)
        argument_names = set()
        options = []
        for param in self.params:
            if help_option is not None and param.name == "_click_default_help":
                import warnings
                warnings.warn("The name '_click_default_help' is reserved for the automatic help option.", UserWarning, stacklevel=3)
            cls = type(param)
            if cls is Option or isinstance(param, Option):
                options.append(param)
            elif cls is Argument or isinstance(param, Argument):
                argument_names.add(param.name)
        if argument_names:
            import warnings
            for param in options:
                if param.name in argument_names:
                    warnings.warn(f"The name {param.name!r} is used by an argument and an option.", UserWarning, stacklevel=3)
        return params

    def format_usage(self, ctx: Context, formatter: HelpFormatter) -> None:
        formatter.write_usage(ctx.command_path, " ".join(self.collect_usage_pieces(ctx)))

    def collect_usage_pieces(self, ctx: Context) -> list[str]:
        pieces = [self.options_metavar] if self.options_metavar else []
        for param in self.get_params(ctx):
            pieces.extend(param.get_usage_pieces(ctx))
        return pieces

    def get_help_option_names(self, ctx: Context) -> list[str]:
        claimed = {s for p in self.params for s in p.opts + p.secondary_opts}
        return list(dict.fromkeys(s for s in ctx.help_option_names if s not in claimed))

    def get_help_option(self, ctx: Context) -> Option | None:
        names = self.get_help_option_names(ctx)
        if not self.add_help_option or not names:
            return None
        if self._help_option is None or self._help_option.opts != names:
            from .decorators import help_option
            holder = lambda: None
            help_option(*names, "_click_default_help")(holder)
            self._help_option = holder.__click_params__[0]
        return self._help_option

    def make_parser(self, ctx: Context) -> _OptionParser:
        parser = _OptionParser(ctx)
        for param in self.get_params(ctx):
            param.add_to_parser(parser, ctx)
        return parser

    def get_help(self, ctx: Context) -> str:
        formatter = ctx.make_formatter()
        self.format_help(ctx, formatter)
        return formatter.getvalue().rstrip("\n")

    def get_short_help_str(self, limit: int = 45) -> str:
        from .utils import _make_default_short_help
        text = self.short_help if self.short_help is not None else _make_default_short_help(self.help or "", limit)
        label = _format_deprecated_label(self.deprecated)
        return f"{text} {label}".strip() if label else text

    def format_help(self, ctx: Context, formatter: HelpFormatter) -> None:
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_arguments(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_epilog(ctx, formatter)

    def format_help_text(self, ctx: Context, formatter: HelpFormatter) -> None:
        text = inspect.cleandoc(self.help).partition("\f")[0] if self.help else ""
        label = _format_deprecated_label(self.deprecated)
        if label:
            text = f"{text} {label}".strip()
        if text:
            formatter.write_paragraph()
            with formatter.indentation():
                formatter.write_text(text)

    def format_options(self, ctx: Context, formatter: HelpFormatter) -> None:
        records = [r for p in self.get_params(ctx) if isinstance(p, Option) and (r := p.get_help_record(ctx)) is not None]
        if records:
            with formatter.section("Options"):
                formatter.write_dl(records)

    def format_arguments(self, ctx: Context, formatter: HelpFormatter) -> None:
        arguments = [p for p in self.get_params(ctx) if isinstance(p, Argument)]
        if any(p.help is not None for p in arguments):
            with formatter.section(_("Positional arguments")):
                formatter.write_dl([p.get_help_record(ctx) for p in arguments])

    def format_epilog(self, ctx: Context, formatter: HelpFormatter) -> None:
        if self.epilog:
            formatter.write_paragraph()
            with formatter.indentation():
                formatter.write_text(inspect.cleandoc(self.epilog))

    def make_context(self, info_name: str | None, args: list[str], parent: Context | None = None, **extra: Any) -> Context:
        for key, value in self.context_settings.items():
            extra.setdefault(key, value)
        ctx = self.context_class(self, info_name=info_name, parent=parent, **extra)
        with ctx.scope(cleanup=False):
            self.parse_args(ctx, args)
        return ctx

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        if not args and self.no_args_is_help and not ctx.resilient_parsing:
            raise NoArgsIsHelpError(ctx)
        parser = self.make_parser(ctx)
        opts, remaining, order = parser.parse_args(args=args)
        for param in iter_params_for_processing(order, self.get_params(ctx)):
            _, remaining = param.handle_parse_result(ctx, opts, remaining)
        ctx.params = {key: Parameter._hide_unset(value) for key, value in ctx.params.items()}
        if remaining and not ctx.allow_extra_args and not ctx.resilient_parsing:
            plural = "s" if len(remaining) != 1 else ""
            ctx.fail(f"Got unexpected extra argument{plural} ({' '.join(remaining)})")
        ctx.args = remaining
        ctx._opt_prefixes.update(parser._opt_prefixes)
        return remaining

    def invoke(self, ctx: Context) -> Any:
        if self.deprecated:
            from .termui import secho
            secho(f"DeprecationWarning: The command {self.name!r} is deprecated.{_format_deprecated_suffix(self.deprecated)}", err=True, fg="red")
        if self.callback is not None:
            return ctx.invoke(self.callback, **ctx.params)
        return None

    def shell_complete(self, ctx: Context, incomplete: str) -> list[Any]:
        from .shell_completion import CompletionItem
        result = []
        if incomplete and not incomplete[0].isalnum():
            for param in self.get_params(ctx):
                if isinstance(param, Option) and not param.hidden:
                    if not param.multiple and ctx.get_parameter_source(param.name) == ParameterSource.COMMANDLINE:
                        continue
                    for name in param.opts + param.secondary_opts:
                        if name.startswith(incomplete):
                            result.append(CompletionItem(name, help=param.help))
        parent = ctx.parent
        while parent is not None:
            if isinstance(parent.command, Group) and parent.command.chain:
                for name in parent.command.list_commands(parent):
                    command = parent.command.get_command(parent, name)
                    if command and not command.hidden and name.startswith(incomplete) and name not in getattr(parent, "_completion_used_commands", parent._protected_args):
                        result.append(CompletionItem(name, help=command.get_short_help_str()))
            parent = parent.parent
        return result

    def main(self, args: Sequence[str] | None = None, prog_name: str | None = None,
             complete_var: str | None = None, standalone_mode: bool = True,
             windows_expand_args: bool = True, **extra: Any) -> Any:
        from .utils import _detect_program_name
        if args is None:
            args = sys.argv[1:]
            if os.name == "nt" and windows_expand_args:
                from .utils import _expand_args
                args = _expand_args(args)
        args = [os.fsdecode(a) if isinstance(a, bytes) else a for a in args]
        if prog_name is None:
            prog_name = _detect_program_name()
        self._main_shell_completion(extra, prog_name, complete_var)
        exit_code = 0
        try:
            with self.make_context(prog_name, args, **extra) as ctx:
                result = self.invoke(ctx)
                if not standalone_mode:
                    return result
                ctx.exit()
        except Exit as exc:
            exit_code = exc.exit_code
            if not standalone_mode:
                return exit_code
        except (EOFError, KeyboardInterrupt) as exc:
            if not standalone_mode:
                echo(file=sys.stderr)
                raise Abort() from exc
            exit_code = 1
            try:
                echo(file=sys.stderr)
                echo("Aborted!", file=sys.stderr)
            except KeyboardInterrupt:
                pass
        except ClickException as exc:
            if not standalone_mode:
                raise
            exit_code = exc.exit_code
            try:
                exc.show()
            except KeyboardInterrupt:
                pass
        except Abort:
            if not standalone_mode:
                raise
            exit_code = 1
            try:
                echo("Aborted!", file=sys.stderr)
            except KeyboardInterrupt:
                pass
        except OSError as exc:
            import errno
            if exc.errno != errno.EPIPE:
                raise
            from .utils import _PacifyFlushWrapper
            sys.stdout = _PacifyFlushWrapper(sys.stdout)
            sys.stderr = _PacifyFlushWrapper(sys.stderr)
            exit_code = 1
        try:
            sys.exit(exit_code)
        except KeyboardInterrupt:
            sys.exit(exit_code)

    def _main_shell_completion(self, ctx_args: MutableMapping[str, Any], prog_name: str, complete_var: str | None = None) -> None:
        complete_var = complete_var or f"_{prog_name.replace('-', '_').replace('.', '_').upper()}_COMPLETE"
        instruction = os.environ.get(complete_var)
        if instruction:
            from .shell_completion import shell_complete
            sys.exit(shell_complete(self, ctx_args, prog_name, complete_var, instruction))

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.main(*args, **kwargs)


class Group(Command):
    allow_extra_args = True
    allow_interspersed_args = False
    command_class = None
    group_class = None

    def __init__(self, name: str | None = None,
                 commands: MutableMapping[str, Command] | Sequence[Command] | None = None,
                 invoke_without_command: bool = False, no_args_is_help: bool | None = None,
                 subcommand_metavar: str | None = None, chain: bool = False,
                 result_callback: Callable[..., Any] | None = None, **kwargs: Any) -> None:
        super().__init__(name, no_args_is_help=not invoke_without_command if no_args_is_help is None else no_args_is_help, **kwargs)
        self.commands = dict(commands) if isinstance(commands, Mapping) else {}
        self.invoke_without_command, self.chain = invoke_without_command, chain
        leading = "COMMAND1" if chain else "COMMAND"
        if invoke_without_command:
            leading = f"[{leading}]"
        self.subcommand_metavar = subcommand_metavar if subcommand_metavar is not None else leading + " [ARGS]..." + (" [COMMAND2 [ARGS]...]..." if chain else "")
        self._result_callback = result_callback
        if commands is not None and not isinstance(commands, Mapping):
            for command in commands:
                self.commands[command.name] = command
        if chain and any(isinstance(p, Argument) and not p.required for p in self.params):
            raise RuntimeError("A group in chain mode cannot have optional arguments.")

    def to_info_dict(self, ctx: Context) -> dict[str, Any]:
        commands = {}
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is not None:
                with cmd.make_context(name, [], parent=ctx, resilient_parsing=True) as subctx:
                    commands[name] = cmd.to_info_dict(subctx)
        return {**super().to_info_dict(ctx), "commands": commands, "chain": self.chain}

    def add_command(self, cmd: Command, name: str | None = None) -> None:
        name = name or cmd.name
        if name is None:
            raise TypeError("Command has no name.")
        _check_nested_chain(self, name, cmd)
        self.commands[name] = cmd

    def command(self, *args: Any, **kwargs: Any):
        from .decorators import command
        if self.command_class is not None:
            kwargs.setdefault("cls", self.command_class)
        def register(f):
            cmd = command(*args, **kwargs)(f)
            self.add_command(cmd)
            return cmd
        if args and callable(args[0]):
            func, args = args[0], args[1:]
            return register(func)
        return register

    def group(self, *args: Any, **kwargs: Any):
        from .decorators import group
        if self.group_class is not None:
            kwargs.setdefault("cls", type(self) if self.group_class is type else self.group_class)
        def register(f):
            cmd = group(*args, **kwargs)(f)
            self.add_command(cmd)
            return cmd
        if args and callable(args[0]):
            func, args = args[0], args[1:]
            return register(func)
        return register

    def result_callback(self, replace: bool = False):
        def decorate(f):
            previous = self._result_callback
            if previous is None or replace:
                self._result_callback = f
            else:
                def chained(value, *args, **kwargs):
                    return f(previous(value, *args, **kwargs), *args, **kwargs)
                self._result_callback = update_wrapper(chained, f)
            return f
        return decorate

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        return self.commands.get(cmd_name)

    def list_commands(self, ctx: Context) -> list[str]:
        return sorted(self.commands)

    def collect_usage_pieces(self, ctx: Context) -> list[str]:
        return super().collect_usage_pieces(ctx) + [self.subcommand_metavar]

    def format_options(self, ctx: Context, formatter: HelpFormatter) -> None:
        super().format_options(ctx, formatter)
        self.format_commands(ctx, formatter)

    def format_commands(self, ctx: Context, formatter: HelpFormatter) -> None:
        visible = [(name, cmd) for name in self.list_commands(ctx) if (cmd := self.get_command(ctx, name)) is not None and not cmd.hidden]
        if visible:
            limit = formatter.width - 6 - max(len(n) for n, _ in visible)
            with formatter.section("Commands"):
                formatter.write_dl([(name, cmd.get_short_help_str(limit)) for name, cmd in visible])

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        rest = super().parse_args(ctx, args)
        ctx._protected_args = rest[:] if self.chain else rest[:1]
        ctx.args = [] if self.chain else rest[1:]
        return ctx.args

    def invoke(self, ctx: Context) -> Any:
        return _invoke_group(self, ctx, super().invoke, _invoke_context)

    def resolve_command(self, ctx: Context, args: list[str]) -> tuple[str | None, Command | None, list[str]]:
        import difflib
        name = args[0]
        command = self.get_command(ctx, name)
        if command is None and ctx.token_normalize_func is not None:
            name = ctx.token_normalize_func(name)
            command = self.get_command(ctx, name)
        if command is None and not ctx.resilient_parsing:
            if _split_opt(name)[0] in ctx._opt_prefixes:
                self.parse_args(ctx, args)
            possible = [n for n in self.list_commands(ctx) if (c := self.get_command(ctx, n)) is not None and not c.hidden]
            raise NoSuchCommand(name, possibilities=difflib.get_close_matches(name, possible), ctx=ctx)
        return (name if command is not None else None), command, args[1:]

    def shell_complete(self, ctx: Context, incomplete: str) -> list[Any]:
        from .shell_completion import CompletionItem
        result = []
        for name in self.list_commands(ctx):
            command = self.get_command(ctx, name)
            if command is not None and not command.hidden and name.startswith(incomplete):
                result.append(CompletionItem(name, help=command.get_short_help_str()))
        return result + super().shell_complete(ctx, incomplete)


def _check_nested_chain(base: Group, name: str, cmd: Command) -> None:
    if base.chain and isinstance(cmd, Group):
        raise RuntimeError(f"It is not possible to add the group {name!r} to another group {base.name!r} that is in chain mode.")


class CommandCollection(Group):
    def __init__(self, name: str | None = None, sources: list[Group] | None = None, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.sources = sources if sources is not None else []

    def add_source(self, group: Group) -> None:
        self.sources.append(group)

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command
        for source in self.sources:
            command = source.get_command(ctx, cmd_name)
            if command is not None:
                _check_nested_chain(self, cmd_name, command)
                return command
        return None

    def list_commands(self, ctx: Context) -> list[str]:
        return sorted(set(super().list_commands(ctx)).union(*(s.list_commands(ctx) for s in self.sources)))


class Parameter(abc.ABC):
    param_type_name = "parameter"

    def __init__(self, param_decls: Sequence[str] | None = None, type: Any = None,
                 required: bool = False, default: Any = UNSET,
                 callback: Callable[[Context, Parameter, Any], Any] | None = None,
                 nargs: int | None = None, multiple: bool = False, metavar: str | None = None,
                 expose_value: bool = True, is_eager: bool = False,
                 envvar: str | Sequence[str] | None = None,
                 shell_complete: Callable[..., list[Any]] | None = None,
                 deprecated: bool | str = False, help: str | None = None) -> None:
        self.name, self.opts, self.secondary_opts = self._parse_decls(param_decls or (), expose_value)
        self.type = types.convert_type(type, None if default is UNSET else default)
        self.required, self.callback = required, callback
        self.nargs = (self.type.arity if self.type.is_composite else 1) if nargs is None else nargs
        self.multiple, self.expose_value = multiple, expose_value
        self.default, self._default_explicit = default, default is not UNSET
        self.is_eager, self.metavar, self.envvar = is_eager, metavar, envvar
        self._custom_shell_complete = shell_complete
        self.deprecated = deprecated
        self.help = inspect.cleandoc(help) if help is not None else None
        if deprecated:
            self.help = " ".join(filter(None, (self.help, _format_deprecated_label(deprecated))))
        if self.type.is_composite and self.nargs != self.type.arity:
            raise ValueError(f"'nargs' must be {self.type.arity} (or None) for type {self.type!r}, but it was {self.nargs}.")
        if deprecated and required:
            raise ValueError(f"The parameter {self.name!r} is deprecated and still required. A deprecated parameter cannot be required.")

    @staticmethod
    def _hide_unset(value: Any) -> Any:
        return None if value is UNSET else value

    def to_info_dict(self) -> dict[str, Any]:
        return {"name": self.name, "param_type_name": self.param_type_name, "opts": self.opts,
                "secondary_opts": self.secondary_opts, "type": self.type.to_info_dict(), "required": self.required,
                "nargs": self.nargs, "multiple": self.multiple, "default": self._hide_unset(self.default),
                "envvar": self.envvar, "help": self.help}

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    @abc.abstractmethod
    def _parse_decls(self, decls: Sequence[str], expose_value: bool):
        raise NotImplementedError

    @property
    def human_readable_name(self) -> str:
        return self.name

    def make_metavar(self, ctx: Context) -> str:
        if self.metavar is not None:
            return self.metavar
        value = self.type.get_metavar(param=self, ctx=ctx) or self.type.name.upper()
        return value + ("..." if self.nargs != 1 else "")

    def get_default(self, ctx: Context, call: bool = True) -> Any:
        value = ctx.lookup_default(self.name, call=False)
        if (value is None and not ctx._default_map_has(self.name)) or value is UNSET:
            value = self.default
        return value() if call and callable(value) else value

    @abc.abstractmethod
    def add_to_parser(self, parser: _OptionParser, ctx: Context) -> None:
        raise NotImplementedError

    def consume_value(self, ctx: Context, opts: Mapping[str, Any]) -> tuple[Any, ParameterSource]:
        if self.name in opts and opts[self.name] is not UNSET:
            return opts[self.name], ParameterSource.COMMANDLINE
        value = self.value_from_envvar(ctx)
        if value is not None:
            return value, ParameterSource.ENVIRONMENT
        value = ctx.lookup_default(self.name)
        if value is not UNSET and (value is not None or ctx._default_map_has(self.name)):
            if isinstance(value, str) and self.nargs != 1:
                value = self.type.split_envvar_value(value)
            return value, ParameterSource.DEFAULT_MAP
        return self.get_default(ctx), ParameterSource.DEFAULT

    def type_cast_value(self, ctx: Context, value: Any) -> Any:
        if value is UNSET:
            return () if self.multiple or self.nargs == -1 else UNSET
        if value is None:
            return () if self.multiple or self.nargs == -1 else None
        multiple = self.multiple
        if not multiple and (self.nargs == 1 or self.type.is_composite):
            return self.type(value, param=self, ctx=ctx)
        def convert(item):
            if self.nargs == 1 or self.type.is_composite:
                return self.type(item, param=self, ctx=ctx)
            if isinstance(item, str):
                raise BadParameter("Value must be an iterable.", ctx, self)
            try:
                parts = tuple(item)
            except TypeError:
                raise BadParameter("Value must be an iterable.", ctx, self) from None
            if self.nargs != -1 and len(parts) != self.nargs:
                raise BadParameter(f"Takes {self.nargs} values but {len(parts)} {'was' if len(parts) == 1 else 'were'} given.", ctx, self)
            return tuple(self.type(x, param=self, ctx=ctx) for x in parts)
        if multiple:
            if isinstance(value, str):
                raise BadParameter("Value must be an iterable.", ctx, self)
            try:
                return tuple(convert(x) for x in value)
            except TypeError:
                raise BadParameter("Value must be an iterable.", ctx, self) from None
        return convert(value)

    def value_is_missing(self, value: Any) -> bool:
        return value is UNSET or ((self.nargs != 1 or self.multiple) and value == ())

    def process_value(self, ctx: Context, value: Any) -> Any:
        if value is UNSET:
            value = () if self.multiple or self.nargs == -1 else UNSET
        else:
            value = self.type_cast_value(ctx, value)
        if self.required and self.value_is_missing(value):
            raise MissingParameter(ctx=ctx, param=self)
        if self.callback is not None:
            missing = [name for name, v in ctx.params.items() if v is UNSET]
            for name in missing:
                ctx.params[name] = None
            try:
                value = self.callback(ctx, self, self._hide_unset(value))
            finally:
                for name in missing:
                    if ctx.params.get(name) is None:
                        ctx.params[name] = UNSET
        return value

    def resolve_envvar_value(self, ctx: Context) -> str | None:
        names = [self.envvar] if isinstance(self.envvar, str) else self.envvar or ()
        return next((value for name in names if (value := os.environ.get(name))), None)

    def value_from_envvar(self, ctx: Context) -> Any:
        value = self.resolve_envvar_value(ctx)
        if value is not None and self.nargs != 1:
            value = self.type.split_envvar_value(value)
        return value

    def handle_parse_result(self, ctx: Context, opts: Mapping[str, Any], args: list[str]) -> tuple[Any, list[str]]:
        old_value = ctx.params.get(self.name, UNSET)
        old_source = ctx.get_parameter_source(self.name)
        old_explicit = ctx._param_default_explicit.get(self.name, False)
        try:
            value, source = self.consume_value(ctx, opts)
            ctx.set_parameter_source(self.name, source)
            if self.deprecated and value is not UNSET and source not in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP):
                from .termui import secho
                secho(f"DeprecationWarning: The {self.param_type_name} {self.human_readable_name!r} is deprecated.{_format_deprecated_suffix(self.deprecated)}", err=True, fg="red")
            try:
                value = self.process_value(ctx, value)
            except Exception:
                if not ctx.resilient_parsing:
                    raise
                value = UNSET
            selected = _select_parameter_value(old_value is UNSET, old_source, source, old_explicit, self._default_explicit)
            if selected and self.expose_value and self.name is not None:
                ctx.params[self.name] = value
                ctx._param_default_explicit[self.name] = self._default_explicit
            elif not selected and old_source is not None:
                ctx.set_parameter_source(self.name, old_source)
        except BadParameter as exc:
            if exc.ctx is None:
                exc.ctx = ctx
            if exc.param is None:
                exc.param = self
            raise
        except UsageError as exc:
            if exc.ctx is None:
                exc.ctx = ctx
            raise
        return value, args

    def get_help_record(self, ctx: Context) -> tuple[str, str] | None:
        return None

    def get_usage_pieces(self, ctx: Context) -> list[str]:
        return []

    def get_error_hint(self, ctx: Context | None) -> str:
        return " / ".join(repr(x) for x in self.opts) or repr(self.human_readable_name)

    def shell_complete(self, ctx: Context, incomplete: str) -> list[Any]:
        from .shell_completion import CompletionItem
        if self._custom_shell_complete is not None:
            return [CompletionItem(v) if isinstance(v, str) else v for v in self._custom_shell_complete(ctx, self, incomplete)]
        return self.type.shell_complete(ctx, self, incomplete)


class Option(Parameter):
    param_type_name = "option"

    def __init__(self, param_decls: Sequence[str] | None = None,
                 show_default: bool | str | None = None, prompt: bool | str = False,
                 confirmation_prompt: bool | str = False, prompt_required: bool = True,
                 hide_input: bool = False, is_flag: bool | None = None, flag_value: Any = UNSET,
                 multiple: bool = False, count: bool = False, allow_from_autoenv: bool = True,
                 type: Any = None, help: str | None = None, hidden: bool = False,
                 show_choices: bool = True, show_envvar: bool = False,
                 deprecated: bool | str = False, **attrs: Any) -> None:
        super().__init__(param_decls, type, multiple=multiple, help=help, deprecated=deprecated, **attrs)
        self.prompt = self.name.replace("_", " ").capitalize() if prompt is True else prompt or None
        self.confirmation_prompt, self.prompt_required, self.hide_input = confirmation_prompt, prompt_required, hide_input
        self.hidden = hidden
        self.is_flag = bool(self.secondary_opts or flag_value is not UNSET) if is_flag is None else is_flag
        if self.prompt and not prompt_required and is_flag is None and flag_value is UNSET:
            self.is_flag = False
        self._flag_needs_value = bool((self.prompt and not prompt_required) or (is_flag is False and (flag_value is not UNSET or self.default is UNSET)))
        self.flag_value, self.count = flag_value, count
        self.allow_from_autoenv, self.show_default = allow_from_autoenv, show_default
        self.show_choices, self.show_envvar = show_choices, show_envvar
        if type is None:
            if self.is_flag:
                self.type = types.BOOL if flag_value is UNSET or isinstance(flag_value, bool) else types.convert_type(None, flag_value)
                if isinstance(self.type, types.StringParamType) and not isinstance(flag_value, str) and flag_value is not None:
                    self.type = types.UNPROCESSED
            elif count:
                self.type = types.IntRange(min=0)
        if count and self.default is UNSET:
            self.default = 0
        self._validate(prompt, deprecated)

    @property
    def is_bool_flag(self) -> bool:
        return self.is_flag and isinstance(self.type, types.BoolParamType)

    @property
    def flag_activation_value(self) -> Any:
        return (True if self.is_flag else None) if self.flag_value is UNSET else self.flag_value

    def _validate(self, prompt: bool | str, deprecated: bool | str) -> None:
        if self.nargs == -1:
            raise TypeError("nargs=-1 is not supported for options.")
        if self.secondary_opts and not self.is_bool_flag:
            raise TypeError("Secondary flag is not valid for non-boolean flag.")
        if self.is_bool_flag and self.hide_input and self.prompt is not None:
            raise TypeError("'prompt' with 'hide_input' is not valid for boolean flag.")
        if self.count and self.multiple:
            raise TypeError("'count' is not valid with 'multiple'.")
        if self.count and self.is_flag:
            raise TypeError("'count' is not valid with 'is_flag'.")
        if deprecated and prompt:
            raise ValueError("`deprecated` options cannot use `prompt`.")

    def _parse_decls(self, decls: Sequence[str], expose_value: bool):
        if isinstance(decls, str):
            decls = [decls]
        opts, secondary, possible = [], [], []
        name = None
        for decl in decls:
            if decl.isidentifier():
                if name is not None:
                    raise TypeError(f"Name {name!r} defined twice")
                name = decl
                continue
            split = ";" if decl.startswith("/") else "/"
            if split in decl:
                first, second = (s.strip() for s in decl.split(split, 1))
                if first == second:
                    raise ValueError(f"Boolean option {decl!r} cannot use the same flag for true/false.")
                if first:
                    opts.append(first)
                    possible.append(_split_opt(first))
                if second:
                    secondary.append(second)
            else:
                opts.append(decl)
                possible.append(_split_opt(decl))
        if name is None and possible:
            candidate = sorted(possible, key=lambda x: -len(x[0]))[0][1]
            name = candidate.replace("-", "_").lower()
            if not name.isidentifier():
                name = None
        if name is None and expose_value:
            raise TypeError(f"Could not determine name for option with declarations {decls!r}")
        if not opts and not secondary:
            raise TypeError(f"No options defined but a name was passed ({name}). Did you mean to declare an argument instead? Did you mean to pass '--{name}'?")
        return name, opts, secondary

    def _resolve_lazy_default(self, value: Any) -> Any:
        if value is UNSET:
            if self.is_flag and self.multiple and not self.required and not self.prompt:
                return ()
            return False if self.is_bool_flag and not self.required else UNSET
        if self.is_flag and not self.is_bool_flag and value is True:
            return self.flag_activation_value
        return value

    def get_default(self, ctx: Context, call: bool = True) -> Any:
        original = super().get_default(ctx, call=False)
        resolved = self._resolve_lazy_default(original)
        return resolved() if resolved is original and call and callable(resolved) else resolved

    def to_info_dict(self) -> dict[str, Any]:
        result = super().to_info_dict()
        result["default"] = self._hide_unset(self._resolve_lazy_default(self.default))
        result.update(prompt=self.prompt, is_flag=self.is_flag, flag_value=self.flag_activation_value,
                      count=self.count, hidden=self.hidden)
        return result

    def add_to_parser(self, parser: _OptionParser, ctx: Context) -> None:
        action = "append" if self.multiple else "count" if self.count else "store"
        if self.is_flag:
            parser.add_option(self, self.opts, self.name, action + "_const" if action != "count" else action,
                              const=self.flag_activation_value)
            if self.secondary_opts:
                parser.add_option(self, self.secondary_opts, self.name, action + "_const", const=False)
        else:
            parser.add_option(self, self.opts, self.name, action, self.nargs)

    def get_error_hint(self, ctx: Context | None) -> str:
        hint = super().get_error_hint(ctx)
        if self.show_envvar:
            envvars = self.envvar
            if not envvars and ctx is not None and self.allow_from_autoenv and ctx.auto_envvar_prefix and self.name:
                envvars = f"{ctx.auto_envvar_prefix}_{self.name.upper()}"
            if envvars:
                values = [envvars] if isinstance(envvars, str) else envvars
                hint += f" (env var: {', '.join(repr(x) for x in values)})"
        return hint

    def get_help_spec(self, ctx: Context) -> str:
        def format_opts(options):
            names = sorted(options, key=lambda x: len(_split_opt(x)[0]))
            value = ", ".join(names)
            if not self.is_flag and not self.count:
                value += " " + self.make_metavar(ctx)
            return value
        result = format_opts(self.opts)
        if self.secondary_opts:
            joiner = "; " if any(x.startswith("/") for x in self.opts + self.secondary_opts) else " / "
            result += joiner + format_opts(self.secondary_opts)
        return result

    def get_help_extra(self, ctx: Context) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if self.show_envvar:
            envvar = self.envvar
            if not envvar and self.allow_from_autoenv and ctx.auto_envvar_prefix and self.name:
                envvar = f"{ctx.auto_envvar_prefix}_{self.name.upper()}"
            if envvar:
                extra["envvars"] = [envvar] if isinstance(envvar, str) else list(envvar)
        show = self.show_default if self.show_default is not None else ctx.show_default
        value = self.get_default(ctx, call=False)
        if isinstance(show, str):
            extra["default"] = f"({show})"
        elif show and value is not UNSET and value is not None:
            if inspect.isfunction(value):
                text = "(dynamic)"
            elif self.is_bool_flag and self.secondary_opts:
                selected = self.opts if value else self.secondary_opts
                text = _split_opt(selected[0])[1]
            elif self.is_bool_flag and value is False:
                text = ""
            elif isinstance(value, (tuple, list)):
                text = ", ".join(str(x) for x in value)
            elif isinstance(value, Enum):
                text = value.name
            elif isinstance(value, str) and value == "":
                text = '""'
            else:
                text = str(value)
            if text:
                extra["default"] = text
        if isinstance(self.type, (types.IntRange, types.FloatRange)) and not (self.count and self.type.min == 0 and self.type.max is None):
            extra["range"] = self.type._describe_range()
        if self.required:
            extra["required"] = "required"
        return extra

    def get_help_record(self, ctx: Context) -> tuple[str, str] | None:
        if self.hidden:
            return None
        text = inspect.cleandoc(self.help).partition("\f")[0] if self.help else ""
        extras = self.get_help_extra(ctx)
        notes = []
        if "envvars" in extras:
            notes.append("env var: " + ", ".join(extras["envvars"]))
        if "default" in extras:
            notes.append("default: " + extras["default"])
        if "range" in extras:
            notes.append(extras["range"])
        if "required" in extras:
            notes.append(extras["required"])
        if notes:
            text = (text + "  " if text else "") + "[" + "; ".join(notes) + "]"
        return self.get_help_spec(ctx), text

    def prompt_for_value(self, ctx: Context) -> Any:
        from .termui import confirm, prompt
        default = self._hide_unset(self.get_default(ctx))
        if self.is_bool_flag:
            return confirm(self.prompt, default=default)
        return prompt(self.prompt, default=default, type=self.type, hide_input=self.hide_input,
                      show_choices=self.show_choices, confirmation_prompt=self.confirmation_prompt,
                      value_proc=lambda value: self.process_value(ctx, value),
                      show_default=True if self.show_default is None else self.show_default)

    def resolve_envvar_value(self, ctx: Context) -> str | None:
        value = super().resolve_envvar_value(ctx)
        if value is None and self.allow_from_autoenv and ctx.auto_envvar_prefix and self.name:
            value = os.environ.get(f"{ctx.auto_envvar_prefix}_{self.name.upper()}") or None
        return value

    def value_from_envvar(self, ctx: Context) -> Any:
        value = self.resolve_envvar_value(ctx)
        if value is None:
            return None
        if self.is_bool_flag and not value.strip():
            return False
        if self.is_flag and not self.is_bool_flag:
            if value == self.flag_activation_value:
                return self.flag_activation_value
            parsed = types.BoolParamType.str_to_bool(value)
            return None if parsed is None else self.flag_activation_value if parsed else False
        if self.multiple or self.nargs != 1:
            split = self.type.split_envvar_value(value)
            return batch(split, self.nargs) if self.multiple and self.nargs != 1 else split
        return value

    def consume_value(self, ctx: Context, opts: Mapping[str, Any]) -> tuple[Any, ParameterSource]:
        value, source = super().consume_value(ctx, opts)
        if value is _flag_needs_value or value is FLAG_NEEDS_VALUE:
            if self.prompt and not ctx.resilient_parsing:
                return self.prompt_for_value(ctx), ParameterSource.PROMPT
            return self.flag_activation_value, ParameterSource.COMMANDLINE
        if self.multiple and source == ParameterSource.COMMANDLINE:
            value = [self.flag_activation_value if x is _flag_needs_value else x for x in value]
        if source in (ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP) and self.prompt and (self.required or self.prompt_required) and not ctx.resilient_parsing:
            return self.prompt_for_value(ctx), ParameterSource.PROMPT
        return value, source

    def process_value(self, ctx: Context, value: Any) -> Any:
        return super().process_value(ctx, value)


class Argument(Parameter):
    param_type_name = "argument"

    def __init__(self, param_decls: Sequence[str], required: bool | None = None,
                 help: str | None = None, **attrs: Any) -> None:
        if "multiple" in attrs:
            raise TypeError("__init__() got an unexpected keyword argument 'multiple'")
        if required is None:
            required = attrs.get("default", UNSET) is UNSET and attrs.get("nargs", 1) > 0
        super().__init__(param_decls, required=required, help=help, **attrs)

    @property
    def human_readable_name(self) -> str:
        return self.metavar or self.name.upper()

    def _parse_decls(self, decls: Sequence[str], expose_value: bool):
        if len(decls) != 1:
            raise TypeError("Arguments take exactly one parameter declaration, got %d." % len(decls))
        return decls[0].replace("-", "_").lower(), list(decls), []

    def make_metavar(self, ctx: Context) -> str:
        if self.metavar is not None:
            return self.metavar
        value = self.type.get_metavar(param=self, ctx=ctx) or self.name.upper()
        if self.deprecated:
            value += "!"
        if not self.required and not value.startswith("["):
            value = f"[{value}]"
        if self.nargs != 1:
            value += "..."
        return value

    def get_usage_pieces(self, ctx: Context) -> list[str]:
        return [self.make_metavar(ctx)]

    def get_help_record(self, ctx: Context) -> tuple[str, str]:
        return self.make_metavar(ctx), self.help or ""

    def get_error_hint(self, ctx: Context | None) -> str:
        return repr(self.make_metavar(ctx))

    def add_to_parser(self, parser: _OptionParser, ctx: Context) -> None:
        parser.add_argument(self, self.name, self.nargs)


class _CommandAlias(type):
    def __instancecheck__(cls, instance):
        return isinstance(instance, cls._target)

    def __subclasscheck__(cls, subclass):
        return issubclass(subclass, cls._target)


class _BaseCommand(Command, metaclass=_CommandAlias):
    _target = Command


class _MultiCommand(Group, metaclass=_CommandAlias):
    _target = Group


def __getattr__(name: str):
    import warnings
    if name not in ("BaseCommand", "MultiCommand"):
        raise AttributeError(name)
    target = _BaseCommand if name == "BaseCommand" else _MultiCommand
    warnings.warn(f"'{name}' is deprecated and will be removed in Click 9.0. Use '{target._target.__name__}' instead.", DeprecationWarning, stacklevel=2)
    return target
