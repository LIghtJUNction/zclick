"""Require successful evidence covering every upstream case before publishing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify(paths: list[Path], api_paths: list[Path]) -> None:
    if not paths or not api_paths:
        raise ValueError("Compatibility and API evidence are both required")
    covered: set[str] = set()
    required: set[str] = set()
    target = None
    for path in paths:
        report = json.loads(path.read_text())
        if not report.get("passed"):
            raise ValueError(f"Compatibility failed: {path}")
        commit = report["target"]["commit"]
        if target is not None and commit != target:
            raise ValueError("Reports mix upstream Click versions")
        target = commit
        ids = set(report["validated_test_ids"])
        if not ids:
            raise ValueError(f"Empty compatibility report: {path}")
        covered.update(ids)
        required.update(ids)
        required.update(report.get("deselected", []))
    missing = required - covered
    if missing:
        raise ValueError(f"{len(missing)} upstream tests have no passing evidence; first: {min(missing)}")
    if not any("test_stress_gc_between_invocations" in node for node in covered):
        raise ValueError("Stress coverage is missing")
    for path in api_paths:
        report = json.loads(path.read_text())
        if not report.get("complete") or report["target"]["commit"] != target:
            raise ValueError(f"Public API contract failed: {path}")
    print(f"Release gate passed: {len(covered)} upstream cases and all public API contracts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", nargs="+", type=Path, required=True)
    parser.add_argument("--api", nargs="+", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(args.reports, args.api)
    except (ValueError, KeyError) as exc:
        parser.exit(1, str(exc) + "\n")
