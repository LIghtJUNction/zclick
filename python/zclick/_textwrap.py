"""Compatibility hooks for extensions using Click's text wrapper."""
from __future__ import annotations
import contextlib
import textwrap
import typing as t
from ._compat import _ansi_re


def _truncate_visible(text: str, length: int) -> str:
    from ._native import truncate_visible
    return truncate_visible(text, length)


class TextWrapper(textwrap.TextWrapper):
    @contextlib.contextmanager
    def extra_indent(self, initial_indent: str, subsequent_indent: str | None = None) -> t.Iterator[None]:
        old = self.initial_indent, self.subsequent_indent
        self.initial_indent += initial_indent
        self.subsequent_indent += initial_indent if subsequent_indent is None else subsequent_indent
        try:
            yield
        finally:
            self.initial_indent, self.subsequent_indent = old

    def indent_only(self, text: str) -> str:
        return "\n".join((self.initial_indent if i == 0 else self.subsequent_indent) + line for i, line in enumerate(text.splitlines()))

    def fill(self, text: str) -> str:
        from .formatting import wrap_text
        return wrap_text(text, self.width, self.initial_indent, self.subsequent_indent)
