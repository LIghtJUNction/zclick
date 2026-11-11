"""Native semantics regression and differential checks against the locked reference.

Click is a development-only oracle. No runtime zclick module imports it.
"""
from __future__ import annotations

import gc
import random
from types import SimpleNamespace
import weakref

import click
from click.parser import _OptionParser
from click._utils import UNSET
import pytest

from zclick import _native


@pytest.mark.parametrize("positions", [(1,), (-1,), (1, -1, 1), (2,), (1, 2)])
@pytest.mark.parametrize("interspersed", [False, True])
@pytest.mark.parametrize("ignore_unknown", [False, True])
def test_native_matches_reference_parser(positions, interspersed, ignore_unknown):
    specs = [(0, ["-v", "--verbose"], 1, True),
             (1, ["-n", "--num"], 1, False),
             (2, ["--pair"], 2, False),
             (3, ["+q", "/quiet"], 1, True)]
    specs += [(4 + i, [], count, False) for i, count in enumerate(positions)]
    objects = [SimpleNamespace(_flag_needs_value=False) for _ in specs]
    parser = _OptionParser()
    parser.allow_interspersed_args = interspersed
    parser.ignore_unknown_options = ignore_unknown
    for index, names, count, flag in specs:
        if names:
            parser.add_option(objects[index], names, str(index),
                              action="append_const" if flag else "append",
                              nargs=count, const=True)
        else:
            parser.add_argument(objects[index], str(index), nargs=count)
    rng = random.Random(18819)
    tokens = ["-v", "-vv", "--verbose", "-n12", "-n=3", "--num", "-1",
              "--num=-2", "--pair", "--pair=x", "value", "", "中", "\udcff",
              "--", "-x", "--wat", "-xvy", "--verbose=yes", "+q", "/quiet"]
    for _ in range(128):
        args = [rng.choice(tokens) for _ in range(rng.randrange(10))]
        actual, remaining, order, error = _native.parse(
            specs, args, interspersed, ignore_unknown)
        try:
            expected, expected_remaining, expected_order = parser.parse_args(args.copy())
        except click.NoSuchOption:
            assert error and error["kind"] == "unknown_option", args
            continue
        except click.BadOptionUsage as exc:
            kind = "unexpected_value" if "does not take a value" in exc.message else "missing_value"
            assert error and error["kind"] == kind, (args, str(exc), error)
            continue
        except click.BadArgumentUsage:
            assert error and error["kind"] == "argument_arity", args
            continue
        assert error is None, (args, error)
        normalized = {}
        for index, rows in actual.items():
            _, names, count, flag = specs[index]
            if names:
                normalized[str(index)] = [True if flag else row[0] if count == 1 else row for row in rows]
            else:
                row = rows[-1]
                normalized[str(index)] = row[0] if count == 1 and row else row if row else UNSET
        assert normalized == expected, args
        assert remaining == expected_remaining, args
        expected_order = [next(i for i, obj in enumerate(objects) if obj is item) for item in expected_order]
        assert order == expected_order, args


def test_original_string_objects_and_surrogates_are_preserved(record_property):
    class UserText(str):
        pass

    value = UserText("\udcff-tail")
    reference = weakref.ref(value)
    values, _, _, error = _native.parse([(0, ["--file"], 1, False)], ["--file", value])
    assert error is None
    assert values[0][0][0] is value
    del values, value
    for collection_pass in range(1, 6):
        gc.collect()
        if reference() is None:
            break
    record_property("gc_collection_passes", collection_pass)
    assert reference() is None
    values, _, _, error = _native.parse([(0, ["--file"], 1, False)], ["--file=\udcff-tail"])
    assert error is None
    assert values[0][0][0] == "\udcff-tail"


def test_distinct_empty_string_subclasses_keep_argument_identity():
    class Text(str):
        pass
    a, b = Text(""), Text("")
    values, _, _, error = _native.parse([(0, ["--a"], 1, False), (1, ["--b"], 1, False)], ["--a", a, "--b", b])
    assert error is None
    assert values[0][0][0] is a
    assert values[1][0][0] is b


