"""Inherited definitions and dictionary callbacks must remain live."""
from __future__ import annotations

import abc
import importlib
from pathlib import Path
import subprocess
import sys

import pytest


def warm_command(cli):
    command = cli.Command(
        "large", add_help_option=False,
        params=[cli.Option([f"--v{i}"], type=int) for i in range(70)],
        callback=lambda **values: values,
    )
    args = [item for i in range(70) for item in (f"--v{i}", str(i))]

    def invoke():
        return command.main(args, prog_name="large", standalone_mode=False)

    assert invoke() == {f"v{i}": i for i in range(70)}
    return command, invoke


def changed_parameter_bases_keep_super_dispatch(cli, monkeypatch):
    _, invoke = warm_command(cli)

    class Alternate(cli.Parameter):
        def process_value(self, ctx, value):
            return super().process_value(ctx, value) + 100

    bases = cli.Option.__bases__
    try:
        cli.Option.__bases__ = (Alternate,)
        assert invoke() == {f"v{i}": i + 100 for i in range(70)}
    finally:
        cli.Option.__bases__ = bases


def mutable_ancestor_attribute_hook_is_observed(cli, monkeypatch):
    _, invoke = warm_command(cli)
    seen = []

    def read_attribute(self, name):
        if type(self) is cli.Option and name == "required":
            seen.append(object.__getattribute__(self, "name"))
        return object.__getattribute__(self, name)

    monkeypatch.setattr(abc.ABC, "__getattribute__", read_attribute, raising=False)
    assert invoke()["v69"] == 69
    assert set(seen) == {f"v{i}" for i in range(70)}


def guard_does_not_add_metaclass_attribute_calls(cli, monkeypatch):
    _, invoke = warm_command(cli)
    seen = []

    def read_class_attribute(cls, name):
        if cls is cli.Option and name == "__dict__":
            seen.append(name)
        return type.__getattribute__(cls, name)

    monkeypatch.setattr(type(cli.Option), "__getattribute__", read_class_attribute)
    assert invoke()["v69"] == 69
    assert seen == []


def dictionary_key_callback_can_change_parameter_callback(cli, monkeypatch):
    command, invoke = warm_command(cli)
    seen = []

    def changed_callback(ctx, param, value):
        seen.append("callback")
        return value + 100

    class CollidingKey:
        def __init__(self, ctx):
            self.ctx = ctx

        def __hash__(self):
            return hash("v1")

        def __eq__(self, other):
            if other == "v1":
                seen.append("collision")
                self.ctx.params.pop(self)
                command.params[1].callback = changed_callback
            return False

    def install_key(ctx, param, value):
        ctx.params[CollidingKey(ctx)] = "temporary"
        return value

    command.params[0].callback = install_key
    result = invoke()
    assert result["v1"] == 101
    assert seen == ["collision", "callback"]


def discarded_handler_value_lives_until_next_assignment(cli, monkeypatch):
    command, invoke = warm_command(cli)
    original = command.params[0].handle_parse_result

    class Marker:
        def __del__(self):
            command.params[1].callback = lambda ctx, param, value: value + 100

    def first(ctx, opts, args):
        _, remaining = original(ctx, opts, args)
        return Marker(), remaining

    command.params[0].handle_parse_result = first
    # The loop's ``_`` variable keeps Marker alive through v1's handler. On
    # reference-counted interpreters its finalizer runs only when v1 finishes.
    assert invoke()["v1"] == 1


def processing_list_append_is_visible_to_the_running_loop(cli, monkeypatch):
    command, invoke = warm_command(cli)
    core = importlib.import_module(f"{cli.__name__}.core")
    monkeypatch.setattr(
        core, "iter_params_for_processing",
        lambda invocation_order, declaration_order: command.params,
    )

    def append_parameter(ctx, param, value):
        command.params.append(cli.Option(["--late"], type=int, default=999))
        return value

    command.params[0].callback = append_parameter
    assert invoke()["late"] == 999


@pytest.mark.parametrize("module", ["click", "zclick"])
@pytest.mark.parametrize("scenario", [
    "changed_parameter_bases_keep_super_dispatch",
    "mutable_ancestor_attribute_hook_is_observed",
    "guard_does_not_add_metaclass_attribute_calls",
    "dictionary_key_callback_can_change_parameter_callback",
    "discarded_handler_value_lives_until_next_assignment",
    "processing_list_append_is_visible_to_the_running_loop",
])
def test_guard_edges_in_fresh_interpreter(module, scenario):
    # Restoring __bases__ creates a new MRO identity. Reusing that interpreter
    # would leave the conservative guard disabled and could hide later bugs.
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), module, scenario],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


if __name__ == "__main__":
    with pytest.MonkeyPatch.context() as patch:
        globals()[sys.argv[2]](importlib.import_module(sys.argv[1]), patch)
