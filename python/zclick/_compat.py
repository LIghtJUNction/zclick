"""Standard-stream adaptation without taking ownership of caller streams."""
from __future__ import annotations

import codecs
import io
import os
import re
import sys
import typing as t

from . import _native

WIN = sys.platform.startswith("win")
CYGWIN = sys.platform.startswith("cygwin")
_ansi_re = re.compile(r"\x1b\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]")
_native_strip_ansi = _native.strip_ansi
_native_text_width = _native.text_width


def strip_ansi(value: str) -> str:
    native = _native.strip_ansi
    if native is _native_strip_ansi and type(value) is str and "\x1b" not in value:
        return value
    return native(value)


def term_len(value: str) -> int:
    native = _native.text_width
    if native is _native_text_width and type(value) is str and "\x1b" not in value:
        return len(value)
    return native(value)


def isatty(stream: t.Any) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, OSError, ValueError):
        return False


def _is_jupyter_kernel_output(stream: t.Any) -> bool:
    return stream.__class__.__module__.startswith("ipykernel.")


def should_strip_ansi(stream: t.Any = None, color: bool | None = None) -> bool:
    if color is not None:
        return not color
    if stream is None:
        stream = sys.stdin
    elif hasattr(stream, "color"):
        return False
    return not (isatty(stream) or _is_jupyter_kernel_output(stream))


def is_ascii_encoding(encoding: str) -> bool:
    try:
        return codecs.lookup(encoding).name == "ascii"
    except LookupError:
        return False


def get_best_encoding(stream: t.Any) -> str:
    encoding = getattr(stream, "encoding", None) or sys.getdefaultencoding()
    return "utf-8" if is_ascii_encoding(encoding) else encoding


class _NonClosingTextIOWrapper(io.TextIOWrapper):
    def __del__(self) -> None:
        try:
            self.detach()
        except (ValueError, OSError):
            pass


def _find_binary_reader(stream: t.Any) -> t.Any:
    if stream is None:
        return None
    try:
        if isinstance(stream.read(0), bytes):
            return stream
    except (AttributeError, OSError, ValueError):
        pass
    return getattr(stream, "buffer", None)


def _find_binary_writer(stream: t.Any) -> t.Any:
    if stream is None:
        return None
    if isinstance(stream, (io.RawIOBase, io.BufferedIOBase)):
        return stream
    return getattr(stream, "buffer", None)


def _binary(name: str) -> t.Any:
    stream = getattr(sys, name)
    result = (_find_binary_reader if name == "stdin" else _find_binary_writer)(stream)
    if result is None:
        raise RuntimeError(f"{name} is not a binary stream")
    return result


def get_binary_stdin() -> t.Any:
    return _binary("stdin")


def get_binary_stdout() -> t.Any:
    return _binary("stdout")


def get_binary_stderr() -> t.Any:
    return _binary("stderr")


def _text(name: str, encoding: str | None, errors: str | None) -> t.Any:
    stream = getattr(sys, name)
    if stream is None:
        return None
    if WIN:
        from ._winconsole import _get_windows_console_stream
        console = _get_windows_console_stream(stream, encoding, errors)
        if console is not None:
            return console
    compatible = (encoding is None or getattr(stream, "encoding", None) == encoding) and (errors is None or getattr(stream, "errors", None) == errors)
    if compatible and not is_ascii_encoding(getattr(stream, "encoding", None) or "utf-8"):
        return stream
    binary = (_find_binary_reader if name == "stdin" else _find_binary_writer)(stream)
    if binary is None:
        return stream
    return _NonClosingTextIOWrapper(binary, encoding=encoding or get_best_encoding(stream), errors=errors or "replace", line_buffering=True)


def get_text_stdin(encoding: str | None = None, errors: str | None = None) -> t.Any:
    return _text("stdin", encoding, errors)


def get_text_stdout(encoding: str | None = None, errors: str | None = None) -> t.Any:
    return _text("stdout", encoding, errors)


def get_text_stderr(encoding: str | None = None, errors: str | None = None) -> t.Any:
    return _text("stderr", encoding, errors)


def open_stream(filename: t.Any, mode: str = "r", encoding: str | None = None, errors: str | None = "strict", atomic: bool = False) -> tuple[t.Any, bool]:
    from .utils import _open_stream
    return _open_stream(filename, mode, encoding, errors, atomic)


_default_text_stdin = get_text_stdin
_default_text_stdout = get_text_stdout
_default_text_stderr = get_text_stderr
binary_streams = {"stdin": get_binary_stdin, "stdout": get_binary_stdout, "stderr": get_binary_stderr}
text_streams = {"stdin": get_text_stdin, "stdout": get_text_stdout, "stderr": get_text_stderr}
