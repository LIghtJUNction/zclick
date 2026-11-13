"""Native parsing plans must preserve every Python action customization boundary."""
from __future__ import annotations

import json
import importlib
import subprocess
import sys
from types import MethodType, SimpleNamespace

import pytest

from zclick import _native
from zclick._utils import FLAG_NEEDS_VALUE, UNSET
from zclick.parser import _Argument, _Option, _ParsingState


@pytest.mark.parametrize("action", ["store", "store_const", "append", "append_const", "count", "invalid"])
def test_action_attribute_reads_follow_click_branch_order(action):
    def observe(package):
        module = importlib.import_module(f"{package}.parser")
        trace = []

        class Watched(module._Option):
            def __getattribute__(self, name):
                if name in {"action", "dest", "const", "obj"}:
                    trace.append(name)
                return super().__getattribute__(name)

        option = Watched("parameter", ["--value"], "out", action=action, const=7)
        state = module._ParsingState([])
        trace.clear()
        try:
            option.process(3, state)
        except ValueError as error:
            failure = str(error)
        else:
            failure = None
        return state.opts, state.order, trace, failure

    expected = observe("click")
    assert observe("zclick") == expected
    if action == "store":
        assert expected == ({"out": 3}, ["parameter"], ["action", "dest", "obj"], None)


def test_action_comparisons_are_not_grouped_or_cached():
    def observe(package):
        module = importlib.import_module(f"{package}.parser")
        compared = []

        class Action:
            def __eq__(self, other):
                compared.append(other)
                return other == "store"

        option = module._Option("parameter", ["--value"], "out", action=Action())
        state = module._ParsingState([])
        option.process("payload", state)
        return state.opts, state.order, compared

    expected = observe("click")
    assert expected == ({"out": "payload"}, ["parameter"], ["store"])
    assert observe("zclick") == expected


def run(definitions, argv, *, state=None, plan=None, prepared=True):
    if state is None:
        state = _ParsingState([])
    if prepared:
        if plan is None:
            plan = _native.ParserPlan.from_definitions(definitions, _Option)
        rest, error = plan.parse_into(argv, definitions, state, UNSET, FLAG_NEEDS_VALUE)
    else:
        specs = [(i, p.opts if isinstance(p, _Option) else [], p.nargs,
                  isinstance(p, _Option) and not p.takes_value,
                  bool(getattr(p.obj, "_flag_needs_value", False)))
                 for i, p in enumerate(definitions)]
        rest, error = _native.parse_into(specs, argv, definitions, state, UNSET, FLAG_NEEDS_VALUE)
    assert rest == [] and error is None
    return state


@pytest.mark.parametrize("action, argv", [
    ("store", ["--value=one", "--value", "two"]),
    ("store_const", ["--value", "--value"]),
    ("count", ["--value", "--value", "--value"]),
    ("append", ["--value=one", "--value", "two"]),
    ("append_const", ["--value", "--value"]),
])
def test_actions_equal_the_live_path(action, argv):
    definition = _Option(None, ["--value"], "value", action=action, const=object())
    expected = run([definition], argv, prepared=False)
    actual = run([definition], argv)
    assert actual.opts == expected.opts
    assert actual.order == expected.order


def test_optional_missing_value_and_scalar_argument_keep_sentinels_and_identity():
    definitions = [_Option(SimpleNamespace(_flag_needs_value=True), ["--value"], "value"),
                   _Option(None, ["--flag"], "flag", action="count"),
                   _Argument(None, "tail")]
    state = run(definitions, ["--value", "--flag", "tail"])
    assert state.opts == {"value": FLAG_NEEDS_VALUE, "flag": 1, "tail": "tail"}


@pytest.mark.parametrize("change", ["class_method", "instance_method", "code", "property"])
def test_changed_process_and_descriptors_fall_back(monkeypatch, change):
    definition = _Option(None, ["--value"], "value")
    plan = _native.ParserPlan.from_definitions([definition], _Option)
    seen = []

    def replacement(self, value, state):
        state.opts["changed"] = value
        state.order.append(self.obj)

    if change == "class_method":
        monkeypatch.setattr(_Option, "process", replacement)
    elif change == "instance_method":
        definition.process = MethodType(replacement, definition)
    elif change == "code":
        monkeypatch.setattr(_Option.process, "__code__", replacement.__code__)
    else:
        def nargs(self):
            seen.append("nargs")
            return 1
        monkeypatch.setattr(_Option, "nargs", property(nargs), raising=False)
    result = run([definition], ["--value=x"], plan=plan)
    if change == "property":
        assert result.opts == {"value": "x"}
        assert seen == ["nargs"]
    else:
        assert result.opts == {"changed": "x"}


