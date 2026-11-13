"""Help preparation preserves the target's live containers and access order."""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
import warnings

import pytest


@pytest.fixture(params=["click", "zclick"])
def cli(request):
    return importlib.import_module(request.param)


def test_without_automatic_help_get_params_returns_original_container(cli):
    class Parameters(list):
        def __getitem__(self, index):
            if isinstance(index, slice):
                raise AssertionError("the parameter container must not be copied")
            return super().__getitem__(index)

    parameters = Parameters([cli.Option(["--value"])])
    command = cli.Command("cli", params=parameters, add_help_option=False)
    assert command.get_params(cli.Context(command)) is parameters


def test_empty_constructor_parameters_follow_container_truthiness(cli):
    calls = []

    class Parameters(list):
        def __bool__(self):
            calls.append("truth")
            return False

    parameters = Parameters()
    command = cli.Command("cli", params=parameters)
    assert command.params == [] and command.params is not parameters
    assert calls == ["truth"]


def test_help_hook_mutations_are_visible_in_the_returned_parameters(cli):
    late = cli.Option(["--late"])

    class Command(cli.Command):
        def get_help_option(self, ctx):
            self.params.append(late)
            return super().get_help_option(ctx)

    first = cli.Option(["--first"])
    command = Command("cli", params=[first])
    result = command.get_params(cli.Context(command))
    assert result[:2] == [first, late]
    assert result[-1] is command._help_option
    assert command.params == [first, late]


def test_help_name_hashing_precedes_parameter_spelling_reads(cli):
    option = cli.Option(["--value"])
    changed = False

    class Name(str):
        def __hash__(self):
            nonlocal changed
            if not changed:
                option.secondary_opts.append("--help")
                changed = True
            return super().__hash__()

    command = cli.Command("cli", params=[option])
    ctx = cli.Context(command, help_option_names=[Name("--help"), "-h", "-h"])
    assert command.get_help_option_names(ctx) == ["-h"]
    assert changed


def test_help_name_attribute_trace_matches_target():
    def observe(package):
        cli = importlib.import_module(package)
        events = []

        class Context(cli.Context):
            def __getattribute__(self, name):
                if name == "help_option_names":
                    events.append("context.names")
                return super().__getattribute__(name)

        class Command(cli.Command):
            def __getattribute__(self, name):
                if name == "params":
                    events.append("command.params")
                return super().__getattribute__(name)

        class Option(cli.Option):
            def __getattribute__(self, name):
                if name in ("opts", "secondary_opts"):
                    events.append("option." + name)
                return super().__getattribute__(name)

        command = Command("cli", params=[Option(["--help"])])
        ctx = Context(command, help_option_names=["--help", "-h"])
        events.clear()
        return command.get_help_option_names(ctx), events

    assert observe("zclick") == observe("click") == (
        ["-h"],
        ["context.names", "command.params", "option.opts", "option.secondary_opts"],
    )


def test_help_cache_and_empty_names_keep_target_behavior(cli):
    command = cli.Command("cli")
    first = command.get_help_option(cli.Context(command, help_option_names=["--help"]))
    second = command.get_help_option(cli.Context(command, help_option_names=["-h"]))
    assert second is first
    assert second.opts == ["--help"]
    assert command.get_help_option(cli.Context(command, help_option_names=[])) is None
    assert command.get_help_option(cli.Context(command, help_option_names=["-h"])) is first


def test_empty_help_names_do_not_evaluate_add_help_flag(cli):
    calls = []

    class Flag:
        def __bool__(self):
            calls.append("flag")
            return False

    command = cli.Command("cli", add_help_option=Flag())
    assert command.get_help_option(cli.Context(command, help_option_names=[])) is None
    assert calls == []
    assert command.get_help_option(cli.Context(command, help_option_names=["--help"])) is None
    assert calls == ["flag"]


def test_first_help_construction_uses_live_parameter_container(cli):
    events = []

    class Parameters(list):
        def append(self, value):
            events.append(("append", value.name))
            return super().append(value)

        def pop(self, *args):
            events.append(("pop", args))
            return super().pop(*args)

    parameters = Parameters()
    command = cli.Command("cli")
    command.params = parameters
    result = command.get_help_option(cli.Context(command))
    assert result is command._help_option
    assert events == [("append", "_click_default_help"), ("pop", ())]
    assert command.params is parameters and parameters == []


@pytest.mark.parametrize("case", ["primary", "secondary", "argument_option", "arguments", "reserved"])
def test_duplicate_warning_messages_and_categories_match_target(case):
    def observe(package):
        cli = importlib.import_module(package)
        if case == "primary":
            parameters = [cli.Option(["--same", "first"]), cli.Option(["--same", "second"])]
        elif case == "secondary":
            parameters = [cli.Option(["--enable/--shared"]), cli.Option(["--shared"])]
        elif case == "argument_option":
            parameters = [cli.Argument(["value"]), cli.Option(["--value"])]
        elif case == "arguments":
            parameters = [cli.Argument(["value"]), cli.Argument(["value"])]
        else:
            parameters = [cli.Option(["--custom", "_click_default_help"])]
        command = cli.Command("cli", params=parameters)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            command.get_params(cli.Context(command))
        return [(type(w.message).__name__, str(w.message)) for w in caught]

    expected = observe("click")
    assert observe("zclick") == expected
    assert len(expected) == {"secondary": 0, "arguments": 2}.get(case, 1)


@pytest.mark.parametrize("package", ["click", "zclick"])
def test_optimized_python_omits_debug_parameter_warnings(package):
    script = '''
import importlib, json, sys, warnings
cli = importlib.import_module(sys.argv[1])
command = cli.Command("cli", params=[cli.Option(["--same", "a"]), cli.Option(["--same", "b"])])
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    params = command.get_params(cli.Context(command))
print(json.dumps({"debug": __debug__, "warnings": len(caught), "params": len(params)}))
'''
    result = subprocess.run([sys.executable, "-O", "-c", script, package], check=True,
                            capture_output=True, text=True)
    assert json.loads(result.stdout) == {"debug": False, "warnings": 0, "params": 3}
