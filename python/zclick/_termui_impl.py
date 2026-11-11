"""OS-facing terminal backends and progress state."""
from __future__ import annotations

import contextlib
import io
import operator
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import typing as t
from io import StringIO

from ._compat import WIN, _default_text_stdout, isatty, strip_ansi, term_len
from .exceptions import ClickException
from .utils import echo

if WIN:
    import msvcrt

V = t.TypeVar("V")


class ProgressBar(t.Generic[V]):
    def __init__(self, iterable: t.Iterable[V] | None = None, length: int | None = None, label: str | None = None, hidden: bool = False, show_eta: bool = True, show_percent: bool | None = None, show_pos: bool = False, item_show_func: t.Callable[[V | None], str | None] | None = None, fill_char: str = "#", empty_char: str = "-", bar_template: str = "%(label)s  [%(bar)s]  %(info)s", info_sep: str = "  ", width: int = 36, file: t.TextIO | None = None, color: bool | None = None, update_min_steps: int = 1) -> None:
        if iterable is None and length is None:
            raise TypeError("iterable or length is required")
        if length is None and iterable is not None:
            try:
                length = len(iterable)
            except TypeError:
                hint = operator.length_hint(iterable, -1)
                length = None if hint < 0 else hint
        self.iterable = iter(range(length or 0) if iterable is None else iterable)
        self.length = length
        self.label = label or ""
        self.hidden = hidden
        self.show_eta, self.show_pos = show_eta, show_pos
        self.show_percent = not show_pos if show_percent is None else show_percent
        self.item_show_func = item_show_func
        self.fill_char, self.empty_char = fill_char, empty_char
        self.bar_template, self.info_sep, self.width = bar_template, info_sep, width
        self.file = _default_text_stdout() if file is None else file
        self.color = color
        self.update_min_steps = update_min_steps
        self.pos = 0
        self.avg: list[float] = []
        self.start = self.last_eta = time.time()
        self.eta_known = False
        self.finished = False
        self.entered = False
        self.current_item: V | None = None
        self._completed_intervals = 0
        self._last_line: str | None = None
        self._max_width = 0
        self._iterator_started = False

    @property
    def time_per_iteration(self) -> float:
        return sum(self.avg) / len(self.avg) if self.avg else 0.0

    @property
    def eta(self) -> float:
        return 0 if self.finished else self.time_per_iteration * ((self.length or 0) - self.pos)

    @property
    def pct(self) -> float:
        return 1 if self.finished else min(1.0, self.pos / self.length) if self.length else 0

    def format_eta(self) -> str:
        if not self.eta_known:
            return ""
        seconds = int(self.eta)
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return (f"{days}d " if days else "") + f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def format_pos(self) -> str:
        return str(self.pos) if self.length is None else f"{self.pos}/{self.length}"

    def format_pct(self) -> str:
        return f"{int(self.pct * 100):3d}%"

    def format_bar(self) -> str:
        width = self.width or max(1, shutil.get_terminal_size().columns - len(self.label) - 20)
        if self.length is not None:
            count = int(self.pct * width)
            return self.fill_char * count + self.empty_char * (width - count)
        if self.finished:
            return self.fill_char * width
        point = self.pos % width
        return self.empty_char * point + self.fill_char + self.empty_char * (width - point - 1)

    def format_progress_line(self) -> str:
        parts: list[str] = []
        if self.show_pos:
            parts.append(self.format_pos())
        if self.show_percent and self.length is not None:
            parts.append(self.format_pct())
        if self.show_eta and self.eta_known and not self.finished:
            parts.append(self.format_eta())
        if self.item_show_func is not None:
            item = self.item_show_func(self.current_item)
            if item:
                parts.append(item)
        return (self.bar_template % {"label": self.label, "bar": self.format_bar(), "info": self.info_sep.join(parts)}).rstrip()

    def render_progress(self) -> None:
        if self.hidden or self.file is None:
            return
        if not isatty(self.file):
            if self._last_line is None:
                echo(self.label, file=self.file, color=self.color)
                self._last_line = self.label
            return
        line = self.format_progress_line()
        if line == self._last_line:
            return
        padding = max(0, self._max_width - term_len(line))
        self._max_width = max(self._max_width, term_len(line))
        echo("\r\033[?25l" + line + " " * padding, file=self.file, nl=False, color=self.color)
        self._last_line = line

    def make_step(self, n_steps: int) -> None:
        self.pos += n_steps
        if self.length is not None and self.pos >= self.length:
            self.finished = True
        elapsed = time.time() - self.start
        if self.pos and elapsed >= 1:
            self.avg.append(elapsed / self.pos)
            self.avg = self.avg[-7:]
            self.eta_known = self.length is not None

    def update(self, n_steps: int, current_item: V | None = None) -> None:
        if current_item is not None:
            self.current_item = current_item
        self._completed_intervals += n_steps
        if self._completed_intervals >= self.update_min_steps:
            self.make_step(self._completed_intervals)
            self._completed_intervals = 0
            self.render_progress()

    def finish(self) -> None:
        if self._completed_intervals:
            self.make_step(self._completed_intervals)
            self._completed_intervals = 0
        self.finished = True
        self.current_item = None
        self.render_progress()

    def __enter__(self) -> ProgressBar[V]:
        self.entered = True
        self.render_progress()
        return self

    def __exit__(self, *args: t.Any) -> None:
        if args[0] is None:
            self.finish()
        if not self.hidden and isatty(self.file):
            echo("\033[?25h", file=self.file, color=self.color)

    def __iter__(self) -> ProgressBar[V]:
        if not self.entered:
            raise RuntimeError("You need to use progress bars in a with block.")
        return self

    def __next__(self) -> V:
        if not self.entered:
            raise RuntimeError("You need to use progress bars in a with block.")
        if self._iterator_started:
            self.update(1)
        try:
            value = next(self.iterable)
        except StopIteration:
            self.finish()
            raise
        self._iterator_started = True
        self.current_item = value
        self.render_progress()
        return value

    def generator(self) -> t.Iterator[V]:
        return iter(self)


