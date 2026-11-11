"""Generate the API contract from the pinned documentation and public exports.

Run reference collection in its own Python process. The generated JSON records
signatures, defaults, return annotations, deprecation warnings and public class
members. It is an inventory; an available name alone never marks behavior passed.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
from pathlib import Path
import re
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
TARGET = json.loads((ROOT / "compatibility/target.json").read_text())
MODULES = ("core", "decorators", "types", "exceptions", "formatting", "parser",
           "termui", "utils", "globals", "shell_completion", "testing")


def describe(obj: object) -> dict[str, object]:
    out: dict[str, object] = {"kind": type(obj).__name__}
    try:
        signature = inspect.signature(obj)
    except (ValueError, TypeError):
        signature = None
    if signature is not None:
        out["signature"] = str(signature)
        out["parameters"] = [
            {"name": p.name, "kind": p.kind.name,
             "default": None if p.default is p.empty else repr(p.default),
             "required": p.default is p.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD),
             "annotation": None if p.annotation is p.empty else repr(p.annotation)}
            for p in signature.parameters.values()
        ]
        out["return_annotation"] = (None if signature.return_annotation is signature.empty
                                    else repr(signature.return_annotation))
    elif isinstance(obj, property):
        out["property"] = True
        if obj.fget:
            out["getter"] = str(inspect.signature(obj.fget))
        out["writable"] = obj.fset is not None
    else:
        out["value"] = re.sub(r" at 0x[0-9a-f]+", "", repr(obj))
    return out


def resolve(name: str) -> object:
    parts = name.split(".")
    for length in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:length]))
        except ImportError:
            continue
        for part in parts[length:]:
            obj = getattr(obj, part)
        return obj
    raise ImportError(name)


def collect(source: Path) -> dict:
    sys.path.insert(0, str(source / "src"))
    click = importlib.import_module("click")
    if not Path(click.__file__).resolve().is_relative_to(source.resolve()):
        raise RuntimeError("Reference inventory imported the wrong Click installation")
    names: dict[str, set[str]] = {}
    current = "click"
    for line in (source / TARGET["api_reference"]).read_text().splitlines():
        match = re.search(r"(?:\.\.\s+currentmodule::|\{currentmodule\})\s+(\S+)", line)
        if match:
            current = match[1]
        match = re.search(r"\.\.\s+auto(?:class|function|data|exception)::\s+(\S+)", line)
        if match:
            name = match[1] if match[1].startswith("click.") else f"{current}.{match[1]}"
            names.setdefault(name, set()).add("official-api-reference")
    init = ast.parse((source / "src/click/__init__.py").read_text())
    for node in init.body:
        if isinstance(node, ast.ImportFrom) and node.level:
            for alias in node.names:
                names.setdefault(f"click.{alias.asname or alias.name}", set()).add("top-level-export")
    for module_name in MODULES:
        module = importlib.import_module(f"click.{module_name}")
        for name, obj in vars(module).items():
            if not name.startswith("_") and getattr(obj, "__module__", "") == module.__name__:
                names.setdefault(f"{module.__name__}.{name}", set()).add("public-submodule-definition")
        path = source / f"src/click/{module_name}.py"
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "__getattr__":
                for comparison in ast.walk(node):
                    if isinstance(comparison, ast.Compare) and isinstance(comparison.left, ast.Name) and comparison.left.id == "name":
                        for value in comparison.comparators:
                            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                                names.setdefault(f"{module.__name__}.{value.value}", set()).add("deprecated-public-export")
    names["click.__version__"] = {"deprecated-public-export"}
    tests = {str(p.relative_to(source)): p.read_text() for p in (source / "tests").rglob("test_*.py")}
    entries = {}
    for name in sorted(names):
        with warnings.catch_warnings(record=True) as emitted:
            warnings.simplefilter("always")
            obj = resolve(name)
        entry = describe(obj)
        entry["sources"] = sorted(names[name])
        entry["warnings"] = [{"category": w.category.__name__, "message": str(w.message),
                              "trigger": "attribute access"} for w in emitted]
        short = name.rsplit(".", 1)[-1]
        entry["test_sources"] = [p for p, text in tests.items() if re.search(rf"\b{re.escape(short)}\b", text)]
        if inspect.isclass(obj):
            members = {}
            for member in sorted(set(dir(obj))):
                if member.startswith("_") and member not in ("__init__", "__call__", "__enter__", "__exit__"):
                    continue
                value = inspect.getattr_static(obj, member)
                if isinstance(value, (staticmethod, classmethod)):
                    value = value.__func__
                if inspect.ismethoddescriptor(value) and getattr(value, "__objclass__", None) in (object, type):
                    continue
                members[member] = describe(value)
            entry["members"] = members
        entry["behavior_status"] = "unverified"
        entries[name] = entry
    return {"schema": 1, "target": TARGET, "entries": entries}


def compare(inventory: dict) -> dict:
    entries = {}
    for reference_name, expected in inventory["entries"].items():
        name = reference_name.replace("click", "zclick", 1)
        with warnings.catch_warnings(record=True) as emitted:
            warnings.simplefilter("always")
            try:
                actual = resolve(name)
            except (ImportError, AttributeError) as exc:
                entries[reference_name] = {"available": False, "error": str(exc)}
                continue
        record = {"available": True, "description": describe(actual)}
        if "parameters" in expected:
            wanted = [(p["name"], p["kind"], p["default"]) for p in expected["parameters"]]
            got = [(p["name"], p["kind"], p["default"]) for p in record["description"].get("parameters", [])]
            record["parameter_contract_matches"] = wanted == got
        record["deprecation_categories_match"] = (
            [w.category.__name__ for w in emitted] == [w["category"] for w in expected["warnings"]]
        )
        record["missing_members"] = [m for m in expected.get("members", {}) if not hasattr(actual, m)]
        mismatches = {}
        for member, member_expected in expected.get("members", {}).items():
            if member in record["missing_members"]:
                continue
            value = inspect.getattr_static(actual, member)
            if isinstance(value, (staticmethod, classmethod)):
                value = value.__func__
            description = describe(value)
            if "parameters" in member_expected:
                want = [(p["name"], p["kind"], p["default"]) for p in member_expected["parameters"]]
                got = [(p["name"], p["kind"], p["default"]) for p in description.get("parameters", [])]
                if want != got:
                    mismatches[member] = {"expected": want, "actual": got}
            elif member_expected.get("property"):
                if not description.get("property") or description.get("writable") != member_expected["writable"]:
                    mismatches[member] = {"expected": member_expected, "actual": description}
        record["member_contract_mismatches"] = mismatches
        entries[reference_name] = record
    return {"schema": 1, "target": TARGET, "entries": entries,
            "complete": all(e.get("available") and e.get("parameter_contract_matches", True)
                            and e.get("deprecation_categories_match") and not e.get("missing_members")
                            and not e.get("member_contract_mismatches")
                            for e in entries.values())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    if args.compare:
        result = compare(json.loads(args.compare.read_text()))
    elif args.source:
        result = collect(args.source)
    else:
        parser.error("Pass --source or --compare")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"Recorded {len(result['entries'])} API objects in {args.output}")
    if args.compare and not result["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
