"""Install the pinned portable Fish and PowerShell test runtimes on Linux x64."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import tarfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT / ".cache/test-shells")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("The pinned portable Shell archives target Linux x86_64")
    lock = json.loads((ROOT / "compatibility/shell-runtime-lock.json").read_text(encoding="utf-8"))
    directories = []
    for runtime in lock["runtimes"]:
        if "sha256" not in runtime:
            continue
        folder = args.destination.resolve() / runtime["name"]
        folder.mkdir(parents=True, exist_ok=True)
        archive = folder / "runtime.tar"
        with urllib.request.urlopen(runtime["source"]) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != runtime["sha256"]:
            raise SystemExit(f"Checksum mismatch: {runtime['name']}")
        archive.write_bytes(data)
        with tarfile.open(archive) as contents:
            contents.extractall(folder, filter="data")
        archive.unlink()
        binary = folder / runtime["name"]
        if not binary.is_file():
            raise SystemExit(f"Missing executable in verified archive: {binary}")
        binary.chmod(binary.stat().st_mode | 0o111)
        directories.append(str(folder))
        print(f"Installed {runtime['name']} {runtime['version']} at {folder}")
    if github_path := os.environ.get("GITHUB_PATH"):
        with open(github_path, "a", encoding="utf-8") as output:
            output.write("\n".join(directories) + "\n")
    else:
        print("Add to PATH: " + os.pathsep.join(directories))


if __name__ == "__main__":
    main()
