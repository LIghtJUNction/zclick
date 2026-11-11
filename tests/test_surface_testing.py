"""Observable contracts not covered by upstream's broad capture assertions."""
from __future__ import annotations

import os
import contextlib
import io
import sys

import pytest

import zclick
from zclick.testing import CliRunner


@pytest.mark.skipif(os.name == "nt", reason="Click 8.5.1 does not support fd capture on Windows")
def test_fd_capture_combines_deferred_streams_in_target_order() -> None:
    @zclick.command()
    def cli():
        zclick.echo("python stdout")
        os.write(1, b"descriptor stdout\n")
        zclick.echo("python stderr", err=True)
        os.write(2, b"descriptor stderr\n")
        zclick.echo("python stdout again")

    result = CliRunner(capture="fd").invoke(cli)
    assert result.exit_code == 0
    assert result.output == (
        "python stdout\npython stderr\npython stdout again\n"
        "descriptor stdout\ndescriptor stderr\n"
    )
    assert result.stdout == "python stdout\npython stdout again\ndescriptor stdout\n"
    assert result.stderr == "python stderr\ndescriptor stderr\n"


def test_composite_type_requires_arity_implementation() -> None:
    from zclick.types import CompositeParamType

    with pytest.raises(TypeError, match="abstract"):
        CompositeParamType()


def test_wrap_text_accepts_python_truth_values() -> None:
    calls = []

    class Truthy:
        def __bool__(self):
            calls.append("bool")
            return True

    assert zclick.wrap_text("a\n\nb", preserve_paragraphs=1) == "a\n\nb"
    assert zclick.wrap_text("a\n\nb", preserve_paragraphs=Truthy()) == "a\n\nb"
    assert calls == ["bool"]


@pytest.mark.skipif(os.name == "nt", reason="Exercises POSIX getchar encoding and terminal rules")
def test_posix_getchar_uses_unicode_fallback_without_echoing_to_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    import zclick._termui_impl as terminal

    @contextlib.contextmanager
    def raw():
        yield 123

    stdin = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
    stdout = io.StringIO()
    monkeypatch.setattr(terminal, "raw_terminal", raw)
    monkeypatch.setattr(os, "read", lambda fd, size: "字".encode("utf-8"))
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    assert terminal.getchar(echo=True) == "字"
    assert stdout.getvalue() == ""
    monkeypatch.setattr(os, "read", lambda fd, size: b"\x1a")
    assert terminal.getchar() == "\x1a"
