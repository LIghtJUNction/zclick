"""Record the subinterpreter compatibility gap and verify safe rejection.

This diagnostic does not turn the difference into a passing compatibility test.
Its exit status verifies rejection safety, while compatibility_passed remains
false until both packages actually support the same interpreter behavior.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

from run_compatibility import implementation_files

ROOT = Path(__file__).resolve().parents[1]

PROGRAM = r'''
import _xxsubinterpreters as interpreters
import json
import sys
try:
    import resource
except ImportError:
    pass
else:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

package, isolated, main_first = sys.argv[1], sys.argv[2] == "1", sys.argv[3] == "1"
command = (
    f"import {package} as click\n"
    "def callback(value): return value + 1\n"
    "cmd = click.Command('probe', callback=callback, params=[click.Option(['--value'], type=int)])\n"
    "assert cmd.main(['--value', '41'], standalone_mode=False) == 42\n"
)
if package == "datetime":
    command = "import datetime\n"
if main_first:
    exec(command, {})
interpreter = interpreters.create(isolated=isolated)
result = {"package": package, "isolated": isolated, "main_first": main_first}
try:
    interpreters.run_string(interpreter, command)
except BaseException as error:
    result.update(subinterpreter_succeeded=False, exception_type=type(error).__name__, error=str(error))
else:
    result["subinterpreter_succeeded"] = True
finally:
    interpreters.destroy(interpreter)
try:
    exec(command, {})
except BaseException as error:
    result.update(main_after_succeeded=False, main_after_error=str(error))
else:
    result["main_after_succeeded"] = True
print(json.dumps(result))
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/subinterpreters")
    args = parser.parse_args()
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        parser.error("This diagnostic uses CPython 3.12's exact _xxsubinterpreters API")
    target = json.loads((ROOT / "compatibility/target.json").read_text(encoding="utf-8"))
    gaps = json.loads((ROOT / "compatibility/known-gaps.json").read_text(encoding="utf-8"))
    unfinished = [gap["id"] for gap in gaps["gaps"] if gap["status"] != "RESOLVED"]
    if importlib.metadata.version("click") != target["version"]:
        parser.error("The reference Click distribution does not match the fixed target")
    source_before = implementation_files()
    cases = []
    for package in ("click", "zclick", "datetime"):
        for isolated in (True, False):
            for main_first in ((False,) if package == "datetime" else (True, False)):
                case = {"package": package, "isolated": isolated, "main_first": main_first}
                try:
                    run = subprocess.run([sys.executable, "-c", PROGRAM, package,
                                          str(int(isolated)), str(int(main_first))],
                                         cwd=ROOT, text=True, encoding="utf-8",
                                         capture_output=True, timeout=30)
                except subprocess.TimeoutExpired as error:
                    case.update(process_succeeded=False, timeout=str(error))
                else:
                    case["returncode"] = run.returncode
                    case["stderr"] = run.stderr
                    try:
                        case.update(json.loads(run.stdout))
                    except (ValueError, TypeError):
                        case["stdout"] = run.stdout
                    case["process_succeeded"] = run.returncode == 0
                cases.append(case)
    reference = [case for case in cases if case["package"] == "click"]
    candidate = [case for case in cases if case["package"] == "zclick"]
    reference_passed = all(case.get("process_succeeded") and case.get("subinterpreter_succeeded")
                           and case.get("main_after_succeeded") for case in reference)
    controls = [case for case in reference if case["main_first"]]
    reference_control_passed = len(controls) == 2 and all(
        case.get("process_succeeded") and case.get("subinterpreter_succeeded")
        and case.get("main_after_succeeded") for case in controls)
    safe_rejection = all(case.get("process_succeeded") and not case.get("subinterpreter_succeeded")
                         and "ImportError" in case.get("error", "")
                         and case.get("main_after_succeeded") for case in candidate)
    compatible = reference_passed and all(case.get("process_succeeded")
                      and case.get("subinterpreter_succeeded")
                      and case.get("main_after_succeeded") for case in candidate)
    source_changed = source_before != implementation_files()
    safe_rejection = safe_rejection and not source_changed
    compatible = compatible and not source_changed
    safety_passed = safe_rejection if "subinterpreters" in unfinished else compatible
    report = {
        "schema": 1, "scope": "subinterpreter-boundary", "target": target,
        "recorded_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
        "implementation_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "reference_passed": reference_passed, "safe_rejection": safe_rejection,
        "reference_control_passed": reference_control_passed,
        "reference_environment_failures": [
            {key: case.get(key) for key in ("isolated", "main_first", "returncode")}
            for case in reference if not case.get("process_succeeded")],
        "reference_scope": "Main-first Click controls establish the compatibility difference. Child-first results and independent datetime-only controls are preserved, including interpreter crashes.",
        "safety_passed": safety_passed, "observable_equivalence": compatible,
        "compatibility_passed": compatible and "subinterpreters" not in unfinished,
        "unfinished": unfinished,
        "source_provenance": {"candidate_files": source_before, "changed_during_run": source_changed},
        "cases": [case for case in cases if case["package"] != "datetime"],
        "stdlib_controls": [case for case in cases if case["package"] == "datetime"],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("reference_passed", "reference_control_passed", "reference_environment_failures", "safe_rejection", "compatibility_passed", "unfinished")}, indent=2))
    raise SystemExit(0 if reference_control_passed and safety_passed else 1)


if __name__ == "__main__":
    main()
