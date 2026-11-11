"""Generated parser interactions outside the original suite's example cases."""
from __future__ import annotations

import random
from types import SimpleNamespace

import pytest
from click.parser import _OptionParser as ReferenceParser
from zclick.parser import _OptionParser as NativeParser


def make_parser(cls, optional, interspersed, ignore_unknown, ctx=None):
    parser = cls(ctx)
    parser.allow_interspersed_args = interspersed
    parser.ignore_unknown_options = ignore_unknown
    for spellings, dest, action, nargs in [
        (["--alpha", "-a"], "a", "store", 1),
        (["--beta", "-b"], "b", "count", 1),
        (["--pair", "-p"], "p", "store", 2),
        (["--many", "-m"], "m", "append", 1),
        (["--zero"], "z", "store", 0),
        (["++word", "+w"], "w", "store", 1),
    ]:
        parser.add_option(SimpleNamespace(_flag_needs_value=optional, label=dest),
                          spellings, dest, action, nargs)
    parser.add_argument(SimpleNamespace(label="arg"), "arg", -1)
    return parser


def outcome(parser, argv):
    try:
        values, rest, order = parser.parse_args(argv)
        # Sentinel objects intentionally live in separate package namespaces.
        # Their repr, nested values, insertion order and encounter order agree.
        return "ok", repr(values), rest, [item.label for item in order]
    except Exception as error:
        return type(error).__name__, str(error)


@pytest.mark.parametrize("optional", [False, True])
@pytest.mark.parametrize("interspersed", [False, True])
@pytest.mark.parametrize("ignore_unknown", [False, True])
def test_generated_parser_interactions(optional, interspersed, ignore_unknown):
    reference = make_parser(ReferenceParser, optional, interspersed, ignore_unknown)
    candidate = make_parser(NativeParser, optional, interspersed, ignore_unknown)
    words = [
        "--alpha", "-a", "-aX", "--alpha=X", "--beta", "-b", "-ab", "-baZ",
        "--pair", "-p", "-pX", "--pair=Y", "--many", "-m", "--zero",
        "--zero=X", "++word", "+w", "+wX", "--", "X", "", "-10",
        "--bad", "-Zb", "漢字", "--beta=1", "-", "--alpha=--beta",
        "path-\udcff", "--zero=--beta", "--alpha=--alpha=--beta",
    ]
    random_source = random.Random(49221)
    for _ in range(1000):
        argv = random_source.choices(words, k=random_source.randrange(9))
        expected = outcome(reference, list(argv))
        assert outcome(candidate, list(argv)) == expected, argv


@pytest.mark.parametrize("argv, interspersed", [
    (["--alpha", "value", "tail"], True),
    (["--alpha", "value", "tail"], False),
    (["--", "--alpha", "tail"], True),
    (["--alpha", "value", "--bad", "tail"], True),
    (["--pair", "only-one"], True),
    (["--zero=attached", "tail"], False),
])
def test_legacy_parser_mutates_input_list_like_reference(argv, interspersed):
    reference_args, candidate_args = list(argv), list(argv)
    reference = make_parser(ReferenceParser, False, interspersed, False)
    candidate = make_parser(NativeParser, False, interspersed, False)
    assert outcome(candidate, candidate_args) == outcome(reference, reference_args)
    assert candidate_args == reference_args


@pytest.mark.parametrize("optional", [False, True])
def test_normalizer_call_order_and_requeued_attached_values(optional):
    import click
    import zclick

    traces = ([], [])
    parsers = []
    for module, cls, trace in zip((click, zclick), (ReferenceParser, NativeParser), traces):
        def normalize(value, trace=trace):
            trace.append(value)
            return value.lower()
        context = module.Context(module.Command("normalize"), token_normalize_func=normalize)
        parsers.append(make_parser(cls, optional, True, True, context))
    assert traces[0] == traces[1]
    for argv in [
        ["--ALPHA=--BETA"], ["--ALPHA=--ALPHA=--BETA"], ["-bAXValue"],
        ["--PAIR=--ALPHA"], ["--ZERO=--BETA"], ["--UNKNOWN=Value", "-Xb"],
        ["--ALPHA", "--BETA", "-p", "UpperValue", "OtherValue"],
        ["--", "--ALPHA"], ["++WORD", "MixedCase"],
    ]:
        traces[0].clear()
        traces[1].clear()
        reference_args, candidate_args = list(argv), list(argv)
        expected = outcome(parsers[0], reference_args)
        assert outcome(parsers[1], candidate_args) == expected, argv
        assert candidate_args == reference_args, argv
        assert traces[0] == traces[1], argv


@pytest.mark.parametrize("action", ["", "append_invalid", "unsupported"])
def test_invalid_parser_actions_are_errors(action):
    outcomes = []
    for cls in (ReferenceParser, NativeParser):
        parser = cls()
        parser.add_option(SimpleNamespace(_flag_needs_value=False, label="flag"),
                          ["--flag"], "flag", action=action)
        outcomes.append(outcome(parser, ["--flag"]))
    assert outcomes[0] == outcomes[1] == ("ValueError", f"unknown action '{action}'")