def test_runtime_definitions_are_rebuilt_and_not_limited_to_256():
    definitions = [(i, [f"--option{i}"], 1, False) for i in range(1025)]
    result = _native.parse(definitions, ["--option1024=last"])
    assert result[0] == {1024: [("last",)]}
    definitions[1024] = (1024, ["--changed"], 1, False)
    assert _native.parse(definitions, ["--option1024=last"])[3]["kind"] == "unknown_option"
    assert _native.parse(definitions, ["--changed=last"])[0] == {1024: [("last",)]}


@pytest.mark.parametrize("width", [32, 60, 100])
@pytest.mark.parametrize("preserve", [False, True])
def test_native_wrapping_matches_reference(width, preserve):
    from click.formatting import wrap_text

    rng = random.Random(9419)
    cases = ["\x1b[31malpha\x1b[0m beta gamma", "\x1b[31mabcdefghij\x1b[0m",
             "\x08\n  A\n   B", "First paragraph.\n\n  Second paragraph.\n", "\udcff a b"]
    cases += ["".join(rng.choice(["hello", "world", " ", "  ", "\n", "-", "--", "abcdefghi", "é", "中"])
                      for _ in range(rng.randrange(1, 10))) for _ in range(128)]
    for text in cases:
        assert _native.wrap_text(text, width, "  ", "  ", preserve) == wrap_text(
            text, width, "  ", "  ", preserve), repr(text)


def test_native_action_hooks_can_reenter_and_keep_python_objects():
    from zclick.parser import _Option, _Argument, _ParsingState, _flag_needs_value
    from zclick._utils import UNSET as LOCAL_UNSET
    events = []
    marker = object()
    class CustomOption(_Option):
        def process(self, value, state):
            events.append(value)
            # A nested native parse must have independent state.
            assert _native.parse([(0, ["--nested"], 1, True)], ["--nested"])[2] == [0]
            return super().process(value, state)
    definitions = [CustomOption(None, ["--number"], "number", action="append"),
                   _Option(None, ["--flag"], "flag", action="store_const", const=marker),
                   _Argument(None, "tail", nargs=-1)]
    specs = [(0, ["--number"], 1, False), (1, ["--flag"], 1, True), (2, [], -1, False)]
    state = _ParsingState([])
    leftovers, error = _native.parse_into(specs, ["--number=1", "--number", "2", "--flag", "x"],
                                         definitions, state, LOCAL_UNSET, _flag_needs_value)
    assert error is None and leftovers == []
    assert state.opts == {"number": ["1", "2"], "flag": marker, "tail": ("x",)}
    assert events == ["1", "2"]


@pytest.mark.parametrize("args", [["--zero"], ["--zero=x"], ["-zx"], ["--zero=--flag"], ["-z--flag"]])
def test_zero_arity_values_follow_reference_requeue_semantics(args):
    parser = _OptionParser()
    obj = SimpleNamespace(_flag_needs_value=False)
    parser.add_option(obj, ["-z", "--zero"], "zero", action="store", nargs=0)
    parser.add_option(obj, ["--flag"], "flag", action="store_const", const=True)
    expected, remaining, _ = parser.parse_args(args.copy())
    values, leftovers, _, error = _native.parse(
        [(0, ["-z", "--zero"], 0, False), (1, ["--flag"], 1, True)], args)
    assert error is None
    actual = {"zero": ()} if 0 in values else {}
    if 1 in values:
        actual["flag"] = True
    assert actual == expected
    assert leftovers == remaining


def test_normalizer_reentry_and_exception_identity():
    failure = ValueError("normalizer failure")
    seen = []
    def normalize(spelling):
        assert _native.parse([(0, ["--nested"], 1, True)], ["--nested"])[2] == [0]
        seen.append(spelling)
        if spelling == "--FAIL":
            raise failure
        return spelling.lower()
    args = ["--OK", "--FAIL", "remaining"]
    with pytest.raises(ValueError) as caught:
        _native.parse([(0, ["--ok"], 1, True)], args, normalizer=normalize, original_args=args)
    assert caught.value is failure
    assert seen == ["--OK", "--FAIL"]
    assert args == ["remaining"]


def test_parameter_eagerness_uses_python_truthiness():
    class Eager:
        def __bool__(self):
            assert _native.parse([], [])[3] is None
            return True
    assert _native.processing_order([0, Eager(), None], [0, 2]) == [1, 0, 2]
