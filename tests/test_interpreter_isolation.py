"""Reject unsupported subinterpreters before native caches capture their objects."""
from __future__ import annotations

import subprocess
import sys

import pytest


MAIN_PROGRAM = r'''
def check_main():
    import zclick as click

    @click.group()
    def cli():
        pass

    @cli.command()
    @click.option("--number", type=int)
    def run(number):
        return number

    expected = 2 ** 130
    assert cli.main(["run", "--number", str(expected)], standalone_mode=False) == expected
'''


def run_fresh(program):
    result = subprocess.run(
        [sys.executable, "-I", "-c", program],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_main_interpreter_still_imports_and_dispatches():
    # This also runs on PyPy, which has no CPython subinterpreter API.
    run_fresh(MAIN_PROGRAM + "\ncheck_main()\n")


@pytest.mark.skipif(sys.implementation.name != "cpython", reason="CPython subinterpreter API")
@pytest.mark.parametrize("main_first", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
def test_subinterpreter_rejection_preserves_main_and_cache_isolation(main_first, legacy):
    program = MAIN_PROGRAM + r'''
import operator
import sys

try:
    import _interpreters as api
    modern = True
except ImportError:
    import _xxsubinterpreters as api
    modern = False

original_length_hint = operator.length_hint
main_calls = []

def main_length_hint(value, default=0):
    main_calls.append("main Python object called")
    return original_length_hint(value, default)

operator.length_hint = main_length_hint
if MAIN_FIRST:
    check_main()

before = list(main_calls)
if LEGACY:
    interpreter = api.create("legacy") if modern else api.create(isolated=False)
else:
    interpreter = api.create()

try:
    outcome = api.run_string(interpreter, """
import sys
try:
    from zclick import _native
except ImportError as error:
    assert "subinterpreter" in str(error), str(error)
    assert "zclick._native" not in sys.modules
else:
    # On the old binding this invokes a main-interpreter cached Python callable
    # when main was imported first. Successful imports are never accepted here.
    _native.parse([(0, ["--value"], 1, False)], ["--value", "child"])
    raise AssertionError("unsupported subinterpreter loaded zclick._native")
""")
    # 3.13+ can return an exception-information object instead of raising.
    assert outcome is None, repr(outcome)
finally:
    api.destroy(interpreter)

assert main_calls == before, "subinterpreter executed a main-interpreter cached callable"
# A rejected first import must not poison subsequent main-interpreter loading.
check_main()
operator.length_hint = original_length_hint
'''
    run_fresh(program.replace("MAIN_FIRST", repr(main_first)).replace("LEGACY", repr(legacy)))
