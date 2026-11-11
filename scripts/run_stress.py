"""Run all pinned stress cases in bounded, independently recorded processes.

Splitting the GC function prevents pytest's unrelated test objects from making
each explicit gc.collect() unnecessarily expensive. Selectors enumerate every
original parameter ID; no tests, assertions or skip conditions are modified.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from prepare_upstream import ROOT, TARGET, prepare
from run_compatibility import compare
from compat_report_plugin import key

CASES = {
    "thread_pool_with_exit": ("tests/test_stream_lifecycle.py", 10000),
    "logging_sequential_invocations": ("tests/test_stream_lifecycle.py", 10000),
    "gc_between_invocations": ("tests/test_stream_lifecycle.py", 10000),
    "echo_via_pager_exception_cleanup": ("tests/test_utils/test_echo_via_pager.py", 1000),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merged(paths: list[Path]) -> dict:
    result = {"schema": 1, "exit_status": 0, "collected": [], "deselected": [],
              "results": {}, "collection_errors": [], "shards": []}
    for path in paths:
        item = json.loads(path.read_text(encoding="utf-8"))
        item["collected"] = [key(node) for node in item["collected"]]
        item["results"] = {key(node): value for node, value in item["results"].items()}
        overlap = set(result["results"]) & set(item["results"])
        if overlap:
            raise ValueError(f"Duplicate stress IDs: {min(overlap)}")
        result["exit_status"] |= item["exit_status"]
        result["collected"].extend(item["collected"])
        result["results"].update(item["results"])
        result["collection_errors"].extend(item["collection_errors"])
        result["shards"].append(str(path))
        result["python"] = item["python"]
        result["platform"] = item["platform"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".cache/click-source")
    parser.add_argument("--destination", type=Path, default=ROOT / ".cache/click-migrated")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/stress")
    parser.add_argument("--case", choices=tuple(CASES), action="append")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    if args.workers < 1 or args.batch_size < 1:
        parser.error("workers and batch-size must be positive")
    source, destination, output = (p.resolve() for p in (args.source, args.destination, args.output))
    if not source.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts/prepare_upstream.py"),
                        "--source", str(source), "--destination", str(destination)], check=True)
    else:
        prepare(source, destination)
    output.mkdir(parents=True, exist_ok=True)
    package = importlib.import_module("zclick")
    native = importlib.import_module("zclick._native")
    snapshot = output / "candidate/python/zclick"
    if snapshot.exists():
        shutil.rmtree(snapshot)
    shutil.copytree(Path(package.__file__).parent, snapshot,
                    ignore=shutil.ignore_patterns("__pycache__", "*.so", "*.pyd"))
    shutil.copy2(native.__file__, snapshot / Path(native.__file__).name)
    provenance = {
        "implementation_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "target": TARGET, "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "candidate_files": {str(p.relative_to(snapshot)): digest(p) for p in snapshot.rglob("*") if p.is_file()},
        "reference_tests": {path: digest(source / path) for path, _ in CASES.values()},
        "candidate_tests": {path: digest(destination / path) for path, _ in CASES.values()},
    }
    (output / "source.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    selections = []
    cases = args.case or list(CASES)
    expected_ids = set()
    for case in cases:
        file, count = CASES[case]
        node = f"{file}::test_stress_{case}"
        expected_ids.update(f"{node}[{i}]" for i in range(count))
        if case == "gc_between_invocations":
            for start in range(0, count, args.batch_size):
                selections.append((f"{case}-{start:05}", [f"{node}[{i}]" for i in range(start, min(count, start + args.batch_size))]))
        elif case == "echo_via_pager_exception_cleanup":
            # Its original fixture relies on imports from other collected test
            # modules. Preserve that collection context while selecting its IDs.
            selections.append((case, ["tests", "-m", "stress", "-k", f"test_stress_{case}"]))
        else:
            selections.append((case, [node]))

    def run(job):
        package_name, name, selectors = job
        report_path = output / f"{package_name}-{name}.json"
        argfile = output / f"{package_name}-{name}.args"
        argfile.write_text("\n".join(selectors) + "\n", encoding="utf-8")
        env = os.environ.copy()
        python_path = source / "src" if package_name == "click" else snapshot.parent
        env["PYTHONPATH"] = os.pathsep.join((str(python_path), str(ROOT / "scripts")))
        env["ZCLICK_COMPAT_REPORT"] = str(report_path)
        command = [sys.executable, "-m", "pytest", "-p", "compat_report_plugin",
                   "-c", str(destination / "pytest.ini"), "-q", "--tb=short", f"@{argfile}"]
        result = subprocess.run(command, cwd=source if package_name == "click" else destination,
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (output / f"{package_name}-{name}.log").write_text(result.stdout, encoding="utf-8")
        if not report_path.exists():
            raise RuntimeError(f"Stress process did not write a report: {package_name}/{name}\n{result.stdout}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print(f"{package_name}/{name}: {len(report['results'])} cases, exit {result.returncode}", flush=True)
        return package_name, report_path

    report_paths = {"click": [], "zclick": []}
    jobs = [(package_name, name, selectors) for package_name in report_paths for name, selectors in selections]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run, job) for job in jobs]
        for future in as_completed(futures):
            package_name, path = future.result()
            report_paths[package_name].append(path)
    reports = {package_name: merged(paths) for package_name, paths in report_paths.items()}
    for package_name, report in reports.items():
        if set(report["collected"]) != expected_ids:
            raise RuntimeError(f"{package_name}: stress case coverage does not match pinned IDs")
        (output / f"{package_name}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = compare(reports["click"], reports["zclick"])
    summary.update({"complete": False, "scope": "stress", "selected_cases": cases,
                    "source_provenance": provenance,
                    "implementation_commit": provenance["implementation_commit"]})
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Stress coverage: {len(expected_ids)} exact IDs; passed={summary['passed']}")
    raise SystemExit(0 if summary["passed"] else 1)


if __name__ == "__main__":
    main()
