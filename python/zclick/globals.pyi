# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import typing as t
from threading import local
from .core import Context
_local: local

@t.overload
def get_current_context(silent: t.Literal[False]=False) -> Context:
    ...

@t.overload
def get_current_context(silent: bool=...) -> Context | None:
    ...

def push_context(ctx: Context) -> None:
    ...

def pop_context() -> None:
    ...

def resolve_color_default(color: bool | None=None) -> bool | None:
    ...
