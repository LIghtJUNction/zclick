"""Materialize the pinned Click tests with a namespace-only migration.

The upstream implementation stays outside the distribution. No test, assertion,
marker, fixture or expected behavior is removed. The changes are recorded so
reviewers can inspect every namespace edit. There is no sys.modules aliasing.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tokenize

ROOT = Path(__file__).resolve().parents[1]
TARGET = json.loads((ROOT / "compatibility/target.json").read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migrate(source: str, path: str) -> tuple[str, list[dict[str, object]]]:
    """Rename only the imported package and references to that package."""
    changes: list[dict[str, object]] = []
    result = []
    # A NAME-token edit leaves comments, expected output and strings unchanged.
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        replacement = token.string
        if token.type == tokenize.NAME and token.string == "click":
            replacement = "zclick"
        elif token.type == tokenize.STRING:
            try:
                value = ast.literal_eval(token.string)
            except (ValueError, SyntaxError):
                value = None
            # Monkeypatch paths are imports too, not output expectations.
            if isinstance(value, str) and value.startswith("click."):
                replacement = token.string.replace("click.", "zclick.", 1)
            # Subprocess snippets import the package in a fresh interpreter.
            elif (isinstance(value, str) and "import click" in value) or (
                isinstance(value, bytes) and b"import click" in value
            ):
                replacement = re.sub(r"\bclick\b", "zclick", token.string)
        if replacement != token.string:
            changes.append({"line": token.start[0], "before": token.string, "after": replacement})
            token = token._replace(string=replacement)
        result.append(token)
    migrated = tokenize.untokenize(result)
    # These identify the distribution/package under test. The same checks are
    # retained with zclick's namespace, including the import allowlist.
    exact_namespace_changes = {
        "test_imports.py": [("module == \"click\"", "module == \"zclick\"")],
        "test_deprecations.py": [
            ('importlib.metadata.version("click")', 'importlib.metadata.version("zclick")')
        ],
        "test_Path.py": [("convert = click.Path", "convert = zclick.Path")],
        "test_options.py": [(r"<click\.types\.Tuple object", r"<zclick\.types\.Tuple object")],
    }
    for before, after in exact_namespace_changes.get(Path(path).name, []):
        if before not in migrated:
            raise RuntimeError(f"Expected namespace anchor missing in {path}: {before}")
        migrated = migrated.replace(before, after)
        changes.append({"namespace_anchor": before, "after": after})
    # Never rewrite package names in arbitrary output assertions.
    ast.parse(migrated, filename=path)
    return migrated, changes


def prepare(source: Path, destination: Path) -> dict[str, object]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if commit != TARGET["commit"]:
        raise SystemExit(f"Wrong Click commit: {commit}; required {TARGET['commit']}")
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=source, text=True)
    if dirty:
        raise SystemExit("The pinned upstream checkout contains modified tracked files")
    manifest = {"target_commit": commit, "files": {}, "namespace_changes": {}}
    for origin in sorted((source / "tests").rglob("*")):
        if not origin.is_file() or "__pycache__" in origin.parts:
            continue
        relative = origin.relative_to(source)
        dest = destination / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if origin.suffix == ".py":
            code, changes = migrate(origin.read_text(encoding="utf-8"), str(relative))
            dest.write_text(code, encoding="utf-8")
            manifest["namespace_changes"][str(relative)] = changes
        else:
            shutil.copyfile(origin, dest)
        manifest["files"][str(relative)] = {
            "original_sha256": digest(origin), "migrated_sha256": digest(dest)
        }
    (destination / "namespace-migration.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # A few upstream glob tests explicitly use the checkout's root files.
    shutil.copyfile(source / "pyproject.toml", destination / "pyproject.toml")
    # Keep upstream warnings and markers. Include stress tests as well.
    (destination / "pytest.ini").write_text(
        "[pytest]\nfilterwarnings =\n    error\nmarkers =\n"
        "    stress: upstream high iteration stress tests\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / ".cache/click-source")
    parser.add_argument("--destination", type=Path, default=ROOT / ".cache/click-migrated")
    args = parser.parse_args()
    if not args.source.exists():
        subprocess.run(["git", "clone", "--depth", "1", "--branch", TARGET["tag"],
                        TARGET["repository"], str(args.source)], check=True)
    manifest = prepare(args.source, args.destination)
    print(f"Prepared {len(manifest['files'])} pinned upstream files at {args.destination}")


if __name__ == "__main__":
    main()
