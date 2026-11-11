"""Rust command dispatch must preserve Python hook, scope, and GC behavior."""
from __future__ import annotations
import gc
import sys
import weakref
import pytest
import zclick as click
from zclick import _native
from zclick.core import _invoke_context

class NativeGroup(click.Group):
    def invoke(self, ctx):
        return _native.invoke_group(self, ctx, super(click.Group, self).invoke, _invoke_context)


def test_native_single_dispatch_and_result_lifetime():
    events = []
    @click.group(cls=NativeGroup)
    @click.pass_context
    def cli(ctx):
        events.append("group")
        ctx.call_on_close(lambda: events.append("group_close"))
    @cli.command()
    @click.pass_context
    def run(ctx):
        events.append("run")
        ctx.call_on_close(lambda: events.append("child_close"))
        return 4
    @cli.result_callback()
    def finish(result):
        events.append(("result", result))
        return result * 2
    assert cli.main(["run"], standalone_mode=False) == 8
    assert events == ["group", "run", ("result", 4), "child_close", "group_close"]


def test_native_chain_dispatch_preserves_subclass_hooks():
    calls = []
    class Custom(click.Command):
        def invoke(self, ctx):
            calls.append(("invoke", self.name))
            return super().invoke(ctx)
    @click.group(cls=NativeGroup, chain=True)
    def cli():
        calls.append("group")
    @cli.command(cls=Custom)
    @click.argument("value", type=int)
    def first(value): return value
    @cli.command(cls=Custom)
    def second(): return 3
    @cli.result_callback()
    def finish(results): return sum(results)
    assert cli.main(["first", "2", "second"], standalone_mode=False) == 5
    assert calls == ["group", ("invoke", "first"), ("invoke", "second")]


def test_native_reentry_restores_context_stack():
    @click.group(cls=NativeGroup)
    def cli(): pass
    @cli.command()
    @click.pass_context
    def inner(ctx):
        assert click.get_current_context() is ctx
        return 9
    @cli.command()
    @click.pass_context
    def outer(ctx):
        value = cli.main(["inner"], standalone_mode=False)
        assert click.get_current_context() is ctx
        return value + 1
    assert cli.main(["outer"], standalone_mode=False) == 10
    assert click.get_current_context(silent=True) is None


def test_native_exit_sees_handled_exception_state():
    seen = []
    error = RuntimeError("callback failure")
    class CustomContext(click.Context):
        def __exit__(self, typ, value, traceback):
            if value is not None:
                seen.append((value, sys.exc_info()[1], traceback))
            return super().__exit__(typ, value, traceback)
    class CustomCommand(click.Command):
        context_class = CustomContext
    @click.group(cls=NativeGroup)
    def cli(): pass
    @cli.command(cls=CustomCommand)
    def fail(): raise error
    with pytest.raises(RuntimeError) as caught:
        cli.main(["fail"], standalone_mode=False)
    assert caught.value is error
    assert seen and seen[0][0] is error and seen[0][1] is error
    assert seen[0][2] is not None


def test_native_chain_can_suppress_one_callback_exception():
    class Suppress(click.Context):
        def __exit__(self, typ, value, traceback):
            super().__exit__(typ, value, traceback)
            return isinstance(value, RuntimeError)
    class Command(click.Command): context_class = Suppress
    @click.group(cls=NativeGroup, chain=True)
    def cli(): pass
    @cli.command(cls=Command)
    def first(): raise RuntimeError("suppressed")
    @cli.command()
    def second(): return 7
    assert cli.main(["first", "second"], standalone_mode=False) == [None, 7]


def test_native_frame_cycles_are_collectible():
    class RetainFrameGroup(click.Group):
        def invoke(self, ctx):
            def scope(active, callback):
                self.retained_frame = callback
                return _invoke_context(active, callback)
            return _native.invoke_group(self, ctx, click.Command.invoke.__get__(self), scope)
    group = RetainFrameGroup("cli", invoke_without_command=True, callback=lambda: 3)
    reference = weakref.ref(group)
    assert group.main([], standalone_mode=False) == 3
    del group
    gc.collect()
    assert reference() is None


@pytest.mark.parametrize("chain, expected", [(False, 5), (True, [])])
def test_native_empty_group_return_value(chain, expected):
    group = NativeGroup("cli", chain=chain, invoke_without_command=True, callback=lambda: 5)
    assert group.main([], standalone_mode=False) == expected
