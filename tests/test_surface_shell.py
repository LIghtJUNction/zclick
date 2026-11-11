"""Execute generated completion source through supported installed shells."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import zclick
from zclick.shell_completion import BashComplete


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
