"""Terminal interactions that preserve Python stream and callback semantics."""
from __future__ import annotations

import contextlib
import os
import re
import sys
import typing as t

from ._compat import isatty, strip_ansi
from .exceptions import Abort, UsageError
from .types import Choice, File, convert_type
from .utils import echo

V = t.TypeVar("V")
visible_prompt_func = input
_getchar: t.Callable[..., str] | None = None


def hidden_prompt_func(prompt: str) -> str:
    import getpass
    return getpass.getpass(prompt)


def _read_prompt(text: str, hidden: bool, err: bool) -> str:
    from ._compat import should_strip_ansi
    from .globals import resolve_color_default
    stream = sys.stderr if err else sys.stdout
    if should_strip_ansi(stream, resolve_color_default()):
        text = strip_ansi(text)
    try:
        with contextlib.redirect_stdout(stream):
            return (hidden_prompt_func if hidden else visible_prompt_func)(text)
    except (EOFError, KeyboardInterrupt):
        if hidden:
            echo(err=err)
        raise Abort() from None


def _default_display(default: t.Any) -> str:
    if hasattr(default, "name") and hasattr(default, "read"):
        return str(default.name)
    return str(default)


def prompt(text: str, default: t.Any = None, hide_input: bool = False, confirmation_prompt: bool | str = False, type: t.Any = None, value_proc: t.Callable[[t.Any], V] | None = None, prompt_suffix: str = ": ", show_default: bool | str = True, err: bool = False, show_choices: bool = True) -> V:
    param_type = convert_type(type, default)
    if value_proc is None:
        value_proc = param_type
    label = text
    if show_choices and isinstance(param_type, Choice):
        label += " (" + ", ".join(param_type.normalize_choice(v, None) for v in param_type.choices) + ")"
    if isinstance(show_default, str) and show_default:
        label += f" ({show_default})"
    elif show_default and default is not None:
        label += " [" + _default_display(default) + "]"
    label += prompt_suffix
    confirmation_label = "Repeat for confirmation" if confirmation_prompt is True else confirmation_prompt
    while True:
        raw = _read_prompt(label, hide_input, err)
        if not raw:
            if default is None:
                continue
            raw = default
        try:
            value = value_proc(raw)
        except UsageError as exc:
            message = exc.message
            if hide_input:
                # A converter can interpolate input multiple times, including repr.
                if str(raw):
                    pattern = re.escape(repr(raw)) + "|(?<!\\w)" + re.escape(str(raw)) + "(?!\\w)"
                    message = re.sub(pattern, "'***'", message)
            echo("Error: " + message, err=err)
            continue
        if not confirmation_prompt:
            return value
        repeated = _read_prompt(str(confirmation_label) + prompt_suffix, hide_input, err)
        if repeated == raw:
            return value
        echo("Error: The two entered values do not match.", err=err)


def confirm(text: str, default: bool | None = False, abort: bool = False, prompt_suffix: str = ": ", show_default: bool = True, err: bool = False) -> bool:
    label = text
    if show_default:
        label += " [" + ("y/n" if default is None else "Y/n" if default else "y/N") + "]"
    while True:
        response = _read_prompt(label + prompt_suffix, False, err).strip().lower()
        if response in ("y", "yes"):
            result = True
        elif response in ("n", "no"):
            result = False
        elif not response and default is not None:
            result = bool(default)
        else:
            echo("Error: invalid input", err=err)
            continue
        if abort and not result:
            raise Abort()
        return result


@contextlib.contextmanager
def get_pager_file(color: bool | None = None) -> t.Iterator[t.TextIO]:
    from ._termui_impl import _PagerWriter, _pager_contextmanager
    from .globals import resolve_color_default
    with _pager_contextmanager() as (stream, preferred_color):
        resolved = resolve_color_default(color)
        writer = _PagerWriter(stream, bool(preferred_color if resolved is None else resolved))
        try:
            yield writer
        finally:
            writer.flush()


def echo_via_pager(text_or_generator: t.Any, color: bool | None = None) -> None:
    content = text_or_generator() if callable(text_or_generator) else text_or_generator
    if isinstance(content, str):
        content = (content,)
    with get_pager_file(color) as stream:
        for item in content:
            stream.write(str(item))
            stream.flush()
        stream.write("\n")


