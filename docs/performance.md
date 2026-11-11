# Measured performance

On the measured CPython 3.12/Linux snapshot, complete `Command.main` invocations were **1.08–1.75× faster** than Click 8.5.1, and the Unicode/ANSI text-wrapping workload was **7.02× faster**. The reused low-level parser was slower in every measured size, nested dispatch was slower, and help generation with 1,000 options was slightly slower. The results do not establish a universal speedup.

## Source and environment

- Date: 2026-11-11.
- zclick version: `0.1.0`; source commit [`8f782c5d83d75b1fe808b81b06bcce3fbed4ef54`](https://github.com/LIghtJUNction/zclick/commit/8f782c5d83d75b1fe808b81b06bcce3fbed4ef54).
- Reference: Click `8.5.1`; its exact source, release and documentation are pinned in [target.json](../compatibility/target.json).
- Interpreter: `3.12.14 (main, Aug 25 2026, 14:00:49) [Clang 22.1.3 ]`.
- Platform: `Linux-6.18.57-x86_64-with-glibc2.41`; 9 logical CPUs reported to the process.
- Build: release Rust extension, Rust 1.99.1 / Edition 2024, zclap 0.1.4 and PyO3 0.30.1.
- Repetitions: 9 samples per workload; 1,000 base iterations, scaled to 100 for 100 parameters and 10 for 1,000 parameters. Help uses one fifth as many iterations, with a minimum of 5.
- [Unmodified raw measurements](../benchmarks/results/cpython312-linux-8f782c5.json) include every wall/CPU sample, source-file and native-binary SHA-256 hashes, Cargo.lock hash, allocation samples and cold-start samples.

## Timing results

Values are median microseconds per call. **Ratio = Click time / zclick time**; a ratio above 1 indicates lower zclick latency. The CPU ratio uses process CPU time; wall time also includes scheduling delays.

| Workload | Click wall µs | zclick wall µs | Wall ratio | CPU ratio |
| --- | ---: | ---: | ---: | ---: |
| Construct command (1 option) | 4.206 | 4.097 | 1.027× | 1.027× |
| Reuse parser (1 option) | 1.552 | 3.964 | 0.392× | 0.392× |
| Command.main (1 option) | 31.571 | 29.268 | 1.079× | 1.079× |
| Render help (1 option) | 77.045 | 34.757 | 2.217× | 2.216× |
| Construct command (10 options) | 41.810 | 44.352 | 0.943× | 0.943× |
| Reuse parser (10 options) | 7.772 | 17.816 | 0.436× | 0.436× |
| Command.main (10 options) | 91.030 | 83.208 | 1.094× | 1.095× |
| Render help (10 options) | 123.549 | 76.853 | 1.608× | 1.607× |
| Construct command (100 options) | 467.610 | 361.951 | 1.292× | 1.292× |
| Reuse parser (100 options) | 63.625 | 158.564 | 0.401× | 0.401× |
| Command.main (100 options) | 814.457 | 610.502 | 1.334× | 1.308× |
| Render help (100 options) | 679.712 | 456.915 | 1.488× | 1.486× |
| Construct command (1000 options) | 5028.771 | 3692.478 | 1.362× | 1.357× |
| Reuse parser (1000 options) | 860.615 | 1635.883 | 0.526× | 0.526× |
| Command.main (1000 options) | 11816.259 | 6757.333 | 1.749× | 1.737× |
| Render help (1000 options) | 4749.309 | 5026.953 | 0.945× | 0.943× |
| Nested command | 52.668 | 60.586 | 0.869× | 0.868× |
| Unicode/ANSI wrap | 485.670 | 69.162 | 7.022× | 7.022× |

The 1,000-option invocation took 11.816 ms with Click and 6.757 ms with zclick: 1.749× throughput at this measured boundary, or about 42.8% less elapsed time per call. This workload includes argument-plan construction, option processing, integer conversion, callback execution and Python binding costs. It does not include process startup or terminal I/O.

The reused-parser result is a material limitation. Click's existing Python parser processes this narrow workload efficiently. Inspection of zclick's execution path shows that it reconstructs the native definition and crosses the Python/Rust boundary while preserving current mutable option objects and original argument identities. The timings do not isolate schema construction, zclap parsing, allocation and binding costs from each other. A future optimization must retain those mutation and identity guarantees.

The small invocation improvements are modest and individual sample ranges overlap. For one option, wall samples ranged from 29.24–50.07 µs for Click and 27.55–44.69 µs for zclick. This run supports the reported medians, not a guarantee for every invocation or machine. The 1,000-option invocation and long text-wrapping improvements were larger than the observed sample variation.

## Startup

Every import sample starts a fresh interpreter. The import interval begins after importing only `time`; the full-process interval additionally includes spawning the interpreter, startup and printing the measurement.

| Boundary | Click median ms | zclick median ms | Ratio |
| --- | ---: | ---: | ---: |
| Import package | 23.600 | 23.420 | 1.008× |
| Fresh process + import | 41.523 | 41.104 | 1.010× |

The startup difference is approximately 1%, within ordinary run-to-run variability. This measurement does not establish a meaningful startup advantage.

## Memory observations

`tracemalloc` records Python-managed allocations during one call, after a collection. Its peak includes temporary and returned Python objects. It does **not** measure every Rust allocation. Process RSS is a separate high-water mark across the worker's entire set of workloads, including the interpreter and benchmark driver.

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
| Nested command | 9,810 | 10,007 |
| Unicode/ANSI wrap | 42,128 | 8,126 |

Worker peak RSS was 22.46 MiB for Click and 23.64 MiB for zclick. The whole-process measurement is not an isolated count of native parser allocations. The text-wrapping workload uses fewer observed Python bytes; large option invocations use more. No zero-allocation claim is made.

## Reproduce and interpret

```sh
maturin develop --release --locked
python benchmarks/compare.py --iterations 1000 --repeats 9 --output reports/benchmarks.json
```

The benchmark driver verifies outputs before timing and runs the packages in separate processes. It leaves normal interpreter GC behavior enabled. Options are long integer-valued options, every option receives a value, and the callback sums the converted integers. Construction, a reused parser, complete invocation, help rendering, nested dispatch and text wrapping are measured separately. Dynamic defaults, prompts, filesystem work and user business logic are outside these workloads.

The execution order is Click followed by zclick, without CPU affinity or frequency locking. A quiet interval was used, but the host can still schedule other work. Nine repeated samples expose variability; they are not a statistical guarantee or an estimate for every Click application. Release CI repeats the same driver on the immutable release commit and attaches its raw JSON to the GitHub release.
