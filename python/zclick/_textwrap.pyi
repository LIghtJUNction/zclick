# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import typing as t
import collections.abc as cabc
import textwrap
from contextlib import contextmanager
from ._compat import _ansi_re
from ._compat import term_len

def _truncate_visible(text: str, n: int) -> str:
    ...

class TextWrapper(textwrap.TextWrapper):

    def _handle_long_word(self, reversed_chunks: list[str], cur_line: list[str], cur_len: int, width: int) -> None:
        ...

    def _wrap_chunks(self, chunks: list[str]) -> list[str]:
        ...

    @contextmanager
    def extra_indent(self, indent: str) -> cabc.Iterator[None]:
        ...

    def indent_only(self, text: str) -> str:
        ...
