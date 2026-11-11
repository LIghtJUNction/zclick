# zclick

Python command-line interfaces backed by Rust and zclap. The compatibility target
is Click **8.5.1**, pinned to its release commit and official test suite.

This repository is under active development. `COMPATIBILITY.md` records measured
coverage and remaining differences. A stable release requires the compatibility
and cross-platform build gates to pass.

```python
import zclick as click

@click.command()
@click.option("--count", default=1, type=int, help="Number of greetings.")
@click.option("--name", prompt="Your name", help="The person to greet.")
def hello(count, name):
    for _ in range(count):
        click.echo(f"Hello, {name}!")

if __name__ == "__main__":
    hello()
```

## Development

Use Python 3.10 or newer and the pinned Rust toolchain. Create a virtual
environment, install Maturin and the test dependencies, then build the extension:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install maturin pytest hypothesis click==8.5.1
maturin develop --release
python -m pytest tests
python scripts/run_compatibility.py
```

The runtime does not depend on Click. Click is installed only in the development
comparison environment. The wheel contains the `zclick` package and does not
install a top-level `click` package or redirect another package's imports.

## Architecture

Python objects preserve decorators, custom subclasses, callbacks and ordinary
Python values. The native extension builds a fresh parsing plan for each call.
The Rust core performs token recognition through zclap, applies Click argument
consumption rules, schedules parameters and formats text. The core uses
`no_std` with `alloc`; its only direct third-party dependency is zclap. The
extension uses PyO3 and the Rust standard library.

The Python interface accepts mutations between invocations. Plans are not cached,
and user callbacks run without a native lock or borrowed mutable parser state.
Python integer conversion uses Python integers rather than fixed-width Rust
integers. Input strings preserve surrogate code points at the binding boundary.

## Migration

Replace `import click` with `import zclick as click`. Replace submodule imports,
for example `from click.testing import CliRunner`, with
`from zclick.testing import CliRunner`.

A third-party extension that imports Click internally continues to use Click.
Its classes and object identity require separate migration and verification.
The import alias alone does not convert those imports.

`CliRunner` changes interpreter streams, environment variables and sometimes the
working directory. Use separate processes for concurrent runner tests.
