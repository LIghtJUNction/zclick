# Measured performance

For the final measured `0.1.1a1` snapshot, the 1,000-option `Command.main` workload was **1.706× faster** than Click 8.5.1 and the Unicode/ANSI wrapping workload was **7.344× faster**. Small warm invocations and reused-parser calls were slower. A fresh process that imported the package, constructed and invoked a 1,000-option command was **1.183× faster** in this run. These results are workload-specific and do not establish a universal speedup.

## Source and environment

- Date: 2026-11-11.
- zclick: `0.1.1a1` at [`86bab2a8de3092155a912a4028382aba8188e6db`](https://github.com/LIghtJUNction/zclick/commit/86bab2a8de3092155a912a4028382aba8188e6db).
- Reference: Click `8.5.1`; [target.json](../compatibility/target.json) pins its source, release and documentation.
- Interpreter: `3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]`.
- Host: `Linux-6.18.57-x86_64-with-glibc2.41`; 9 logical CPUs reported to the process.
- Build: release extension, Rust 1.99.1 / Edition 2024, zclap 0.1.4 and PyO3 0.30.1.
- Samples: 9 per workload. Warm measurements use 1,000 base iterations, scaled to 100 for 100 parameters and 10 for 1,000 parameters; help uses one fifth as many, with a minimum of 5. Cold measurements use 9 separate fresh interpreters for each package, size and action.
- [Final raw measurements](../benchmarks/results/cpython312-linux-86bab2a.json) retain every sample, runtime/native-file hashes, Cargo.lock hash, Python allocation observations and process peak RSS.
- [Earlier 0.1.0 development measurements](../benchmarks/results/cpython312-linux-8f782c5.json) are retained as history. They are not substituted for the final measurements when an earlier number was more favorable.

## Warm Python API measurements

Values are median microseconds per call. **Ratio = Click time / zclick time**; above 1 means lower zclick latency. CPU ratios use process CPU time. Wall time also includes scheduling delays.

| Workload | Click wall µs | zclick wall µs | Wall ratio | CPU ratio |
| --- | ---: | ---: | ---: | ---: |
| Construct command (1 option) | 3.410 | 3.981 | 0.857× | 0.856× |
| Reuse parser (1 option) | 1.558 | 3.867 | 0.403× | 0.403× |
| Command.main (1 option) | 23.453 | 33.813 | 0.694× | 0.694× |
| Render help (1 option) | 53.449 | 35.509 | 1.505× | 1.504× |
| Construct command (10 options) | 29.481 | 38.888 | 0.758× | 0.758× |
| Reuse parser (10 options) | 6.389 | 17.415 | 0.367× | 0.367× |
| Command.main (10 options) | 70.954 | 86.287 | 0.822× | 0.822× |
| Render help (10 options) | 103.318 | 74.396 | 1.389× | 1.389× |
| Construct command (100 options) | 292.765 | 367.733 | 0.796× | 0.796× |
| Reuse parser (100 options) | 60.797 | 167.109 | 0.364× | 0.364× |
| Command.main (100 options) | 606.239 | 528.201 | 1.148× | 1.148× |
| Render help (100 options) | 525.247 | 452.839 | 1.160× | 1.160× |
| Construct command (1000 options) | 4781.334 | 3478.570 | 1.375× | 1.374× |
| Reuse parser (1000 options) | 1000.769 | 1516.540 | 0.660× | 0.660× |
| Command.main (1000 options) | 11176.295 | 6552.579 | 1.706× | 1.707× |
| Render help (1000 options) | 4899.930 | 4896.697 | 1.001× | 1.001× |
| Nested command | 51.620 | 53.222 | 0.970× | 0.969× |
| Unicode/ANSI wrap | 471.700 | 64.231 | 7.344× | 7.272× |

The 1,000-option warm invocation took 11.176 ms with Click and 6.553 ms with zclick, about 41.4% less elapsed time per call. It reuses an already-defined `Command`: the timed work includes a fresh invocation context, parser-plan setup, argument processing, integer conversion and the command callback. `Command` and `Option` construction, process startup and terminal I/O are outside this warm invocation measurement.

The reused-parser result is a material limitation. That workload constructs its parser before timing and measures `parse_args` plus a fresh argument-list copy. Inspection of zclick shows that it reconstructs the native definition while preserving mutable option objects and original argument identities. The timings do not separate schema construction, zclap work, allocations and binding overhead from each other. A future optimization must retain those mutation and identity guarantees.

## Whole fresh-process commands

Each sample creates a new interpreter, imports the selected package, constructs all `Option` and `Command` objects, then invokes the command or renders `--help`. The interval ends after process termination and includes output capture. These measurements answer a different question from repeated calls in an already-running Python process.

| Fresh process action | Click median ms | zclick median ms | Ratio |
| --- | ---: | ---: | ---: |
| Invoke command (1 option) | 44.227 | 41.522 | 1.065× |
| Render help (1 option) | 44.435 | 41.370 | 1.074× |
| Invoke command (10 options) | 39.195 | 40.491 | 0.968× |
| Render help (10 options) | 47.201 | 41.713 | 1.132× |
| Invoke command (100 options) | 44.755 | 40.799 | 1.097× |
| Render help (100 options) | 46.028 | 41.057 | 1.121× |
| Invoke command (1000 options) | 62.046 | 52.450 | 1.183× |
| Render help (1000 options) | 74.022 | 57.461 | 1.288× |

The roughly 3–10% differences in small fresh-process cases should not be treated as significant or guaranteed improvements. Process scheduling, CPU frequency and filesystem caches can affect measurements of this size. Full sample ranges are preserved in the raw JSON. A CLI with expensive user callbacks or filesystem work can show a different ratio.

## Import-only startup

These samples start a fresh interpreter and import the package without constructing a command. Only `time` is imported before the inner import interval. The whole-process interval includes interpreter startup and printing the timing. Operating-system filesystem caches are not flushed.

| Boundary | Click median ms | zclick median ms | Ratio |
| --- | ---: | ---: | ---: |
| Import package | 21.352 | 26.043 | 0.820× |
| Fresh process + import | 40.251 | 46.862 | 0.859× |

Import-only timing does not establish the performance of an actual command. Use the fresh-process command results for that boundary.

## Memory observations

`tracemalloc` observes Python-managed allocations during one call after a collection; returned objects remain alive through the sample. It does **not** count every Rust allocation. RSS is a separate process high-water mark across the worker's complete workload set, including the interpreter and benchmark driver.

| Workload | Click Python peak bytes | zclick Python peak bytes |
| --- | ---: | ---: |
| Construct command (1 option) | 3,290 | 3,458 |
| Reuse parser (1 option) | 2,488 | 1,330 |
| Command.main (1 option) | 7,274 | 7,160 |
| Render help (1 option) | 5,288 | 2,996 |
| Construct command (10 options) | 20,252 | 20,420 |
| Reuse parser (10 options) | 2,792 | 2,522 |
| Command.main (10 options) | 14,857 | 14,891 |
| Render help (10 options) | 7,102 | 4,850 |
| Construct command (100 options) | 189,828 | 189,996 |
| Reuse parser (100 options) | 6,584 | 16,362 |
| Command.main (100 options) | 93,387 | 98,625 |
| Render help (100 options) | 25,999 | 23,729 |
| Construct command (1000 options) | 1,887,972 | 1,888,140 |
| Reuse parser (1000 options) | 54,560 | 163,850 |
| Command.main (1000 options) | 780,943 | 919,413 |
| Render help (1000 options) | 215,608 | 213,339 |
| Nested command | 9,810 | 9,951 |
| Unicode/ANSI wrap | 42,128 | 8,126 |

Worker peak RSS was 22.78 MiB for Click and 23.82 MiB for zclick. This is not an isolated measurement of native parser allocations. Text wrapping uses fewer observed Python bytes, while large option invocation uses more. The extension allocates Python and Rust objects; no zero-allocation claim is made.

## Reproduce and interpret

```sh
maturin develop --release --locked
python benchmarks/compare.py --iterations 1000 --repeats 9 --output reports/benchmarks.json
```

The driver verifies outputs before warm timing and validates every fresh-process result. The two packages run in separate worker processes. Normal interpreter GC remains enabled. Command construction uses the public `Option` and `Command` constructors; each long option receives an integer value, and the callback sums the converted values. Dynamic defaults, prompts, user business logic and application filesystem work are outside these workloads.

Packages run in a fixed order: Click, then zclick. The shared host is not isolated with CPU affinity or frequency locking, and package order is not randomized or interleaved. A quiet interval was used, but other host activity remains possible. Nine samples show variability; they are not a statistical guarantee. Small differences and differences between the earlier and final snapshot can reflect both code and measurement conditions. Release CI independently runs this driver on its immutable commit and publishes its raw JSON.

## Independent release CI comparison

The release pipeline measured commit [`a8bc735a3df168b62b2e11d99b34e7ab40530ba7`](https://github.com/LIghtJUNction/zclick/commit/a8bc735a3df168b62b2e11d99b34e7ab40530ba7) on a separate runner. Its runtime code is the same as the locally measured `86bab2a` snapshot; the release-trigger commit adds documentation and release-note generation. The host and interpreter differ, so the two sets remain separate measurements.

- CI interpreter: `3.14.10 (main, Oct 26 2026, 14:17:03) [GCC 15.2.0]`.
- CI host: `Linux-7.0.0-1019-azure-x86_64-with-glibc2.43`; 4 logical CPUs reported.
- [CI raw JSON](../benchmarks/results/cpython314-linux-a8bc735.json) and [release workflow](https://github.com/LIghtJUNction/zclick/actions/runs/43029689108) retain source hashes, all repeated samples and the exact environment.

Ratios below are Click median / zclick median. All listed boundaries use the same driver and parameters on both hosts.

| Boundary | Local CPython 3.12 ratio | CI CPython 3.14 ratio |
| --- | ---: | ---: |
| Warm Command.main / 1 option | 0.694× | 0.939× |
| Warm Command.main / 10 options | 0.822× | 1.006× |
| Warm Command.main / 100 options | 1.148× | 1.185× |
| Warm Command.main / 1,000 options | 1.706× | 2.013× |
| Reused parser / 1 option | 0.403× | 0.464× |
| Reused parser / 1,000 options | 0.660× | 0.425× |
| Nested command | 0.970× | 0.886× |
| Unicode/ANSI wrapping | 7.344× | 9.038× |
| Fresh-process command / 1 option | 1.065× | 0.952× |
| Fresh-process command / 10 options | 0.968× | 0.945× |
| Fresh-process command / 100 options | 1.097× | 0.961× |
| Fresh-process command / 1,000 options | 1.183× | 1.067× |
| Fresh-process help / 1,000 options | 1.288× | 0.953× |

The larger warm invocation and text-wrapping gains appear on both hosts. The reused parser remains slower on both. Small warm commands and whole-process startup show mixed results. The local 1.288× fresh-process help result did **not** reproduce on CI, where that boundary measured 0.953×. It must not be presented as a portable help-startup improvement.

On CI, the 1,000-option warm invocation was 14.713 ms for Click and 7.309 ms for zclick. Whole-process invocation was 71.540 ms and 67.020 ms respectively; whole-process help was 73.347 ms and 76.995 ms. The approximately 6.7% invocation difference is small relative to the scheduling and frequency limitations of this method and is not claimed to be statistically significant.

Neither host's results replace the other. The source archives and release assets retain the original measurements, including regressions.
