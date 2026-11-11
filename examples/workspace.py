"""Context resources, custom conversion, environment defaults and completion.

Run: python examples/workspace.py --prefix demo convert 0x10000000000000000
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import zclick as click
from zclick.shell_completion import CompletionItem


class IntegerLiteral(click.ParamType):
    name = "integer-literal"

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value
        try:
            return int(value, 0)
        except (ValueError, TypeError):
            self.fail(f"{value!r} is not a Python integer literal", param, ctx)

    def shell_complete(self, ctx, param, incomplete):
        return [CompletionItem(value, help="Integer literal")
                for value in ("0xff", "0b1010", "42") if value.startswith(incomplete)]


@dataclass
class Workspace:
    prefix: str
    opened: bool = False

    @contextmanager
    def session(self):
        self.opened = True
        try:
            yield self
        finally:
            self.opened = False


pass_workspace = click.make_pass_decorator(Workspace)


@click.group(context_settings={"auto_envvar_prefix": "WORKSPACE"})
@click.option("--prefix", default="result", show_default=True, show_envvar=True)
@click.pass_context
def cli(ctx: click.Context, prefix: str):
    """Convert integer literals while a context-owned resource is open."""
    ctx.obj = ctx.with_resource(Workspace(prefix).session())


@cli.command()
@click.argument("value", type=IntegerLiteral(), help="A decimal, hexadecimal or binary integer.")
@pass_workspace
def convert(workspace: Workspace, value: int):
    assert workspace.opened
    click.echo(f"{workspace.prefix}: {value}")


if __name__ == "__main__":
    cli()
