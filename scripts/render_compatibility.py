"""Render the public API checklist from the fixed reference and measured results."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render(api_path: Path, normal_path: Path, output: Path) -> None:
    reference = json.loads((ROOT / "compatibility/api-reference.json").read_text())
    audit = json.loads(api_path.read_text()) if api_path.exists() else {"entries": {}, "complete": False}
    normal = json.loads(normal_path.read_text()) if normal_path.exists() else {}
    target = reference["target"]
    lines = [
        "# Click compatibility", "",
        f"The fixed target is **Click {target['version']}**, released {target['released_at']}, "
        f"at commit `{target['commit']}`. The target was verified on {target['verified_at']} "
        "against PyPI and the upstream Git tag.", "",
        "The contract covers public object names, call parameters and defaults, return annotations, "
        "class members, properties, deprecated imports, exception behavior, CLI output and terminal tools. "
        "The generated [API inventory](compatibility/api-reference.json) records each declaration and "
        "associated upstream test source. The `.pyi` declarations describe this same fixed target.", "",
        "## Evidence and scope", "",
        "| Evidence | Result |", "| --- | --- |",
        f"| Public object and member signature audit | {'Passed' if audit['complete'] else 'Incomplete'}; "
        f"{len(reference['entries'])} public objects |",
    ]
    if normal:
        counts = normal["counts"]
        lines.append("| Upstream normal suite on the local interpreter | " +
                     ", ".join(f"{count} {name}" for name, count in counts.items() if count) + " |")
        lines.append(f"| Upstream stress suite | {len(normal.get('deselected', []))} cases tracked separately; "
                     "passing stress reports must cover every case before release |")
    else:
        lines.append("| Upstream suite | Not yet measured |")
    lines.extend([
        "| Cross platform validation | See the [CI runs](https://github.com/LIghtJUNction/zclick/actions/workflows/ci.yml); "
        "a configured runner is not a passing result |", "",
        "The normal run preserves the upstream `not stress` development selection. "
        "The release workflow runs all four original stress functions with their original parameter counts, "
        "then checks the union of test IDs. It rejects failures, collection errors, missing tests and extra skips. "
        "Upstream platform skips and expected failures retain their original conditions; they are reported separately.", "",
        "Tests are copied only into `.cache/click-migrated`, outside the runtime package. "
        "The migration changes package imports, module references, monkeypatch import paths, subprocess imports, "
        "distribution metadata lookup and four module-qualified object repr patterns. "
        "The complete edit log is `.cache/click-migrated/namespace-migration.json`. "
        "Assertions, argument values, expected behavior and skip markers remain intact.", "",
        "## Behavior checklist", "",
        "Each row names the original tests that verify its observable behavior. The API inventory below "
        "adds the exact call and member contract for every public object.", "",
        "| Area | Covered behavior | Upstream test sources |",
        "| --- | --- | --- |",
        "| Command construction | Decorators, arbitrary classes, subclass overrides, direct invocation | `test_command_decorators.py`, `test_custom_classes.py`, `test_commands.py` |",
        "| Command groups | Nested and chained groups, invocation without subcommand, result callbacks, dynamic and lazy lookup | `test_commands.py`, `test_chain.py`, `test_custom_classes.py` |",
        "| Context | Parent propagation, objects, metadata, resources, invoke/forward, resilient parsing | `test_context.py`, `test_commands.py` |",
        "| Options | Aliases, prefixes, clusters, attached values, optional values, count, dual flags, multiple/nargs, shared flag destinations | `test_options.py`, `test_parser.py` |",
        "| Arguments | Fixed and variadic arity, negative tokens, `--`, positional allocation, missing and extra arguments | `test_arguments.py`, `test_parser.py` |",
        "| Defaults and sources | Callable defaults, default maps, environment variables, automatic prefixes, prompts and ParameterSource | `test_defaults.py`, `test_options.py`, `test_context.py` |",
        "| Conversion | Unbounded Python integers, floats, ranges, enum choices, tuples, UUID, dates, paths, files, custom types | `test_types/`, `test_basic.py` |",
        "| Control flow | Eager options, callbacks, abort, EOF, KeyboardInterrupt, usage exceptions, standalone/nonstandalone exits | `test_abort_interrupt.py`, `test_basic.py`, `test_exceptions/` |",
        "| Help | Usage/metavars, command/option ordering, defaults/envvars, hidden/deprecated items, ANSI wrapping and widths | `test_formatting.py`, `test_options.py`, `test_commands.py` |",
        "| Terminal tools | Echo, styles, prompting, progress bars, pager lifecycle, editor, launcher, streams and file helpers | `test_termui.py`, `test_utils/`, `test_compat.py` |",
        "| Completion | Bash, Zsh, Fish, PowerShell, custom classes, protocol output, context resolution without command callbacks | `test_shell_completion.py` |",
        "| Testing tools | Result output streams, simulated input, isolated environment/filesystem, exceptions and return values | `test_testing.py`, `test_stream_lifecycle.py` |",
        "| Deprecations | Available deprecated names, warning categories and triggering attribute access | `test_deprecations.py` |",
        "| Typing | Decorator inference, prompts, generic types, paths, callbacks and callable return values | `tests/typing/` (12 files) |",
        "| Resource stress | 10,000 thread-pool, 10,000 logging, 10,000 GC, 1,000 pager cleanup cases | `test_stream_lifecycle.py`, `test_utils/test_echo_via_pager.py` |", "",
        "## Migration and dynamic behavior", "",
        "Use `import zclick as click` and replace `from click.module` with `from zclick.module`. "
        "The distribution installs only the `zclick` namespace and never rewrites `sys.modules['click']`. "
        "An extension that internally imports original Click still uses original Click: module aliasing "
        "does not merge class identities across packages. Such extensions need their own import migration and tests.", "",
        "Command callbacks, parameter objects and type converters remain Python extension points. "
        "Invocation observes changes to `command.params`, registered commands, callbacks and option attributes. "
        "Per-invocation defaults, environment values and context state are not cached. "
        "The native parser receives the current definition and does not retain borrowed schema references.", "",
        "`CliRunner` temporarily changes interpreter-wide streams, environment and working directory, "
        "matching Click's isolation model. Concurrent runner invocations in the same process are not a supported "
        "thread-safe isolation boundary. Native parsing state is per call; this does not make the testing tools thread-safe.", "",
        "## zclap adaptation", "",
        "| zclap contract | Click requirement | Adaptation |",
        "| --- | --- | --- |",
        "| Runtime definitions are borrowed | Python can create and mutate parameter tables | Build owned call-local storage and borrow it while parsing; no leaked strings or fake static lifetimes |",
        "| Option names and values have kernel conventions | Multiple prefixes, aliases, combined shorts, negative and dash-prefixed values | Translate current option spellings and use zclap event parsing for recognition; retain original values and error spelling |",
        "| Parent/child parsing scope and final validation differ | Click controls interspersed arguments, chain groups and deferred validation | A Rust semantic layer controls boundaries and event sequencing around zclap |",
        "| Kernel help output has its own layout | Exact Click help and terminal formatting | Rust wrapping/ANSI primitives feed the Click-compatible formatter |",
        "| Kernel arity rules are lower-level | Variadics, optional values, callbacks and source precedence | Rust semantic operations and Python extension hooks preserve target ordering |", "",
        "The core directly depends only on registry `zclap = 0.1.4` and builds with `no_std + alloc`. "
        "The Python extension also depends on PyO3, uses std, creates Python objects and allocates memory. "
        "The published Python package has no third-party Python runtime requirements. "
        "Click, pytest, Maturin and type-checking tools are development dependencies.", "",
        "## Public API checklist", "",
        "`Contract passed` means availability, positional/keyword parameters and defaults, member availability, "
        "member signatures, property mutability and deprecation categories passed introspection. "
        "Observable behavior is measured by the associated tests and platform runs above.", "",
        "| Public object | Declaration source | Contract | Behavior test sources |",
        "| --- | --- | --- | --- |",
    ])
    for name, expected in reference["entries"].items():
        actual = audit["entries"].get(name, {})
        passed = (actual.get("available") and actual.get("parameter_contract_matches", True)
                  and actual.get("deprecation_categories_match") and not actual.get("missing_members")
                  and not actual.get("member_contract_mismatches"))
        tests = ", ".join(f"`{Path(t).name}`" for t in expected["test_sources"][:4]) or "Inventory contract; see related public class tests"
        if len(expected["test_sources"]) > 4:
            tests += f"; +{len(expected['test_sources']) - 4} in JSON"
        lines.append(f"| `{name}` | {', '.join(expected['sources'])} | {'Contract passed' if passed else 'Incomplete'} | {tests} |")
    lines.extend(["", "## Reproduction", "", "```sh",
                  "python -m pip install -r requirements-dev.txt",
                  "maturin build --release --locked --out dist",
                  "python -m pip install --no-deps --force-reinstall dist/*.whl",
                  "python scripts/run_compatibility.py",
                  "python scripts/api_inventory.py --compare compatibility/api-reference.json --output reports/api.json",
                  "python -m mypy .cache/click-migrated/tests/typing --no-incremental",
                  "python benchmarks/compare.py", "```", ""])
    output.write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", type=Path, default=ROOT / "reports/api.json")
    parser.add_argument("--normal", type=Path, default=ROOT / "reports/compatibility-normal/summary.json")
    parser.add_argument("--output", type=Path, default=ROOT / "COMPATIBILITY.md")
    args = parser.parse_args()
    render(args.api, args.normal, args.output)
