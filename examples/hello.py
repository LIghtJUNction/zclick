"""Run with: python examples/hello.py --count 2 --name Ada."""
import zclick as click


@click.command()
@click.option("--count", default=1, type=int, help="Number of greetings.")
@click.option("--name", prompt="Your name", help="The person to greet.")
def hello(count: int, name: str) -> None:
    """Greet someone using a native-backed command."""
    for _ in range(count):
        click.echo(f"Hello, {name}!")


if __name__ == "__main__":
    hello()