def progressbar(iterable: t.Iterable[V] | None = None, length: int | None = None, label: str | None = None, hidden: bool = False, show_eta: bool = True, show_percent: bool | None = None, show_pos: bool = False, item_show_func: t.Callable[[V | None], str | None] | None = None, fill_char: str = "#", empty_char: str = "-", bar_template: str = "%(label)s  [%(bar)s]  %(info)s", info_sep: str = "  ", width: int = 36, file: t.TextIO | None = None, color: bool | None = None, update_min_steps: int = 1) -> t.Any:
    from ._termui_impl import ProgressBar
    return ProgressBar(iterable, length, label, hidden, show_eta, show_percent, show_pos, item_show_func, fill_char, empty_char, bar_template, info_sep, width, file, color, update_min_steps)


def clear() -> None:
    if isatty(sys.stdout):
        echo("\033[2J\033[1;1H", nl=False, color=True)


_COLORS = {name: index for index, name in enumerate(("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"))}


def _color(value: t.Any, background: bool) -> str:
    base = 40 if background else 30
    if isinstance(value, str):
        if value == "reset":
            return str(base + 9)
        bright = value.startswith("bright_")
        name = value[7:] if bright else value
        if name in _COLORS:
            return str(base + _COLORS[name] + (60 if bright else 0))
    elif type(value) is int and 0 <= value <= 255:
        return f"{base + 8};5;{value}"
    elif isinstance(value, (tuple, list)) and len(value) == 3 and all(type(n) is int and 0 <= n <= 255 for n in value):
        return f"{base + 8};2;" + ";".join(map(str, value))
    raise ValueError(f"Unknown color {value!r}")


def style(text: t.Any, fg: t.Any = None, bg: t.Any = None, bold: bool | None = None, dim: bool | None = None, underline: bool | None = None, overline: bool | None = None, italic: bool | None = None, blink: bool | None = None, reverse: bool | None = None, strikethrough: bool | None = None, reset: bool = True) -> str:
    codes: list[str] = []
    for value, is_background in ((fg, False), (bg, True)):
        if value is not None:
            codes.append(_color(value, is_background))
    for value, on, off in ((bold, 1, 22), (dim, 2, 22), (underline, 4, 24), (overline, 53, 55), (italic, 3, 23), (blink, 5, 25), (reverse, 7, 27), (strikethrough, 9, 29)):
        if value is not None:
            codes.append(str(on if value else off))
    return "".join(f"\033[{code}m" for code in codes) + str(text) + ("\033[0m" if reset else "")


def unstyle(text: str) -> str:
    return strip_ansi(text)


def secho(message: t.Any = None, file: t.IO[t.Any] | None = None, nl: bool = True, err: bool = False, color: bool | None = None, **styles: t.Any) -> None:
    if message is not None and not isinstance(message, (bytes, bytearray)):
        message = style(message, **styles)
    echo(message, file, nl, err, color)


def edit(text: str | bytes | bytearray | None = None, editor: str | None = None, env: t.Mapping[str, str] | None = None, require_save: bool = True, extension: str = ".txt", filename: t.Any = None) -> t.Any:
    from ._termui_impl import Editor
    instance = Editor(editor, env, require_save, extension)
    if filename is not None:
        instance.edit_files(filename)
        return None
    return instance.edit(text)


def launch(url: str, wait: bool = False, locate: bool = False) -> int:
    from ._termui_impl import open_url
    return open_url(url, wait, locate)


def getchar(echo: bool = False) -> str:
    global _getchar
    if _getchar is None:
        from ._termui_impl import getchar as read
        _getchar = read
    return _getchar(echo)


def raw_terminal() -> t.Any:
    from ._termui_impl import raw_terminal as terminal
    return terminal()


def pause(info: str | None = None, err: bool = False) -> None:
    if not isatty(sys.stdin) or not isatty(sys.stderr if err else sys.stdout):
        return
    echo("Press any key to continue..." if info is None else info, nl=False, err=err)
    try:
        getchar()
    except (KeyboardInterrupt, EOFError):
        pass
    echo(err=err)
