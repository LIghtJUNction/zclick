"""Regression tests for test migration, without relaxing upstream assertions."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


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
