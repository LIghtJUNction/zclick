"""Record concrete boundaries with unmodified third-party Click extensions.

These passing diagnostic tests include assertions that mixed imports fail.
They do not mean the tested extension supports zclick. See docs/extensions.md.
"""
from __future__ import annotations

from importlib.metadata import version
from types import SimpleNamespace

import click as original
from click.testing import CliRunner as OriginalRunner
from click_didyoumean import DYMGroup
from click_plugins import with_plugins
from click_repl import register_repl
import pytest

import zclick
from zclick.testing import CliRunner


def test_extension_versions_are_the_documented_versions() -> None:
    assert {name: version(name) for name in ("click", "click-didyoumean", "click-plugins", "click-repl")} == {
        "click": "8.5.1", "click-didyoumean": "0.3.1", "click-plugins": "1.1.1.2", "click-repl": "0.4.1",
    }


def test_original_and_zclick_context_stacks_remain_separate() -> None:
    assert original is not zclick
    with zclick.Context(zclick.Command("native")) as ctx:
        assert zclick.get_current_context() is ctx
        assert original.get_current_context(silent=True) is None
    with original.Context(original.Command("original")) as ctx:
        assert original.get_current_context() is ctx
        assert zclick.get_current_context(silent=True) is None


def test_didyoumean_original_click_baseline() -> None:
    @original.group(cls=DYMGroup)
    def cli():
        pass

    @cli.command()
    def hello():
        original.echo("hello")

    result = OriginalRunner().invoke(cli, ["helo"])
    assert result.exit_code == 2
    assert "Did you mean one of these?" in result.output
    assert "hello" in result.output


def test_didyoumean_alias_still_constructs_original_click_group() -> None:
    @zclick.group(cls=DYMGroup)
    def cli():
        pass

    @cli.command()
    def hello():
        zclick.echo("hello")

    assert isinstance(cli, original.Group)
    assert not isinstance(cli, zclick.Group)
    result = CliRunner().invoke(cli, ["hello"])
    assert result.exit_code == 0
    assert result.output == "hello\n"


def test_didyoumean_mixed_context_decorator_is_incompatible() -> None:
    @zclick.group(cls=DYMGroup)
    @zclick.pass_context
    def cli(ctx):
        raise AssertionError("The original Click context cannot enter this callback")

    @cli.command()
    def hello():
        pass

    result = CliRunner().invoke(cli, ["hello"])
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == "There is no active click context."


def test_plugins_original_click_baseline() -> None:
    child = original.Command("hello", callback=lambda: original.echo("hello"))
    entry_point = SimpleNamespace(name="hello", load=lambda: child)
    group = with_plugins([entry_point])(original.Group("cli"))
    result = OriginalRunner().invoke(group, ["hello"])
    assert result.exit_code == 0
    assert result.output == "hello\n"


def test_plugins_rejects_zclick_group_identity() -> None:
    with pytest.raises(TypeError, match=r"Plugins can only be attached to an instance of click.Group\(\)"):
        with_plugins([])(zclick.Group("cli"))


def test_repl_original_click_baseline() -> None:
    @original.group()
    def cli():
        pass

    @cli.command()
    def hello():
        original.echo("hello")

    register_repl(cli)
    # This pinned extension itself still uses Click's deprecated MultiCommand.
    with pytest.warns(DeprecationWarning, match="MultiCommand"):
        result = OriginalRunner().invoke(cli, ["repl"], input="hello\n:exit\n")
    assert result.exit_code == 0
    assert result.output == "hello\n"


def test_repl_registered_zclick_command_uses_wrong_context_stack() -> None:
    group = zclick.Group("cli")
    register_repl(group)
    assert isinstance(group.commands["repl"], zclick.Command)
    result = CliRunner().invoke(group, ["repl"], input=":exit\n")
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == "There is no active click context."
