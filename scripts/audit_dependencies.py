"""Fail closed on runtime Click imports, hidden fallbacks, or extra core parsers."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


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
    metadata = json.loads(subprocess.check_output(
        ["cargo", "metadata", "--no-deps", "--format-version", "1", "--locked"], cwd=ROOT
    ))
    for package in metadata["packages"]:
        runtime = [dep for dep in package["dependencies"] if dep["kind"] is None]
        names = {dep["name"] for dep in runtime}
        if package["name"] == "zclick-core" and names != {"zclap"}:
            problems.append(f"zclick-core runtime dependencies must be exactly zclap, got {sorted(names)}")
        if package["name"] == "zclick-python" and names != {"pyo3", "zclick-core"}:
            problems.append(f"Unexpected extension dependencies: {sorted(names)}")
        for dep in runtime:
            if dep["name"] == "zclap" and (not dep["req"].startswith("=") or dep.get("source") != "registry+https://github.com/rust-lang/crates.io-index"):
                problems.append("zclap must have an exact crates.io requirement")
    for path in (ROOT / "crates").rglob("*.rs"):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("Box::leak", "std::process::exit", "process::exit(", "from_utf8_lossy", "to_string_lossy"):
            if forbidden in text:
                problems.append(f"{path.relative_to(ROOT)}: forbidden lifetime, exit, or lossy conversion: {forbidden}")
    return problems


if __name__ == "__main__":
    failures = audit()
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        raise SystemExit(1)
    print("Dependency boundaries and runtime import audit passed")
