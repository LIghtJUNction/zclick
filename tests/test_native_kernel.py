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


def test_original_string_objects_and_surrogates_are_preserved():
    class UserText(str):
        pass

    value = UserText("\udcff-tail")
    reference = weakref.ref(value)
    values, _, _, error = _native.parse([(0, ["--file"], 1, False)], ["--file", value])
    assert error is None
    assert values[0][0][0] is value
    del values, value
    gc.collect()
    assert reference() is None
    values, _, _, error = _native.parse([(0, ["--file"], 1, False)], ["--file=\udcff-tail"])
    assert error is None
    assert values[0][0][0] == "\udcff-tail"


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
