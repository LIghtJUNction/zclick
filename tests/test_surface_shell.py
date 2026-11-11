"""Execute generated completion source through supported installed shells."""
from __future__ import annotations

import os
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import zclick
from zclick.shell_completion import BashComplete, CompletionItem, FishComplete, PowerShellComplete, ShellComplete, ZshComplete


def _completion_cli(tmp_path: Path, directory_only: bool = False) -> tuple[dict[str, str], Path]:
    marker = tmp_path / "callback-ran"
    app = tmp_path / "surface_cli_app.py"
    app.write_text(
        "import zclick\n"
        "from pathlib import Path\n"
        "@zclick.command()\n"
        "@zclick.option('--choice', type=zclick.Choice(['alpha', 'alpine', 'beta']))\n"
        f"@zclick.option('--file', type=zclick.Path(file_okay={not directory_only!r}))\n"
        "def main(choice, file):\n"
        f"    Path({str(marker)!r}).write_text('unexpected')\n"
        "main(prog_name='surface-cli')\n"
    )
    if os.name == "nt":
        (tmp_path / "surface-cli.cmd").write_text(f'@"{sys.executable}" "{app}" %*\n')
    else:
        command = tmp_path / "surface-cli"
        command.write_text(f'#!{sys.executable}\nexec(compile(open({str(app)!r}, encoding="utf-8").read(), {str(app)!r}, "exec"))\n')
        command.chmod(0o755)
    return {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"}, marker


@pytest.mark.parametrize("argument", [False, True])
def test_chained_command_names_do_not_filter_parameter_choices(argument: bool) -> None:
    """A completed command name can also be a legitimate option/argument value."""
    choices = zclick.Choice(["set", "other"])
    parameter = zclick.Argument(["value"], type=choices) if argument else zclick.Option(["-c"], type=choices)
    group = zclick.Group("cli", chain=True, commands=[zclick.Command("set", params=[parameter])])
    completion = ShellComplete(group, {}, "cli", "_CLI_COMPLETE")
    args = ["set"] if argument else ["set", "-c"]
    assert [item.value for item in completion.get_completions(args, "")] == ["set", "other"]


def test_chained_command_does_not_filter_custom_completion_override() -> None:
    class Custom(zclick.Command):
        def shell_complete(self, ctx, incomplete):
            return [CompletionItem("set", help="A value supplied by the application")]

    group = zclick.Group("cli", chain=True, commands=[Custom("set")])
    completion = ShellComplete(group, {}, "cli", "_CLI_COMPLETE")
    assert [item.value for item in completion.get_completions(["set"], "")] == ["set"]


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="Requires a POSIX Bash executable")
def test_bash_completion_preserves_file_names_with_spaces(tmp_path: Path) -> None:
    """Shell arrays retain each filesystem completion as one candidate."""
    script = tmp_path / "surface-cli"
    callback_marker = tmp_path / "callback-ran"
    script.write_text(
        f"#!{sys.executable}\n"
        "import zclick\n"
        "from pathlib import Path\n"
        "@zclick.command()\n"
        "@zclick.option('--file', type=zclick.Path())\n"
        "def main(file):\n"
        f"    Path({str(callback_marker)!r}).write_text('unexpected')\n"
        "main()\n"
    )
    script.chmod(0o755)
    (tmp_path / "a file.txt").touch()
    (tmp_path / "another file.txt").touch()
    completion = BashComplete(zclick.Command("surface-cli"), {}, "surface-cli", "_SURFACE_CLI_COMPLETE")
    if not completion._check_version():
        pytest.skip("Click's Bash completion protocol requires Bash 4.4 or newer")
    program = completion.source() + "\n".join(
        (
            # compopt is only enabled by readline during real tab completion.
            # The completion function and compgen run in the actual shell.
            "compopt() { test \"$*\" = '-o filenames'; }",
            "COMP_WORDS=(surface-cli --file a)",
            "COMP_CWORD=2",
            "_surface_cli_completion",
            "printf '%s\\0' \"${COMPREPLY[@]}\"",
        )
    )
    result = subprocess.run(
        [shutil.which("bash"), "--noprofile", "--norc", "-c", program],
        cwd=tmp_path,
        env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        check=True,
    )
    assert sorted(result.stdout.split(b"\0")[:-1]) == [b"a file.txt", b"another file.txt"]
    assert not callback_marker.exists()
    assert not result.stderr


