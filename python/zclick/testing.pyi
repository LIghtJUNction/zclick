# Type declarations for Click 8.5.1, extracted without implementation bodies.
from __future__ import annotations
import builtins
import collections.abc as cabc
import contextlib
import io
import os
import pdb
import shlex
import sys
import tempfile
import typing as t
from types import TracebackType
from . import _compat
from . import formatting
from . import termui
from . import utils
from ._compat import _find_binary_reader
from _typeshed import ReadableBuffer
from .core import Command
ExceptionInfo: t.TypeAlias = tuple[builtins.type[BaseException], BaseException, TracebackType]

class EchoingStdin:
    _input: t.BinaryIO
    _output: t.BinaryIO
    _paused: bool

    def __init__(self, input: t.BinaryIO, output: t.BinaryIO) -> None:
        ...

    def __getattr__(self, x: str) -> t.Any:
        ...

    def _echo(self, rv: bytes) -> bytes:
        ...

    def read(self, n: int=-1) -> bytes:
        ...

    def read1(self, n: int=-1) -> bytes:
        ...

    def readline(self, n: int=-1) -> bytes:
        ...

    def readlines(self) -> list[bytes]:
        ...

    def __iter__(self) -> cabc.Iterator[bytes]:
        ...

    def __repr__(self) -> str:
        ...

@contextlib.contextmanager
def _pause_echo(stream: EchoingStdin | None) -> cabc.Generator[None]:
    ...

class _FDCapture:
    _targetfd: int
    saved_fd: int
    _tmpfile: t.BinaryIO | None

    def __init__(self, targetfd: int) -> None:
        ...

    def start(self) -> None:
        ...

    def stop(self) -> bytes:
        ...

class BytesIOCopy(io.BytesIO):
    copy_to: io.BytesIO

    def __init__(self, copy_to: io.BytesIO) -> None:
        ...

    def flush(self) -> None:
        ...

    def write(self, b: ReadableBuffer) -> int:
        ...

class StreamMixer:
    output: io.BytesIO
    stdout: BytesIOCopy
    stderr: BytesIOCopy

    def __init__(self) -> None:
        ...

class _NamedTextIOWrapper(io.TextIOWrapper):
    _name: str
    _mode: str
    _original_fd: int

    def __init__(self, buffer: t.BinaryIO, name: str, mode: str, **kwargs: t.Any) -> None:
        ...

    def close(self) -> None:
        ...

    def fileno(self) -> int:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def mode(self) -> str:
        ...

def make_input_stream(input: str | bytes | t.IO[t.Any] | None, charset: str) -> t.BinaryIO:
    ...

class Result:
    runner: CliRunner
    stdout_bytes: bytes
    stderr_bytes: bytes
    output_bytes: bytes
    return_value: t.Any
    exit_code: int
    exception: BaseException | None
    exc_info: ExceptionInfo | None

    def __init__(self, runner: CliRunner, stdout_bytes: bytes, stderr_bytes: bytes, output_bytes: bytes, return_value: t.Any, exit_code: int, exception: BaseException | None, exc_info: ExceptionInfo | None=None) -> None:
        ...

    @property
    def output(self) -> str:
        ...

    @property
    def stdout(self) -> str:
        ...

    @property
    def stderr(self) -> str:
        ...

    def __repr__(self) -> str:
        ...

class CliRunner:
    charset: str
    env: cabc.Mapping[str, str | None]
    echo_stdin: bool
    catch_exceptions: bool
    capture: CaptureMode

    def __init__(self, charset: str='utf-8', env: cabc.Mapping[str, str | None] | None=None, echo_stdin: bool=False, catch_exceptions: bool=True, capture: CaptureMode='sys') -> None:
        ...

    def get_default_prog_name(self, cli: Command) -> str:
        ...

    def make_env(self, overrides: cabc.Mapping[str, str | None] | None=None) -> cabc.Mapping[str, str | None]:
        ...

    @contextlib.contextmanager
    def isolation(self, input: str | bytes | t.IO[t.Any] | None=None, env: cabc.Mapping[str, str | None] | None=None, color: bool=False) -> cabc.Generator[tuple[io.BytesIO, io.BytesIO, io.BytesIO]]:
        ...

    def invoke(self, cli: Command, args: str | cabc.Sequence[str] | None=None, input: str | bytes | t.IO[t.Any] | None=None, env: cabc.Mapping[str, str | None] | None=None, catch_exceptions: bool | None=None, color: bool=False, **extra: t.Any) -> Result:
        ...

    @contextlib.contextmanager
    def isolated_filesystem(self, temp_dir: str | os.PathLike[str] | None=None) -> cabc.Generator[str]:
        ...
