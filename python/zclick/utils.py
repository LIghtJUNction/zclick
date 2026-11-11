"""Filesystem and stream operations used by the compatibility interface."""
from __future__ import annotations

import errno
import functools
import io
import os
import re
import stat
import sys
import typing as t

from . import _compat

R = t.TypeVar("R")

_default_text_stdin = _compat.get_text_stdin
_default_text_stdout = _compat.get_text_stdout
_default_text_stderr = _compat.get_text_stderr


def make_str(value: t.Any) -> str:
    return os.fsdecode(value) if isinstance(value, bytes) else str(value)


def _safecall(func: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
    @functools.wraps(func)
    def wrapped(*args: t.Any, **kwargs: t.Any) -> t.Any:
        try:
            return func(*args, **kwargs)
        except Exception:
            return None
    return wrapped


def _make_default_short_help(help: str, max_length: int = 45) -> str:
    paragraph = help.strip().split("\n\n", 1)[0]
    paragraph = " ".join(paragraph.replace("\b", "").split())
    sentence = re.split(r"(?<=\.)\s+(?=[A-Z0-9])", paragraph, maxsplit=1)[0]
    if len(sentence) <= max_length:
        return sentence
    words: list[str] = []
    for word in sentence.split():
        if len(" ".join([*words, word])) > max_length - 3:
            break
        words.append(word)
    return " ".join(words) + "..."


def echo(message: object = None, file: t.IO[t.Any] | None = None, nl: bool = True, err: bool = False, color: bool | None = None) -> None:
    if file is None:
        file = _default_text_stderr() if err else _default_text_stdout()
    if file is None:
        return
    if isinstance(message, (bytes, bytearray)):
        binary = _compat._find_binary_writer(file)
        if binary is not None:
            file.flush()
            binary.write(bytes(message) + (b"\n" if nl else b""))
            binary.flush()
            return
        message = bytes(message)
    text = "" if message is None else message if isinstance(message, (str, bytes)) else str(message)
    if nl:
        text += b"\n" if isinstance(text, bytes) else "\n"
    if isinstance(text, str):
        from .globals import resolve_color_default
        if _compat.should_strip_ansi(file, resolve_color_default(color)):
            text = _compat.strip_ansi(text)
    file.write(text)
    file.flush()


def _get_binary_stream(name: str) -> t.Any:
    try:
        return _compat.binary_streams[name]()
    except KeyError:
        raise TypeError(f"Unknown standard stream {name!r}") from None


def _get_text_stream(name: str, encoding: str | None = None, errors: str | None = "strict") -> t.Any:
    try:
        return _compat.text_streams[name](encoding, errors)
    except KeyError:
        raise TypeError(f"Unknown standard stream {name!r}") from None


class _KeepOpenFile:
    def __init__(self, file: t.IO[t.Any]) -> None:
        self._file = file

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self._file, name)

    def __enter__(self) -> _KeepOpenFile:
        return self

    def __exit__(self, *args: t.Any) -> None:
        pass

    def __iter__(self) -> t.Iterator[t.Any]:
        return iter(self._file)

    def __repr__(self) -> str:
        return repr(self._file)


class _AtomicFile:
    def __init__(self, stream: t.IO[t.Any], temporary: str, target: str) -> None:
        self._file = stream
        self._temporary = temporary
        self.name = target
        self.closed = False

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self._file, name)

    def close(self, delete: bool = False) -> None:
        if self.closed:
            return
        self._file.close()
        if delete:
            os.unlink(self._temporary)
        else:
            os.replace(self._temporary, self.name)
        self.closed = True

    def __enter__(self) -> _AtomicFile:
        return self

    def __exit__(self, *args: t.Any) -> None:
        self.close()

    def __iter__(self) -> t.Iterator[t.Any]:
        return iter(self._file)


def _open_stream(filename: t.Any, mode: str = "r", encoding: str | None = None, errors: str | None = "strict", atomic: bool = False) -> tuple[t.Any, bool]:
    name = os.fspath(filename)
    if name == (b"-" if isinstance(name, bytes) else "-"):
        stream_name = "stdout" if any(c in mode for c in "wax") else "stdin"
        stream = _get_binary_stream(stream_name) if "b" in mode else _get_text_stream(stream_name, encoding, errors)
        return stream, False
    kwargs = {} if "b" in mode else {"encoding": encoding, "errors": errors}
    if not atomic:
        return open(filename, mode, **kwargs), True
    if "a" in mode:
        raise ValueError("Appending to an existing file is not supported, because that would involve an expensive `copy`-operation to a temporary file. Open the file in normal `w`-mode and copy explicitly if that's what you're after.")
    if "x" in mode:
        raise ValueError("Use the `overwrite`-parameter instead.")
    if "w" not in mode:
        raise ValueError("Atomic writes only make sense with `w`-mode.")
    import tempfile
    target = os.path.realpath(os.fsdecode(filename))
    fd, temporary = tempfile.mkstemp(prefix=".__atomic-write", dir=os.path.dirname(target))
    try:
        try:
            permissions = stat.S_IMODE(os.stat(target).st_mode)
        except FileNotFoundError:
            probe = temporary + ".permissions"
            probe_fd = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            try:
                permissions = stat.S_IMODE(os.fstat(probe_fd).st_mode)
            finally:
                os.close(probe_fd)
                os.unlink(probe)
        os.chmod(temporary, permissions)
        stream = os.fdopen(fd, mode, **kwargs)
    except BaseException:
        os.close(fd)
        os.unlink(temporary)
        raise
    return _AtomicFile(stream, temporary, target), True


