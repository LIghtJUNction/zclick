# Measured performance: 0.1.1a3 candidate

**Status: local candidate measurement, not a release result.** This report
records the frozen 0.1.1a3 candidate at commit `2a9e2c3` after correction of
a PyPy import failure. It contains the complete CPython 3.12 run on one Linux
host. It does not assert a second-host result, a completed platform gate or
publication of a3.

On this host, one-option warm invocation measured **1.083×**
relative to Click 8.5.1 and **1.079×** relative to the
published zclick 0.1.1a2 wheel. The nested-command ratios were
**1.040×** and **1.166×**.
These are modest workload improvements, with substantial round-to-round
variation. The larger version changes were in reused parsing at one and ten
options: **1.615×** and
**1.370×** relative to a2. Both cases still took
longer than Click.

The result is mixed. One-option help and wrapping have higher median latency
than a2; ten-option construction differs by less than half a percent. Four of
eight complete fresh-process workloads are slower than a2, while import-only
medians are almost unchanged. The **1.776×** Click comparison
for the 1,000-option full invocation and **7.507×** comparison
for wrapping mostly describe advantages already present in a2: their a2/a3
ratios are only **1.042×** and
**0.978×**. A large advantage over Click in these
rows is not a large new gain from this revision.

All values below come from the unchanged
[local schema-2 report](../benchmarks/results/cpython312-linux-2a9e2c3.json). The a2 wheel was measured again
in the same run; this report does not compare new timings against old runs.
The [a2 report](performance-0.1.1a2.md) and [a1 report](performance.md) remain
separate historical records. An earlier candidate run is retained in
[`cpython312-linux-6cdbcd7.json`](../benchmarks/results/cpython312-linux-6cdbcd7.json).
It predates the PyPy fix and is superseded for this candidate by the new complete
run below. Samples from the two runs are not pooled or selected by which is
faster, and their differences cannot be attributed to the import fix alone.
Ratios everywhere mean **reference median time /
candidate median time**. Above one means lower candidate latency; below one
means higher candidate latency. A ratio of 1.10 means approximately 9.1% less
time, not 10% less time.

## Source, distributions and environment

The experiment fixes the Click behavior target and the published version
control independently of the candidate. Package file hashes are recorded and
checked before and after measurement. This prevents a local source edit from
silently changing the published baseline.

