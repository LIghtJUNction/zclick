# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import typing as t
import collections.abc as cabc
from contextlib import contextmanager
from gettext import gettext as _
from ._compat import term_len
from .parser import _split_opt
FORCED_WIDTH: int | None

def measure_table(rows: cabc.Iterable[tuple[str, str]]) -> tuple[int, ...]:
    ...

def iter_rows(rows: cabc.Iterable[tuple[str, str]], col_count: int) -> cabc.Iterator[tuple[str, ...]]:
    ...

def wrap_text(text: str, width: int=78, initial_indent: str='', subsequent_indent: str='', preserve_paragraphs: bool=False) -> str:
    ...

class HelpFormatter:
    indent_increment: int
    width: int
    current_indent: int
    buffer: list[str]

    def __init__(self, indent_increment: int=2, width: int | None=None, max_width: int | None=None) -> None:
        ...

    def write(self, string: str) -> None:
        ...

    def indent(self) -> None:
        ...

    def dedent(self) -> None:
        ...

    def write_usage(self, prog: str, args: str='', prefix: str | None=None) -> None:
        ...

    def write_heading(self, heading: str) -> None:
        ...

    def write_paragraph(self) -> None:
        ...

    def write_text(self, text: str) -> None:
        ...

    def write_dl(self, rows: cabc.Iterable[tuple[str, str]], col_max: int=30, col_spacing: int=2) -> None:
        ...

    @contextmanager
    def section(self, name: str) -> cabc.Generator[None]:
        ...

    @contextmanager
    def indentation(self) -> cabc.Generator[None]:
        ...

    def getvalue(self) -> str:
        ...

def join_options(options: cabc.Iterable[str]) -> tuple[str, bool]:
    ...
