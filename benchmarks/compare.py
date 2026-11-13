"""Balanced three-way measurements of Click, published zclick and a candidate.

Every round uses fresh isolated worker processes, a reproducible package order,
and identical workload boundaries. Environments contain only the fixed wheels
and pip. Raw timing, memory, ordering, integrity and machine observations remain
in the result. Native allocations are not fully visible to tracemalloc.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import importlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
# -I excludes the script directory. This adds only the benchmark helpers; no
# runtime package lives here, and workers execute outside the source checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from environment import affinity, load_average, package_record, runtime_details
from prepare_baseline import prepare, prepare_candidate, verify_published_snapshot, verify_snapshot


LABELS = ("click", "zclick-baseline", "zclick")


def sample_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def round_orders(labels: tuple[str, ...], rounds: int, seed: int) -> list[list[str]]:
    """Every complete block contains each ordering exactly once."""
    rng = random.Random(seed)
    permutations = list(itertools.permutations(labels))
    result = []
    while len(result) < rounds:
        block = permutations.copy()
        rng.shuffle(block)
        result.extend(list(order) for order in block)
    return result[:rounds]


def timing(fn, loops: int) -> dict:
    for _ in range(5):
        fn()
    start_cpu, start_wall = time.process_time_ns(), time.perf_counter_ns()
    for _ in range(loops):
        fn()
    return {"iterations": loops,
            "wall_us": (time.perf_counter_ns() - start_wall) / loops / 1000,
            "cpu_us": (time.process_time_ns() - start_cpu) / loops / 1000}


def memory(fn) -> dict:
    # PyPy can import the protocol helpers even when its _tracemalloc extension
    # is unavailable. Actual measurement still requires allocation accounting.
    import tracemalloc

    gc.collect()
    tracemalloc.start()
    value = fn()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del value
    return {"python_current_bytes": current, "python_peak_bytes": peak}


def worker(package: str, sizes: list[int], loops: int) -> dict:
    before = package_record(package)
    runtime = runtime_details()
    cli = importlib.import_module(package)
    results, checks = {}, {}
    for size in sizes:
        def construct():
            params = [cli.Option([f"--value-{i}"], type=int, default=0) for i in range(size)]
            return cli.Command("bench", params=params, callback=lambda **values: sum(values.values()))

        command = construct()
        argv = [part for i in range(size) for part in (f"--value-{i}", str(i))]
        expected = sum(range(size))
        ctx = cli.Context(command, info_name="bench")
        parser = command.make_parser(ctx)
        parse = lambda: parser.parse_args(list(argv))
        invoke = lambda: command.main(args=list(argv), prog_name="bench", standalone_mode=False)
        parsed, rest, order = parse()
        assert parsed == {f"value_{i}": str(i) for i in range(size)} and rest == []
        assert len(order) == size and all(item is param for item, param in zip(order, command.params))
        assert invoke() == expected
        checks[f"construct/{size}"] = sample_hash({"name": command.name,
            "params": [{"name": p.name, "opts": p.opts, "default": p.default,
                        "nargs": p.nargs, "type": p.type.name} for p in command.params]})
        checks[f"parse/{size}"] = sample_hash([parsed, rest, [p.name for p in order]])
        checks[f"invoke/{size}"] = sample_hash(expected)
        count = max(10, loops // max(1, size // 10))
        for label, fn in (("construct", construct), ("parse", parse), ("invoke", invoke)):
            results[f"{label}/{size}"] = {**timing(fn, count), **memory(fn)}
        help_fn = lambda: command.get_help(ctx)
        help_text = help_fn()
        assert "Usage: bench" in help_text
        checks[f"help/{size}"] = sample_hash(help_text)
        results[f"help/{size}"] = {**timing(help_fn, max(5, count // 5)), **memory(help_fn)}

    @cli.command()
    @cli.option("--amount", default=1, type=int)
    def leaf(amount):
        return amount + 1

    group = cli.Group("bench", commands={"leaf": leaf})
    nested = lambda: group.main(["leaf", "--amount", "9"], prog_name="bench", standalone_mode=False)
    assert nested() == 10
    checks["nested-command"] = sample_hash(10)
    results["nested-command"] = {**timing(nested, loops), **memory(nested)}

    paragraph = "Unicode café 零 copy and ANSI \x1b[31mcolor\x1b[0m text. " * 50
    wrap = lambda: cli.wrap_text(paragraph, width=78)
    wrapped = wrap()
    assert wrapped.replace("\n", " ").split() == paragraph.split()
    checks["wrap-text"] = sample_hash(wrapped)
    results["wrap-text"] = {**timing(wrap, loops), **memory(wrap)}
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_bytes = rss if sys.platform == "darwin" else rss * 1024
    except ImportError:
        rss_bytes = None
    if before != package_record(package):
        raise RuntimeError(f"{package} source changed during worker execution")
    return {**before, "cases": results, "result_checks": checks,
            "runtime": runtime, "load_average_after": load_average(),
            "process_peak_rss_bytes": rss_bytes, "gc_enabled": gc.isenabled()}


def cold_program(package: str, kind: str, size: int | None) -> str:
    if kind == "import":
        return f"import time\ns = time.perf_counter_ns()\nimport {package}\nprint((time.perf_counter_ns()-s)/1000)"
    setup = (f"import {package} as click\n"
             f"params = [click.Option([f'--value-{{i}}'], type=int, default=0) for i in range({size})]\n"
             "command = click.Command('bench', params=params, callback=lambda **v: sum(v.values()))\n")
    if kind == "command":
        return setup + (f"args = [part for i in range({size}) for part in (f'--value-{{i}}', str(i))]\n"
                        "print(command.main(args, prog_name='bench', standalone_mode=False))\n")
    return setup + "command.main(['--help'], prog_name='bench', standalone_mode=False)\n"


def cold_sample(variant: dict, kind: str, size: int | None, cwd: str) -> dict:
    program = cold_program(variant["package"], kind, size)
    start = time.perf_counter_ns()
    output = subprocess.check_output([variant["python"], "-I", "-c", program],
                                     cwd=cwd, text=True, encoding="utf-8")
    elapsed = (time.perf_counter_ns() - start) / 1000
    if kind == "import":
        return {"wall_us": elapsed, "import_us": float(output.strip())}
    if kind == "command":
        assert output.strip() == str(sum(range(size)))
    else:
        assert output.startswith("Usage: bench") and "--value-0" in output
    return {"wall_us": elapsed, "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


def summarize_samples(values: list[dict]) -> dict:
    wall = [v["wall_us"] for v in values]
    result = {"repeats": len(values), "wall_us": wall,
              "median_wall_us": statistics.median(wall), "min_wall_us": min(wall), "max_wall_us": max(wall)}
    if "cpu_us" in values[0]:
        cpu = [v["cpu_us"] for v in values]
        assert len({v["iterations"] for v in values}) == 1
        result.update({"iterations": values[0]["iterations"], "cpu_us": cpu,
                       "median_cpu_us": statistics.median(cpu),
                       "memory_samples": [{k: v[k] for k in ("python_current_bytes", "python_peak_bytes")} for v in values],
                       "python_current_bytes": statistics.median(v["python_current_bytes"] for v in values),
                       "python_peak_bytes": statistics.median(v["python_peak_bytes"] for v in values)})
    return result


def compare_cases(reference: dict, candidate: dict) -> dict:
    result = {}
    for name, first in reference["cases"].items():
        second = candidate["cases"][name]
        result[name] = {"wall_speedup": first["median_wall_us"] / second["median_wall_us"],
                        "cpu_speedup": first["median_cpu_us"] / second["median_cpu_us"],
                        "python_peak_ratio": first["python_peak_bytes"] / max(1, second["python_peak_bytes"]),
                        "paired_wall_speedups": [a / b for a, b in zip(first["wall_us"], second["wall_us"])]}
    return result


def cold_ratios(reference: dict, candidate: dict) -> dict:
    return {name: value["median_wall_us"] / candidate["cold_commands"][name]["median_wall_us"]
            for name, value in reference["cold_commands"].items()}


def source_status(snapshot: dict) -> dict:
    version = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)[1]
    package = snapshot["packages"]["zclick"]
    packaged = {name: digest for name, digest in package["source_files"].items() if name.endswith(".py")}
    package_root = ROOT / "python/zclick"
    checkout = {path.relative_to(package_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in package_root.rglob("*.py") if "__pycache__" not in path.parts}
    differences = sorted(name for name in packaged.keys() | checkout.keys()
                         if packaged.get(name) != checkout.get(name))
    return {"version_matches": package["version"] == version,
            "wheel_python_source_matches_checkout": not differences, "different_python_files": differences}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("click", "zclick"))
    parser.add_argument("--sizes", nargs="+", type=int, default=[1, 10, 100, 1000])
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--candidate-wheel", type=Path)
    parser.add_argument("--baseline-manifest", type=Path)
    parser.add_argument("--baseline-lock", type=Path,
                        help="Published release wheel lock; defaults to benchmarks/baseline-lock.json")
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache/benchmark-baselines")
    parser.add_argument("--affinity", help="auto or a comma-separated subset of currently allowed CPUs; inherited by workers")
    parser.add_argument("--diagnostic", action="store_true", help="Permit a short harness check; result cannot support release claims")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/benchmarks.json")
    args = parser.parse_args()
    if args.iterations < 1 or args.repeats < 1 or not args.sizes or any(size < 1 for size in args.sizes):
        parser.error("sizes, iterations and repeats must be positive")
    if len(set(args.sizes)) != len(args.sizes):
        parser.error("sizes must be unique")
    if args.worker:
        print(json.dumps(worker(args.worker, args.sizes, args.iterations)))
        return
    if not args.diagnostic and (args.sizes != [1, 10, 100, 1000]
            or args.repeats < 12 or args.repeats % 6 or args.iterations < 1000):
        parser.error("Formal runs require all four sizes, >=1000 iterations and >=12 rounds in complete six-round blocks; use --diagnostic for short checks")
    original_affinity = affinity()
    if args.affinity:
        if original_affinity is None:
            parser.error("CPU affinity control is unavailable on this platform")
        selected = {original_affinity[0]} if args.affinity == "auto" else {int(s) for s in args.affinity.split(",")}
        if not selected or not selected.issubset(original_affinity):
            parser.error("Requested CPUs are outside the allowed affinity set")
        os.sched_setaffinity(0, selected)
    if args.baseline_manifest:
        baseline = json.loads(args.baseline_manifest.read_text(encoding="utf-8"))
        verify_published_snapshot(baseline, args.baseline_lock)
    else:
        baseline = prepare(args.cache, lock_path=args.baseline_lock)
        verify_published_snapshot(baseline, args.baseline_lock)
    if args.candidate_wheel is None:
        version = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)[1]
        wheels = list((ROOT / "dist").glob("zclick-" + version + "-*.whl"))
        if len(wheels) != 1:
            parser.error("Build one candidate wheel, then pass --candidate-wheel PATH")
        args.candidate_wheel = wheels[0]
    candidate = prepare_candidate(args.candidate_wheel, args.cache, baseline)
    target = json.loads((ROOT / "compatibility/target.json").read_text(encoding="utf-8"))
    if baseline["packages"]["click"]["version"] != target["version"]:
        parser.error("Click baseline does not match the pinned compatibility target")
    checked_source = source_status(candidate)
    if not args.diagnostic and not all((checked_source["version_matches"], checked_source["wheel_python_source_matches_checkout"])):
        parser.error("Candidate wheel does not match current project version/Python sources; rebuild after freezing")
    for field in ("python", "implementation", "cache_tag", "gil_disabled_build", "machine"):
        if baseline["runtime"][field] != candidate["runtime"][field]:
            parser.error("Candidate and baseline interpreters differ: " + field)
    variants = {
        "click": {"package": "click", "python": baseline["python"], "expected": baseline["packages"]["click"]},
        "zclick-baseline": {"package": "zclick", "python": baseline["python"], "expected": baseline["packages"]["zclick"]},
        "zclick": {"package": "zclick", "python": candidate["python"], "expected": candidate["packages"]["zclick"]},
    }
    warm_orders = round_orders(LABELS, args.repeats, args.seed)
    cold_cases = [("import", None)] + [(kind, size) for size in args.sizes for kind in ("command", "help")]
    cold_orders = {f"{kind}/{size}" if size is not None else kind:
                   round_orders(LABELS, args.repeats, args.seed + 104729 * (i + 1))
                   for i, (kind, size) in enumerate(cold_cases)}
    rounds, warm, cold = [], {label: [] for label in LABELS}, {label: {} for label in LABELS}
    benchmark_sources = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree_before = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines()
    machine_before = runtime_details()
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="zclick-benchmark-working-directory-") as cwd:
        for index in range(args.repeats):
            record = {"round": index + 1, "warm_order": warm_orders[index], "cold_orders": {},
                      "load_before": load_average(), "warm_workers": {}}
            for label in warm_orders[index]:
                variant = variants[label]
                output = subprocess.check_output([variant["python"], "-I", str(Path(__file__).resolve()),
                    "--worker", variant["package"], "--sizes", *map(str, args.sizes),
                    "--iterations", str(args.iterations)], cwd=cwd, text=True, encoding="utf-8")
                value = json.loads(output)
                for field, expected in variant["expected"].items():
                    if value[field] != expected:
                        raise RuntimeError(f"{label} baseline/candidate changed: {field}")
                warm[label].append(value)
                record["warm_workers"][label] = {"runtime": value["runtime"],
                    "load_average_after": value["load_average_after"],
                    "process_peak_rss_bytes": value["process_peak_rss_bytes"], "gc_enabled": value["gc_enabled"]}
            gold = warm["click"][-1]["result_checks"]
            for label in LABELS:
                if warm[label][-1]["result_checks"] != gold:
                    raise RuntimeError(f"{label} benchmark outputs differ from Click")
            for kind, size in cold_cases:
                name = f"{kind}/{size}" if size is not None else kind
                order = cold_orders[name][index]
                record["cold_orders"][name] = order
                values = {}
                for label in order:
                    values[label] = cold_sample(variants[label], kind, size, cwd)
                    cold[label].setdefault(name, []).append(values[label])
                if kind != "import" and len({v["output_sha256"] for v in values.values()}) != 1:
                    raise RuntimeError(f"Fresh-process {name} output differs between packages")
            record["load_after"] = load_average()
            rounds.append(record)
            print(f"Completed round {index + 1}/{args.repeats}: {' / '.join(warm_orders[index])}", flush=True)
    verify_published_snapshot(baseline, args.baseline_lock)
    verify_snapshot(candidate)
    if benchmark_sources != {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}:
        raise RuntimeError("Benchmark driver changed during measurement")
    if source_commit != subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip():
        raise RuntimeError("Source commit changed during measurement")
    measurements = {}
    for label in LABELS:
        samples = warm[label]
        rss = [s["process_peak_rss_bytes"] for s in samples]
        imports = cold[label]["import"]
        measurements[label] = {**variants[label]["expected"],
            "cases": {name: summarize_samples([s["cases"][name] for s in samples]) for name in samples[0]["cases"]},
            "result_checks": samples[0]["result_checks"], "process_peak_rss_samples": rss,
            "process_peak_rss_bytes": statistics.median(rss) if all(v is not None for v in rss) else None,
            "cold": {"import_us": [v["import_us"] for v in imports],
                     "median_import_us": statistics.median(v["import_us"] for v in imports),
                     "fresh_process_wall_us": [v["wall_us"] for v in imports],
                     "median_fresh_process_wall_us": statistics.median(v["wall_us"] for v in imports)},
            "cold_commands": {name: summarize_samples(values) for name, values in cold[label].items() if name != "import"}}
    reference, previous, native = (measurements[label] for label in LABELS)
    result = {
        "schema": 2, "diagnostic": args.diagnostic, "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": machine_before["platform"], "machine": machine_before["machine"],
        "cpu_count": os.cpu_count(), "load_average": machine_before["load_average"],
        "host_before": machine_before, "host_after": runtime_details(), "original_affinity": original_affinity,
        "git_commit": source_commit, "working_tree_status_before": tree_before,
        "working_tree_status": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines(),
        "cargo_lock_sha256": hashlib.sha256((ROOT / "Cargo.lock").read_bytes()).hexdigest(),
        "benchmark_source_files": benchmark_sources, "candidate_checkout_check": checked_source,
        "target": target, "baseline_snapshot": baseline, "candidate_snapshot": candidate,
        "measurements": measurements, "ratios": compare_cases(reference, native),
        "baseline_ratios": compare_cases(reference, previous),
        "improvement_over_baseline": compare_cases(previous, native),
        "cold_command_ratios": cold_ratios(reference, native),
        "baseline_cold_command_ratios": cold_ratios(reference, previous),
        "improvement_over_baseline_cold_command_ratios": cold_ratios(previous, native),
        "rounds": rounds,
        "method": {
            "build": "maturin build --release --locked; install immutable wheels in minimal virtual environments",
            "ordering": "Seeded permutation blocks; every six rounds use all six package orders once for each measurement boundary",
            "seed": args.seed, "repeats": args.repeats, "complete_balanced_blocks": args.repeats // 6,
            "partial_block_rounds": args.repeats % 6, "warmup_calls_per_case_per_round": 5,
            "runtime_boundary": "identical Python constructors, parser.parse_args, Command.main and get_help",
            "speedup_definition": "Reference median / candidate median; >1 is faster. Paired raw round ratios are also retained.",
            "memory_scope": "tracemalloc: Python allocations only; RSS: per-worker whole-process high-water mark. Scalars are medians across rounds.",
            "isolation": "Fresh -I worker per variant and round; fresh -I interpreter per cold sample; no runtime imports from checkout",
            "hash_seed": "Interpreter-randomized in each isolated process; -I ignores PYTHONHASHSEED",
            "frequency_control": "Observed, not locked; optional affinity is recorded and inherited by children",
            "limitations": "Results are workload-specific. Shared-host activity, frequency, caches and GC affect timing. No universal speedup is claimed.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("case                       Click us    old zclick us   candidate us  vs Click  vs old")
    for name, ratio in result["ratios"].items():
        print(f"{name:24s}{reference['cases'][name]['median_wall_us']:11.3f}"
              f"{previous['cases'][name]['median_wall_us']:16.3f}{native['cases'][name]['median_wall_us']:15.3f}"
              f"{ratio['wall_speedup']:10.3f}x{result['improvement_over_baseline'][name]['wall_speedup']:8.3f}x")
    print("fresh process               Click ms    old zclick ms   candidate ms  vs Click  vs old")
    for name, ratio in result["cold_command_ratios"].items():
        print(f"{name:24s}{reference['cold_commands'][name]['median_wall_us']/1000:11.3f}"
              f"{previous['cold_commands'][name]['median_wall_us']/1000:16.3f}"
              f"{native['cold_commands'][name]['median_wall_us']/1000:15.3f}{ratio:10.3f}x"
              f"{result['improvement_over_baseline_cold_command_ratios'][name]:8.3f}x")
    print(f"Saved {'DIAGNOSTIC ONLY' if args.diagnostic else 'measurements'}: {args.output}")


if __name__ == "__main__":
    main()