| Item | Recorded value |
| --- | --- |
| Candidate source | [`2a9e2c32a5deb91422902d906894ad33a4de6ff3`](https://github.com/LIghtJUNction/zclick/commit/2a9e2c32a5deb91422902d906894ad33a4de6ff3) |
| Source state during timing | Clean before and after; candidate version and all Python file hashes match the frozen checkout |
| Behavioral reference | Click 8.5.1, commit `cf19179e8e2fd54c601378cec9e0d21bb12b6fb1`; [target lock](../compatibility/target.json) |
| Published performance baseline | zclick 0.1.1a2, commit `7e3d597873b737bbfc8c2df090773aad56d9bd73`; [distribution lock](../benchmarks/baseline-lock.json) |
| Measurement interval | 2026-11-13 06:12:49–06:13:35 UTC; 46.65 seconds overall |
| Interpreter | CPython 3.12.14, Clang 22.1.3, ordinary GIL build |
| Host | Linux 6.18.57 x86-64, glibc 2.41, AMD EPYC 9V74 80-Core Processor |
| CPU affinity | Nine logical CPUs available; orchestrator and all measured workers pinned to CPU 0 |
| Repetition and ordering | Twelve rounds, two complete blocks of all six implementation orders; seed `20261111` |
| Warmup and collection | Five warmup calls per workload and round; normal garbage collection enabled |
| Rust dependencies | Rust 1.99.1, Edition 2024; registry zclap 0.1.4 and PyO3 0.30.1 |
| Raw report SHA-256 | `d652b4a2293c3282aa3c8c0fde61e524fbe710d0aaef4e51a7f1d55d0087fa1f` |
| Candidate native file SHA-256 | `e6ee14999248235b5928fe1c5102d39bae9885fd9b05652061b8583d410bb63a` |
| Cargo.lock SHA-256 | `e1388e66bad5c93c59bfcfd9deecc1255c201fa18a30bc170d95c1459d5a969b` |
| Baseline lock SHA-256 | `f7960066066e89299d8b550fc02ed9d9f9184b94814125fe691861de205170ae` |

**Table 1. Actual distributions measured.** Filenames and hashes identify the
wheels installed into the isolated environments.

| Distribution | Wheel filename | Wheel SHA-256 |
| --- | ---: | ---: |
| Click 8.5.1 | `click-8.5.1-py3-none-any.whl` | `8bb5376d2006950386f8c6427613334a2acadc5f559cb80e638d00b4df957e37` |
| Published zclick 0.1.1a2 | `zclick-0.1.1a2-cp310-abi3-manylinux2014_x86_64.manylinux_2_17_x86_64.whl` | `dd69bc1b014559a0c77319f52334811951e49fb134f916a3e76f5b7abd493a0c` |
| Candidate zclick 0.1.1a3 | `zclick-0.1.1a3-cp310-abi3-manylinux_2_34_x86_64.whl` | `154c50dfd6659089a959075570bea30ab3eb93a0d0bbf3644b0c859ef871bc51` |

The published a2 wheel targets `manylinux_2_17`; the candidate is a host build
targeting `manylinux_2_34`. The interpreter, measurement host and execution
schedule are controlled, but the build environments are not identical.
**The entire measured difference cannot be attributed to source changes
alone.** A later distribution build on another host needs its own measurement
and provenance; this report does not substitute the local wheel for that work.

## What changed and what the measurements cover

The main change reduces the number of Python-to-Rust calls in reused parsing.
The parser previously validated its current definitions and then entered
native parsing separately. The new entry point performs those operations in
one call while preserving publication of the owned plan and the order of
normalizer lookup, Python state construction, flag evaluation and resource
release. Dynamic hooks still execute. This mechanism is documented in
[the architecture](architecture.md#one-invocation) and implemented in
[`plan.rs`](../crates/zclick-python/src/plan.rs) and
[`parser.py`](../python/zclick/parser.py). The experiment compares the complete
distributions; it does not isolate the number of microseconds contributed by
this change alone.

Smaller changes reduce repeated work without caching application results.
The binding reuses a finite set of literal protocol names such as `process`
and `nargs`; user-defined names and values remain owned. Exact lists of
parameter definitions use a live cursor, so mutation during an attribute
lookup remains visible, and list subclasses keep their Python iterator
protocol. Each zclap candidate command uses one-argument presence storage,
while successful matches still require zclap's event and final validation.
These changes are described in
[the ownership section](architecture.md#mutation-recursion-and-ownership)
and [`parse.rs`](../crates/zclick-core/src/parse.rs).

Group dispatch reuses the same fixed protocol names and context-stack push
performs one thread-local lookup. The implementation continues to use
`threading.local`: an attempted direct `_thread` import was reverted to keep
the pinned upstream light-import behavior. Error-only helpers are imported
when needed. Context managers, Python overrides, conversion and callback calls
remain observable; there is no cache of default values, environment results,
contexts or callback results. The relevant source is
[`dispatch.rs`](../crates/zclick-python/src/dispatch.rs),
[`globals.py`](../python/zclick/globals.py) and
[`core.py`](../python/zclick/core.py).

This revision also fixes observable help and parameter behavior. It preserves
the target's parameter-container identity, help-option cache and dynamic
attribute access order, constructor truthiness and duplicate-parameter
warnings. Those are compatibility changes, not evidence of a speedup. Their
paired regression cases are in
[`test_command_help_protocols.py`](../tests/test_command_help_protocols.py).
The tables retain the help regressions instead of removing this cost from the
comparison.

### Measurement boundaries

The driver measures four distinct operations at each of four sizes. Keeping
the boundaries separate shows where a parser improvement affects a complete
command and where other work dominates.

| Boundary | Included work |
| --- | --- |
| Construct | Public option and command construction for 1, 10, 100 or 1,000 options |
| Reuse parser | A fresh argument list, live definition validation, token processing and current parser actions through an already-created parser |
| Command.main | Invocation of an already-created command, including context creation, parsing, conversion, callback binding and return; `standalone_mode=False` |
| Render help | Public help generation for an already-created command and context |
| Nested command | A group resolving and invoking a child with one integer option and a checked result |
| Unicode/ANSI wrapping | Public wrapping on fixed Unicode and ANSI-containing text with a checked complete output |
| Fresh-process command or help | Interpreter startup, import, construction, invocation or `--help`, output capture and exit |

Each warm worker starts in an isolated interpreter with `-I`, outside the
source checkout. Its imports and file hashes are verified before and after
measurement. Every round starts a new worker per implementation; each six-round
block contains all six implementation orders once. Cold workloads have their
own balanced order schedules. The warm driver checks and retains full help and wrapped-text hashes, parsed
values, option object identity and callback return values across implementations.
Cold-process output is also validated by the driver, but the report does not
retain a separate stdout hash for every cold sample. The complete method is in
[the protocol](../benchmarks/README.md) and
[`compare.py`](../benchmarks/compare.py).

## All eighteen warm wall-time measurements

**Table 2. Median microseconds per call; lower time is better.** Each of the
twelve observations is a batch average. Base batches contain 1,000 calls,
scaled to 100 calls at 100 options and ten at 1,000 options; help uses one fifth
as many calls with a minimum of five. The two ratio columns use the same a3
median and separate Click and published-a2 references.

| Workload (options) | Click µs ↓ | a2 µs ↓ | a3 µs ↓ | Click / a3 ↑ | a2 / a3 ↑ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Construct (1) | 3.495 | 3.419 | 3.352 | 1.043× | 1.020× |
| Reuse parser (1) | 1.541 | 2.798 | 1.732 | 0.890× | 1.615× |
| Command.main (1) | 24.329 | 24.220 | 22.455 | 1.083× | 1.079× |
| Render help (1) | 55.361 | 22.529 | 24.773 | 2.235× | 0.909× |
| Construct (10) | 29.213 | 28.304 | 28.413 | 1.028× | 0.996× |
| Reuse parser (10) | 6.091 | 8.840 | 6.453 | 0.944× | 1.370× |
| Command.main (10) | 70.358 | 63.041 | 57.386 | 1.226× | 1.099× |
| Render help (10) | 95.230 | 55.477 | 55.133 | 1.727× | 1.006× |
| Construct (100) | 286.798 | 289.088 | 285.954 | 1.003× | 1.011× |
| Reuse parser (100) | 55.453 | 61.344 | 52.448 | 1.057× | 1.170× |
| Command.main (100) | 554.781 | 477.843 | 452.120 | 1.227× | 1.057× |
| Render help (100) | 477.816 | 373.913 | 366.728 | 1.303× | 1.020× |
| Construct (1,000) | 3,417.822 | 3,009.171 | 2,953.356 | 1.157× | 1.019× |
| Reuse parser (1,000) | 748.167 | 610.192 | 517.490 | 1.446× | 1.179× |
| Command.main (1,000) | 9,122.238 | 5,354.941 | 5,137.751 | 1.776× | 1.042× |
| Render help (1,000) | 4,340.031 | 3,506.862 | 3,448.216 | 1.259× | 1.017× |
| Nested command | 43.249 | 48.478 | 41.584 | 1.040× | 1.166× |
| Unicode/ANSI wrapping | 444.740 | 57.917 | 59.247 | 7.507× | 0.978× |

One-option full invocation took 22.455 µs,
compared with 24.329 µs for Click
and 24.220 µs for a2.
The nested command took 41.584 µs,
compared with 43.249 µs
and 48.478 µs.
These are the small-invocation comparisons this revision set out to improve.
Both Click/a3 paired ranges cross one. The nested case favors a3 over a2 in all
twelve rounds, whereas one-option invocation favors it in eleven. These results
support lower medians on this host; they do not establish an advantage on every
future invocation or interpreter.

The parsing rows show a larger change relative to a2 at small sizes. All twelve
paired rounds favor a3 over a2 at one option, and ten of twelve do so at ten
options, while the Click/a3 median ratios remain 0.890× and
0.944×.
The 100-option and 1,000-option ratios against Click are
1.057× and 1.446×. Only the latter stays
above one throughout this run's paired range. Parsing remains a separate
boundary; its ratio must not be substituted for the complete-command ratio.

Several changes are close to no difference or unfavorable relative to a2.
The a2/a3 ratios for 1,000-option invocation and wrapping are
1.042× and
0.978×. One-option help is
0.909×, a median regression despite its advantage over
Click. Help at ten, 100 and 1,000 options changes only modestly relative to a2.
The full table retains construction differences as well; rounding a ratio to
1.000 is not a test of equivalence.

### Process CPU time

**Table 3. Median process CPU microseconds per call.** The same workload
boundaries and twelve rounds are used. CPU time excludes time when the process
is not scheduled; its agreement with a wall-time result is supporting detail,
not an independent replication.

| Workload (options) | Click CPU µs ↓ | a2 CPU µs ↓ | a3 CPU µs ↓ | Click / a3 ↑ | a2 / a3 ↑ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Construct (1) | 3.500 | 3.424 | 3.357 | 1.043× | 1.020× |
| Reuse parser (1) | 1.544 | 2.801 | 1.735 | 0.890× | 1.614× |
| Command.main (1) | 24.334 | 24.224 | 22.459 | 1.083× | 1.079× |
| Render help (1) | 55.377 | 22.542 | 24.790 | 2.234× | 0.909× |
| Construct (10) | 29.219 | 28.309 | 28.418 | 1.028× | 0.996× |
| Reuse parser (10) | 6.095 | 8.841 | 6.457 | 0.944× | 1.369× |
| Command.main (10) | 70.350 | 63.047 | 57.377 | 1.226× | 1.099× |
| Render help (10) | 95.253 | 55.494 | 55.151 | 1.727× | 1.006× |
| Construct (100) | 286.848 | 289.048 | 286.005 | 1.003× | 1.011× |
| Reuse parser (100) | 55.485 | 61.387 | 52.486 | 1.057× | 1.170× |
| Command.main (100) | 554.834 | 477.913 | 452.117 | 1.227× | 1.057× |
| Render help (100) | 477.986 | 374.053 | 366.907 | 1.303× | 1.019× |
| Construct (1,000) | 3,418.425 | 3,009.925 | 2,954.274 | 1.157× | 1.019× |
| Reuse parser (1,000) | 748.586 | 610.742 | 518.080 | 1.445× | 1.179× |
| Command.main (1,000) | 9,122.508 | 5,262.054 | 5,138.433 | 1.775× | 1.024× |
| Render help (1,000) | 4,341.023 | 3,508.169 | 3,449.452 | 1.258× | 1.017× |
| Nested command | 43.253 | 48.486 | 41.589 | 1.040× | 1.166× |
| Unicode/ANSI wrapping | 440.471 | 57.924 | 59.253 | 7.434× | 0.978× |

## Variation across warm rounds

**Table 4. Observed a3 ranges, sample coefficient of variation and paired wall
ratios.** CV is sample standard deviation divided by sample mean, in percent.
Each paired ratio divides the reference observation by the candidate observation
from the same round. The faster-round counts retain reversals. Ranges are
observed extrema, not confidence intervals or predictions of future latency.

| Workload (options) | a3 range µs | a3 CV % | Paired Click / a3 range | Paired a2 / a3 range | Faster than Click | Faster than a2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Construct (1) | 3.201–3.879 | 5.35 | 0.886–1.194 | 0.874–1.482 | 9/12 | 6/12 |
| Reuse parser (1) | 1.637–2.099 | 7.26 | 0.710–0.934 | 1.317–1.869 | 0/12 | 12/12 |
| Command.main (1) | 20.919–38.728 | 20.78 | 0.615–3.232 | 0.602–2.594 | 9/12 | 11/12 |
| Render help (1) | 22.409–39.837 | 18.40 | 1.393–2.577 | 0.621–3.384 | 12/12 | 2/12 |
| Construct (10) | 27.763–44.629 | 16.09 | 0.864–1.152 | 0.627–1.090 | 7/12 | 6/12 |
| Reuse parser (10) | 6.233–10.257 | 18.14 | 0.600–1.017 | 0.821–1.519 | 1/12 | 10/12 |
| Command.main (10) | 55.108–84.377 | 15.97 | 0.781–1.353 | 0.760–1.220 | 10/12 | 10/12 |
| Render help (10) | 53.036–71.645 | 10.40 | 1.224–2.079 | 0.751–1.118 | 12/12 | 6/12 |
| Construct (100) | 267.936–306.297 | 5.10 | 0.921–1.432 | 0.897–1.319 | 6/12 | 7/12 |
| Reuse parser (100) | 49.200–86.827 | 22.89 | 0.648–1.281 | 0.678–1.817 | 8/12 | 10/12 |
| Command.main (100) | 429.300–596.130 | 10.50 | 0.924–1.371 | 0.830–1.220 | 11/12 | 8/12 |
| Render help (100) | 338.356–830.169 | 33.28 | 0.554–1.504 | 0.436–1.242 | 11/12 | 6/12 |
| Construct (1,000) | 2,871.312–5,748.553 | 30.26 | 0.586–1.273 | 0.535–1.119 | 10/12 | 5/12 |
| Reuse parser (1,000) | 493.089–568.769 | 4.43 | 1.273–1.595 | 1.036–1.259 | 12/12 | 12/12 |
| Command.main (1,000) | 4,966.890–5,959.961 | 5.10 | 1.478–1.967 | 0.856–1.095 | 12/12 | 11/12 |
| Render help (1,000) | 3,289.961–4,702.339 | 10.67 | 0.925–3.250 | 0.728–1.194 | 11/12 | 7/12 |
| Nested command | 39.003–52.925 | 8.76 | 0.789–1.760 | 1.049–1.335 | 8/12 | 12/12 |
| Unicode/ANSI wrapping | 56.795–64.446 | 3.67 | 6.629–9.581 | 0.909–1.169 | 12/12 | 5/12 |

The two small full-invocation improvements are variable. One-option invocation
is faster than a2 in 11 of 12 paired rounds and the nested case in all 12.
The a3 nested-case CV is 8.76%,
and its paired a2/a3 range is
1.049–1.335.
The 100-option help CV is
33.28%; its slowest retained
sample is 0.830 ms.
One-option full invocation also has a CV of
20.78%, so its favorable median
must be read alongside the wider observed range.
No slow sample was removed to improve a median or range.

The host is shared and its frequency was not locked. The observed one-minute
load changed from 0.465 to
0.886; no CPU-frequency readings were available.
Pinning the measured processes to CPU 0 limits migration but does not isolate
them from other activity. Garbage collection stays enabled, operating-system
caches are not flushed and Python hash randomization varies between isolated
processes. Workload order inside each worker is fixed, so balanced variant
ordering does not remove every carryover effect.

## All eight fresh-process workloads

**Table 5. Median milliseconds per complete process; twelve samples per
implementation and workload.** These include startup and construction, unlike
the warm Command.main and help rows.

| Fresh-process workload (options) | Click ms ↓ | a2 ms ↓ | a3 ms ↓ | Click / a3 ↑ | a2 / a3 ↑ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Command (1) | 34.188 | 26.601 | 26.818 | 1.275× | 0.992× |
| Render help (1) | 37.605 | 27.960 | 28.275 | 1.330× | 0.989× |
| Command (10) | 34.634 | 26.188 | 25.794 | 1.343× | 1.015× |
| Render help (10) | 37.252 | 28.290 | 29.564 | 1.260× | 0.957× |
| Command (100) | 34.420 | 27.202 | 27.782 | 1.239× | 0.979× |
| Render help (100) | 38.736 | 29.409 | 28.537 | 1.357× | 1.031× |
| Command (1,000) | 50.539 | 38.879 | 38.687 | 1.306× | 1.005× |
| Render help (1,000) | 51.844 | 42.709 | 42.150 | 1.230× | 1.013× |

All eight a3 process medians are lower than Click's in this run. Four are
higher than the a2 medians and four are lower. The 1,000-option complete command is
1.306× relative to Click but only
1.005×
relative to a2. Faster warm parsing therefore does not establish a general
startup improvement over the preceding distribution.

**Table 6. Fresh-process observed ranges and sample CVs.** Units are milliseconds
for ranges and percent for CV. All twelve observations are retained, including
startup outliers.

| Fresh-process workload (options) | Click range ms; CV % | a2 range ms; CV % | a3 range ms; CV % |
| --- | ---: | ---: | ---: |
| Command (1) | 31.226–44.064; 9.66 | 25.799–36.302; 11.05 | 25.203–47.576; 21.19 |
| Render help (1) | 35.779–50.290; 10.47 | 26.540–40.271; 14.84 | 26.390–40.738; 13.67 |
| Command (10) | 31.160–114.259; 56.66 | 24.331–38.490; 13.54 | 24.910–38.779; 13.93 |
| Render help (10) | 35.158–57.533; 15.56 | 25.671–70.571; 39.13 | 27.194–126.349; 67.77 |
| Command (100) | 33.950–63.825; 22.41 | 25.921–55.318; 27.40 | 25.940–31.774; 5.96 |
| Render help (100) | 36.833–66.336; 20.03 | 27.677–136.014; 79.65 | 26.981–42.876; 14.63 |
| Command (1,000) | 48.623–72.498; 12.23 | 37.560–43.048; 4.55 | 34.983–45.602; 8.64 |
| Render help (1,000) | 47.982–230.674; 75.23 | 38.175–104.807; 38.66 | 38.775–48.700; 6.82 |

The cold results contain substantial outliers. Ten-option help for a3 ranges
from 27.194 to 126.349 ms, with a 67.77% CV. The published a2 control also has
a large outlier in 100-option help: 136.014 ms, with a 79.65% CV. Neither sample
was dropped. These observations limit how much can be inferred from the small
median differences between releases.

### Import-only startup

**Table 7. Median milliseconds for import-only boundaries.** The inner interval
starts immediately before the package import; only `time` is imported first.
The whole-process interval also includes interpreter startup, reporting and
exit.

| Boundary | Click ms ↓ | a2 ms ↓ | a3 ms ↓ | Click / a3 ↑ | a2 / a3 ↑ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Import interval | 19.706 | 14.175 | 14.175 | 1.390× | 1.000× |
| Whole import-only process | 33.267 | 25.802 | 25.876 | 1.286× | 0.997× |

The a2 and a3 import intervals are almost the same: their medians differ by
0.481 µs,
below the displayed millisecond precision and much smaller than their observed
variation. Both remain below Click. The whole import-only process is slightly
slower for a3. These observations do not establish a new import-speed gain from
delaying individual helper imports.

**Table 8. Import-only observed ranges and sample CVs.** Cold means a fresh
interpreter, not a reset operating-system cache.

| Boundary | Click range ms; CV % | a2 range ms; CV % | a3 range ms; CV % |
| --- | ---: | ---: | ---: |
| Import interval | 18.296–49.770; 39.15 | 13.161–16.834; 7.01 | 13.358–15.966; 5.20 |
| Whole import-only process | 30.380–114.091; 57.52 | 24.242–30.432; 7.38 | 24.967–30.240; 5.68 |

## Python allocations and process memory

**Table 9. Median current / peak Python-managed bytes for one call.** The driver
collects before each observation, starts `tracemalloc` and keeps the returned
value alive while reading current bytes. These are medians of twelve calls.
They omit Rust allocations and other untracked native memory, so they are not
a total memory model of the parser or its retained schema.

| Workload (options) | Click bytes | a2 bytes | a3 bytes |
| --- | ---: | ---: | ---: |
| Construct (1) | 3,250 / 3,290 | 3,370 / 3,410 | 3,370 / 3,410 |
| Reuse parser (1) | 720 / 2,488 | 1,059 / 1,327 | 720 / 832 |
| Command.main (1) | 3,208 / 7,274 | 3,573.5 / 7,252 | 3,352 / 6,710 |
| Render help (1) | 1,830 / 5,288 | 1,414 / 2,996 | 1,478 / 3,060 |
| Construct (10) | 20,212 / 20,252 | 20,332 / 20,372 | 20,332 / 20,372 |
| Reuse parser (10) | 1,024 / 2,792 | 1,319 / 1,659 | 1,024 / 1,208 |
| Command.main (10) | 5,456 / 14,857 | 5,329 / 14,654 | 5,080 / 14,085 |
| Render help (10) | 2,394 / 7,102 | 2,098 / 4,850 | 2,042 / 4,794 |
| Construct (100) | 189,788 / 189,828 | 189,908 / 189,948 | 189,908 / 189,948 |
| Reuse parser (100) | 4,816 / 6,584 | 5,109 / 7,561 | 4,816 / 7,056 |
| Command.main (100) | 20,900 / 93,387 | 12,116 / 96,298 | 11,868 / 95,707 |
| Render help (100) | 9,325 / 25,999 | 9,029 / 23,729 | 8,973 / 23,673 |
| Construct (1,000) | 1,887,924 / 1,887,972 | 1,888,044 / 1,888,084 | 1,888,044 / 1,888,084 |
| Reuse parser (1,000) | 35,456 / 54,560 | 35,795 / 54,327 | 35,456 / 53,776 |
| Command.main (1,000) | 71,300 / 780,943 | 6,681.5 / 832,312.5 | 6,389 / 831,700 |
| Render help (1,000) | 79,526 / 215,608 | 79,230 / 213,339 | 79,174 / 213,283 |
| Nested command | 3,680 / 9,810 | 5,055 / 10,299 | 4,112 / 9,198 |
| Unicode/ANSI wrapping | 5,576 / 42,128 | 5,056 / 8,062 | 5,056 / 8,062 |

One-option reused parsing records a Python peak of
832 bytes, compared with
1,327 for a2 and
2,488 for Click.
At 1,000 options, full invocation still records a larger Python peak than
Click: 831,700 versus
780,943 bytes. Neither
result implies zero allocation or accounts for every native object.

**Table 10. Whole-worker peak RSS.** One MiB is 1,048,576 bytes. These observations
include interpreter and package imports, hash verification, `tracemalloc` and
the entire sequence of workloads. They cannot be assigned to one parser call.

| Implementation | Median peak RSS MiB ↓ | Observed range MiB |
| --- | ---: | ---: |
| Click 8.5.1 | 24.062 | 24.055–24.066 |
| zclick 0.1.1a2 | 25.473 | 25.324–25.523 |
| zclick 0.1.1a3 | 25.193 | 25.047–25.262 |

The candidate worker's median peak RSS is lower than a2's but higher than
Click's. Python allocation reductions in individual rows therefore do not
establish that zclick uses less total memory than Click.

## Scope of the conclusions

These measurements test repeated synthetic option lists, a small nested
command and a fixed wrapping workload. They include bindings and context
costs at the named boundaries, but they do not represent interactive prompts,
filesystem work, completion, expensive application callbacks or every custom
subclass. A user's elapsed time also includes their own work. There is no
basis here for a claim that every Click application becomes substantially
faster after changing its imports.

The comparison is with both a fixed behavioral reference and an actual
published zclick release. It is not a component ablation: changes in call
boundaries, protocol-name reuse, zclap setup and compatibility corrections are
measured together. Their individual causal contributions cannot be read from
the tables. The substantial wrapping and large-command advantages over Click
predate this revision, while the a2 comparison exposes the smaller new changes.

Runtime correctness remains a separate requirement. The performance worker
checks its outputs, not the entire Click API or all platform behavior. The
earlier PyPy import failure was corrected before this frozen run, but this
CPython measurement does not itself validate PyPy or the complete release
matrix. The project's declared main-interpreter restriction
also remains an unfinished compatibility item in
[COMPATIBILITY.md](../COMPATIBILITY.md); benchmark success does not remove it.
No new release or platform-completeness claim is made by this document.

### Claim–evidence review

| Claim | Evidence | Status and scope |
| --- | --- | --- |
| One-option and nested full invocation have lower medians than a2 and Click | Tables 2–4, complete Command.main boundaries | Supported locally; both Click/a3 paired ranges cross one |
| One- and ten-option parsing improve relative to a2 | Tables 2–4; twelve and ten paired rounds favor a3, respectively | Supported locally; both medians remain slower than Click |
| Large invocation and wrapping are much faster than Click | Table 2 with a2/a3 comparison alongside Click/a3 | Supported for these workloads; mostly existing gains, not large new a3 gains |
| Every operation improves over a2 | Help and cold counterexamples in Tables 2 and 5; no clear import gain in Table 7 | Rejected |
| zclick always uses less memory | Table 9 omits native allocations; Table 10 is above Click | Rejected |
| Each optimization causes a known fraction of the gain | No independently frozen component ablation in this report | Not established; no numerical attribution |
| The candidate is release-ready on all supported interpreters | The corrected CPython run is not the complete platform gate | Not established by this report |

### Five-question self-review

1. **Contribution:** Is this a new large speedup everywhere? No. The strongest
   relative version change is reused parsing at small sizes; complete invocation
   improves more modestly and several operations regress.
2. **Clarity:** Can a reader tell which work each number includes? Tables 2–8
   separate construction, parser reuse, warm invocation, help and complete
   process startup; units and reference direction are explicit.
3. **Experimental strength:** Are the controls immutable and the reversals
   visible? Both distributions, source and native hashes, all eighteen warm
   cases, all eight cold cases, raw samples and paired ranges are retained.
4. **Evaluation completeness:** What evidence is missing? An independent host
   and final release validation are not present here. Component ablation and
   application-specific measurements would be needed for stronger causal or
   general claims. The earlier candidate's data remains separate.
5. **Design soundness:** Is less work obtained by removing public behavior?
   The design retains live definitions, dynamic Python methods and context
   cleanup. Its behavior must pass the separate compatibility checks; the
   corrected PyPy import must be validated in its own environment, outside this
   CPython performance experiment.

## Reproducing the local comparison

Use a separate clean checkout of the recorded commit and the same CPython
interpreter for both controls and the candidate. The protocol validates the
candidate's version and Python file hashes against that checkout. The baseline
is selected by [baseline-lock.json](../benchmarks/baseline-lock.json), which
pins the published a2 and Click wheels. The earlier a1 lock remains available
for reproducing its own reports and must not be silently substituted here.

```sh
maturin build --release --locked --out dist/benchmark-candidate
python benchmarks/compare.py \
  --candidate-wheel dist/benchmark-candidate/zclick-0.1.1a3-cp310-abi3-manylinux_2_34_x86_64.whl \
  --iterations 1000 --repeats 12 --seed 20261111 --affinity auto \
  --output reports/benchmarks-0.1.1a3.json
```

The example wheel filename is the one measured on this host; use the actual
filename produced by the local build, and pass exactly one candidate. On Linux,
`--affinity auto` selects the first CPU in the allowed set. Omit affinity
control where it is unavailable and retain that difference in the report.
Run timing without competing local builds or tests, preserve the complete JSON
and review its source, native hashes and sample ranges before interpreting
results. Keep later builds or platforms in separate immutable timing records.
