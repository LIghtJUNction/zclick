# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import inspect
import typing as t
from functools import update_wrapper
from gettext import gettext as _
from .core import Argument
from .core import Command
from .core import Context
from .core import Group
from .core import Option
from .core import Parameter
from .globals import get_current_context
from .utils import echo
import typing_extensions as te
P = te.ParamSpec('P')
R = t.TypeVar('R')
T = t.TypeVar('T')
_AnyCallable = t.Callable[..., t.Any]
FC = t.TypeVar('FC', bound='_AnyCallable | Command')

def pass_context(f: t.Callable[te.Concatenate[Context, P], R]) -> t.Callable[P, R]:
    ...

def pass_obj(f: t.Callable[te.Concatenate[T, P], R]) -> t.Callable[P, R]:
    ...

def make_pass_decorator(object_type: builtins.type[T], ensure: bool=False) -> t.Callable[[t.Callable[te.Concatenate[T, P], R]], t.Callable[P, R]]:
    ...

def pass_meta_key(key: str, *, doc_description: str | None=None) -> t.Callable[[t.Callable[te.Concatenate[T, P], R]], t.Callable[P, R]]:
    ...
CmdType = t.TypeVar('CmdType', bound=Command)

@t.overload
def command(name: _AnyCallable) -> Command:
    ...

@t.overload
def command(name: str | None, cls: builtins.type[CmdType], **attrs: t.Any) -> t.Callable[[_AnyCallable], CmdType]:
    ...

@t.overload
def command(name: None=None, *, cls: builtins.type[CmdType], **attrs: t.Any) -> t.Callable[[_AnyCallable], CmdType]:
    ...

@t.overload
def command(name: str | None=..., cls: None=None, **attrs: t.Any) -> t.Callable[[_AnyCallable], Command]:
    ...
GrpType = t.TypeVar('GrpType', bound=Group)

@t.overload
def group(name: _AnyCallable) -> Group:
    ...

@t.overload
def group(name: str | None, cls: builtins.type[GrpType], **attrs: t.Any) -> t.Callable[[_AnyCallable], GrpType]:
    ...

@t.overload
def group(name: None=None, *, cls: builtins.type[GrpType], **attrs: t.Any) -> t.Callable[[_AnyCallable], GrpType]:
    ...

@t.overload
def group(name: str | None=..., cls: None=None, **attrs: t.Any) -> t.Callable[[_AnyCallable], Group]:
    ...

def _param_memo(f: t.Callable[..., t.Any], param: Parameter) -> None:
    ...

def argument(*param_decls: str, cls: builtins.type[Argument] | None=None, **attrs: t.Any) -> t.Callable[[FC], FC]:
    ...

def option(*param_decls: str, cls: builtins.type[Option] | None=None, **attrs: t.Any) -> t.Callable[[FC], FC]:
    ...

def confirmation_option(*param_decls: str, **kwargs: t.Any) -> t.Callable[[FC], FC]:
    ...

def password_option(*param_decls: str, **kwargs: t.Any) -> t.Callable[[FC], FC]:
    ...

def version_option(version: str | None=None, *param_decls: str, package_name: str | None=None, prog_name: str | None=None, message: str | None=None, **kwargs: t.Any) -> t.Callable[[FC], FC]:
    ...

def custom_version_option(callback: t.Callable[[Context], str], *param_decls: str, **kwargs: t.Any) -> t.Callable[[FC], FC]:
    ...

def help_option(*param_decls: str, **kwargs: t.Any) -> t.Callable[[FC], FC]:
    ...
