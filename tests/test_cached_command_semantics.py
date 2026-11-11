"""Repeat real command invocations while changing public Python definitions."""
from __future__ import annotations

import importlib
import inspect

import pytest


@pytest.fixture(params=["click", "zclick"])
def cli(request):
    return importlib.import_module(request.param)


def test_repeated_command_observes_shape_and_conversion_changes(cli):
    option = cli.Option(["--item"], type=int)
    command = cli.Command("mutable", params=[option], callback=lambda **v: v)
    invoke = lambda args: command.main(args, prog_name="mutable", standalone_mode=False)
    assert invoke(["--item", "4"]) == {"item": 4}
    assert invoke(["--item", "5"]) == {"item": 5}
    option.opts[:] = ["--pair"]
    option.nargs = 2
    assert invoke(["--pair", "6", "7"]) == {"item": (6, 7)}
    option.multiple = True
    assert invoke(["--pair", "8", "9", "--pair", "10", "11"]) == {"item": ((8, 9), (10, 11))}
    command.params[:] = [cli.Argument(["items"], nargs=-1, type=int)]
    assert invoke(["12", "13"]) == {"items": (12, 13)}


def test_late_class_and_instance_hooks_run_after_repeated_calls(cli, monkeypatch):
    option = cli.Option(["--item"], type=int)
    command = cli.Command("mutable", params=[option], callback=lambda item: item)
    invoke = lambda: command.main(["--item", "4"], prog_name="mutable", standalone_mode=False)
    assert invoke() == invoke() == 4
    original = cli.Option.add_to_parser
    seen = []

    def add_to_parser(self, parser, ctx):
        seen.append(ctx)
        return original(self, parser, ctx)

    monkeypatch.setattr(cli.Option, "add_to_parser", add_to_parser)
    assert invoke() == 4
    assert seen
    monkeypatch.setattr(option, "process_value", lambda ctx, value: int(value) + 10)
    assert invoke() == 14


def test_reentrant_definition_changes_have_separate_invocation_state(cli):
    depth = 0

    def convert(ctx, param, value):
        nonlocal depth
        if not depth:
            depth += 1
            option.opts[:] = ["--inner"]
            try:
                assert command.main(["--inner", "7"], prog_name="nested", standalone_mode=False) == 7
                assert cli.get_current_context() is ctx
            finally:
                depth -= 1
                option.opts[:] = ["--outer"]
        return value

    option = cli.Option(["--outer"], type=int, callback=convert)
    command = cli.Command("nested", params=[option], callback=lambda outer: outer)
    for value in (3, 4):
        assert command.main(["--outer", str(value)], prog_name="nested", standalone_mode=False) == value


@pytest.mark.parametrize("text", ["", "  plain  ", "\ttext\tmore  ", "\u2003Unicode 零\u2003", "  \n    line one\n      line two\n", "path-\udcff"])
def test_help_cleanup_retains_stdlib_semantics(text):
    from zclick.core import _clean_help
    assert _clean_help(text) == inspect.cleandoc(text)


def test_help_cleanup_does_not_bypass_str_subclass_methods():
    from zclick.core import _clean_help
    seen = []

    class Text(str):
        def expandtabs(self, tabsize=8):
            seen.append(tabsize)
            return "  replaced  "

    assert _clean_help(Text("original")) == "replaced  "
    assert seen == [8]
