# Measurement protocol

The current driver measures fixed Click 8.5.1, the published zclick 0.1.1a1
wheel and a candidate wheel under the same Python interpreter. It retains slow
results as well as improvements. The original schema-1, fixed-order results in
`results/` remain historical measurements; this protocol produces schema 2.

## Inputs and isolation

`baseline-lock.json` records the exact published wheel hashes and source
commit. `prepare_baseline.py` installs the compatible baseline wheel and fixed
Click wheel into a separate environment, marks runtime files read-only and
records their contents. An existing baseline is verified before reuse. Source
changes or rebuilding the candidate cannot change this environment.

The candidate wheel is copied into its own content-addressed environment. Both
environments contain the same Click wheel and use the same interpreter and
minimal virtual-environment setup. The candidate's Python source hashes and
package version must match the current checkout for a formal run. Native wheel
hashes, Cargo.lock, source commit and driver hashes are also retained. Build the
candidate from that frozen checkout with `--release --locked`.

Workers use isolated Python (`-I`) and a temporary working directory outside
the source tree. They do not import either zclick version from the checkout.
Every warm worker verifies its imported source paths and file hashes before
and after measurement. A final check verifies both complete snapshots.

## Balanced execution

Each of twelve rounds launches one fresh worker for each implementation.
Every six-round block contains all six possible implementation orders once,
shuffled with a recorded seed. Thus each implementation occupies each position
twice per block. Every cold workload has a separately seeded order schedule.
The raw report records every actual order and per-worker machine observation.

For each warm workload the worker checks outputs, makes five warmup calls,
then records one batch of wall and process CPU time. The outer rounds supply
the repeated samples. Full help and wrap output hashes, parse results, option
object identities and command return values are checked across implementations.
Normal garbage collection remains enabled. Workloads inside a worker retain a
fixed order; this is recorded and does not randomize away application state.

## Boundaries retained

All four sizes (1, 10, 100 and 1,000 options) retain construction, reuse of an
already-created parser, complete invocation of an already-created command and
help formatting. Nested invocation and Unicode/ANSI wrapping remain separate.
Complete warm invocation includes Context creation, parsing, conversion,
callbacks and binding costs. Construction is measured separately.

Cold samples launch a new interpreter for each observation. They include
import-only startup and, for all four sizes, complete command construction plus
invocation or `--help`. Whole-process timing ends after output capture and exit.
Operating-system caches are not flushed. No driver or metadata modules are
imported before the inner cold import interval except `time`.

Each round also records Python allocations while the returned value remains
alive, and the worker's whole-process peak RSS. `tracemalloc` does not count all
native allocations. Memory scalars are medians of the retained round samples;
RSS includes the interpreter and full worker workload, not just native parsing.

## Running and interpreting

```sh
maturin build --release --locked --out dist
python benchmarks/compare.py --candidate-wheel dist/*.whl \
  --iterations 1000 --repeats 12 --seed 20261111 --affinity auto \
  --output reports/benchmarks.json
```

`--affinity auto` pins the orchestrator and children to the first CPU in the
allowed Linux affinity set. An explicit subset such as `--affinity 2` can be
used instead; unavailable CPUs cause an error. Omit the option when affinity
control is unavailable. CPU model, allowed/current affinity, available frequency
observations, load, interpreter flags and clock details are recorded. Frequency
and shared-host activity remain uncontrolled. Isolated Python ignores
`PYTHONHASHSEED`, so hash randomization varies across fresh processes.

Ratios are reference median time divided by candidate median time: greater
than one means the candidate was faster for that workload. The report retains
Click-versus-candidate, Click-versus-published-version and published-versus-
candidate comparisons, plus raw paired round ratios. Differences in hosts,
protocols or interpreter versions must not be described as optimization gains.
Small differences require caution; a favorable individual workload does not
establish a universal speedup.

A short harness check can use `--iterations 1 --repeats 1 --diagnostic` with a
published wheel as the candidate. It verifies execution and report structure,
not performance. Diagnostic reports are marked explicitly and rejected by the
release-notes generator. Formal timing waits for a frozen build and a quiet
measurement interval; no unrelated tests or builds run concurrently locally.
