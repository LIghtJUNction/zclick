# Architecture and dependency boundaries

zclick separates token processing from Python's object protocol. The fixed
behavioral reference is [Click 8.5.1](../compatibility/target.json). A Python
callback is an arbitrary program: it may mutate an option, replace a converter,
invoke another command, or raise an exception. Keeping these operations
observable is part of the interface, rather than an optional slow path.

## What runs where

| Component | Responsibility | Runtime dependencies |
| --- | --- | --- |
| `python/zclick` | Public classes and decorators, context lifecycle, overridable parameter hooks, defaults and environment lookup, type conversion, help assembly, terminal utilities, completion and testing | Python standard library |
| `crates/zclick-python` | PyO3 binding, parser action orchestration, command group dispatch, Python object ownership | PyO3 and the local Rust core; `std` |
| `crates/zclick-core` | Argument consumption, option recognition adapter, positional allocation, eager ordering, value-source arbitration, ANSI and text wrapping | Exactly registry `zclap = "=0.1.4"`; `no_std + alloc` |
| zclap | Actual recognition of normalized option tokens through its event parser | Its published dependency graph |

This is a hybrid implementation with substantial Python responsibilities.
Python owns the public object model and dynamic hooks listed above; Rust owns
token and arity processing, parameter ordering, source arbitration, group
dispatch and the text primitives used by the Python help formatter. The
boundary preserves ordinary subclass overrides and Python object semantics.

The core obtains successful option matches from zclap's `Event::Flag` and
requires the parser's final `finish()` check. Larger schemas use a hash to
choose candidate tables; zclap still decides whether a spelling matches.
Consumed values also pass through zclap's byte-input parser, with a terminator
that preserves Click's treatment of dash-leading values. These paths are
implemented in [`parse.rs`](../crates/zclick-core/src/parse.rs). The Rust
semantic layer supplies the Click rules that differ from zclap's default
value consumption, help and parent-command conventions, as recorded in
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
held across a call to user Python code. Parsing state is local to one call.

Native dispatch frames expose their captured Python references to garbage
collection through explicit traversal. They also release those references when
the complete Python context scope returns or raises. This deterministic cleanup
breaks retained extension-callback cycles on PyPy while keeping the callback
usable throughout the active scope, including `__exit__` and resource cleanup.
The mutable PyO3 borrow ends before captured references are released, so a
Python finalizer can reenter safely. These rules are implemented in
[`dispatch.rs`](../crates/zclick-python/src/dispatch.rs).

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
their interpreter.

The CPython extension currently supports the main interpreter only. zclick's
parser schemas and dispatch handles are local to an invocation, but the pinned
PyO3 0.30.1 binding has process-global Python-object caches, including the
iterator [length-hint callable](https://github.com/PyO3/pyo3/blob/v0.30.1/src/types/iterator.rs)
used in stable-ABI builds and native type state. These caches are not partitioned
by interpreter. Subinterpreter support therefore remains an
[unfinished compatibility item](../compatibility/known-gaps.json), including
subinterpreters that share the main interpreter's GIL.

The first operation in zclick's standard PyO3 module initializer checks
`PyInterpreterState_GetID(PyInterpreterState_Get()) == 0` and raises
`ImportError` for other IDs. Both identity queries are part of CPython's
[stable C API](https://docs.python.org/3.12/c-api/init.html#c.PyInterpreterState_GetID);
the supported CPython 3.10–3.15 sources assign ID zero exclusively to the main
interpreter (see [`pystate.c`](https://github.com/python/cpython/blob/3.15/Python/pystate.c)).
CPython invokes module initialization with the current thread attached, so the
queries receive a valid current interpreter. They do not create Python object
references or require manual reference counting or interpreter-structure
access. The implementation retains PyO3's standard module initialization and
does not declare subinterpreter support.

The package imports the native module before its Python public modules, so an
unsupported import is rejected before those modules initialize additional
native state. The CPython identity check is excluded from PyPy builds, which
do not provide CPython's subinterpreter API. The guard and its import-order
regressions are in
[`interpreter.rs`](../crates/zclick-python/src/interpreter.rs) and
[`test_interpreter_isolation.py`](../tests/test_interpreter_isolation.py).
The tests cover default and legacy shared-GIL subinterpreters, both import
orders, continued main-interpreter operation after rejection, and prevention
of calls to a main-interpreter cached callable from a child interpreter.

Tiny parser calls keep their interpreter attachment; releasing and reacquiring
it for every token would itself add overhead. No GIL speedup is claimed without
a workload-specific measurement.

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
