"""Regression tests for test migration, without relaxing upstream assertions."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


_path = Path(__file__).resolve().parents[1] / "scripts/prepare_upstream.py"
_spec = importlib.util.spec_from_file_location("prepare_upstream", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
sys.path.insert(0, str(_path.parent))
from compat_report_plugin import key


def test_old_python_fstring_expression_namespace_only():
    source = '''f"click: {click.style('click', fg='blue')}"'''
    expected = '''f"click: {zclick.style('click', fg='blue')}"'''
    assert _module.migrate_fstring(source) == expected


def test_fstring_multiline_unicode_and_nested_expression():
    source = '''f"""点击 {click.style('click')}\n{click.echo(f'{click.INT}')}"""'''
    expected = '''f"""点击 {zclick.style('click')}\n{zclick.echo(f'{zclick.INT}')}"""'''
    assert _module.migrate_fstring(source) == expected


def test_import_migration_preserves_output_assertion():
    source = '''import click\nassert f"click {click.INT}" == "click INT"\n'''
    expected = '''import zclick\nassert f"click {zclick.INT}" == "click INT"\n'''
    assert _module.migrate(source, "test_fixture.py")[0] == expected


def test_report_ids_preserve_escaped_parameter_values():
    node = r"tests\test_utils\test_style.py::test_styling[styles1-\x1b[31m]"
    assert key(node) == r"tests/test_utils/test_style.py::test_styling[styles1-\x1b[31m]"
    assert key(r"tests/test.py::test_a[foo\bar]") != key("tests/test.py::test_a[foo/bar]")


def test_report_ids_normalize_only_pinned_platform_path_example():
    windows = r"tests/test_utils/test__detect_program_name.py::test_detect_program_name[example\\cli.py-example-python -m example.cli]"
    posix = "tests/test_utils/test__detect_program_name.py::test_detect_program_name[example/cli.py-example-python -m example.cli]"
    assert key(windows) == key(posix)


@pytest.mark.parametrize(("python310", "python311"), [
    ("ColorInt-ColorInt.GREEN-GREEN", "ColorInt-2-GREEN"),
    ("Number-Number.TWO-TWO", "Number-2-TWO"),
    ("Letter-Letter.NAME_1-NAME_1", "Letter-Value-1-NAME_1"),
    ("Letter-Letter.NAME_2-NAME_2", "Letter-Value_2-NAME_2"),
    ("Letter-Letter.NAME_3-NAME_3", "Letter-42_value-NAME_3"),
])
def test_pinned_enum_parameter_ids_across_python_versions(python310, python311):
    prefix = "tests/test_options.py::test_choice_default_rendering"
    expected = f"{prefix}[{python311}]"
    assert key(f"{prefix}[{python310}]") == expected
    assert key(expected) == expected


def test_enum_id_normalization_preserves_distinct_defaults_and_other_tests():
    prefix = "tests/test_options.py::test_choice_default_rendering"
    enum_default = f"{prefix}[Letter-Letter.NAME_1-NAME_1]"
    string_default = f"{prefix}[Letter-NAME_1-NAME_1]"
    assert key(enum_default) != key(string_default)
    assert key(string_default) == string_default
    other_test = "tests/test_other.py::test_choice_default_rendering[Letter-Letter.NAME_1-NAME_1]"
    assert key(other_test) == other_test
