"""In-process CLI testing.

Isolation replaces process-wide streams, environment variables, and terminal
hooks. Like Click's runner, it is not safe for concurrent invocations in threads;
use separate processes when running CLI tests in parallel.
"""
from __future__ import annotations

import contextlib
import io
import os
import pdb
import shlex
import shutil
import sys
import tempfile
import typing as t
import warnings


class BytesIOCopy(io.BytesIO):
    def __init__(self, copy_to: io.BytesIO) -> None:
        super().__init__()
        self.copy_to = copy_to

    def write(self, b: t.Any) -> int:
        self.copy_to.write(b)
        return super().write(b)

    def flush(self) -> None:
        self.copy_to.flush()
        super().flush()


class StreamMixer:
    def __init__(self) -> None:
        self.output = io.BytesIO()
        self.stdout = BytesIOCopy(self.output)
        self.stderr = BytesIOCopy(self.output)


class _NamedTextIOWrapper(io.TextIOWrapper):
    def __init__(self, buffer: t.Any, name: str, mode: str, **kwargs: t.Any) -> None:
        self._name, self._mode = name, mode
        self._fd: int | None = kwargs.pop("fd", None)
        super().__init__(buffer, **kwargs)

    @property
    def name(self) -> str:
        return self._name

    @property
    def mode(self) -> str:
        return self._mode

    def close(self) -> None:
        try:
            self.flush()
        except (ValueError, OSError):
            pass

    def __del__(self) -> None:
        try:
            self.detach()
        except (ValueError, OSError):
            pass

    def fileno(self) -> int:
        if self._fd is not None:
            return self._fd
        return super().fileno()


class EchoingStdin:
    def __init__(self, input: t.BinaryIO, output: t.BinaryIO) -> None:
        self._input, self._output = input, output
        self._paused = False

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self._input, name)

    def _read(self, method: str, *args: t.Any) -> bytes:
        value = getattr(self._input, method)(*args)
        if not self._paused:
            self._output.write(value)
        return value

    def read(self, n: int = -1) -> bytes:
        return self._read("read", n)

    def read1(self, n: int = -1) -> bytes:
        return self._read("read", 1 if n != 0 else 0)

    def readline(self, n: int = -1) -> bytes:
        return self._read("readline", n)

    def readlines(self) -> list[bytes]:
        return list(iter(self))

    def __iter__(self) -> t.Iterator[bytes]:
        while line := self.readline():
            yield line


def make_input_stream(input: t.Any, charset: str) -> t.BinaryIO:
    if input is None:
        return io.BytesIO()
    if isinstance(input, str):
        return io.BytesIO(input.encode(charset))
    if isinstance(input, bytes):
        return io.BytesIO(input)
    from ._compat import _find_binary_reader
    binary = _find_binary_reader(input)
    if binary is None:
        raise TypeError("Could not find binary reader for input stream.")
    return binary


class Result:
    def __init__(self, runner: CliRunner, stdout_bytes: bytes, stderr_bytes: bytes, output_bytes: bytes, return_value: t.Any, exit_code: int, exception: BaseException | None, exc_info: t.Any = None) -> None:
        self.runner, self.stdout_bytes, self.stderr_bytes, self.output_bytes = runner, stdout_bytes, stderr_bytes, output_bytes
        self.return_value, self.exit_code, self.exception, self.exc_info = return_value, exit_code, exception, exc_info

    def _decode(self, value: bytes) -> str:
        return value.decode(self.runner.charset, "replace").replace("\r\n", "\n")

    @property
    def output(self) -> str:
        return self._decode(self.output_bytes)

    @property
    def stdout(self) -> str:
        return self._decode(self.stdout_bytes)

    @property
    def stderr(self) -> str:
        return self._decode(self.stderr_bytes)

    def __repr__(self) -> str:
        return f"<Result {self.exception!r}>" if self.exception else "<Result okay>"


