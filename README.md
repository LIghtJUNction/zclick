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
[0.1.1a3 measurements](docs/performance-0.1.1a3.md) ·
[Architecture](docs/architecture.md) · [Build and release](docs/development.md) ·
[中文交付记录](docs/DELIVERY-0.1.1a3.zh-CN.md) ·
[0.1.1a2 中文记录](docs/DELIVERY-0.1.1a2.zh-CN.md) ·
[0.1.1a1 中文记录](docs/DELIVERY.zh-CN.md)

## Installation and a first command

The **0.1.1a3** preview is available on
[PyPI](https://pypi.org/project/zclick/0.1.1a3/) and
[GitHub Releases](https://github.com/LIghtJUNction/zclick/releases/tag/v0.1.1a3).
Install the published version:

```sh
python -m pip install --upgrade zclick==0.1.1a3
```

To select the latest available preview instead:

```sh
pip install --pre zclick
```

The [publication verification](compatibility/releases/0.1.1a3-pypi.json)
records all 12 wheels and the source archive, matching PyPI/GitHub hashes,
the Trusted Publisher identity, and a new isolated PyPI installation that ran
the prompting greeting example without original Click. Earlier
[a2](compatibility/releases/0.1.1a2-pypi.json) and
[a1](compatibility/releases/0.1.1a1-pypi.json) verification records remain available.

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

Version 0.1.1a3 completed the full release validation at source
[`9afcc753`](https://github.com/LIghtJUNction/zclick/commit/9afcc7537212563f66a5d99c9f08f99bfa692731).
All 61 jobs in the [release run](https://github.com/LIghtJUNction/zclick/actions/runs/43377480224)
succeeded. The [validation record](compatibility/releases/0.1.1a3.json)
separates the 12 normal test environments, seven stress environments, API and
Shell checks from the 12 actual wheel installations and source-archive rebuild.
Original skips and the unresolved subinterpreter difference remain explicit.
The [a2 validation record](compatibility/releases/0.1.1a2.json) is retained.

The [0.1.1a3 performance report](docs/performance-0.1.1a3.md) compares fixed
Click 8.5.1, the published a2 wheel and a3 in twelve balanced rounds on each of
two Linux hosts. Local CPython 3.12.14 and release-CI CPython 3.14.10 both ran
on machines reporting AMD EPYC 9V74; their systems, available CPU counts and
wheel build environments differ. Ratios divide the reference median wall time
by a3's: **above one means lower a3 latency**. The last two columns isolate the
comparison with the previous release from the project's advantage over Click.

| Workload | Local Click / a3 | CI Click / a3 | Local a2 / a3 | CI a2 / a3 |
| --- | ---: | ---: | ---: | ---: |
| Reused parser, 1 option | 0.890× | 1.023× | 1.615× | 1.674× |
| Reused parser, 10 options | 0.944× | 0.853× | 1.370× | 1.318× |
| Reused parser, 100 options | 1.057× | 0.872× | 1.170× | 1.208× |
| Reused parser, 1,000 options | 1.446× | 1.154× | 1.179× | 1.166× |
| Full warm invocation, 1 option | 1.083× | 1.141× | 1.079× | 1.097× |
| Full warm invocation, 1,000 options | 1.776× | 2.128× | 1.042× | 1.033× |
| Warm help, 1 option | 2.235× | 2.619× | 0.909× | 0.936× |
| Warm help, 10 options | 1.727× | 1.886× | 1.006× | 0.971× |
| Warm help, 1,000 options | 1.259× | 1.329× | 1.017× | 1.014× |
| Nested command | 1.040× | 1.101× | 1.166× | 1.143× |
| Unicode/ANSI wrapping | 7.507× | 9.055× | 0.978× | 0.988× |

One-option parsing improved relative to a2 by 1.615× locally and 1.674× in CI.
Nested invocation improved by 1.166× and 1.143×. Full invocation at 1,000 options
was 1.776× and 2.128× relative to Click, but its new improvement over a2 was only
1.042× and 1.033×. The large wrapping advantage over Click also predates this
release; wrapping regressed slightly relative to a2 in both runs.

Pure parsing still has slower cases: one and ten options locally, and ten and
100 options in CI. The 100-option local advantage did not reproduce in CI.
One-option help regressed relative to a2 on both hosts, and ten-option help
regressed in CI; both CI help cases were slower than a2 in all twelve paired
rounds. These results do not support a universal speedup.

All eight fresh-process medians were lower than Click on both hosts, while
four per host were higher than a2. Whole-worker peak RSS remained above Click:
a3 / Click measured 25.193 / 24.062 MiB locally and 33.121 / 32.014 MiB in CI.
Python allocation samples do not include every native allocation. All eighteen
warm workloads, eight cold workloads, CPU times, variation, import and memory
observations are retained in the report.

The CI benchmark and published GNU wheel contain the
[same 18 Python/native runtime files](compatibility/releases/0.1.1a3-benchmark-payload.json),
although their wheel archive hashes differ. The earlier
[a2](docs/performance-0.1.1a2.md) and [a1](docs/performance.md) reports remain
unchanged historical measurements.

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
