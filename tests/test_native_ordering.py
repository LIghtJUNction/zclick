"""The ordering optimization must match Click's live index and stable sort."""
from __future__ import annotations

import importlib
import sys

import pytest

from zclick import _native


@pytest.mark.parametrize("package", ["click", "zclick"])
@pytest.mark.parametrize("reverse", [False, True])
def test_repeated_parameter_declarations_share_first_invocation(package, reverse):
    cli = importlib.import_module(package)
    seen = []

    def record(ctx, parameter, value):
        seen.append(parameter.name)
        return value

    first = cli.Option(["--a"], callback=record)
    second = cli.Option(["--b"], callback=record)
    command = cli.Command("order", params=[first, second, first], add_help_option=False)
    argv = ["--b", "2", "--a", "1"] if reverse else ["--a", "1", "--b", "2"]
    with pytest.warns(UserWarning, match="The parameter --a is used more than once"):
        command.main(argv, standalone_mode=False)
    assert seen == (["b", "a", "a"] if reverse else ["a", "a", "b"])


@pytest.mark.parametrize("reverse", [False, True])
def test_custom_parameter_equality_keeps_python_index_calls(reverse):
    def observe(package):
        cli = importlib.import_module(package)
        core = importlib.import_module(f"{package}.core")
        trace = []

        class Equal(cli.Option):
            def __eq__(self, other):
                trace.append((self.name, other.name))
                return True

        first, second = Equal(["--a"]), Equal(["--b"])
        invocation = [second, first] if reverse else [first, second]
        ordered = core.iter_params_for_processing(invocation, [first, second])
        return [parameter.name for parameter in ordered], trace

    expected = observe("click")
    assert expected[0] == ["a", "b"]
    assert observe("zclick") == expected


@pytest.mark.parametrize("truthiness", [False, True])
def test_eager_hooks_mutate_invocation_before_later_index_calls(truthiness):
    def observe(package):
        core = importlib.import_module(f"{package}.core")
        invocation = []
        trace = []

        def eager(name):
            trace.append(name)
            if name == "a":
                invocation.reverse()
            return False

        class Truth:
            def __init__(self, name):
                self.name = name

            def __bool__(self):
                return eager(self.name)

        class Parameter:
            def __init__(self, name):
                self.name = name
                if truthiness:
                    self.is_eager = Truth(name)

        if not truthiness:
            Parameter.is_eager = property(lambda self: eager(self.name))
        first, second, third = [Parameter(name) for name in "abc"]
        invocation[:] = [second, first, third]
        ordered = core.iter_params_for_processing(invocation, [first, second, third])
        return [parameter.name for parameter in ordered], trace

    expected = observe("click")
    assert expected == (["c", "a", "b"], ["a", "b", "c"])
    assert observe("zclick") == expected


def test_custom_metaclass_attribute_hooks_are_not_used_for_classification():
    def observe(package):
        core = importlib.import_module(f"{package}.core")
        trace = []

        class Meta(type):
            def __getattribute__(cls, name):
                trace.append(name)
                return super().__getattribute__(name)

        class Parameter(metaclass=Meta):
            def __init__(self, name):
                self.name = name
                self.is_eager = False

        first, second = Parameter("a"), Parameter("b")
        trace.clear()
        ordered = core.iter_params_for_processing([second, first], [first, second])
        return [parameter.name for parameter in ordered], trace

    expected = observe("click")
    assert expected == (["b", "a"], [])
    assert observe("zclick") == expected


@pytest.mark.parametrize("declaration_kind", ["list_subclass", "iterator"])
def test_custom_containers_preserve_index_iteration_and_sort_protocol(declaration_kind):
    def observe(package):
        core = importlib.import_module(f"{package}.core")
        trace = []

        class Parameter:
            def __init__(self, name):
                self.name = name
                self.is_eager = False

        class Rank:
            def __init__(self, rank):
                self.rank = rank

            def __lt__(self, other):
                trace.append(("lt", self.rank, other.rank))
                return self.rank < other.rank

        class Invocation(list):
            def index(self, item):
                trace.append(("index", item.name))
                return Rank(-super().index(item))

        class Declaration(list):
            def __iter__(self):
                trace.append("iter")
                return super().__iter__()

            def __len__(self):
                trace.append("len")
                return super().__len__()

        first, second = Parameter("a"), Parameter("b")
        declarations = Declaration([first, second])
        if declaration_kind == "iterator":
            declarations = iter(declarations)
        trace.clear()
        ordered = core.iter_params_for_processing(Invocation([first, second]), declarations)
        return [parameter.name for parameter in ordered], trace

    expected = observe("click")
    assert expected[0] == ["b", "a"]
    assert observe("zclick") == expected


def test_standard_option_and_argument_follow_the_runtime_ordering_policy():
    import zclick

    first, second = zclick.Option(["--a"]), zclick.Argument(["b"])
    ordered = _native.order_parameters([first, second], [first, second, first])
    if sys.implementation.name != "cpython":
        # cpyext materializes type wrappers through Python metaclass hooks;
        # its native classifier must decline before examining those types.
        assert ordered is None
        ordered = zclick.core.iter_params_for_processing([first, second], [first, second, first])
    else:
        assert ordered is not None
    assert len(ordered) == 3
    assert all(actual is expected for actual, expected in zip(ordered, [first, first, second]))


def test_nonstring_dictionary_keys_do_not_call_equality_during_classification():
    calls = []

    class Parameter:
        def __init__(self):
            self.is_eager = False

    class Collision:
        def __hash__(self):
            return hash("is_eager")

        def __eq__(self, other):
            calls.append(other)
            return False

    parameter = Parameter()
    parameter.__dict__[Collision()] = "foreign"
    calls.clear()
    assert _native.order_parameters([parameter], [parameter]) is None
    assert calls == []
