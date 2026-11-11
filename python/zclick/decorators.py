"""Decorators attach Python callbacks to native-backed command definitions."""
from __future__ import annotations

import inspect
from functools import update_wrapper, wraps
from typing import Any, Callable, Concatenate, ParamSpec, TypeVar, overload

from .core import Argument, Command, Context, Group, Option, Parameter
from .globals import get_current_context

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")
FC = TypeVar("FC", bound=Callable[..., Any] | Command)
CmdType = TypeVar("CmdType", bound=Command)
GrpType = TypeVar("GrpType", bound=Group)


def pass_context(f: Callable[Concatenate[Context, P], R]) -> Callable[P, R]:
    @wraps(f)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        return f(get_current_context(), *args, **kwargs)
    return wrapped


def pass_obj(f: Callable[Concatenate[T, P], R]) -> Callable[P, R]:
    @wraps(f)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        return f(get_current_context().obj, *args, **kwargs)
    return wrapped


def make_pass_decorator(object_type: type[T], ensure: bool = False) -> Callable[[Callable[Concatenate[T, P], R]], Callable[P, R]]:
    def decorate(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ctx = get_current_context()
            obj = ctx.ensure_object(object_type) if ensure else ctx.find_object(object_type)
            if obj is None:
                raise RuntimeError(f"Managed to invoke callback without a context object of type {object_type.__name__!r} existing.")
            return ctx.invoke(f, obj, *args, **kwargs)
        return wrapped
    return decorate


def pass_meta_key(key: str, *, doc_description: str | None = None):
    def decorate(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ctx = get_current_context()
            return ctx.invoke(f, ctx.meta[key], *args, **kwargs)
        return wrapped
    decorate.__doc__ = f"Decorator that passes {doc_description or f'the {key!r} key from :attr:`click.Context.meta`'} as the first argument."
    return decorate


@overload
def command(name: Callable[..., Any]) -> Command: ...
@overload
def command(name: str | None = None, cls: type[CmdType] = ..., **attrs: Any) -> Callable[[Callable[..., Any]], CmdType]: ...
@overload
def command(name: str | None = None, cls: None = None, **attrs: Any) -> Callable[[Callable[..., Any]], Command]: ...
def command(name: str | Callable[..., Any] | None = None, cls: type[CmdType] | None = None, **attrs: Any):
    direct = name if callable(name) else None
    if direct is not None:
        name = None
    def decorate(f):
        if isinstance(f, Command):
            raise TypeError("Attempted to convert a callback into a command twice.")
        config = attrs.copy()
        parameters = list(config.pop("params", ()))
        parameters.extend(reversed(getattr(f, "__click_params__", ())))
        if hasattr(f, "__click_params__"):
            del f.__click_params__
        config.setdefault("help", f.__doc__)
        cmd_name = name
        if cmd_name is None:
            cmd_name = f.__name__.lower().replace("_", "-")
            for suffix in ("-command", "-cmd", "-group", "-grp"):
                if cmd_name.endswith(suffix):
                    cmd_name = cmd_name[:-len(suffix)]
                    break
        result = (cls or Command)(name=cmd_name, callback=f, params=parameters, **config)
        result.__doc__ = f.__doc__
        return result
    return decorate(direct) if direct is not None else decorate


@overload
def group(name: Callable[..., Any]) -> Group: ...
@overload
def group(name: str | None = None, cls: type[GrpType] = ..., **attrs: Any) -> Callable[[Callable[..., Any]], GrpType]: ...
@overload
def group(name: str | None = None, cls: None = None, **attrs: Any) -> Callable[[Callable[..., Any]], Group]: ...
def group(name: str | Callable[..., Any] | None = None, cls: type[GrpType] | None = None, **attrs: Any):
    return command(name, cls or Group, **attrs)


def _param_memo(f: FC, param: Parameter) -> None:
    if isinstance(f, Command):
        f.params.append(param)
    else:
        if not hasattr(f, "__click_params__"):
            f.__click_params__ = []
        f.__click_params__.append(param)


def argument(*param_decls: str, cls: type[Argument] | None = None, **attrs: Any) -> Callable[[FC], FC]:
    def decorate(f: FC) -> FC:
        _param_memo(f, (cls or Argument)(param_decls, **attrs))
        return f
    return decorate


def option(*param_decls: str, cls: type[Option] | None = None, **attrs: Any) -> Callable[[FC], FC]:
    def decorate(f: FC) -> FC:
        _param_memo(f, (cls or Option)(param_decls, **attrs))
        return f
    return decorate


def confirmation_option(*param_decls: str, **kwargs: Any) -> Callable[[FC], FC]:
    def confirm(ctx, param, value):
        if not value and not ctx.resilient_parsing:
            ctx.abort()
    kwargs.setdefault("is_flag", True)
    kwargs.setdefault("callback", confirm)
    kwargs.setdefault("expose_value", False)
    kwargs.setdefault("prompt", "Do you want to continue?")
    kwargs.setdefault("help", "Confirm the action without prompting.")
    return option(*(param_decls or ("--yes",)), **kwargs)


def password_option(*param_decls: str, **kwargs: Any) -> Callable[[FC], FC]:
    kwargs.setdefault("prompt", True)
    kwargs.setdefault("confirmation_prompt", True)
    kwargs.setdefault("hide_input", True)
    return option(*(param_decls or ("--password",)), **kwargs)


def version_option(version: str | None = None, *param_decls: str,
                   package_name: str | None = None, prog_name: str | None = None,
                   message: str | None = None, **kwargs: Any) -> Callable[[FC], FC]:
    if package_name is None:
        frame = inspect.currentframe()
        try:
            caller = frame.f_back
            package_name = caller.f_globals.get("__package__") or caller.f_globals.get("__name__", "")
            if package_name == "__main__":
                package_name = None
            elif package_name:
                package_name = package_name.split(".", 1)[0]
        finally:
            del frame
    def show(ctx):
        resolved = version
        if resolved is None and package_name:
            import importlib.metadata
            try:
                resolved = importlib.metadata.version(package_name)
            except importlib.metadata.PackageNotFoundError:
                candidates = importlib.metadata.packages_distributions().get(package_name, ())
                if len(candidates) == 1:
                    resolved = importlib.metadata.version(candidates[0])
                elif len(candidates) > 1:
                    raise RuntimeError(f"{package_name!r} refers to multiple installed distributions: {', '.join(candidates)}. Pass 'package_name' to select one.") from None
                else:
                    raise RuntimeError(f"{package_name!r} is not installed. Try passing 'package_name' instead.") from None
        if resolved is None:
            raise RuntimeError("Could not determine the version for None automatically.")
        return (message or "%(prog)s, version %(version)s") % {
            "prog": prog_name or ctx.find_root().info_name,
            "package": package_name, "version": resolved}
    return custom_version_option(show, *param_decls, **kwargs)


def custom_version_option(callback: Callable[[Context], str], *param_decls: str, **kwargs: Any) -> Callable[[FC], FC]:
    def display(ctx, param, value):
        if value and not ctx.resilient_parsing:
            from .utils import echo
            echo(callback(ctx), color=ctx.color)
            ctx.exit()
    kwargs.setdefault("is_flag", True)
    kwargs.setdefault("is_eager", True)
    kwargs.setdefault("expose_value", False)
    kwargs.setdefault("callback", display)
    kwargs.setdefault("help", "Show the version and exit.")
    return option(*(param_decls or ("--version",)), **kwargs)


def help_option(*param_decls: str, **kwargs: Any) -> Callable[[FC], FC]:
    def display(ctx, param, value):
        if value and not ctx.resilient_parsing:
            from .utils import echo
            echo(ctx.get_help(), color=ctx.color)
            ctx.exit()
    kwargs.setdefault("is_flag", True)
    kwargs.setdefault("is_eager", True)
    kwargs.setdefault("expose_value", False)
    kwargs.setdefault("callback", display)
    kwargs.setdefault("help", "Show this message and exit.")
    return option(*(param_decls or ("--help",)), **kwargs)
