"""A combined binding preserves the former separate entry points and hooks."""
from __future__ import annotations

import gc
import importlib
import builtins
from types import SimpleNamespace

import pytest

from zclick import _native
from zclick import parser as adapter


def namespace():
    return {"_Option": adapter._Option, "_ParsingState": adapter._ParsingState,
            "UNSET": adapter.UNSET, "_flag_needs_value": adapter._flag_needs_value,
            "_make_parser_normalizer": adapter._make_parser_normalizer}


def separated(parser, argv, definitions, bindings):
    plan = _native.ParserPlan.from_definitions(definitions, bindings["_Option"], parser._plan)
    parser._plan = plan
    normalize = None
    if parser.ctx is not None and parser.ctx.token_normalize_func is not None:
        normalize = bindings["_make_parser_normalizer"](parser)
    state = bindings["_ParsingState"]([])
    leftovers, error = plan.parse_into(
        argv, definitions, state, bindings["UNSET"], bindings["_flag_needs_value"],
        bool(parser.allow_interspersed_args), bool(parser.ignore_unknown_options),
        normalizer=normalize, original_args=argv,
    )
    return state, leftovers, error


@pytest.mark.parametrize("normalize", [False, True])
@pytest.mark.parametrize("failure", [None, "state", "flag"])
def test_combined_entry_keeps_getter_constructor_flag_and_action_order(normalize, failure):
    def observe(entry):
        trace = []

        class Parser(adapter._OptionParser):
            def __getattribute__(self, name):
                if name in {"_plan", "ctx", "allow_interspersed_args", "ignore_unknown_options"}:
                    trace.append(("get", name))
                return super().__getattribute__(name)

            def __setattr__(self, name, value):
                if name == "_plan":
                    trace.append(("set", name))
                return super().__setattr__(name, value)

        class Option(adapter._Option):
            def __getattribute__(self, name):
                if name in {"opts", "nargs", "takes_value", "obj"}:
                    trace.append(("definition", name))
                return super().__getattribute__(name)

            def process(self, value, state):
                trace.append("process")
                return super().process(value, state)

        class State(adapter._ParsingState):
            def __init__(self, args):
                trace.append("state")
                if failure == "state":
                    raise RuntimeError("state failure")
                super().__init__(args)

        class Flag:
            def __init__(self, label, value):
                self.label, self.value = label, value

            def __bool__(self):
                trace.append(self.label)
                if failure == "flag" and self.label == "interspersed":
                    raise RuntimeError("flag failure")
                return self.value

        def normalizer(value):
            trace.append(("normalize", value))
            return value.lower()

        context = SimpleNamespace(token_normalize_func=normalizer,
                                  allow_interspersed_args=True,
                                  ignore_unknown_options=False) if normalize else None
        parser = Parser(context)
        parser.allow_interspersed_args = Flag("interspersed", True)
        parser.ignore_unknown_options = Flag("unknown", False)
        definitions = [Option(None, ["--value"], "out")]
        bindings = namespace()
        bindings["_ParsingState"] = State
        argv = ["--VALUE=x" if normalize else "--value=x"]
        trace.clear()
        try:
            state, rest, error = entry(parser, argv, definitions, bindings)
            result = (state.opts, rest, error)
        except RuntimeError as error:
            result = (type(error).__name__, str(error))
        plan_exists = parser._plan is not None
        return result, argv, trace, plan_exists

    expected = observe(separated)
    assert observe(_native.parse_live) == expected
    assert expected[-1] is True


def test_constructor_can_reenter_after_new_plan_is_published():
    parser = adapter._OptionParser()
    definitions = [adapter._Option(None, ["--value"], "out")]
    bindings = namespace()
    seen = []
    nested = False

    def state_factory(args):
        nonlocal nested
        assert parser._plan is not None
        if not nested:
            nested = True
            state, rest, error = _native.parse_live(parser, ["--value", "inner"], definitions, bindings)
            assert rest == [] and error is None
            seen.append(state.opts)
        return adapter._ParsingState(args)

    bindings["_ParsingState"] = state_factory
    state, rest, error = _native.parse_live(parser, ["--value", "outer"], definitions, bindings)
    assert rest == [] and error is None
    assert state.opts == {"out": "outer"}
    assert seen == [{"out": "inner"}]


def test_definition_getter_can_replace_the_later_state_constructor():
    parser = adapter._OptionParser()
    bindings = namespace()
    seen = []

    def replacement(args):
        seen.append("replacement")
        return adapter._ParsingState(args)

    class Option(adapter._Option):
        def __getattribute__(self, name):
            if name == "nargs":
                bindings["_ParsingState"] = replacement
            return super().__getattribute__(name)

    definitions = [Option(None, ["--value"], "out")]
    state, rest, error = _native.parse_live(parser, ["--value=x"], definitions, bindings)
    assert rest == [] and error is None and state.opts == {"out": "x"}
    assert seen == ["replacement"]


def test_replaced_state_factory_is_released_before_flag_truthiness(monkeypatch):
    def observe(package):
        module = importlib.import_module(f"{package}.parser")
        original_state = module._ParsingState
        parser = module._OptionParser()
        parser.add_option(SimpleNamespace(_flag_needs_value=False), ["--value"], "out")
        trace = []
        settings = {"allow": True}

        class Flag:
            def __bool__(self):
                # Makes the lifetime check meaningful on tracing-GC runtimes.
                gc.collect()
                trace.append(("flag", settings["allow"]))
                return settings["allow"]

        class Factory:
            def __call__(self, args):
                trace.append("state")
                module._ParsingState = original_state
                return original_state(args)

            def __del__(self):
                settings["allow"] = False
                trace.append("release")

        parser.allow_interspersed_args = Flag()
        with monkeypatch.context() as patch:
            patch.setattr(module, "_ParsingState", Factory())
            opts, rest, order = parser.parse_args(["plain", "--value", "payload"])
        return opts, rest, order, trace

    expected = observe("click")
    assert expected == ({}, ["plain", "--value", "payload"], [],
                        ["state", "release", ("flag", False)])
    assert observe("zclick") == expected


def test_state_global_falls_back_to_definition_time_builtins(monkeypatch):
    def observe(package):
        module = importlib.import_module(f"{package}.parser")
        original_state = module._ParsingState
        parser = module._OptionParser()
        parser.add_option(SimpleNamespace(_flag_needs_value=False), ["--value"], "out")
        trace = []

        def factory(args):
            trace.append("builtins-state")
            return original_state(args)

        with monkeypatch.context() as patch:
            patch.delattr(module, "_ParsingState")
            patch.setattr(builtins, "_ParsingState", factory, raising=False)
            # The existing function keeps its original builtins dictionary.
            patch.setattr(module, "__builtins__", {})
            opts, rest, _ = parser.parse_args(["--value", "payload"])
        return opts, rest, trace

    expected = observe("click")
    assert expected == ({"out": "payload"}, [], ["builtins-state"])
    assert observe("zclick") == expected