class _LazyFile:
    def __init__(self, filename: t.Any, mode: str = "r", encoding: str | None = None, errors: str | None = "strict", atomic: bool = False) -> None:
        self.name, self.mode, self.encoding, self.errors, self.atomic = os.fspath(filename), mode, encoding, errors, atomic
        self._f: t.Any = None
        self.should_close = True
        if self.name == (b"-" if isinstance(self.name, bytes) else "-"):
            self._f, self.should_close = _open_stream(filename, mode, encoding, errors, atomic)
        elif "r" in mode:
            with open(filename, "rb"):
                pass

    def open(self) -> t.Any:
        if self._f is None:
            try:
                self._f, self.should_close = _open_stream(self.name, self.mode, self.encoding, self.errors, self.atomic)
            except OSError as exc:
                from .exceptions import FileError
                raise FileError(self.name, hint=exc.strerror) from exc
        return self._f

    def close(self) -> None:
        if self._f is not None:
            self._f.close()

    def close_intelligently(self) -> None:
        if self.should_close:
            self.close()

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.open(), name)

    def __enter__(self) -> _LazyFile:
        return self

    def __exit__(self, *args: t.Any) -> None:
        self.close_intelligently()

    def __iter__(self) -> t.Iterator[t.Any]:
        return iter(self.open())

    def __repr__(self) -> str:
        return repr(self._f) if self._f is not None else f"<unopened file {self.name!r} {self.mode}>"


def open_file(filename: t.Any, mode: str = "r", encoding: str | None = None, errors: str | None = "strict", lazy: bool = False, atomic: bool = False) -> t.Any:
    if lazy:
        return _LazyFile(filename, mode, encoding, errors, atomic)
    stream, owned = _open_stream(filename, mode, encoding, errors, atomic)
    return stream if owned else _KeepOpenFile(stream)


def format_filename(filename: t.Any, shorten: bool = False) -> str:
    filename = os.fspath(filename)
    if shorten:
        filename = os.path.basename(filename)
    if isinstance(filename, bytes):
        return filename.decode(sys.getfilesystemencoding(), "replace")
    return filename.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def _posixify(name: str) -> str:
    return "-".join(name.split()).lower()


def get_app_dir(app_name: str, roaming: bool = True, force_posix: bool = False) -> str:
    if force_posix:
        return os.path.join(os.path.expanduser("~"), "." + _posixify(app_name))
    if _compat.WIN:
        root = os.environ.get("APPDATA" if roaming else "LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(root, app_name)
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), app_name)
    return os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), _posixify(app_name))


class _PacifyFlushWrapper:
    def __init__(self, wrapped: t.Any) -> None:
        self.wrapped = wrapped

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.wrapped, name)

    def flush(self) -> None:
        try:
            self.wrapped.flush()
        except OSError as exc:
            if exc.errno != errno.EPIPE:
                raise


def _detect_program_name(path: str | None = None, _main: t.Any = None) -> str:
    path = sys.argv[0] if path is None else path
    main = sys.modules.get("__main__") if _main is None else _main
    package = getattr(main, "__package__", None)
    name = os.path.basename(path)
    if package:
        module = package if name == "__main__.py" else f"{package}.{os.path.splitext(name)[0]}"
        return "python -m " + module
    return name


def _expand_args(args: t.Iterable[str], *, user: bool = True, env: bool = True, glob_recursive: bool = True) -> list[str]:
    import glob
    result: list[str] = []
    for value in args:
        if user:
            value = os.path.expanduser(value)
        if env:
            value = os.path.expandvars(value)
        matches = glob.glob(value, recursive=glob_recursive)
        result.extend(matches or [value])
    return result


def __getattr__(name: str) -> t.Any:
    names = {"LazyFile", "KeepOpenFile", "PacifyFlushWrapper", "safecall", "make_default_short_help", "get_binary_stream", "get_text_stream"}
    if name in names:
        import warnings
        warnings.warn(f"'{name}' is deprecated and will be removed in Click 9.0.", DeprecationWarning, stacklevel=2)
        return globals()["_" + name]
    raise AttributeError(name)
