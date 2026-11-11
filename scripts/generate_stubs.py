"""Extract type declarations, never implementation bodies, from the fixed API.

The generated .pyi files describe the compatibility target. Runtime behavior is
implemented independently and tested separately. The source license is retained
in compatibility/CLICK_LICENSE.txt.
"""
from __future__ import annotations

import argparse
import ast
import copy
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def annotation(value: ast.expr) -> ast.expr:
    if isinstance(value, ast.Constant):
        return ast.Name(id=type(value.value).__name__ if value.value is not None else "object")
    if isinstance(value, ast.Call):
        return copy.deepcopy(value.func)
    if isinstance(value, ast.Dict):
        return ast.parse("dict[t.Any, t.Any]", mode="eval").body
    if isinstance(value, ast.List):
        return ast.parse("list[t.Any]", mode="eval").body
    if isinstance(value, ast.Tuple):
        return ast.parse("tuple[t.Any, ...]", mode="eval").body
    return ast.parse("t.Any", mode="eval").body


def declaration(nodes: list[ast.stmt], in_class: bool = False) -> list[ast.stmt]:
    result: list[ast.stmt] = []
    overloaded = {n.name for n in nodes if isinstance(n, ast.FunctionDef)
                  and any(ast.unparse(d).endswith("overload") for d in n.decorator_list)}
    existing = {n.target.id for n in nodes if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    for original in nodes:
        node = copy.deepcopy(original)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            result.append(node)
        elif isinstance(node, ast.If):
            if ast.unparse(node.test) in ("t.TYPE_CHECKING", "typing.TYPE_CHECKING", "TYPE_CHECKING"):
                result.extend(declaration(node.body, in_class))
        elif isinstance(node, ast.ClassDef):
            node.body = declaration(node.body, True) or [ast.Expr(value=ast.Constant(value=Ellipsis))]
            result.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_overload = any(ast.unparse(d).endswith("overload") for d in node.decorator_list)
            if node.name in overloaded and not is_overload:
                continue
            if in_class and node.name == "__init__":
                for attribute in ast.walk(node):
                    if isinstance(attribute, ast.AnnAssign) and isinstance(attribute.target, ast.Attribute):
                        target = attribute.target
                        if isinstance(target.value, ast.Name) and target.value.id == "self" and target.attr not in existing:
                            existing.add(target.attr)
                            result.append(ast.AnnAssign(target=ast.Name(id=target.attr, ctx=ast.Store()),
                                                        annotation=attribute.annotation, value=None, simple=1))
            node.body = [ast.Expr(value=ast.Constant(value=Ellipsis))]
            result.append(node)
        elif isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name):
                continue
            if not ast.unparse(node.annotation).endswith("TypeAlias"):
                node.value = None
            result.append(node)
        elif isinstance(node, ast.Assign):
            if not all(isinstance(t, ast.Name) for t in node.targets):
                continue
            value_text = ast.unparse(node.value)
            is_type = (isinstance(node.value, (ast.Subscript, ast.BinOp, ast.Name)) or
                       isinstance(node.value, ast.Call) and ast.unparse(node.value.func).endswith(("TypeVar", "ParamSpec", "NamedTuple")))
            if is_type or any(t.id == "__all__" for t in node.targets):
                result.append(node)
            else:
                for target in node.targets:
                    if in_class and value_text.startswith("enum.auto("):
                        result.append(ast.Assign(targets=[target], value=ast.Constant(value=Ellipsis)))
                    else:
                        result.append(ast.AnnAssign(target=target, annotation=annotation(node.value), value=None, simple=1))
    return result


def generate(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for file in sorted((source / "src/click").glob("*.py")):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        body = declaration(tree.body)
        # A few inferred declarations use Any even in modules without typing.
        has_t = any(isinstance(n, ast.Import) and any(a.name == "typing" and a.asname == "t" for a in n.names) for n in body)
        if not has_t:
            index = 1 if body and isinstance(body[0], ast.ImportFrom) and body[0].module == "__future__" else 0
            body.insert(index, ast.Import(names=[ast.alias(name="typing", asname="t")]))
        index = 1 if body and isinstance(body[0], ast.ImportFrom) and body[0].module == "__future__" else 0
        body.insert(index, ast.Import(names=[ast.alias(name="builtins")]))
        text = ast.unparse(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])))
        # Public attributes called ``type`` must not shadow the annotation's
        # builtin after instance annotations are moved into the class body.
        text = re.sub(r"(?<![\w.])type\[", "builtins.type[", text)
        header = "# Type declarations for Click 8.5.1, extracted without implementation bodies.\n"
        (destination / file.with_suffix(".pyi").name).write_text(header + text + "\n", encoding="utf-8")
    (ROOT / "compatibility/CLICK_LICENSE.txt").write_text((source / "LICENSE.txt").read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=ROOT / "python/zclick")
    args = parser.parse_args()
    generate(args.source, args.destination)
