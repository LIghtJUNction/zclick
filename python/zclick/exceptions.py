"""Python exception objects keep user tracebacks and subclass behavior intact."""
from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from .core import Context, Parameter


def _join_param_hints(hints: Sequence[str] | str) -> str:
    return hints if isinstance(hints, str) else " / ".join(repr(x) for x in hints)


class ClickException(Exception):
    exit_code = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
        from .globals import resolve_color_default
        self.show_color = resolve_color_default()

    def format_message(self) -> str:
        return self.message

    def __str__(self) -> str:
        return self.message

    def show(self, file: TextIO | None = None) -> None:
        from .utils import echo
        echo(f"Error: {self.format_message()}", file=file or sys.stderr, color=self.show_color)


class UsageError(ClickException):
    exit_code = 2

    def __init__(self, message: str, ctx: Context | None = None) -> None:
        super().__init__(message)
        self.ctx = ctx
        self.cmd = ctx.command if ctx is not None else None

    def show(self, file: TextIO | None = None) -> None:
        from .utils import echo
        file = file or sys.stderr
        if self.ctx is not None:
            echo(self.ctx.get_usage(), file=file, color=self.ctx.color)
            names = self.ctx.command.get_help_option_names(self.ctx)
            if names and self.ctx.command.get_help_option(self.ctx) is not None:
                echo(f"Try '{self.ctx.command_path} {max(names, key=len)}' for help.", file=file, color=self.ctx.color)
            echo(file=file)
        super().show(file)


class BadParameter(UsageError):
    def __init__(self, message: str, ctx: Context | None = None,
                 param: Parameter | None = None, param_hint: Sequence[str] | str | None = None) -> None:
        super().__init__(message, ctx)
        self.param = param
        self.param_hint = param_hint

    def format_message(self) -> str:
        hint = self.param_hint
        if hint is None and self.param is not None:
            hint = self.param.get_error_hint(self.ctx)
        return f"Invalid value for {_join_param_hints(hint)}: {self.message}" if hint else f"Invalid value: {self.message}"


class MissingParameter(BadParameter):
    def __init__(self, message: str | None = None, ctx: Context | None = None,
                 param: Parameter | None = None, param_hint: Sequence[str] | str | None = None,
                 param_type: str | None = None) -> None:
        super().__init__(message or "", ctx, param, param_hint)
        self.param_type = param_type

    def format_message(self) -> str:
        hint = self.param_hint
        if hint is None and self.param is not None:
            hint = self.param.get_error_hint(self.ctx)
        kind = self.param_type or (self.param.param_type_name if self.param is not None else "parameter")
        extra = self.message
        if not extra and self.param is not None:
            extra = self.param.type.get_missing_message(self.param, self.ctx) or ""
        return f"Missing {kind}{' ' + _join_param_hints(hint) if hint else ''}.{(' ' + extra) if extra else ''}"

    def __str__(self) -> str:
        return f"Missing parameter: {self.param.name if self.param is not None else self.param_hint}"


class NoSuchOption(UsageError):
    def __init__(self, option_name: str, message: str | None = None,
                 possibilities: Iterable[str] | None = None, ctx: Context | None = None) -> None:
        super().__init__(message or f"No such option {option_name!r}.", ctx)
        self.option_name = option_name
        self.possibilities = list(possibilities or ())

    def format_message(self) -> str:
        return _suggest(self.message, self.possibilities)


class NoSuchCommand(UsageError):
    def __init__(self, command_name: str, message: str | None = None,
                 possibilities: Iterable[str] | None = None, ctx: Context | None = None) -> None:
        super().__init__(message or f"No such command {command_name!r}.", ctx)
        self.command_name = command_name
        self.possibilities = list(possibilities or ())

    def format_message(self) -> str:
        return _suggest(self.message, self.possibilities)


def _suggest(message: str, possibilities: Sequence[str]) -> str:
    if len(possibilities) == 1:
        return f"{message} Did you mean {possibilities[0]!r}?"
    if possibilities:
        return f"{message} (Did you mean one of: {', '.join(repr(x) for x in sorted(possibilities))}?)"
    return message


class BadOptionUsage(UsageError):
    def __init__(self, option_name: str, message: str, ctx: Context | None = None) -> None:
        super().__init__(message, ctx)
        self.option_name = option_name


class BadArgumentUsage(UsageError):
    pass


class NoArgsIsHelpError(UsageError):
    def __init__(self, ctx: Context) -> None:
        super().__init__(ctx.get_help(), ctx)

    def show(self, file: TextIO | None = None) -> None:
        from .utils import echo
        echo(self.message, file=file or sys.stderr, color=self.ctx.color)


class FileError(ClickException):
    def __init__(self, filename: str, hint: str | None = None) -> None:
        from .utils import format_filename
        self.ui_filename = format_filename(filename)
        self.filename = filename
        super().__init__(hint or "unknown error")

    def format_message(self) -> str:
        return f"Could not open file {self.ui_filename!r}: {self.message}"


class Abort(RuntimeError):
    pass


class Exit(RuntimeError):
    __slots__ = ("exit_code",)

    def __init__(self, code: int = 0) -> None:
        self.exit_code = code
