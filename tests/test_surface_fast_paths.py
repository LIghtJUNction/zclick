"""Dynamic behavior that must survive the surface performance paths."""
from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize("package", ["click", "zclick"])
def test_unhashable_callable_type_converter(package):
    types = importlib.import_module(f"{package}.types")

    class Converter:
        __hash__ = None
        __name__ = "converter"

        def __init__(self):
            self.seen = []

        def __call__(self, value):
            self.seen.append(value)
            return int(value) + len(self.seen)

    callback = Converter()
    converted = types.convert_type(callback)
    assert converted("3") == 4
    assert converted("5") == 7
    assert callback.seen == ["3", "5"]


@pytest.mark.parametrize("package", ["click", "zclick"])
def test_function_type_requires_callable_name(package):
    types = importlib.import_module(f"{package}.types")

    class Anonymous:
        def __call__(self, value):
            return value

    with pytest.raises(AttributeError, match="__name__"):
        types.FuncParamType(Anonymous())


@pytest.mark.parametrize("package", ["click", "zclick"])
@pytest.mark.parametrize("name,builtin,value", [
    ("STRING", str, "text"),
    ("INT", int, 1 << 200),
    ("FLOAT", float, 1.25),
    ("BOOL", bool, False),
])
def test_builtin_type_selection_observes_rebound_singletons(monkeypatch, package, name, builtin, value):
    types = importlib.import_module(f"{package}.types")

    class Replacement(types.ParamType):
        name = "replacement"

        def convert(self, value, param, ctx):
            return ("converted", value)

    replacement = Replacement()
    monkeypatch.setattr(types, name, replacement)
    assert types.convert_type(builtin) is replacement
    assert types.convert_type(default=value) is replacement
    assert replacement(value) == ("converted", value)
    monkeypatch.setattr(replacement, "convert", lambda value, param, ctx: ("changed", value))
    assert types.convert_type(builtin)(value) == ("changed", value)


@pytest.mark.parametrize("package", ["click", "zclick"])
def test_string_conversion_observes_str_subclass_override(package):
    types = importlib.import_module(f"{package}.types")

    class Text(str):
        def __str__(self):
            return "overridden"

    assert types.STRING(Text("original")) == "overridden"


@pytest.mark.parametrize("package", ["click", "zclick"])
def test_plain_text_measurement_keeps_unicode_and_subclass_semantics(package):
    compat = importlib.import_module(f"{package}._compat")
    value = "Ω中文\ud800"
    assert compat.term_len(value) == 4
    assert compat.strip_ansi(value) == value

    class Text(str):
        def __len__(self):
            return 1000

    assert compat.term_len(Text("plain")) == 5
    assert type(compat.strip_ansi(Text("plain"))) is str


def test_formatting_wrappers_observe_native_replacements(monkeypatch):
    from zclick import _compat, _native, formatting

    monkeypatch.setattr(_native, "strip_ansi", lambda value: "replacement")
    monkeypatch.setattr(_native, "text_width", lambda value: 37)
    monkeypatch.setattr(_native, "wrap_text", lambda *args: "wrapped")
    monkeypatch.setattr(_native, "join_options", lambda value: ("joined", True))
    assert _compat.strip_ansi("plain") == "replacement"
    assert _compat.term_len("plain") == 37
    assert formatting.wrap_text("plain") == "wrapped"
    assert formatting.join_options(["--plain"]) == ("joined", True)


@pytest.mark.parametrize("package", ["click", "zclick"])
def test_style_truthiness_is_observed_once_in_parameter_order(package):
    library = importlib.import_module(package)
    seen = []

    class Flag:
        def __init__(self, name, enabled):
            self.name = name
            self.enabled = enabled

        def __bool__(self):
            seen.append(self.name)
            return self.enabled

    names = ["bold", "dim", "underline", "overline", "italic", "blink", "reverse", "strikethrough"]
    values = {name: Flag(name, index % 2 == 0) for index, name in enumerate(names)}
    result = library.style("text", **values, reset=Flag("reset", True))
    assert seen == [*names, "reset"]
    assert result == "\x1b[1m\x1b[22m\x1b[4m\x1b[55m\x1b[3m\x1b[25m\x1b[7m\x1b[29mtext\x1b[0m"


@pytest.mark.parametrize("prefix", [
    "\t", "\v", "\f", "\r", "\x1c", "\x85", "\u00a0", "\u1680",
    "\u2003", "\u2028", "\u2029", "\u3000",
])
def test_help_whitespace_follows_the_running_stdlib(prefix):
    import inspect
    from zclick.core import _clean_help

    for suffix in ("", "Unicode 零  "):
        value = "  " + prefix + suffix
        assert _clean_help(value) == inspect.cleandoc(value)
