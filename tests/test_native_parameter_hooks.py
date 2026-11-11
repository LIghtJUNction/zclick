"""Application hooks remain live after a large ordinary command is warmed."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(params=["click", "zclick"])
def cli(request):
    return importlib.import_module(request.param)


def command_and_args(cli, count=70):
    command = cli.Command("large", params=[cli.Option([f"--v{i}"], type=int) for i in range(count)], callback=lambda **v: v)
    args = [item for i in range(count) for item in (f"--v{i}", str(i))]
    invoke = lambda: command.main(args, prog_name="large", standalone_mode=False)
    assert invoke() == {f"v{i}": i for i in range(count)}
    return command, args, invoke


@pytest.mark.parametrize("hook", ["handle_parse_result", "consume_value", "process_value", "type_cast_value"])
def test_late_parameter_class_hooks(cli, monkeypatch, hook):
    command, _, invoke = command_and_args(cli)
    seen = []
    original = getattr(cli.Option, hook)

    def replacement(self, *args, **kwargs):
        seen.append(self.name)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(cli.Option, hook, replacement)
    assert invoke()["v69"] == 69
    assert all(f"v{i}" in seen for i in range(70))


def test_late_type_instance_override(cli, monkeypatch):
    command, _, invoke = command_and_args(cli)
    monkeypatch.setattr(command.params[0].type, "convert", lambda value, param, ctx: int(value) + 100)
    assert invoke() == {f"v{i}": i + 100 for i in range(70)}


def test_mutated_function_code_is_not_cached(cli, monkeypatch):
    _, _, invoke = command_and_args(cli)

    def replacement(self, ctx, value):
        return value if self.name == "_click_default_help" else "changed code"

    original = cli.Parameter.type_cast_value
    assert not original.__code__.co_freevars
    monkeypatch.setattr(original, "__code__", replacement.__code__)
    assert all(value == "changed code" for value in invoke().values())


def test_descriptors_installed_after_warmup_remain_observable(cli, monkeypatch):
    _, _, invoke = command_and_args(cli)
    seen = []

    def required(self):
        seen.append(self.name)
        return False

    monkeypatch.setattr(cli.Option, "required", property(required), raising=False)
    assert invoke()["v69"] == 69
    assert all(f"v{i}" in seen for i in range(70))


def test_callback_can_replace_conversion_for_later_parameters(cli, monkeypatch):
    command, _, invoke = command_and_args(cli)

    def callback(ctx, param, value):
        monkeypatch.setattr(cli.types.IntParamType, "convert", lambda self, value, param, ctx: int(value) + 1000)
        return value

    command.params[0].callback = callback
    result = invoke()
    assert result["v0"] == 0
    assert all(result[f"v{i}"] == i + 1000 for i in range(1, 70))


def test_truthy_dynamic_required_is_evaluated(cli):
    command, _, invoke = command_and_args(cli)
    seen = []

    class Required:
        def __bool__(self):
            seen.append(True)
            return False

    command.params[35].required = Required()
    assert invoke()["v35"] == 35
    assert seen == [True]


def test_custom_string_conversion_runs_once(cli):
    command, args, _ = command_and_args(cli)
    seen = []

    class Number(str):
        def __int__(self):
            seen.append(True)
            return 12345

    args[71] = Number("35")
    result = command.main(args, prog_name="large", standalone_mode=False)
    assert result["v35"] == 12345
    assert seen == [True]


def test_large_integer_float_and_string_results(cli):
    command, args, _ = command_and_args(cli)
    command.params[0].type = cli.types.StringParamType()
    command.params[1].type = cli.types.FloatParamType()
    args[1], args[3], args[5] = "Unicode 零\udcff", "1.25", str(10**180)
    result = command.main(args, prog_name="large", standalone_mode=False)
    assert result["v0"] == args[1]
    assert result["v1"] == 1.25
    assert result["v2"] == 10**180
