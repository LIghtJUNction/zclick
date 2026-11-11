"""Contracts needed by mutable applications and Python extension authors."""
from __future__ import annotations

import gc
import weakref

import pytest
import zclick as click
from zclick.testing import CliRunner


def test_mutations_are_observed_by_next_call():
    runner = CliRunner()
    option = click.Option(["--value"], default=1, type=int)
    command = click.Command("mutable", params=[option], callback=lambda value: value)
    assert runner.invoke(command, standalone_mode=False).return_value == 1
    option.default = lambda: 2
    command.callback = lambda value: value * 3
    assert runner.invoke(command, standalone_mode=False).return_value == 6
    option.opts[:] = ["--renamed"]
    assert runner.invoke(command, ["--renamed", "9"], standalone_mode=False).return_value == 27
    command.params[:] = [click.Argument(["text"])]
    command.callback = lambda text: text
    assert runner.invoke(command, ["fresh"], standalone_mode=False).return_value == "fresh"


def test_dynamic_defaults_execute_once_per_call():
    calls = []

    def make_default():
        calls.append(1)
        return len(calls)

    command = click.Command("counter", params=[click.Option(["--number"], default=make_default, type=int)], callback=lambda number: number)
    runner = CliRunner()
    assert runner.invoke(command, standalone_mode=False).return_value == 1
    assert runner.invoke(command, standalone_mode=False).return_value == 2
    assert runner.invoke(command, ["--number", "10"], standalone_mode=False).return_value == 10
    assert len(calls) == 2


def test_parameter_callbacks_can_reenter_same_command():
    contexts = []
    depth = 0

    def callback(ctx, param, value):
        nonlocal depth
        contexts.append(ctx)
        if depth == 0:
            depth += 1
            try:
                assert command.main(["--value", "7"], standalone_mode=False) == 7
                assert click.get_current_context() is ctx
            finally:
                depth -= 1
        return value

    command = click.Command("nested", params=[click.Option(["--value"], type=int, callback=callback)], callback=lambda value: value)
    assert command.main(["--value", "3"], standalone_mode=False) == 3
    assert len(contexts) == 2 and contexts[0] is not contexts[1]
    assert click.get_current_context(silent=True) is None


def test_type_override_and_large_integers():
    class MutableType(click.ParamType):
        name = "mutable"

        def convert(self, value, param, ctx):
            return int(value) + 1

    kind = MutableType()
    parameter = click.Option(["--value"], type=kind)
    command = click.Command("number", params=[parameter], callback=lambda value: value)
    huge = 10 ** 150
    assert command.main(["--value", str(huge)], standalone_mode=False) == huge + 1
    kind.convert = lambda value, param, ctx: int(value) - 1
    assert command.main(["--value", str(huge)], standalone_mode=False) == huge - 1


def test_native_boundary_preserves_surrogates():
    command = click.Command("native-text", params=[click.Argument(["text"])], callback=lambda text: text)
    value = "path-\udcff-漢字"
    assert command.main([value], standalone_mode=False) == value


def test_command_cycles_are_collectable():
    def make_cycle():
        command = click.Command("cycle")
        command.callback = lambda: command.name
        command.main([], standalone_mode=False)
        return weakref.ref(command)

    refs = [make_cycle() for _ in range(200)]
    gc.collect()
    assert all(ref() is None for ref in refs)


def test_lazy_group_overrides_and_registration():
    class LazyGroup(click.Group):
        def list_commands(self, ctx):
            return ["lazy"] + super().list_commands(ctx)

        def get_command(self, ctx, name):
            if name == "lazy":
                return click.Command("lazy", callback=lambda: "loaded")
            return super().get_command(ctx, name)

    group = LazyGroup("root")
    runner = CliRunner()
    assert runner.invoke(group, ["lazy"], standalone_mode=False).return_value == "loaded"
    group.add_command(click.Command("added", callback=lambda: "registered"))
    assert runner.invoke(group, ["added"], standalone_mode=False).return_value == "registered"


@pytest.mark.parametrize("tokens", [
    ["-NVALUE"], ["-vNValue"], ["-VNValue"], ["--NAME=Value"],
    ["--NAME", "Value"], ["-N", "--VERBOSE"], ["--NAME", "--VERBOSE"],
    ["--UNKNOWN=Value"], ["-Xv"], ["--", "--NAME"],
    ["positional", "--NAME=Value"], ["-N=Value"],
])
@pytest.mark.parametrize("optional", [False, True])
@pytest.mark.parametrize("interspersed", [False, True])
def test_normalization_preserves_values_and_unknown_tokens(tokens, optional, interspersed):
    import click as reference
    from click.testing import CliRunner as ReferenceRunner

    def execute(module, runner):
        kwargs = {"is_flag": False, "flag_value": "implicit"} if optional else {}
        command = module.Command("normalize", params=[
            module.Option(["-n", "--name"], **kwargs),
            module.Option(["-v", "--verbose"], is_flag=True),
        ], callback=module.pass_context(lambda ctx, **values: (values, ctx.args)),
           context_settings={"token_normalize_func": str.lower,
                             "allow_extra_args": True,
                             "ignore_unknown_options": True,
                             "allow_interspersed_args": interspersed})
        result = runner.invoke(command, tokens, standalone_mode=False)
        return result.return_value, result.output, result.exit_code

    assert execute(click, CliRunner()) == execute(reference, ReferenceRunner())
