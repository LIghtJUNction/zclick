"""Reproducible Click/zclick measurements at identical Python API boundaries.

Every timed workload checks its result before measurement. Each package runs in
its own process. Timings include Python bindings and result construction, and
both process CPU time and wall time are recorded. Tracemalloc covers Python
allocations only; process peak RSS also includes the interpreter and native code.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]


def timing(fn, loops: int, repeats: int) -> dict:
    for _ in range(5):
        fn()
    wall, cpu = [], []
    for _ in range(repeats):
        start_cpu, start_wall = time.process_time_ns(), time.perf_counter_ns()
        for _ in range(loops):
            fn()
        wall.append((time.perf_counter_ns() - start_wall) / loops / 1000)
        cpu.append((time.process_time_ns() - start_cpu) / loops / 1000)
    return {
        "iterations": loops, "repeats": repeats,
        "wall_us": wall, "cpu_us": cpu,
        "median_wall_us": statistics.median(wall),
        "median_cpu_us": statistics.median(cpu),
        "min_wall_us": min(wall), "max_wall_us": max(wall),
    }


def memory(fn) -> dict:
    gc.collect()
    tracemalloc.start()
    value = fn()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # Keep the result alive through the sample; this includes returned objects.
    del value
    return {"python_current_bytes": current, "python_peak_bytes": peak}


def worker(package: str, sizes: list[int], loops: int, repeats: int) -> dict:
    cli = importlib.import_module(package)
    package_path = Path(cli.__file__).parent
    def fingerprints():
        return {str(path.relative_to(package_path)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(package_path.rglob("*"))
                if path.is_file() and "__pycache__" not in path.parts
                and path.suffix in (".py", ".so", ".pyd")}
    source_files = fingerprints()
    results = {}
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
        assert rest == [] and sum(map(int, parsed.values())) == expected
        assert len(order) == size
        assert invoke() == expected
        count = max(10, loops // max(1, size // 10))
        for label, fn in (("construct", construct), ("parse", parse), ("invoke", invoke)):
            results[f"{label}/{size}"] = {**timing(fn, count, repeats), **memory(fn)}
        help_fn = lambda: command.get_help(ctx)
        assert "Usage: bench" in help_fn()
        results[f"help/{size}"] = {**timing(help_fn, max(5, count // 5), repeats), **memory(help_fn)}

    @cli.command()
    @cli.option("--amount", default=1, type=int)
    def leaf(amount):
        return amount + 1

    group = cli.Group("bench", commands={"leaf": leaf})
    nested = lambda: group.main(["leaf", "--amount", "9"], prog_name="bench", standalone_mode=False)
    assert nested() == 10
    results["nested-command"] = {**timing(nested, loops, repeats), **memory(nested)}

    paragraph = "Unicode café 零 copy and ANSI \x1b[31mcolor\x1b[0m text. " * 50
    wrap = lambda: cli.wrap_text(paragraph, width=78)
    assert wrap().replace("\n", " ").split() == paragraph.split()
    results["wrap-text"] = {**timing(wrap, loops, repeats), **memory(wrap)}

    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_bytes = rss if sys.platform == "darwin" else rss * 1024
    except ImportError:
        rss_bytes = None
    if source_files != fingerprints():
        raise RuntimeError(f"{package} source changed during measurement")
    return {"package": package, "version": importlib.metadata.version(package), "cases": results,
            "source_files": source_files, "process_peak_rss_bytes": rss_bytes}


def cold(package: str, repeats: int) -> dict:
    values = []
    whole = []
    # Only time is imported before the measured import; the process is fresh for
    # every repetition. No benchmark driver modules prewarm the dependency graph.
    program = f"import time\ns = time.perf_counter_ns()\nimport {package}\nprint((time.perf_counter_ns()-s)/1000)"
    for _ in range(repeats):
        start = time.perf_counter_ns()
        output = subprocess.check_output([sys.executable, "-c", program], text=True)
        whole.append((time.perf_counter_ns() - start) / 1000)
        values.append(float(output.strip()))
    return {"import_us": values, "median_import_us": statistics.median(values),
            "fresh_process_wall_us": whole, "median_fresh_process_wall_us": statistics.median(whole)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("click", "zclick"))
    parser.add_argument("--sizes", nargs="+", type=int, default=[1, 10, 100, 1000])
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/benchmarks.json")
    args = parser.parse_args()
    if args.iterations < 1 or args.repeats < 1 or any(size < 1 for size in args.sizes):
        parser.error("sizes, iterations and repeats must be positive")
    if args.worker:
        print(json.dumps(worker(args.worker, args.sizes, args.iterations, args.repeats)))
        return
    measurements = {}
    for package in ("click", "zclick"):
        output = subprocess.check_output([
            sys.executable, __file__, "--worker", package, "--sizes", *map(str, args.sizes),
            "--iterations", str(args.iterations), "--repeats", str(args.repeats),
        ], text=True)
        measurements[package] = json.loads(output)
        measurements[package]["cold"] = cold(package, args.repeats)
    reference, native = measurements["click"], measurements["zclick"]
    expected_target = json.loads((ROOT / "compatibility/target.json").read_text(encoding="utf-8"))["version"]
    if reference["version"] != expected_target:
        raise SystemExit(f"Wrong Click benchmark version {reference['version']}; expected {expected_target}")
    ratios = {}
    for name, result in reference["cases"].items():
        other = native["cases"][name]
        ratios[name] = {
            "wall_speedup": result["median_wall_us"] / other["median_wall_us"],
            "cpu_speedup": result["median_cpu_us"] / other["median_cpu_us"],
            "python_peak_ratio": result["python_peak_bytes"] / max(1, other["python_peak_bytes"]),
        }
    result = {
        "schema": 1, "python": sys.version, "platform": platform.platform(),
        "machine": platform.machine(), "cpu_count": os.cpu_count(),
        "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "cargo_lock_sha256": hashlib.sha256((ROOT / "Cargo.lock").read_bytes()).hexdigest(),
        "target": json.loads((ROOT / "compatibility/target.json").read_text(encoding="utf-8")),
        "measurements": measurements, "ratios": ratios,
        "method": {
            "build": "maturin build/develop --release --locked",
            "runtime_boundary": "identical Python constructors, parser.parse_args, Command.main and get_help",
            "speedup_definition": "Click median / zclick median; >1 is faster",
            "memory_scope": "tracemalloc: Python allocations only; RSS: whole process high-water mark",
            "limitations": "Microbenchmarks are workload-specific. Background load and allocator state affect timings. No universal speedup is claimed.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("case                    Click us    zclick us   speedup")
    for name, ratio in ratios.items():
        print(f"{name:24s}{reference['cases'][name]['median_wall_us']:10.3f}"
              f"{native['cases'][name]['median_wall_us']:12.3f}{ratio['wall_speedup']:9.3f}x")
    print(f"Saved measurements: {args.output}")


if __name__ == "__main__":
    main()
