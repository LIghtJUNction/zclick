"""Mutable help document builder using the Rust text layout engine."""
from __future__ import annotations

import contextlib
import typing as t

from ._compat import term_len

FORCED_WIDTH: int | None = None


def measure_table(rows: t.Iterable[tuple[str, str]]) -> tuple[int, ...]:
    widths: list[int] = []
    for row in rows:
        for index, value in enumerate(row):
            if len(widths) <= index:
                widths.append(0)
            widths[index] = max(widths[index], term_len(value))
    return tuple(widths)


def iter_rows(rows: t.Iterable[tuple[str, str]], col_count: int) -> t.Iterator[tuple[str, ...]]:
    for row in rows:
        yield tuple(row) + ("",) * max(0, col_count - len(row))


def wrap_text(text: str, width: int = 78, initial_indent: str = "", subsequent_indent: str = "", preserve_paragraphs: bool = False) -> str:
    from ._native import wrap_text as native
    return native(text, width, initial_indent, subsequent_indent, bool(preserve_paragraphs))


def join_options(options: t.Iterable[str]) -> tuple[str, bool]:
    from ._native import join_options as native
    return native(list(options))


class HelpFormatter:
    def __init__(self, indent_increment: int = 2, width: int | None = None, max_width: int | None = None) -> None:
        import shutil
        self.indent_increment = indent_increment
        self.width = width if width is not None else FORCED_WIDTH if FORCED_WIDTH is not None else max(50, min(shutil.get_terminal_size().columns, max_width or 80) - 2)
        self.current_indent = 0
        self.buffer: list[str] = []

    def write(self, string: str) -> None:
        self.buffer.append(string)

    def indent(self) -> None:
        self.current_indent += self.indent_increment

    def dedent(self) -> None:
        self.current_indent -= self.indent_increment

    def write_usage(self, prog: str, args: str = "", prefix: str | None = None) -> None:
        prefix = "Usage: " if prefix is None else prefix
        lead = prefix + prog
        if not args:
            self.write(lead + "\n")
            return
        lead += " "
        if self.width - term_len(lead) >= 20:
            self.write(wrap_text(args, self.width, lead, " " * term_len(lead)) + "\n")
        else:
            self.write(lead + "\n")
            indent = " " * (term_len(prefix) + 4)
            self.write(wrap_text(args, self.width, indent, indent) + "\n")

    def write_heading(self, heading: str) -> None:
        self.write(" " * self.current_indent + heading + ":\n")

    def write_paragraph(self) -> None:
        if self.buffer:
            self.write("\n")

    def write_text(self, text: str) -> None:
        indent = " " * self.current_indent
        self.write(wrap_text(text, self.width, indent, indent, True) + "\n")

    def write_dl(self, rows: t.Iterable[tuple[str, str]], col_max: int = 30, col_spacing: int = 2) -> None:
        rows = list(rows)
        if not rows:
            return
        widths = measure_table(rows)
        if len(widths) != 2:
            raise TypeError("Expected two columns for definition list")
        first_width = min(widths[0], col_max) + col_spacing
        indent = " " * self.current_indent
        description_indent = " " * (self.current_indent + first_width)
        for first, second in rows:
            self.write(indent + first)
            if not second:
                self.write("\n")
                continue
            if term_len(first) <= first_width - col_spacing:
                self.write(" " * (first_width - term_len(first)))
            else:
                self.write("\n" + description_indent)
            wrapped = wrap_text(second, max(self.width - self.current_indent - first_width, 10), preserve_paragraphs=True)
            lines = wrapped.splitlines()
            self.write(("\n" + description_indent).join(lines) + "\n")

    @contextlib.contextmanager
    def section(self, name: str) -> t.Iterator[None]:
        self.write_paragraph()
        self.write_heading(name)
        with self.indentation():
            yield

    @contextlib.contextmanager
    def indentation(self) -> t.Iterator[None]:
        self.indent()
        try:
            yield
        finally:
            self.dedent()

    def getvalue(self) -> str:
        return "".join(self.buffer)
