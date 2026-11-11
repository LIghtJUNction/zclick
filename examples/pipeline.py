"""Composable chained commands and context-owned state."""
import zclick as click


@click.group(chain=True)
@click.option("--text", default="Hello, world!")
@click.pass_context
def pipeline(ctx: click.Context, text: str) -> None:
    ctx.obj = text


@pipeline.command()
def uppercase():
    """Convert the text to uppercase."""
    return str.upper


@pipeline.command()
@click.argument("old")
@click.argument("new")
def replace(old: str, new: str):
    """Replace an occurrence of text."""
    return lambda text: text.replace(old, new)


@pipeline.result_callback()
@click.pass_context
def finish(ctx: click.Context, operations, **kwargs) -> None:
    text = ctx.obj
    for operation in operations:
        text = operation(text)
    click.echo(text)


if __name__ == "__main__":
    pipeline()
