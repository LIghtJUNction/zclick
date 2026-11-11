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

[Compatibility evidence](COMPATIBILITY.md) · [0.1.1a1 measurements](docs/performance.md) ·
[0.1.1a2 measurements](docs/performance-0.1.1a2.md) ·
[Architecture](docs/architecture.md) · [Build and release](docs/development.md) ·
[中文交付记录](docs/DELIVERY-0.1.1a2.zh-CN.md) ·
[0.1.1a1 中文记录](docs/DELIVERY.zh-CN.md)

## Installation and a first command

The **0.1.1a2** preview is available on
[PyPI](https://pypi.org/project/zclick/0.1.1a2/) and
[GitHub Releases](https://github.com/LIghtJUNction/zclick/releases/tag/v0.1.1a2).
Install the published version:

```sh
python -m pip install zclick==0.1.1a2
```

To select the latest available preview instead:

```sh
pip install --pre zclick
```

All 12 wheels and the source archive have matching hashes on PyPI and GitHub.
The [publication verification](compatibility/releases/0.1.1a2-pypi.json) records
the released files, the Trusted Publisher identity reported by PyPI, and an
isolated installation that ran the greeting example without original Click.
The previous
0.1.1a1 [verification](compatibility/releases/0.1.1a1-pypi.json) remains available.

Source installation requires Rust 1.99.1 and the platform build tools.

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

Version 0.1.1a2 completed the full release validation run at source
`7e3d597873b737bbfc8c2df090773aad56d9bd73`. Its
[validation record](compatibility/releases/0.1.1a2.json) preserves the actual
platform results, including original skips, separately from wheel installation
checks and the disclosed subinterpreter gap.

The [0.1.1a2 performance report](docs/performance-0.1.1a2.md) compares Click 8.5.1,
the published zclick 0.1.1a1 wheel and a2 in twelve balanced rounds on each of
two Linux hosts. The local run used CPython 3.12.14 / AMD EPYC 9V74; release CI
used CPython 3.14.10 / AMD EPYC 7763. The table compares a2 with Click on each
host. Ratios divide Click's median wall time by a2's: **above one means lower
a2 latency**.

| Workload | Local Click / a2 | Release CI Click / a2 |
| --- | ---: | ---: |
| Reused parser, 1 option | 0.541× | 0.617× |
| Reused parser, 10 options | 0.757× | 0.650× |
| Reused parser, 100 options | 0.868× | 0.735× |
| Reused parser, 1,000 options | 1.236× | 0.975× |
| Full warm invocation, 1 option | 0.973× | 0.979× |
| Full warm invocation, 1,000 options | 1.771× | 2.017× |
| Warm help, 1,000 options | 1.214× | 1.320× |
| Unicode/ANSI wrapping | 7.404× | 9.314× |
| Nested command | 0.886× | 0.909× |

The local 1,000-option parser advantage over Click **did not reproduce in CI**.
Smaller parser cases, the one-option warm invocation and nested commands
remain slower than Click on both hosts. Relative to the published a1 wheel,
the 1,000-option parser improved by **2.535× locally / 2.354× in CI**; the full
invocation improved only **1.042× / 1.050×**. These comparisons distinguish the
project's existing advantage over Click from this version's additional gain.

All eight fresh-process command and help medians were lower than both references
on both hosts, but retained outliers prevent a claim that every startup is
faster. The report includes all eighteen warm workloads, eight cold workloads,
import timing, variability and memory. The local run used different wheel build
targets for a1 and a2. CI used the release's manylinux build, and the benchmark
and release GNU wheels contain the
[same 18 Python/native runtime files](compatibility/releases/0.1.1a2-benchmark-payload.json),
although their wheel archive hashes differ.

Whole-worker peak RSS remained higher than Click on both hosts: a2 measured
25.492 versus 24.059 MiB locally and 33.324 versus 32.039 MiB in CI. These values
include the full benchmark worker, not one parser call. Results remain specific
to the recorded workloads, distributions, interpreters and hosts; no universal
speedup or zero-allocation claim is made. The
[historical a1 report](docs/performance.md) retains its original data and method.

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
Python values. The native extension validates current definitions before reusing
an immutable parsing schema; every call has its own execution state.
The Rust core performs token recognition through zclap, applies Click argument
consumption rules, schedules parameters and formats text. Rust also drives
command groups and parser actions through Python's current methods. The core uses
`no_std` with `alloc`; its only direct third-party dependency is zclap. The
extension uses PyO3 and the Rust standard library.

The Python interface accepts mutations between invocations. Each parser or
command retains at most its most recent owned Rust schema. Defaults, environment
values, callbacks and contexts are evaluated anew. User callbacks run without a
native lock or borrowed mutable parser state.
Python integer conversion uses Python integers rather than fixed-width Rust
integers. Input strings preserve surrogate code points at the binding boundary.

`CliRunner` changes interpreter streams, environment variables and sometimes the
working directory. Use separate processes for concurrent runner tests.

The project implementation is MIT licensed. Distribution notices for the
generated Click API declarations, Rust dependencies and standard library are
listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
