# zclick

Python command-line interfaces backed by Rust and zclap. Import the public API
as `import zclick as click`, including the matching `zclick.core`, `zclick.types`,
`zclick.testing` and `zclick.shell_completion` submodules.

The fixed compatibility target is **Click 8.5.1**, source commit
[`cf19179`](https://github.com/pallets/click/tree/cf19179e8e2fd54c601378cec9e0d21bb12b6fb1).
The versioned documentation, API inventory and original tests are pinned in
[`compatibility/target.json`](compatibility/target.json). The implementation uses
registry **zclap 0.1.4**, **PyO3 0.30.1** and **Rust 1.99.1 / Edition 2024**.

**This is a preview release; the complete compatibility target is not yet met.**
CPython subinterpreters are currently unsupported and are explicitly rejected
at native module initialization. The locked PyO3 binding has Python object
caches that are not partitioned by interpreter. See the
[open compatibility record](compatibility/known-gaps.json). Stable publication
is blocked while an open compatibility gap remains.

[Compatibility evidence](COMPATIBILITY.md) · [Performance measurements](docs/performance.md) ·
[Architecture](docs/architecture.md) · [Build and release](docs/development.md) ·
[中文交付记录](docs/DELIVERY.zh-CN.md)

## Installation and a first command

The **0.1.1a1** preview is available from
[GitHub Releases](https://github.com/LIghtJUNction/zclick/releases/tag/v0.1.1a1),
with 12 wheels, a source archive and the complete validation evidence.
Its PyPI upload was attempted and returned `invalid-publisher`: a matching
Trusted Publisher has not been configured. A PyPI installation is therefore
not yet available from this release workflow.

Install the matching wheel from the release assets, or build the released
source archive on ordinary CPython with Rust 1.99.1 and the platform build tools:

```sh
python -m pip install https://github.com/LIghtJUNction/zclick/releases/download/v0.1.1a1/zclick-0.1.1a1.tar.gz
```

Once PyPI publication is configured, the preview installation is:

```sh
pip install --pre zclick
```

Ordinary CPython wheels support Python 3.10 and newer; PyPy and free-threaded CPython
require their corresponding wheels or an interpreter-specific source build.
The intended stable installation is `pip install zclick` once the outstanding
compatibility gate is satisfied.

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

## Migration

Replace `import click` with `import zclick as click`. Replace submodule imports,
for example `from click.testing import CliRunner`, with
`from zclick.testing import CliRunner`.

The wheel installs the `zclick` namespace. It has **no third-party Python runtime
requirements**, does not install a top-level `click` package, and does not
redirect another package's imports. Original Click is only a development and
comparison dependency.

A third-party extension that imports Click internally continues to use Click.
Its classes and context stack require separate migration. The
[extension compatibility report](docs/extensions.md) reproduces this boundary
with locked releases of click-didyoumean, click-plugins and click-repl, including
their original-Click control runs. Changing an application's import alias does
not automatically migrate those extensions.

## Compatibility and performance

The release gate requires the complete **33,459-case** official test collection,
including **31,000 stress cases**, with the same test IDs and original platform
skip/expected-failure conditions. It additionally checks **196 public objects**
and their members, the 12 upstream typing examples, native property and
differential tests, and real Bash, Zsh, Fish and PowerShell completion. Results
are tied to an immutable implementation commit; configured platforms are not
reported as passing until their jobs succeed. See
[COMPATIBILITY.md](COMPATIBILITY.md) and the
[CI runs](https://github.com/LIghtJUNction/zclick/actions/workflows/ci.yml).

Rust removes interpreter work from parsing, scheduling, dispatch and text
formatting. Python object creation and virtual method calls still have a cost.
The [benchmark report](docs/performance.md) includes construction, repeated
parser calls, full `Command.main` calls, nested commands, help, wrapping, imports
and memory measurements. Some workloads are faster and some are slower; the
report includes both. No universal speedup or zero-allocation claim is made.

## Examples

| Example | Behavior |
| --- | --- |
| [`hello.py`](examples/hello.py) | Decorators, options, prompting and output |
| [`pipeline.py`](examples/pipeline.py) | Chained commands, context state and result callbacks |
| [`workspace.py`](examples/workspace.py) | A custom type, arbitrary-size integers, context resources, environment defaults and completion |

```sh
python examples/hello.py --count 2 --name Ada
python examples/pipeline.py --text 'hello world' uppercase replace WORLD Rust
python examples/workspace.py --prefix demo convert 0x10000000000000000
```

[Shell completion setup](docs/shell-completion.md) covers the source/complete
protocols and the scope of actual shell-engine validation.

## Development

Use Python 3.10 or newer and the pinned Rust toolchain. Create a virtual
environment, install Maturin and the test dependencies, then build the extension:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
maturin develop --release --locked
python -m pytest tests
python scripts/run_compatibility.py
```

Use the [development guide](docs/development.md) for complete stress verification,
cross-platform builds, dependency audits, reproducible benchmarks and version
bumps. The [release workflow](.github/workflows/release.yml) builds and installs
the actual wheels before publishing them.

## Architecture

Python objects preserve decorators, custom subclasses, callbacks and ordinary
Python values. The native extension builds a fresh parsing plan for each call.
The Rust core performs token recognition through zclap, applies Click argument
consumption rules, schedules parameters and formats text. Rust also drives
command groups and parser actions through Python's current methods. The core uses
`no_std` with `alloc`; its only direct third-party dependency is zclap. The
extension uses PyO3 and the Rust standard library.

The Python interface accepts mutations between invocations. Plans are not cached,
and user callbacks run without a native lock or borrowed mutable parser state.
Python integer conversion uses Python integers rather than fixed-width Rust
integers. Input strings preserve surrogate code points at the binding boundary.

`CliRunner` changes interpreter streams, environment variables and sometimes the
working directory. Use separate processes for concurrent runner tests.

The project implementation is MIT licensed. Distribution notices for the
generated Click API declarations, Rust dependencies and standard library are
listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
