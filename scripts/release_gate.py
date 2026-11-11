"""Require successful evidence covering every upstream case before publishing."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from compat_report_plugin import key
from bump_version import parse as parse_version


ROOT = Path(__file__).resolve().parents[1]


def verify(paths: list[Path], api_paths: list[Path], *, shell_path: Path | None = None,
           implementation: str | None = None, manifest: Path | None = None,
           known_gaps: Path | None = None, version: str | None = None,
           boundary_path: Path | None = None) -> None:
    if not paths or not api_paths:
        raise ValueError("Compatibility and API evidence are both required")
    covered: set[str] = set()
    required: set[str] = set()
    contract = json.loads((manifest or ROOT / "compatibility/test-manifest.json").read_text(encoding="utf-8"))
    target = contract["target_commit"]
    gaps = json.loads((known_gaps or ROOT / "compatibility/known-gaps.json").read_text(encoding="utf-8"))
    if gaps.get("target_commit") != target:
        raise ValueError("Known gaps refer to a different compatibility target")
    unfinished = [gap for gap in gaps["gaps"] if gap.get("status") != "RESOLVED"]
    if version is None:
        match = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
        if match is None:
            raise ValueError("Could not read the release version")
        version = match[1]
    if unfinished and parse_version(version)[3] is None:
        raise ValueError("A stable release is blocked by unfinished compatibility items: " +
                         ", ".join(gap["id"] for gap in unfinished))
    if any(not gap.get("disclosure") for gap in unfinished):
        raise ValueError("Every unfinished compatibility item needs an explicit disclosure")
    if any(gap["id"] == "subinterpreters" for gap in unfinished) and boundary_path is None:
        raise ValueError("Subinterpreter safety evidence is required for this prerelease")
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        if not report.get("passed"):
            raise ValueError(f"Compatibility failed: {path}")
        commit = report["target"]["commit"]
        if commit != target:
            raise ValueError("Reports mix upstream Click versions")
        if implementation and report.get("implementation_commit") != implementation:
            raise ValueError(f"Compatibility report does not match release commit: {path}")
        normalized = [key(node) for node in report["validated_test_ids"]]
        ids = set(normalized)
        if len(ids) != len(normalized):
            raise ValueError(f"Canonical test IDs are not unique within report: {path}")
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
        raise ValueError("Evidence does not cover the exact pinned upstream test inventory: "
                         f"count={len(covered)}, expected={contract['test_count']}; "
                         f"sha256={fingerprint}, expected={contract['test_ids_sha256']}")
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
    if boundary_path is not None:
        boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
        if (boundary.get("scope") != "subinterpreter-boundary" or not boundary.get("reference_control_passed")
                or not boundary.get("safety_passed")
                or boundary.get("target", {}).get("commit") != target):
            raise ValueError("Subinterpreter boundary safety failed")
        if any(gap["id"] == "subinterpreters" for gap in unfinished) and not boundary.get("safe_rejection"):
            raise ValueError("The unresolved subinterpreter boundary must safely reject imports")
        if implementation and boundary.get("implementation_commit") != implementation:
            raise ValueError("Subinterpreter report does not match release commit")
    print(f"Release gate passed: {len(covered)} upstream cases and all public API contracts")
    if unfinished:
        print("Prerelease only; unfinished compatibility: " + ", ".join(gap["id"] for gap in unfinished))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", nargs="+", type=Path, required=True)
    parser.add_argument("--api", nargs="+", type=Path, required=True)
    parser.add_argument("--shell", type=Path)
    parser.add_argument("--implementation", help="Exact git SHA required for every report")
    parser.add_argument("--version", help="Release version; defaults to pyproject.toml")
    parser.add_argument("--boundary", type=Path, help="Subinterpreter compatibility and safety evidence")
    args = parser.parse_args()
    try:
        verify(args.reports, args.api, shell_path=args.shell, implementation=args.implementation,
               version=args.version, boundary_path=args.boundary)
    except (ValueError, KeyError) as exc:
        parser.exit(1, str(exc) + "\n")
