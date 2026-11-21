"""Fail closed on runtime Click imports, hidden fallbacks, or extra core parsers."""
from __future__ import annotations

import ast
from contextlib import contextmanager
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib

ROOT = Path(__file__).resolve().parents[1]

CRATES_IO = "registry+https://github.com/rust-lang/crates.io-index"
ZCLAP_GIT = "git+https://github.com/LIghtJUNction/zclap.git"


def is_zclap_git_source(source: str | None) -> bool:
    return source is not None and bool(re.fullmatch(re.escape(ZCLAP_GIT) + r"#[0-9a-f]{40}", source))


def audit_cargo(root: Path, *, release: dict | None = None) -> list[str]:
    problems = []
    metadata = json.loads(subprocess.check_output(
        ["cargo", "metadata", "--format-version", "1", "--locked"], cwd=root
    ))
    packages = {package["id"]: package for package in metadata["packages"]}
    nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
    locked = tomllib.loads((root / "Cargo.lock").read_text(encoding="utf-8"))["package"]
    for package_id in metadata["workspace_members"]:
        package = packages[package_id]
        runtime = [dep for dep in package["dependencies"] if dep["kind"] is None]
        names = {dep["name"] for dep in runtime}
        if package["name"] == "zclick-core" and names != {"zclap"}:
            problems.append(f"zclick-core runtime dependencies must be exactly zclap, got {sorted(names)}")
        if package["name"] == "zclick-python" and names != {"pyo3", "zclick-core"}:
            problems.append(f"Unexpected extension dependencies: {sorted(names)}")
        for dep in runtime:
            if dep["name"] != "zclap":
                continue
            resolved = [
                packages[edge["pkg"]]
                for edge in nodes[package_id]["deps"]
                if packages[edge["pkg"]]["name"] == "zclap"
                and any(kind["kind"] is None for kind in edge["dep_kinds"])
            ]
            if len(resolved) != 1:
                problems.append("zclap must resolve to exactly one runtime dependency")
                continue
            selected = resolved[0]
            matches = [
                entry for entry in locked
                if (entry["name"], entry["version"], entry.get("source"))
                == ("zclap", selected["version"], selected["source"])
            ]
            if len(matches) != 1:
                problems.append("resolved zclap must match a unique Cargo.lock entry")
                continue
            if release:
                if (dep["source"] != CRATES_IO or dep["req"] != release["requirement"]
                        or selected["source"] != CRATES_IO
                        or selected["version"] != release["version"]
                        or matches[0].get("checksum") != release["checksum"]):
                    problems.append("release zclap must match the exact crates.io pin and checksum")
            elif (dep["source"] != ZCLAP_GIT or dep["req"] != "*"
                  or not is_zclap_git_source(selected["source"])):
                problems.append("development zclap must use the GitHub source and a locked Git SHA")
    return problems


@contextmanager
def release_workspace(root: Path):
    """Stage the crates.io dependency and lock in a disposable workspace."""
    pin = json.loads((root / "compatibility/zclap.json").read_text(encoding="utf-8"))
    if pin["requirement"] != "=" + pin["version"]:
        raise ValueError("release zclap must have an exact crates.io requirement")
    with TemporaryDirectory(prefix="zclick-release-") as tmp:
        projection = Path(tmp)
        shutil.copytree(root / "crates", projection / "crates")
        for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml"):
            shutil.copy2(root / name, projection / name)
        manifest = projection / "crates/zclick-core/Cargo.toml"
        source = manifest.read_text(encoding="utf-8")
        git_clause = f'git = "{ZCLAP_GIT.removeprefix("git+")}"'
        if source.count(git_clause) != 1:
            raise ValueError("expected a single zclap Git source in the core manifest")
        manifest.write_text(source.replace(git_clause, f'version = "{pin["requirement"]}"'),
                            encoding="utf-8")
        subprocess.run(["cargo", "update", "--workspace"], cwd=projection, check=True)
        failures = audit_cargo(projection, release=pin)
        if failures:
            raise ValueError("\n".join(failures))
        yield projection


def audit() -> list[str]:
    problems = []
    for source in (ROOT / "python/zclick").rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            imports = []
            if isinstance(node, ast.Import):
                imports = [name.name for name in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""] if not node.level else []
            elif isinstance(node, ast.Call) and node.args:
                function = node.func
                dynamic_import = ((isinstance(function, ast.Name) and function.id == "__import__")
                                  or (isinstance(function, ast.Attribute) and function.attr == "import_module"))
                if dynamic_import and isinstance(node.args[0], ast.Constant):
                    imports = [node.args[0].value]
            for name in imports:
                if isinstance(name, str) and (name == "click" or name.startswith("click.")):
                    problems.append(f"{source.relative_to(ROOT)}:{node.lineno}: imports runtime Click")
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
                if (node.value.attr == "modules" and isinstance(node.ctx, ast.Store)
                        and isinstance(node.slice, ast.Constant)
                        and isinstance(node.slice.value, str)
                        and (node.slice.value == "click" or node.slice.value.startswith("click."))):
                    problems.append(f"{source.relative_to(ROOT)}:{node.lineno}: replaces Click in sys.modules")
    for path in (ROOT / "crates").rglob("*.rs"):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("Box::leak", "std::process::exit", "process::exit(", "from_utf8_lossy", "to_string_lossy"):
            if forbidden in text:
                problems.append(f"{path.relative_to(ROOT)}: forbidden lifetime, exit, or lossy conversion: {forbidden}")
    problems.extend(audit_cargo(ROOT))
    if not problems:
        try:
            with release_workspace(ROOT):
                pass
        except ValueError as error:
            problems.append(str(error))
    return problems


if __name__ == "__main__":
    failures = audit()
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        raise SystemExit(1)
    print("Dependency boundaries and runtime import audit passed")
