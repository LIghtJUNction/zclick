"""Install and execute one built wheel outside its source checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


PROGRAM = r'''
import importlib.metadata
import json
import platform
import sys
import zclick as click
from zclick import _native
from zclick.testing import CliRunner

assert _native.ZCLAP_VERSION == "0.1.4"
assert _native.parse([(0, ["--number"], 1, False)], ["--number", "-23"])[0] == {0: [("-23",)]}
assert _native.wrap_text("one two three", 7) == "one two\nthree"

@click.group()
def cli():
    pass

@cli.command()
@click.option("--number", type=int)
def echo(number):
    click.echo(f"值: {number}")
    return number

number = 2 ** 130
result = CliRunner().invoke(cli, ["echo", "--number", str(number)], standalone_mode=False)
assert result.exit_code == 0, result.exception
assert result.return_value == number
assert result.output == f"值: {number}\n"
assert CliRunner().invoke(cli, ["--help"]).exit_code == 0
print(json.dumps({"passed": True, "version": importlib.metadata.version("zclick"),
    "python": sys.version, "platform": platform.platform(), "native": _native.__file__,
    "zclap": _native.ZCLAP_VERSION}))
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("dist"))
    parser.add_argument("--output", type=Path, default=Path("reports/wheel-smoke.json"))
    args = parser.parse_args()
    wheels = list(args.directory.resolve().glob("*.whl"))
    if len(wheels) != 1:
        parser.error(f"Expected exactly one wheel, found {len(wheels)}")
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index",
                    "--force-reinstall", str(wheels[0])], check=True)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory() as directory:
        result = subprocess.check_output([sys.executable, "-I", "-c", PROGRAM], cwd=directory,
                                         env=environment, text=True, encoding="utf-8")
    report = json.loads(result)
    report["wheel"] = wheels[0].name
    report["wheel_sha256"] = hashlib.sha256(wheels[0].read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
