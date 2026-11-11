"""Require real Shell runtimes and record generated-source integration results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TEST = "tests/test_surface_shell.py"
SHELL_TESTS = {
    "bash": ["test_bash_completion_preserves_file_names_with_spaces"],
    "zsh": ["test_zsh_source_runs_completion_function"],
    "fish": ["test_fish_completion_engine_executes_generated_source"],
    "pwsh": ["test_powershell_completion_engine_executes_generated_source", "test_powershell_file_and_directory_directives"],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/shells")
    parser.add_argument("--shell", action="append", choices=tuple(SHELL_TESTS))
    args = parser.parse_args()
    requested = list(dict.fromkeys(args.shell or SHELL_TESTS))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    runtimes = []
    for shell in requested:
        executable = shutil.which(shell)
        if executable is None:
            parser.error(f"Required Shell is unavailable: {shell}; refusing to replace execution with a skipped test")
        command = [executable, "--version"] if shell != "pwsh" else [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "$PSVersionTable.PSVersion.ToString()"]
        version = subprocess.check_output(command, text=True, encoding="utf-8").strip()
        runtimes.append({"name": shell, "executable": executable, "version": version.splitlines()[0]})
    report_file = output / "tests.json"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "scripts"), environment.get("PYTHONPATH")]))
    environment["ZCLICK_COMPAT_REPORT"] = str(report_file)
    selectors = [f"{TEST}::{name}" for shell in requested for name in SHELL_TESTS[shell]]
    selectors += [f"{TEST}::test_chained_command_names_do_not_filter_parameter_choices", f"{TEST}::test_chained_command_does_not_filter_custom_completion_override"]
    run = subprocess.run([sys.executable, "-m", "pytest", "-p", "compat_report_plugin", "-q", "--tb=short", *selectors], cwd=ROOT, env=environment)
    report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.exists() else {"results": {}}
    values = list(report["results"].values())
    successful = bool(values) and run.returncode == 0 and all(value["outcome"] == "passed" for value in values)
    from zclick import shell_completion
    evidence = {
        "schema": 1,
        "scope": "actual-shell-integration",
        "implementation_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "runtimes": runtimes,
        "tests": len(values),
        "passed": successful,
        "test_source_sha256": hashlib.sha256((ROOT / TEST).read_bytes()).hexdigest(),
        "implementation_sha256": hashlib.sha256(Path(shell_completion.__file__).read_bytes()).hexdigest(),
        "report": str(report_file),
        "limits": {
            "bash": "Real generated function and compgen; noninteractive compopt recording hook.",
            "zsh": "Real generated function and child process; noninteractive ZLE recording hooks.",
            "fish": "Real complete -C completion engine.",
            "pwsh": "Real CommandCompletion.CompleteInput completion engine.",
        },
    }
    (output / "summary.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": successful, "tests": len(values), "runtimes": runtimes}, indent=2))
    raise SystemExit(0 if successful else 1)


if __name__ == "__main__":
    main()
