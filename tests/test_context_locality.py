"""Context stack storage stays independent of concurrent and nested scopes."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib
from threading import Barrier

import pytest


@pytest.mark.parametrize("package", ["click", "zclick"])
def test_context_stacks_are_thread_local_during_reentry_and_cleanup(package):
    click = importlib.import_module(package)
    barrier = Barrier(2)
    main = click.Context(click.Command("main"))

    def run(name):
        assert click.get_current_context(silent=True) is None
        parent = click.Context(click.Command(name))
        child = click.Context(click.Command("child"), parent=parent)
        closed = []
        parent.call_on_close(lambda: closed.append(click.get_current_context()))
        with parent:
            barrier.wait(timeout=5)
            assert click.get_current_context() is parent
            with child.scope(cleanup=False):
                assert click.get_current_context() is child
                with parent:
                    assert click.get_current_context() is parent
                assert click.get_current_context() is child
            assert click.get_current_context() is parent
            barrier.wait(timeout=5)
        assert closed == [parent]
        assert click.get_current_context(silent=True) is None
        return parent

    with main:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, name) for name in ("first", "second")]
            contexts = [future.result(timeout=10) for future in futures]
        assert contexts[0] is not contexts[1]
        assert click.get_current_context() is main
    assert click.get_current_context(silent=True) is None