@pytest.mark.skipif(shutil.which("zsh") is None or os.name == "nt", reason="Requires a POSIX Zsh executable")
def test_zsh_source_runs_completion_function(tmp_path: Path) -> None:
    environment, marker = _completion_cli(tmp_path)
    completion = ZshComplete(zclick.Command("surface-cli"), {}, "surface-cli", "_SURFACE_CLI_COMPLETE")
    # Widget hooks need an interactive ZLE session; capture their arguments while
    # executing the generated function, process invocation and parsing in Zsh.
    program = "compdef() { :; }\ncompadd() { shift; print -r -- \"$@\"; }\n" + completion.source()
    program += "\nwords=(surface-cli --choice al)\nCURRENT=3\n_surface_cli_completion\ntrue\n"
    result = subprocess.run([shutil.which("zsh"), "-f", "-c", program], cwd=tmp_path, env=environment, capture_output=True, text=True, check=True)
    assert result.stdout.splitlines() == ["alpha", "alpine"]
    assert not result.stderr
    assert not marker.exists()


@pytest.mark.skipif(shutil.which("fish") is None or os.name == "nt", reason="Requires a POSIX Fish executable")
def test_fish_completion_engine_executes_generated_source(tmp_path: Path) -> None:
    environment, marker = _completion_cli(tmp_path)
    completion = FishComplete(zclick.Command("surface-cli"), {}, "surface-cli", "_SURFACE_CLI_COMPLETE")
    program = completion.source() + "\ncomplete -C 'surface-cli --choice al'\n"
    result = subprocess.run([shutil.which("fish"), "--no-config", "-c", program], cwd=tmp_path, env=environment, capture_output=True, text=True, check=True)
    assert result.stdout.splitlines() == ["alpha", "alpine"]
    assert not result.stderr
    assert not marker.exists()


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="Requires PowerShell Core")
def test_powershell_completion_engine_executes_generated_source(tmp_path: Path) -> None:
    environment, marker = _completion_cli(tmp_path)
    completion = PowerShellComplete(zclick.Command("surface-cli"), {}, "surface-cli", "_SURFACE_CLI_COMPLETE")
    program = completion.source() + "\n".join((
        "$line = 'surface-cli --choice al'",
        "$matches = [System.Management.Automation.CommandCompletion]::CompleteInput($line, $line.Length, $null).CompletionMatches",
        "ConvertTo-Json -Compress -InputObject @($matches | ForEach-Object { $_.CompletionText })",
    ))
    result = subprocess.run([shutil.which("pwsh"), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", program], cwd=tmp_path, env=environment, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == ["alpha", "alpine"]
    assert not result.stderr
    assert not marker.exists()


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="Requires PowerShell Core")
@pytest.mark.parametrize("directory_only", [False, True])
def test_powershell_file_and_directory_directives(tmp_path: Path, directory_only: bool) -> None:
    environment, marker = _completion_cli(tmp_path, directory_only=directory_only)
    folder = tmp_path / "a directory"
    folder.mkdir()
    file = tmp_path / "a file.txt"
    file.touch()
    completion = PowerShellComplete(zclick.Command("surface-cli"), {}, "surface-cli", "_SURFACE_CLI_COMPLETE")
    program = completion.source() + "\n".join((
        "$line = 'surface-cli --file a'",
        "$matches = [System.Management.Automation.CommandCompletion]::CompleteInput($line, $line.Length, $null).CompletionMatches",
        "ConvertTo-Json -Compress -InputObject @($matches | ForEach-Object { $_.CompletionText })",
    ))
    result = subprocess.run([shutil.which("pwsh"), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", program], cwd=tmp_path, env=environment, capture_output=True, text=True, check=True)
    expected = [str(folder)] if directory_only else [str(folder), str(file)]
    assert json.loads(result.stdout) == expected
    assert not result.stderr
    assert not marker.exists()
