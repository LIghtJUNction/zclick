# Architecture and dependency boundaries

zclick separates token processing from Python's object protocol. The fixed
behavioral reference is [Click 8.5.1](../compatibility/target.json). A Python
callback is an arbitrary program: it may mutate an option, replace a converter,
invoke another command, or raise an exception. Keeping these operations
observable is part of the interface, rather than an optional slow path.

## What runs where

| Component | Responsibility | Runtime dependencies |
| --- | --- | --- |
| `python/zclick` | Public classes, decorators, virtual methods, Python type conversion, streams and platform integration | Python standard library |
| `crates/zclick-python` | PyO3 binding, parser action orchestration, command group dispatch, Python object ownership | PyO3 and the local Rust core; `std` |
| `crates/zclick-core` | Argument consumption, option recognition adapter, positional allocation, eager ordering, value-source arbitration, ANSI and text wrapping | Exactly registry `zclap = "=0.1.4"`; `no_std + alloc` |
| zclap | Actual recognition of normalized option tokens through its event parser | Its published dependency graph |

The core invokes zclap for option events. The dependency is not a dormant
manifest entry. zclap's default help, value consumption, final validation and
parent-command conventions do not define the Python interface; the Rust
semantic layer implements the differences listed in
[COMPATIBILITY.md](../COMPATIBILITY.md#zclap-adaptation).

The Python extension is not a `no_std` program. It allocates Python objects,
uses PyO3 and its required build/transitive dependencies, and links to the
interpreter. Python runtime requirements are empty. Maturin, pytest,
Hypothesis, mypy and original Click belong to build or comparison environments.
[`audit_dependencies.py`](../scripts/audit_dependencies.py) verifies these
boundaries; [`check_wheel.py`](../scripts/check_wheel.py) inspects the actual
distribution, including its namespace and dependency metadata.

## One invocation

The public command asks its current parameter objects to register with a fresh
parser. The binding creates call-local Rust schema storage. This storage owns
the names while zclap borrows them. No argument name is leaked or retained for
the lifetime of the process, and no borrowed value is given a fabricated
`'static` lifetime.

The Rust core recognizes tokens, consumes values using Click's rules, allocates
positional arguments and records encounter order. The binding invokes the
current Python parser action for each event, including overridden actions. Rust
then provides the stable eager-parameter schedule and value-source arbitration.
Python parameter hooks perform the requested conversion and callback with the
current context. Environment lookups, callable defaults and prompting happen
for that invocation.

Group invocation is driven by Rust. It resolves child commands through virtual
Python methods, calls custom `make_context` and `invoke` methods, handles chained
commands, and invokes result callbacks while the appropriate resources remain
open. A small Python `with` helper preserves the interpreter's handled-exception
state. Consequently a user-defined `__exit__` sees the real exception and
traceback, and exception suppression has the same meaning as a Python context
manager. The library never terminates the process through Rust
`std::process::exit`.

## Mutation, recursion and ownership

There is deliberately no schema cache. Building a plan on each invocation
observes mutations to `command.params`, option aliases and defaults, type
objects, callbacks and registered child commands. It also avoids retaining
Python application objects in a process-global cache. Benchmarks include the
cost of this policy; an optimization may not substitute stale structure or
cache the result of a callable default.

Callbacks may reenter the same command. No native lock or mutable PyO3 borrow is
held across a call to user Python code. Native dispatch frames participate in
Python garbage collection through explicit traversal, including cycles created
when an application retains a callback. Parsing state is local to one call.

Ordinary UTF-8 strings use the direct PyString path. Python strings containing
surrogate code points use a reversible `surrogatepass` representation at the
boundary. Values originating as whole argument objects retain their Python
identity where the reference parser does. There is no lossy UTF-8 conversion.
Integer conversion uses Python integers and therefore does not introduce an
`i64` or `u64` limit. Open files and user-provided streams preserve Python
ownership and closing behavior.

These properties have focused regressions in
[`test_dynamic_semantics.py`](../tests/test_dynamic_semantics.py),
[`test_native_dispatch.py`](../tests/test_native_dispatch.py) and
[`test_native_kernel.py`](../tests/test_native_kernel.py). The larger official
suite checks the behavior exposed by the fixed Click version.

## Interpreters and concurrency

The standard CPython wheel uses the stable ABI with a Python 3.10 minimum.
Free-threaded CPython and PyPy builds disable that ABI feature and build for
their interpreter. The native module does not keep Python objects in a global
cross-interpreter cache. Tiny parser calls keep their interpreter attachment;
releasing and reacquiring it for every token would itself add overhead. No GIL
speedup is claimed without a workload-specific measurement.

`CliRunner` intentionally changes interpreter-wide streams, environment values
and, for filesystem isolation, the process working directory. Its isolation
operations are not thread-safe. Use separate processes for parallel runner
tests. Per-call native parser state does not change that public testing-tool
boundary.

## Toolchain and licensing

The checked-in toolchain and declared MSRV are Rust **1.99.1**, Edition **2024**.
This is the version used for compilation and CI, not a lower version inferred
from one dependency's metadata. The registry version and checksum are fixed in
Cargo manifests and `Cargo.lock`; release builds use `--locked`.

Runtime implementations are written for this project. Public type declarations
are generated from the fixed Click API and retain Click's BSD attribution in
[`CLICK_LICENSE.txt`](../compatibility/CLICK_LICENSE.txt), included alongside
the project's MIT license in distributions. Upstream behavioral tests remain
comparison inputs outside the runtime package.
