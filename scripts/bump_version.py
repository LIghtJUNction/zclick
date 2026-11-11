"""Bump Python and workspace versions together, without external dependencies."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:(a|b|rc)(\d+))?\Z")


def parse(value: str) -> tuple[int, int, int, str | None, int | None]:
    match = VERSION.fullmatch(value)
    if match is None:
        raise ValueError("Version must be MAJOR.MINOR.PATCH with optional aN, bN, or rcN")
    return (int(match[1]), int(match[2]), int(match[3]), match[4],
            int(match[5]) if match[5] is not None else None)


def cargo_version(value: str) -> str:
    major, minor, patch, phase, number = parse(value)
    phase_names = {"a": "alpha", "b": "beta", "rc": "rc"}
    suffix = "" if phase is None else f"-{phase_names[phase]}.{number}"
    return f"{major}.{minor}.{patch}{suffix}"


def next_version(current: str, part: str) -> str:
    major, minor, patch, phase, number = parse(current)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch if phase else patch + 1}"
    if part == "prerelease":
        return f"{major}.{minor}.{patch if phase else patch + 1}{phase or 'a'}{(number or 0) + 1}"
    raise ValueError(f"Unknown bump part {part!r}")


def order(value: str) -> tuple[int, int, int, int, int]:
    major, minor, patch, phase, number = parse(value)
    return major, minor, patch, {"a": 0, "b": 1, "rc": 2, None: 3}[phase], number or 0


def bump(root: Path, part: str, explicit: str | None = None, dry_run: bool = False) -> str:
    pyproject = root / "pyproject.toml"
    python_text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', python_text, re.M)
    if match is None:
        raise ValueError("pyproject.toml needs one explicit project version")
    current = match[1]
    proposed = explicit if part == "custom" else next_version(current, part)
    if not proposed:
        raise ValueError("A custom bump requires --version")
    parse(proposed)
    if order(proposed) <= order(current):
        raise ValueError(f"Version {proposed} must be newer than {current}")
    rust_version = cargo_version(proposed)
    updates = {pyproject: python_text[:match.start(1)] + proposed + python_text[match.end(1):]}
    workspace = root / "Cargo.toml"
    cargo = workspace.read_text(encoding="utf-8")
    cargo, changed = re.subn(r'(?ms)(\[workspace\.package\]\n.*?^version = ")[^"]+("$)',
                             lambda m: m[1] + rust_version + m[2], cargo, count=1)
    if changed != 1:
        raise ValueError("Cargo.toml needs workspace.package.version")
    updates[workspace] = cargo
    for manifest in sorted((root / "crates").glob("*/Cargo.toml")):
        text = manifest.read_text(encoding="utf-8")
        text = re.sub(r'(?m)^(zclick-[\w-]+\s*=\s*\{[^\n]*?version\s*=\s*"=)[^"]+',
                      lambda m: m[1] + rust_version, text)
        updates[manifest] = text
    if not dry_run:
        for path, content in updates.items():
            temp = path.with_suffix(path.suffix + ".bump.tmp")
            temp.write_text(content, encoding="utf-8")
            temp.replace(path)
    print(f"{current} -> {proposed} (Cargo {rust_version})")
    return proposed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=("patch", "minor", "major", "prerelease", "custom"), required=True)
    parser.add_argument("--version")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        value = bump(ROOT, args.part, args.version, args.dry_run)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.dry_run and (ROOT / "Cargo.lock").exists():
        subprocess.run(["cargo", "check", "--workspace"], cwd=ROOT, check=True)
    if not args.dry_run and os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write(f"version={value}\ntag=v{value}\n")


if __name__ == "__main__":
    main()
