"""Combine disjoint test reports and verify complete upstream case coverage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_compatibility import compare
from run_stress import merged
from compat_report_plugin import key


def combine(paths: list[Path]) -> dict:
    result = merged(paths)
    expected = set(result["collected"])
    for path in paths:
        expected.update(key(node) for node in json.loads(path.read_text(encoding="utf-8")).get("deselected", []))
    result["deselected"] = sorted(expected - set(result["collected"]))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--click", type=Path, nargs="+", required=True)
    parser.add_argument("--zclick", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline, candidate = combine(args.click), combine(args.zclick)
    result = compare(baseline, candidate)
    result["source_reports"] = {"click": list(map(str, args.click)), "zclick": list(map(str, args.zclick))}
    args.output.mkdir(parents=True, exist_ok=True)
    for name, report in (("click", baseline), ("zclick", candidate), ("summary", result)):
        (args.output / f"{name}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: result[name] for name in ("complete", "expected_tests", "counts")}, indent=2))
    raise SystemExit(0 if result["complete"] else 1)
