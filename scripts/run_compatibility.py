"""Run every pinned upstream test against Click and zclick in separate processes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from prepare_upstream import ROOT, TARGET, prepare
from compat_report_plugin import key


def run(source: Path, migrated: Path, report: Path, baseline: bool, extra: list[str],
        selected: list[str] | None = None) -> int:
    env = os.environ.copy()
    paths = [str(ROOT / "scripts")]
    if baseline:
        paths.insert(0, str(source / "src"))
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["ZCLICK_COMPAT_REPORT"] = str(report.resolve())
    directory = source if baseline else migrated
    tests = [str(directory / test) for test in selected] if selected else [str(directory / "tests")]
    command = [sys.executable, "-m", "pytest", *tests, "-c", str(migrated / "pytest.ini"),
               "-p", "compat_report_plugin", "--continue-on-collection-errors", "--tb=short", "-q", *extra]
    return subprocess.run(command, cwd=source if baseline else migrated, env=env).returncode


def compare(reference: dict, candidate: dict) -> dict:
    for report in (reference, candidate):
        report["collected"] = [key(node) for node in report["collected"]]
        report["results"] = {key(node): value for node, value in report["results"].items()}
    expected = set(reference["collected"])
    actual = set(candidate["collected"])
    failures, unexpected_skips = [], []
    for node in sorted(expected | actual):
        baseline = reference["results"].get(node, {})
        current = candidate["results"].get(node, {})
        if current.get("outcome") in ("failed", "pending"):
            failures.append(node)
        elif current.get("outcome") == "skipped" and baseline.get("outcome") != "skipped":
            unexpected_skips.append(node)
    counts = {state: sum(r.get("outcome") == state for r in candidate["results"].values())
              for state in ("passed", "failed", "skipped", "pending")}
    result = {
        "schema": 1, "target": TARGET, "expected_tests": len(expected),
        "collected_tests": len(actual), "counts": counts,
        "missing_tests": sorted(expected - actual), "extra_tests": sorted(actual - expected),
        "failures": failures, "unexpected_skips": unexpected_skips,
        "baseline_exit_status": reference["exit_status"],
        "candidate_exit_status": candidate["exit_status"],
        "collection_errors": candidate["collection_errors"],
        "deselected": reference.get("deselected", []),
        "validated_test_ids": sorted(expected),
    }
    result["passed"] = bool(expected) and not any((
        reference["exit_status"], candidate["exit_status"], result["missing_tests"],
        result["extra_tests"], failures, unexpected_skips, candidate["collection_errors"],
    ))
    result["scope"] = "selection" if result["deselected"] else "all-collected"
    result["complete"] = result["passed"] and not result["deselected"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".cache/click-source")
    parser.add_argument("--destination", type=Path, default=ROOT / ".cache/click-migrated")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/compatibility")
    parser.add_argument("--candidate-only", action="store_true", help="Reuse existing baseline report")
    parser.add_argument("--test", action="append", help="Run an explicit upstream path or node, recorded in the summary")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    args.source = args.source.resolve()
    args.destination = args.destination.resolve()
    args.output = args.output.resolve()
    if not args.source.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts/prepare_upstream.py"),
                        "--source", str(args.source), "--destination", str(args.destination)], check=True)
    else:
        prepare(args.source, args.destination)
    args.output.mkdir(parents=True, exist_ok=True)
    baseline = args.output / "click.json"
    candidate = args.output / "zclick.json"
    extra = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
    if not args.candidate_only:
        run(args.source, args.destination, baseline, True, extra, args.test)
    if not baseline.exists():
        parser.error("No baseline report to reuse")
    run(args.source, args.destination, candidate, False, extra, args.test)
    if not candidate.exists():
        raise SystemExit("Candidate process produced no report")
    result = compare(json.loads(baseline.read_text()), json.loads(candidate.read_text()))
    result["selected_paths"] = args.test
    result["complete"] = result["complete"] and not args.test
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("complete", "expected_tests", "collected_tests", "counts")}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