class _PagerWriter:
    def __init__(self, stream: t.Any, color: bool | None = None) -> None:
        self.stream = stream
        self.color = color

    def write(self, text: str) -> int:
        value = text if self.color else strip_ansi(text)
        try:
            result = self.stream.write(value)
        except TypeError:
            result = self.stream.write(value.encode(getattr(self.stream, "encoding", None) or "utf-8", "replace"))
        return len(text) if result is None else result

    def flush(self) -> None:
        self.stream.flush()

    def close(self) -> None:
        self.flush()

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.stream, name)


@contextlib.contextmanager
def _nullpager() -> t.Iterator[tuple[t.Any, bool | None]]:
    stream = _default_text_stdout()
    if stream is None:
        stream = StringIO()
    yield stream, False


def _less_raw(tokens: list[str]) -> bool:
    for token in tokens:
        if token == "--":
            break
        if token in ("--raw-control-chars", "--RAW-CONTROL-CHARS"):
            return True
        if token.startswith("-") and not token.startswith("--") and ("r" in token or "R" in token):
            return True
    return False


@contextlib.contextmanager
def _pipepager(cmd: t.Any, args: list[str]) -> t.Iterator[tuple[t.Any, bool | None]]:
    environment = dict(os.environ)
    color = None
    stem = pathlib.Path(cmd).stem
    if (stem.casefold() if WIN else stem) == "less":
        if not args and "LESS" not in environment:
            environment["LESS"] = "-R"
        try:
            flags = shlex.split(environment.get("LESS", ""))
        except ValueError:
            flags = environment.get("LESS", "").split()
        if _less_raw(flags + args):
            color = True
    process = subprocess.Popen([os.fspath(cmd), *args], stdin=subprocess.PIPE, env=environment, text=True, encoding="utf-8", errors="replace")
    try:
        yield process.stdin, color
    finally:
        try:
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        while True:
            try:
                process.wait()
                break
            except KeyboardInterrupt:
                continue


@contextlib.contextmanager
def _tempfilepager(cmd: t.Any, args: list[str]) -> t.Iterator[tuple[t.Any, bool | None]]:
    stream = tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", delete=False)
    filename = stream.name
    try:
        yield stream, None
        stream.close()
        subprocess.call([os.fspath(cmd), *args, filename])
    finally:
        stream.close()
        os.unlink(filename)


