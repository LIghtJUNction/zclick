# Changelog

## 0.1.1a3 — 2026-11-13

- Combine live schema validation and parsing in one native call. Preserve plan
  publication, normalizer lookup, state construction, flag evaluation and
  temporary-object release order, including callbacks that reenter parsing.
- Reuse fixed internal protocol strings, walk exact definition lists with a
  live cursor, and use single-argument zclap presence storage for each kernel
  recognition command. Dynamic names and invocation values remain owned.
- Reduce group dispatch and context-stack overhead, and load error-only helpers
  when their branch is taken.
- Match Click's parser action comparison order, help-option cache, parameter
  container identity, constructor truthiness and duplicate-parameter warnings.
- Compare the candidate with the immutable published 0.1.1a2 distribution and
  fixed Click 8.5.1. Preserve the older a1 lock for historical reproduction.

The pinned dependency and interpreter boundaries remain in force. This is an
alpha release with subinterpreter compatibility still unfinished. Performance
results report complete workload boundaries and include cases that remain
slower than Click.

## 0.1.1a2 — 2026-11-11

Reuse owned native schemas after validating live definitions, borrow ordinary
argument buffers, and reduce parser-event and formatting allocations. Published
results and exact release validation are retained in the
[a2 performance report](docs/performance-0.1.1a2.md) and
[release record](compatibility/releases/0.1.1a2.json).

## 0.1.1a1 — 2026-11-11

This is the first preview distribution. The fixed compatibility target is
Click 8.5.1; complete compatibility remains unfinished because CPython
subinterpreters are not supported.

### Implementation

- Provide the `zclick` Python namespace and matching public submodules, with
  generated API declarations and `py.typed`.
- Implement option recognition through registry zclap 0.1.4, with Rust adapters
  for Click's value consumption, positional arguments, eager ordering and
  value-source rules.
- Drive parser actions and command-group dispatch from Rust while preserving
  current Python methods, callbacks, subclass overrides and context scopes.
- Implement native text wrapping, ANSI handling and visible-width operations.
- Provide parameter types, prompts, terminal tools, shell completion and the
  public testing interface without a runtime dependency on original Click.
- Rebuild invocation plans after mutations, preserve arbitrary-size Python
  integers and surrogate-containing strings, and support callback reentry.

### Verification and distribution

- Pin the reference source, versioned documentation, official API inventory and
  all 33,459 upstream test IDs, including 31,000 stress cases.
- Add differential, mutation, ownership, callback-order and parser tests;
  retain the original assertions, platform skips and expected failures.
- Exercise generated completion with Bash, Zsh, Fish and PowerShell.
- Add immutable-source CI, API and typing checks, dependency/license audits,
  installed-wheel smoke tests, source-archive rebuilds and complete release
  evidence archives.
- Configure CPython wheels for Linux glibc/musl, macOS and Windows on x86-64 and
  ARM64, plus interpreter-specific Linux wheels for PyPy and free-threaded
  CPython. Actual outcomes are recorded by the release workflow.
- Add version bump automation and separate GitHub Release/PyPI publication jobs.
- Measure the Python API end to end, including startup, construction, dispatch,
  repeated parsing, help, formatting and memory. Results include slower cases.

### Known boundaries

- CPython subinterpreter import is deliberately rejected with `ImportError`
  before the binding can share Python objects across interpreters. This is an
  unresolved compatibility item, not a passing compatibility claim. A stable
  release is blocked while this item remains open.
- An application import alias does not migrate third-party extensions that
  continue to import original Click internally. See
  [the extension report](docs/extensions.md).
- `CliRunner` changes process/interpreter state and is not a thread-safe
  concurrent isolation mechanism.
- Performance depends on the workload; native calls and dynamic Python hooks
  have measurable overhead. See [the full measurements](docs/performance.md).

The [compatibility record](COMPATIBILITY.md),
[known gaps](compatibility/known-gaps.json) and release artifacts provide the
evidence and limitations for this version.
