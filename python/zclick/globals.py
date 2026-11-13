"""Invocation-local context stack. Each thread owns its own stack."""
from __future__ import annotations

try:
    # threading.local is this same built-in class on CPython and PyPy. Avoid
    # importing the thread-management module just to allocate local storage.
    from _thread import _local as local
except ImportError:
    # Preserve the interpreter's standard-library fallback where needed.
    from threading import local
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Context

_local = local()


def get_current_context(silent: bool = False) -> Context | None:
    stack = getattr(_local, "stack", ())
    if stack:
        return stack[-1]
    if silent:
        return None
    raise RuntimeError("There is no active click context.")


def push_context(ctx: Context) -> None:
    try:
        stack = _local.stack
    except AttributeError:
        stack = _local.stack = []
    stack.append(ctx)


def pop_context() -> None:
    _local.stack.pop()


def resolve_color_default(color: bool | None = None) -> bool | None:
    if color is not None:
        return color
    ctx = get_current_context(silent=True)
    return ctx.color if ctx is not None else None
