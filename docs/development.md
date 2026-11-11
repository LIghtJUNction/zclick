# Build, verify and release

## Local build

Install the pinned Rust toolchain with rustup, and use Python 3.10 or newer.
The standard development setup is:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
maturin develop --release --locked
python -m pytest tests
python scripts/audit_dependencies.py
```

On Windows, activate with `.venv\Scripts\Activate.ps1`. On PyPy or free-threaded
CPython, add `--no-default-features` to the Maturin command. Those interpreters
need their own extension build, rather than the ordinary CPython stable ABI.

The Rust core can be checked independently:

```sh
cargo test -p zclick-core --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo check -p zclick-core --target wasm32-unknown-unknown --locked
```

The last command requires `rustup target add wasm32-unknown-unknown`. It verifies
the core's `no_std + alloc` boundary; it does not describe the Python extension.

## Reproduce compatibility evidence

[`compatibility/target.json`](../compatibility/target.json) locks the original
Click commit, distribution checksums, documentation and test sources. The
harness verifies the checkout, prepares a namespace-only migration and runs
both packages. It does not import original Click from the runtime package.

```sh
python scripts/run_compatibility.py --output reports/normal -- -m 'not stress'
python scripts/run_stress.py --output reports/stress --workers 4 --batch-size 500
python scripts/api_inventory.py --source .cache/click-source --output reports/api-reference.json
python scripts/api_inventory.py --compare reports/api-reference.json --output reports/api.json
python3.12 scripts/check_subinterpreters.py --output reports/subinterpreters
python scripts/release_gate.py --reports reports/normal/summary.json reports/stress/summary.json --api reports/api.json --boundary reports/subinterpreters/summary.json
```

The stress runner uses exact original node IDs in smaller subprocesses. This
limits how many pytest collection objects its repeated GC tests must traverse.
It checks the union for missing, extra and duplicate cases. This changes test
batching, not assertions, parameter counts or skips. The pager function retains
the upstream full-suite collection imports on which its fixture relies.

The API inventory is generated on the same interpreter as the candidate audit.
This matters for inherited standard-library methods: an `Enum` constructor's
signature can change between Python versions even when the same Click source
commit is used. Tests compare both packages under the same interpreter.

CI also runs the original typing examples and the focused native, mutation,
platform and shell regressions. A passing Linux job does not stand in for a
Windows or macOS result. Individual results and unchanged upstream platform
skips remain visible in the workflow artifacts.

[`compatibility/test-manifest.json`](../compatibility/test-manifest.json) records
the count and SHA-256 fingerprint of all 33,459 canonical upstream test IDs. The
release gate requires that exact set. It also checks every report's source
commit against the immutable release commit. Per-file source hashes identify
locally tested changes that have not yet been committed. A normal compatibility
run fails if those files change while its tests are running.

The dedicated Shell job installs Fish and PowerShell archives from the URLs
and SHA-256 checksums in `compatibility/shell-runtime-lock.json`, uses Bash and
Zsh on the runner, and requires all four executables. It then executes the
generated completion sources. See [Shell completion](shell-completion.md) for
the exact integration boundaries and reproducible commands.

## Reproduce benchmarks

```sh
maturin develop --release --locked
python benchmarks/compare.py --iterations 1000 --repeats 9 --output reports/benchmarks.json
```

The driver checks each workload's result before timing. It records separate
processes for the two packages, repeated wall and CPU measurements, import
latency, Python allocation peaks and process peak RSS. The `invoke` workload
includes Python binding and command setup costs; `parse` uses an already-created
Python parser. These are different boundaries and must remain separately
reported. Ratios greater than one mean that zclick was faster in that workload.
Python `tracemalloc` does not measure all Rust allocations.

## Interpreter compatibility boundary

Subinterpreter compatibility is **UNFINISHED**. Click 8.5.1 works in the tested
CPython 3.12 subinterpreters; zclick's native binding is restricted to the main
interpreter. This includes worker threads in that interpreter. It does not
include isolated or legacy shared-GIL subinterpreters.

The pinned PyO3 0.30.1 binding keeps Python-object caches that cannot safely be
shared across interpreters. zclick rejects child-interpreter initialization
before entering those caches. The diagnostic compares both packages in fresh
processes, checks both import orders and verifies that the main interpreter
still works afterward. Its report distinguishes `safe_rejection` from
`compatibility_passed`; safety does not remove the compatibility difference.

The [known gap list](../compatibility/known-gaps.json) remains part of the
release evidence. While any item is unfinished, the release gate rejects a
version without an `a`, `b` or `rc` suffix. A disclosed prerelease still requires
all original tests, API contracts, actual Shell tests and interpreter safety
checks. No upstream tests are removed, weakened or marked xfail for this gap.

## Distribution and release gates

Build and inspect distributions locally with:

```sh
maturin build --release --locked --out dist
maturin sdist --out dist
python scripts/check_wheel.py dist/*.whl
python -m twine check dist/*
```

The [release workflow](../.github/workflows/release.yml) first pins the exact
release commit. It then requires the compatibility, typing, dependency and
platform gates, builds Linux glibc/musl, macOS and Windows wheels for x86-64 and
ARM64, and builds a source distribution. Publishing uses those artifacts, not a
second unverified build.

Every wheel is installed and executed outside the source checkout. The checks
call the native parser, render help, dispatch a group, preserve a Python integer
larger than 64 bits and capture Unicode-capable output. The musllinux wheels
run in an official Python Alpine container pinned by its multi-architecture
manifest digest. The source archive is independently rebuilt, installed and
executed before it can be published.

The eight ordinary wheel targets use CPython's stable ABI from Python 3.10.
Linux x86-64 also has separate interpreter-specific wheels for PyPy 3.11 and
3.12, and free-threaded CPython 3.14 and 3.15. Other PyPy or free-threaded platforms require
a source build with `--no-default-features`; a successful CPython stable-ABI
wheel does not establish support for those runtimes. The exact platform results
remain in the CI artifacts and release evidence archive.

Version changes use [`bump_version.py`](../scripts/bump_version.py). It updates
the Python project, Rust workspace packages and lockfile together. The workflow
supports prerelease, patch, minor, major and explicit PEP 440 versions. A tag
must exactly match the project version. A release entry records whether the
version is a prerelease.

Release automation accepts a matching version tag, a workflow dispatch, or a
push to `main` whose first commit-message line is exactly `release: VERSION`.
The branch trigger is useful when an authorized repository connector can push
commits but cannot dispatch workflows. It still requires the same source,
compatibility, Shell, type, build and artifact-execution gates. Alpha, beta and
release-candidate versions are marked as GitHub prereleases. GitHub release
assets include the distributions, per-case evidence archive and raw benchmark
JSON. GitHub artifact publication and PyPI publication run as separate jobs so
PyPI authentication failure does not hide downloadable GitHub artifacts.

PyPI publication uses its GitHub Trusted Publisher configuration or the
repository's `PYPI_API_TOKEN` secret. Repository write access alone does not
establish PyPI publishing ownership. A publication failure remains a visible
failed job and must not be described as an available `pip install` release.