@contextlib.contextmanager
def _pager_contextmanager() -> t.Iterator[tuple[t.Any, bool | None]]:
    if not isatty(sys.stdin) or not isatty(_default_text_stdout()):
        with _nullpager() as pair:
            yield pair
        return
    parts = shlex.split(os.environ.get("PAGER", ""))
    if not parts:
        found = shutil.which("less") or shutil.which("more")
        if found:
            parts = [found]
    executable = shutil.which(parts[0]) if parts else None
    if executable is None:
        with _nullpager() as pair:
            yield pair
        return
    with (_tempfilepager if WIN else _pipepager)(pathlib.Path(executable), parts[1:]) as pair:
        yield pair


class Editor:
    def __init__(self, editor: str | None = None, env: t.Mapping[str, str] | None = None, require_save: bool = True, extension: str = ".txt") -> None:
        self.editor, self.env, self.require_save, self.extension = editor, env, require_save, extension

    def get_editor(self) -> str:
        if self.editor:
            return self.editor
        for key in ("VISUAL", "EDITOR"):
            if os.environ.get(key):
                return os.environ[key]
        if WIN:
            return "notepad"
        for command in ("sensible-editor", "vim", "nano", "vi"):
            if shutil.which(command):
                return command
        return "vi"

    def edit_files(self, filenames: t.Any) -> None:
        if isinstance(filenames, (str, bytes, os.PathLike)):
            filenames = [filenames]
        try:
            argv = shlex.split(self.get_editor()) + [os.fspath(f) for f in filenames]
            environment = {**os.environ, **self.env} if self.env else None
            status = subprocess.Popen(argv, env=environment).wait()
        except OSError as exc:
            raise ClickException(f"Editing failed: {exc}") from exc
        if status:
            raise ClickException("Editing failed")

    def edit_file(self, filename: t.Any) -> None:
        self.edit_files(filename)

    def edit(self, text: str | bytes | bytearray | None) -> t.Any:
        binary = isinstance(text, (bytes, bytearray))
        initial = bytes(text) if binary else (text or "").replace("\r\n", "\n").encode("utf-8")
        if initial and not initial.endswith(b"\n"):
            initial += b"\n"
        fd, filename = tempfile.mkstemp(prefix="editor-", suffix=self.extension)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(initial)
            before = os.stat(filename).st_mtime_ns
            self.edit_files(filename)
            if self.require_save and os.stat(filename).st_mtime_ns == before:
                return None
            with open(filename, "rb") as stream:
                result = stream.read()
            return result if binary else result.decode("utf-8-sig").replace("\r\n", "\n")
        finally:
            os.unlink(filename)


def open_url(url: str, wait: bool = False, locate: bool = False) -> int:
    try:
        if WIN:
            if locate:
                process = subprocess.Popen(["explorer", "/select,", os.path.normpath(url)])
            else:
                os.startfile(url)
                return 0
        elif sys.platform == "darwin":
            process = subprocess.Popen(["open", *(["-W"] if wait else []), *(["-R"] if locate else []), url])
        else:
            process = subprocess.Popen(["xdg-open", os.path.dirname(url) if locate else url])
        return process.wait() if wait else 0
    except OSError:
        return 1


@contextlib.contextmanager
def raw_terminal() -> t.Iterator[int]:
    if WIN:
        yield sys.stdin.fileno()
        return
    import termios
    import tty
    stream = sys.stdin if isatty(sys.stdin) else open("/dev/tty")
    fd = stream.fileno()
    before = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield fd
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, before)
        if stream is not sys.stdin:
            stream.close()


def getchar(echo: bool = False) -> str:
    if WIN:
        value = (msvcrt.getwche if echo else msvcrt.getwch)()
        if value in ("\x00", "\xe0"):
            value += msvcrt.getwch()
    else:
        with raw_terminal() as fd:
            value = os.read(fd, 32).decode(sys.stdin.encoding or "utf-8", "replace")
        if echo:
            from .utils import echo as write
            write(value, nl=False)
    if value == "\x03":
        raise KeyboardInterrupt()
    if value in ("\x04", "\x1a"):
        raise EOFError()
    return value