def test_str_subclass_argument_comparison_is_not_bypassed():
    calls = []

    class Text(str):
        def __eq__(self, other):
            calls.append(other)
            return other == ()

    value = Text("text")
    state = run([_Argument(None, "value")], [value])
    assert state.opts["value"] is UNSET
    assert calls == [()]


def test_shared_destination_preserves_custom_add_and_subsequent_hook_change(monkeypatch):
    original = _Option.process
    calls = []

    def changed(self, value, state):
        calls.append(self.dest)
        return original(self, value, state)

    class Constant:
        def __add__(self, other):
            assert other == 1
            monkeypatch.setattr(_Option, "process", changed)
            return 42

    definitions = [_Option(None, ["--const"], "shared", "store_const", const=Constant()),
                   _Option(None, ["--count"], "shared", "count"),
                   _Option(None, ["--later"], "later")]
    state = run(definitions, ["--const", "--count", "--later=x"])
    assert state.opts == {"shared": 42, "later": "x"}
    assert calls == ["later"]


def test_input_list_subclass_iterator_remains_observable():
    calls = []

    class Arguments(list):
        def __iter__(self):
            calls.append("iter")
            return super().__iter__()

    value = _native.ParserPlan([(0, [], 1, False)]).parse(Arguments(["tail"]))
    assert value[0] == {0: [("tail",)]}
    assert calls == ["iter"]


def test_non_string_attribute_key_preserves_comparison_side_effects():
    option = _Option(None, ["--value"], "out")
    calls = []

    class Key:
        def __hash__(self):
            return hash("dest")

        def __eq__(self, other):
            if other == "dest":
                calls.append("dest")
                option.action = "count"
                return True
            return False

    del option.__dict__["dest"]
    option.__dict__[Key()] = "out"
    # CPython 3.14 can compare against a deleted shared-dict key during
    # insertion. Start measuring the parser after that fixture side effect.
    option.action = "store"
    calls.clear()
    result = run([option], ["--value", "value"])
    assert result.opts == {"out": "value"}
    assert calls == ["dest"]


@pytest.mark.parametrize("reset_after_insertion", [False, True])
def test_public_parser_dictionary_key_trace_matches_click(reset_after_insertion):
    # Use fresh interpreters for the same class/dict and bytecode warm-up state
    # on both sides. Record initialization separately from parser callbacks.
    script = r'''
import importlib
import json
import sys
from types import SimpleNamespace

parser_module = importlib.import_module(sys.argv[1] + ".parser")
parser = parser_module._OptionParser()
parser.add_option(SimpleNamespace(_flag_needs_value=False), ["--value"], "out")
option = parser._long_opt["--value"]
calls = []

class Key:
    def __hash__(self):
        return hash("dest")

    def __eq__(self, other):
        if other == "dest":
            calls.append("dest")
            option.action = "count"
            return True
        return False

del option.__dict__["dest"]
option.__dict__[Key()] = "out"
setup = {"action": option.action, "calls": calls.copy()}
if sys.argv[2] == "reset":
    option.action = "store"
    calls.clear()
opts, rest, order = parser.parse_args(["--value", "value"])
print(json.dumps({"setup": setup, "opts": opts, "rest": rest, "calls": calls,
                  "action": option.action, "order_length": len(order)}))
'''

    def observe(package):
        process = subprocess.run(
            [sys.executable, "-c", script, package,
             "reset" if reset_after_insertion else "unchanged"],
            capture_output=True, text=True, check=True,
        )
        return json.loads(process.stdout)

    expected = observe("click")
    actual = observe("zclick")
    assert actual == expected
    assert actual["action"] == "count"
    assert actual["order_length"] == 1
    if reset_after_insertion:
        assert actual["opts"] == {"out": "value"}
        assert actual["rest"] == []
        assert actual["calls"]
