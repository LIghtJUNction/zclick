"""Owned plan reuse must preserve mutation, provenance and Python hooks."""
from __future__ import annotations

import gc
import copy
import importlib
import pickle
from types import SimpleNamespace
import weakref

import pytest

from zclick import _native
from zclick._utils import FLAG_NEEDS_VALUE, UNSET
from zclick.parser import _Argument, _Option, _ParsingState


def make_definitions():
    return [_Option(SimpleNamespace(_flag_needs_value=False), ["--value", "-v"], "value"),
            _Argument(SimpleNamespace(), "tail", -1)]


def invoke(plan, definitions, argv):
    state = _ParsingState([])
    remaining, error = plan.parse_into(argv, definitions, state, UNSET, FLAG_NEEDS_VALUE)
    assert error is None
    return state, remaining


@pytest.mark.parametrize("change", ["alias", "append_alias", "arity", "action", "optional", "append", "remove", "replace_kind"])
def test_refresh_observes_every_parsing_field(change):
    definitions = make_definitions()
    first = _native.ParserPlan.from_definitions(definitions, _Option)
    assert _native.ParserPlan.from_definitions(definitions, _Option, first) is first
    if change == "alias":
        definitions[0].opts[0] = "--changed"
    elif change == "append_alias":
        definitions[0].opts.append("/value")
    elif change == "arity":
        definitions[0].nargs = 2
    elif change == "action":
        definitions[0].action = "store_const"
    elif change == "optional":
        definitions[0].obj._flag_needs_value = True
    elif change == "append":
        definitions.append(_Option(None, ["--more"], "more"))
    elif change == "remove":
        definitions.pop()
    else:
        definitions[1] = _Option(None, ["--tail"], "tail")
    assert not first.matches_definitions(definitions, _Option)
    second = _native.ParserPlan.from_definitions(definitions, _Option, first)
    assert second is not first
    assert second.matches_definitions(definitions, _Option)
    assert _native.ParserPlan.from_definitions(definitions, _Option, second) is second


def test_refresh_does_not_retain_action_values_or_python_definitions():
    definitions = make_definitions()
    plan = _native.ParserPlan.from_definitions(definitions, _Option)
    definitions[0].dest = "renamed"
    definitions[0].action = "append"  # Same parsing shape, a different live action.
    assert _native.ParserPlan.from_definitions(definitions, _Option, plan) is plan
    state, remaining = invoke(plan, definitions, ["--value", "first", "-vsecond", "tail"])
    assert state.opts == {"renamed": ["first", "second"], "tail": ("tail",)}
    assert remaining == []
    reference = weakref.ref(definitions[0])
    del state, definitions
    for _ in range(5):
        gc.collect()
        if reference() is None:
            break
    assert reference() is None
    assert plan.parse(["--value=third"])[0][0] == [("third",)]


def test_refresh_reads_properties_once_even_on_a_changed_plan():
    seen = []

    class Watched(_Option):
        def __getattribute__(self, name):
            if name in {"opts", "nargs", "takes_value", "obj"}:
                seen.append(name)
            return super().__getattribute__(name)

    definition = Watched(SimpleNamespace(_flag_needs_value=False), ["--a"], "a")
    plan = _native.ParserPlan.from_definitions([definition], _Option)
    definition.nargs = 2
    seen.clear()
    updated = _native.ParserPlan.from_definitions([definition], _Option, plan)
    assert updated is not plan
    assert seen == ["opts", "nargs", "takes_value", "obj"]


def test_plan_normalizer_and_actions_can_reenter_the_same_plan():
    plan = _native.ParserPlan([(0, ["--value"], 1, False)])
    seen = []

    def normalize(spelling):
        assert plan.parse(["--value=nested"])[0] == {0: [("nested",)]}
        return spelling.lower()

    class Reenter(_Option):
        def process(self, value, state):
            seen.append(plan.parse(["--value", value])[0][0][0][0])
            super().process(value, state)

    definitions = [Reenter(None, ["--value"], "value")]
    state = _ParsingState([])
    assert plan.parse_into(["--VALUE=outer"], definitions, state, UNSET,
                           FLAG_NEEDS_VALUE, normalizer=normalize) == ([], None)
    assert state.opts == {"value": "outer"} and seen == ["outer"]


def test_plan_provenance_distinguishes_empty_objects_and_borrowed_surrogates():
    class Text(str):
        def encode(self, *args, **kwargs):
            raise AssertionError("str subclass override must not change parser bytes")

    first, second, surrogate = Text(""), Text(""), Text("\udcff-tail")
    plan = _native.ParserPlan([(0, [], -1, False)])
    values, remaining, order, error = plan.parse([first, second, surrogate])
    assert error is None and remaining == [] and order == [0]
    assert all(actual is expected for actual, expected in zip(values[0][0], (first, second, surrogate)))
    assert plan.parse(["later"])[0] == {0: [("later",)]}


def test_plan_schema_owns_names_without_retaining_the_source_container():
    options = ["--initial"]
    plan = _native.ParserPlan([(0, options, 1, False)])
    options[0] = "--changed"
    assert plan.parse(["--initial=x"])[0] == {0: [("x",)]}
    assert plan.parse(["--changed=x"])[3]["kind"] == "unknown_option"


def test_order_parameters_preserves_duplicate_identity_and_truthiness():
    from zclick.core import iter_params_for_processing

    calls = []

    class Parameter:
        def __init__(self, is_eager):
            self.is_eager = is_eager

    class Eager:
        def __bool__(self):
            calls.append("eager")
            assert _native.ParserPlan([]).parse([])[3] is None
            return True

    first = Parameter(False)
    eager = Parameter(Eager())
    last = Parameter(False)
    # Every repeated declaration shares its first invocation position.
    result = iter_params_for_processing([last, first, last], [first, eager, last, first])
    assert result == [eager, last, first, first]
    assert result[2] is first and result[3] is first
    assert calls == ["eager"]


def _pickle_command_callback(x):
    return x


@pytest.mark.parametrize("package", ["click", "zclick"])
@pytest.mark.parametrize("method", ["pickle", "deepcopy"])
def test_warm_command_can_be_pickled_or_deepcopied(package, method):
    cli = importlib.import_module(package)
    command = cli.Command("copy", add_help_option=False,
                          params=[cli.Option(["--x", "--surrogate-\udcff"], type=int)],
                          callback=_pickle_command_callback)
    assert command.main(["--x", "17"], standalone_mode=False) == 17
    restored = pickle.loads(pickle.dumps(command)) if method == "pickle" else copy.deepcopy(command)
    assert restored is not command and restored.params[0] is not command.params[0]
    assert restored.main(["--surrogate-\udcff", "23"], standalone_mode=False) == 23
    restored.params[0].opts = ["--changed"]
    assert restored.main(["--changed", "29"], standalone_mode=False) == 29
    assert command.main(["--x", "31"], standalone_mode=False) == 31


@pytest.mark.parametrize("method", ["pickle", "deepcopy"])
def test_plan_roundtrip_preserves_every_structural_field(method):
    plan = _native.ParserPlan([(42, ["--surrogate-\udcff", "--alias"], 1, False, True),
                               (7, ["-q"], 1, True, False),
                               (99, [], -1, False, False)])
    restored = pickle.loads(pickle.dumps(plan)) if method == "pickle" else copy.deepcopy(plan)
    assert restored is not plan
    for argv in (["--surrogate-\udcff", "\udcfe", "-q", "tail"],
                 ["--alias"], ["--alias=attached"], ["--", "-q"]):
        assert restored.parse(argv) == plan.parse(argv)
