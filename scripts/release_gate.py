"""Require successful evidence covering every upstream case before publishing."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from compat_report_plugin import key


ROOT = Path(__file__).resolve().parents[1]


def verify(paths: list[Path], api_paths: list[Path], *, shell_path: Path | None = None,
           implementation: str | None = None, manifest: Path | None = None) -> None:
    if not paths or not api_paths:
        raise ValueError("Compatibility and API evidence are both required")
    covered: set[str] = set()
    required: set[str] = set()
    contract = json.loads((manifest or ROOT / "compatibility/test-manifest.json").read_text(encoding="utf-8"))
    target = contract["target_commit"]
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        if not report.get("passed"):
            raise ValueError(f"Compatibility failed: {path}")
        commit = report["target"]["commit"]
        if commit != target:
            raise ValueError("Reports mix upstream Click versions")
        if implementation and report.get("implementation_commit") != implementation:
            raise ValueError(f"Compatibility report does not match release commit: {path}")
        ids = {key(node) for node in report["validated_test_ids"]}
        if not ids:
            raise ValueError(f"Empty compatibility report: {path}")
        covered.update(ids)
        required.update(ids)
        required.update(key(node) for node in report.get("deselected", []))
    missing = required - covered
    if missing:
        raise ValueError(f"{len(missing)} upstream tests have no passing evidence; first: {min(missing)}")
    fingerprint = hashlib.sha256(("\n".join(sorted(covered)) + "\n").encode("utf-8")).hexdigest()
    if len(covered) != contract["test_count"] or fingerprint != contract["test_ids_sha256"]:
        raise ValueError("Evidence does not cover the exact pinned upstream test inventory")
    for path in api_paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        if not report.get("complete") or report["target"]["commit"] != target:
            raise ValueError(f"Public API contract failed: {path}")
        if implementation and report.get("implementation_commit") != implementation:
            raise ValueError(f"API report does not match release commit: {path}")
    if shell_path is not None:
        shell = json.loads(shell_path.read_text(encoding="utf-8"))
        if not shell.get("passed") or shell.get("scope") != "actual-shell-integration":
            raise ValueError("Real Shell execution has not passed")
        if {runtime["name"] for runtime in shell.get("runtimes", [])} != {"bash", "zsh", "fish", "pwsh"}:
            raise ValueError("Real Shell evidence must include all four target shells")
        if implementation and shell.get("implementation_commit") != implementation:
            raise ValueError("Shell report does not match release commit")
    print(f"Release gate passed: {len(covered)} upstream cases and all public API contracts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", nargs="+", type=Path, required=True)
    parser.add_argument("--api", nargs="+", type=Path, required=True)
    parser.add_argument("--shell", type=Path)
    parser.add_argument("--implementation", help="Exact git SHA required for every report")
    args = parser.parse_args()
    try:
        verify(args.reports, args.api, shell_path=args.shell, implementation=args.implementation)
    except (ValueError, KeyError) as exc:
        parser.exit(1, str(exc) + "\n")
