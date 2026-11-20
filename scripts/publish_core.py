#!/usr/bin/env python3
"""Validate and publish the independent Rust core without rebuilding Python wheels."""
import argparse
from pathlib import Path
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def run(*args, capture=False):
    result = subprocess.run(args, cwd=ROOT, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true",
                        help="publish the tested crate and push its immutable source tag")
    args = parser.parse_args()
    package = tomllib.loads((ROOT / "crates/zclick-core/Cargo.toml").read_text())["package"]
    version = tomllib.loads((ROOT / "Cargo.toml").read_text())["workspace"]["package"]["version"]
    if package["name"] != "zclick-core" or package.get("publish") is False:
        parser.error("the public Rust package must be zclick-core")
    if run("git", "status", "--porcelain", capture=True):
        parser.error("commit the candidate before validating its distributable package")
    candidate = run("git", "rev-parse", "HEAD", capture=True)
    tag = "zclick-core-v" + version
    if args.publish:
        remote = run("git", "ls-remote", "--exit-code", "origin",
                     "refs/heads/main", capture=True).split()[0]
        if remote != candidate:
            parser.error("the candidate must equal the published origin/main commit")
        existing = run("git", "ls-remote", "--tags", "origin",
                       "refs/tags/" + tag, capture=True)
        if existing:
            parser.error("the crate source tag already exists; verify the registry before retrying")
    run("cargo", "fmt", "--all", "--", "--check")
    run("cargo", "test", "--locked", "-p", "zclick-core")
    run("cargo", "check", "--locked", "-p", "zclick-core",
        "--target", "wasm32-unknown-unknown")
    run("cargo", "clippy", "--locked", "-p", "zclick-core", "--all-targets",
        "--", "-D", "warnings")
    run("cargo", "package", "--locked", "-p", "zclick-core")
    if args.publish:
        run("cargo", "publish", "--locked", "-p", "zclick-core")
        run("git", "tag", "-a", tag, candidate, "-m", "zclick-core " + version)
        run("git", "push", "origin", "refs/tags/" + tag)
        print("Published zclick-core " + version + " from " + candidate)
    else:
        print("Validated zclick-core " + version + " from " + candidate +
              "; no registry upload or tag was created.")


if __name__ == "__main__":
    main()