class CliRunner:
    def __init__(self, charset: str = "utf-8", env: t.Mapping[str, str | None] | None = None, echo_stdin: bool = False, catch_exceptions: bool = True, capture: t.Literal["sys", "fd"] = "sys") -> None:
        if capture not in ("sys", "fd"):
            raise ValueError(f"Unknown capture mode: {capture!r}")
        if capture == "fd" and sys.platform == "win32":
            raise ValueError("fd capture is not supported on Windows")
        self.charset, self.env, self.echo_stdin, self.catch_exceptions, self.capture = charset, env or {}, echo_stdin, catch_exceptions, capture

    def get_default_prog_name(self, cli: t.Any) -> str:
        return cli.name or "root"

    def make_env(self, overrides: t.Mapping[str, str | None] | None = None) -> dict[str, str | None]:
        return {**self.env, **(overrides or {})}

    @contextlib.contextmanager
    def isolation(self, input: t.Any = None, env: t.Mapping[str, str | None] | None = None, color: bool = False) -> t.Iterator[tuple[io.BytesIO, io.BytesIO, io.BytesIO]]:
        from . import _compat, formatting, termui
        mixer = StreamMixer()
        saved_streams = sys.stdin, sys.stdout, sys.stderr
        saved_hooks = termui.visible_prompt_func, termui.hidden_prompt_func, termui._getchar, _compat.should_strip_ansi, formatting.FORCED_WIDTH, pdb.Pdb.__init__
        overrides = self.make_env(env)
        previous_env = {name: os.environ.get(name) for name in overrides}
        binary_input = make_input_stream(input, self.charset)
        echoed = EchoingStdin(binary_input, mixer.stdout) if self.echo_stdin else None
        stdin = _NamedTextIOWrapper(echoed or binary_input, encoding=self.charset, name="<stdin>", mode="r")
        stdout = _NamedTextIOWrapper(mixer.stdout, encoding=self.charset, name="<stdout>", mode="w", write_through=True, fd=1 if self.capture == "fd" else None)
        stderr = _NamedTextIOWrapper(mixer.stderr, encoding=self.charset, errors="backslashreplace", name="<stderr>", mode="w", write_through=True, fd=2 if self.capture == "fd" else None)
        fd_captures: list[tuple[int, int, t.BinaryIO, io.BytesIO]] = []
        def read_prompt(prompt: str, hidden: bool = False) -> str:
            sys.stdout.write(prompt)
            sys.stdout.flush()
            if echoed is not None:
                echoed._paused = True
            try:
                line = sys.stdin.readline()
            finally:
                if echoed is not None:
                    echoed._paused = False
            if not line:
                raise EOFError()
            line = line.rstrip("\r\n")
            sys.stdout.write("\n" if hidden else line + "\n")
            sys.stdout.flush()
            return line
        def getchar(echo: bool = False) -> str:
            if echoed is not None:
                echoed._paused = True
            try:
                value = sys.stdin.read(1)
            finally:
                if echoed is not None:
                    echoed._paused = False
            if echo:
                sys.stdout.write(value)
            return value
        original_pdb = saved_hooks[-1]
        def pdb_init(instance: t.Any, *args: t.Any, **kwargs: t.Any) -> None:
            kwargs.setdefault("stdin", sys.__stdin__)
            kwargs.setdefault("stdout", sys.__stdout__)
            original_pdb(instance, *args, **kwargs)
        try:
            if self.capture == "fd":
                for fd, target in ((1, mixer.stdout), (2, mixer.stderr)):
                    stream = saved_streams[fd]
                    if stream is not None:
                        stream.flush()
                    backup = os.dup(fd)
                    temporary = tempfile.TemporaryFile()
                    os.dup2(temporary.fileno(), fd)
                    fd_captures.append((fd, backup, temporary, target))
            sys.stdin, sys.stdout, sys.stderr = stdin, stdout, stderr
            termui.visible_prompt_func = read_prompt
            termui.hidden_prompt_func = lambda prompt: read_prompt(prompt, True)
            termui._getchar = getchar
            _compat.should_strip_ansi = lambda stream=None, color=None: not (color if color is not None else isolation_color)
            isolation_color = color
            formatting.FORCED_WIDTH = 80
            pdb.Pdb.__init__ = pdb_init
            for name, value in overrides.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            yield mixer.stdout, mixer.stderr, mixer.output
        finally:
            for stream in (stdout, stderr):
                try:
                    stream.flush()
                except (ValueError, OSError):
                    pass
            for fd, backup, temporary, target in fd_captures:
                os.dup2(backup, fd)
                os.close(backup)
                temporary.seek(0)
                target.write(temporary.read())
                temporary.close()
            sys.stdin, sys.stdout, sys.stderr = saved_streams
            termui.visible_prompt_func, termui.hidden_prompt_func, termui._getchar, _compat.should_strip_ansi, formatting.FORCED_WIDTH, pdb.Pdb.__init__ = saved_hooks
            for name, value in previous_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    def invoke(self, cli: t.Any, args: str | t.Sequence[str] | None = None, input: t.Any = None, env: t.Mapping[str, str | None] | None = None, catch_exceptions: bool | None = None, color: bool = False, **extra: t.Any) -> Result:
        args = shlex.split(args) if isinstance(args, str) else [str(value) for value in args or ()]
        if catch_exceptions is None:
            catch_exceptions = self.catch_exceptions
        exception = exc_info = return_value = None
        exit_code = 0
        with self.isolation(input, env, color) as (stdout, stderr, output):
            try:
                return_value = cli.main(args=args, prog_name=extra.pop("prog_name", self.get_default_prog_name(cli)), **extra)
            except SystemExit as exc:
                exc_info = sys.exc_info()
                code = exc.code
                if code is None:
                    code = 0
                if code != 0:
                    exception = exc
                if not isinstance(code, int):
                    sys.stdout.write(str(code) + "\n")
                    code = 1
                exit_code = code
            except Exception as exc:
                if not catch_exceptions:
                    raise
                exception = exc
                exc_info = sys.exc_info()
                exit_code = 1
        return Result(self, stdout.getvalue(), stderr.getvalue(), output.getvalue(), return_value, exit_code, exception, exc_info)

    @contextlib.contextmanager
    def isolated_filesystem(self, temp_dir: str | os.PathLike[str] | None = None) -> t.Iterator[str]:
        warnings.warn("'isolated_filesystem' is deprecated and will be removed in Click 9.0. Use tempfile.TemporaryDirectory and absolute paths instead.", DeprecationWarning, stacklevel=2)
        previous = os.getcwd()
        directory = tempfile.mkdtemp(dir=temp_dir)
        try:
            os.chdir(directory)
            yield directory
        finally:
            os.chdir(previous)
            if temp_dir is None:
                shutil.rmtree(directory)
