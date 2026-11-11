"""Install verified Zsh source and portable Fish/PowerShell runtimes on Linux x64."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
ZSH_CONFIGURE_FLAGS = ("--with-tcsetpgrp", "--enable-multibyte", "--enable-cflags=-O2 -std=gnu89")


def download(runtime: dict) -> bytes:
    for attempt in range(3):
        try:
            with urllib.request.urlopen(runtime["source"], timeout=60) as response:
                data = response.read()
            break
        except urllib.error.HTTPError as error:
            try:
                if error.code not in (502, 503, 504) or attempt == 2:
                    raise
                retry_after = error.headers.get("Retry-After", "") if error.headers else ""
                if retry_after and (not retry_after.isdigit() or int(retry_after) > 60):
                    raise
                delay = max(2 ** attempt, int(retry_after or "0"))
            finally:
                # HTTPError owns a response stream, including on retry. Relying
                # on destruction raises ResourceWarning on newer interpreters.
                error.close()
            print(f"Temporary HTTP {error.code} for {runtime['name']}; retrying in {delay}s", flush=True)
            time.sleep(delay)
    if hashlib.sha256(data).hexdigest() != runtime["sha256"]:
        raise ValueError(f"Checksum mismatch: {runtime['name']}")
    return data


def build_zsh(data: bytes, runtime: dict, folder: Path, jobs: int) -> Path:
    """Install the executable, dynamic completion modules and autoload functions."""
    log_path = folder / "build.log"
    with tempfile.TemporaryDirectory(prefix="zsh-source-", dir=folder.parent) as temporary:
        with tarfile.open(fileobj=io.BytesIO(data)) as contents:
            contents.extractall(temporary, filter="data")
        source = Path(temporary) / ("zsh-" + runtime["version"])
        if not (source / "configure").is_file():
            raise ValueError("Verified Zsh archive lacks its release configure script")
        environment = os.environ.copy()
        for dependency in runtime.get("build_dependencies", []):
            if dependency.get("format") != "deb":
                raise ValueError("Unsupported Zsh build dependency format")
            archive = Path(temporary) / "development-headers.deb"
            archive.write_bytes(download(dependency))
            headers = Path(temporary) / "development-headers"
            # Extract files only; no package-manager state or maintainer scripts.
            subprocess.run(["dpkg-deb", "-x", str(archive), str(headers)], check=True)
            environment["CPPFLAGS"] = "-I" + str(headers / "usr/include") + " " + environment.get("CPPFLAGS", "")
            environment["LIBS"] = "-l:libtinfo.so.6 " + environment.get("LIBS", "")
        commands = [
            # Zsh 5.9 supports C89; its release configure probes predate the
            # stricter C99 pointer-conversion diagnostics in recent GCC.
            [str(source / "configure"), "--prefix=" + str(folder), *ZSH_CONFIGURE_FLAGS],
            ["make", "-j", str(jobs), "-C", "Src"],
            ["make", "install.bin", "install.modules", "install.fns"],
        ]
        try:
            with log_path.open("w", encoding="utf-8") as log:
                for command in commands:
                    subprocess.run(command, cwd=source, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True)
        except subprocess.CalledProcessError:
            print("Zsh build failed; last log lines:", flush=True)
            print("\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]), flush=True)
            raise
        finally:
            if (source / "config.log").is_file():
                shutil.copyfile(source / "config.log", folder / "configure.log")
    binary = folder / "bin/zsh"
    # Loading these modules catches an executable-only install that cannot run
    # the completion system. The source/build tree is already removed here.
    verify_zsh(binary)
    return binary


def verify_zsh(binary: Path) -> None:
    # Load the autoloaded definition without initializing an interactive user
    # session or asking compaudit questions about the parent working directory.
    subprocess.run([str(binary), "-f", "-c", "zmodload zsh/zle && zmodload zsh/complete && "
                    "autoload -Uz compinit && autoload +X compinit"], check=True)


def install(runtime: dict, destination: Path, jobs: int = 2) -> dict:
    folder = destination.resolve() / runtime["name"]
    folder.mkdir(parents=True, exist_ok=True)
    data = download(runtime)
    if runtime.get("build") == "zsh-source":
        binary = build_zsh(data, runtime, folder, jobs)
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as contents:
            contents.extractall(folder, filter="data")
        binary = folder / runtime["name"]
    if not binary.is_file():
        raise ValueError(f"Missing executable in verified archive: {binary}")
    binary.chmod(binary.stat().st_mode | 0o111)
    print(f"Installed {runtime['name']} {runtime['version']} at {binary}", flush=True)
    return {"name": runtime["name"], "version": runtime["version"], "executable": str(binary),
            "source": runtime["source"], "archive_sha256": runtime["sha256"],
            "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "build": runtime.get("build", "published-binary-archive"),
            "configure_flags": list(ZSH_CONFIGURE_FLAGS) if runtime.get("build") == "zsh-source" else [],
            "build_dependencies": runtime.get("build_dependencies", [])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT / ".cache/test-shells")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/shells/install.json")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("The pinned Shell installer targets Linux x86_64")
    if args.jobs < 1:
        parser.error("Build job count must be positive")
    lock = json.loads((ROOT / "compatibility/shell-runtime-lock.json").read_text(encoding="utf-8"))
    installed = []
    for runtime in lock["runtimes"]:
        if "sha256" not in runtime:
            continue
        installed.append(install(runtime, args.destination, args.jobs))
    directories = [str(Path(runtime["executable"]).parent) for runtime in installed]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema": 1, "scope": "test-shell-installation", "runtimes": installed}, indent=2) + "\n", encoding="utf-8")
    if github_path := os.environ.get("GITHUB_PATH"):
        with open(github_path, "a", encoding="utf-8") as output:
            output.write("\n".join(directories) + "\n")
    else:
        print("Add to PATH: " + os.pathsep.join(directories))


if __name__ == "__main__":
    main()
