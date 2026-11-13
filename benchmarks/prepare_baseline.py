"""Create a content-addressed environment from the published baseline wheels.

This development tool never modifies the active candidate environment. Wheel
checksums and the installed runtime files are verified again on every reuse.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
from email.parser import BytesParser

ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).with_name("environment.py")


def published_lock(path: Path | None = None) -> tuple[dict, dict]:
    """Read the selected release lock without changing the Click target."""
    path = (path or ROOT / "benchmarks/baseline-lock.json").resolve()
    raw = path.read_bytes()
    lock = json.loads(raw)
    target = json.loads((ROOT / "compatibility/target.json").read_text(encoding="utf-8"))
    reference = lock["packages"]["click"]
    if (reference["version"] != target["version"]
            or reference["source_commit"] != target["commit"]
            or reference["wheels"] != {
                f"click-{target['version']}-py3-none-any.whl": target["wheel_sha256"]}):
        raise RuntimeError("Baseline lock does not match the pinned Click version, source commit and wheel")
    return lock, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def python_in(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def probe(python: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="zclick-baseline-probe-") as cwd:
        return json.loads(subprocess.check_output(
            [str(python), "-I", str(PROBE), "click", "zclick"], cwd=cwd, text=True, encoding="utf-8"))


def verify_snapshot(manifest: dict) -> dict:
    for package, artifact in manifest["artifacts"].items():
        if hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest() != artifact["sha256"]:
            raise RuntimeError("Baseline wheel changed: " + artifact["path"])
        with zipfile.ZipFile(artifact["path"]) as archive:
            prefix = package + "/"
            wheel_files = {name[len(prefix):]: hashlib.sha256(archive.read(name)).hexdigest()
                           for name in archive.namelist() if name.startswith(prefix)
                           and not name.endswith("/") and "__pycache__" not in name.split("/")
                           and (Path(name).suffix in (".py", ".so", ".pyd", ".dll") or ".so." in Path(name).name)}
        if wheel_files != manifest["packages"][package]["source_files"]:
            raise RuntimeError(f"{package} installed-file manifest differs from its wheel")
    actual = probe(Path(manifest["python"]))
    for package, expected in manifest["packages"].items():
        observed = actual["packages"][package]
        if observed != expected:
            raise RuntimeError(f"Immutable {package} baseline changed or imported from another path")
    for field in ("python", "implementation", "cache_tag", "gil_disabled_build", "machine"):
        if actual["runtime"][field] != manifest["runtime"][field]:
            raise RuntimeError(f"Baseline interpreter changed: {field}")
    return actual


def verify_published_snapshot(manifest: dict, lock_path: Path | None = None) -> dict:
    lock, identity = published_lock(lock_path)
    if ("baseline_lock" in manifest
            and manifest["baseline_lock"]["sha256"] != identity["sha256"]):
        raise RuntimeError("Baseline snapshot uses a different published wheel lock")
    if manifest.get("published_source_commit") != lock["published_source_commit"]:
        raise RuntimeError("Baseline snapshot uses a different published source commit")
    for package, expected in lock["packages"].items():
        artifact = manifest["artifacts"][package]
        if (expected["wheels"].get(artifact["filename"]) != artifact["sha256"]
                or manifest["packages"][package]["version"] != expected["version"]):
            raise RuntimeError("Baseline snapshot differs from the published wheel lock")
    return verify_snapshot(manifest)


def prepare(cache: Path, wheel: Path | None = None, click_wheel: Path | None = None,
            *, lock_path: Path | None = None) -> dict:
    lock, lock_identity = published_lock(lock_path)
    cache = cache.resolve()
    downloads = cache / "artifacts"
    downloads.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for package, supplied in (("click", click_wheel), ("zclick", wheel)):
        fixed = lock["packages"][package]
        selection = None
        if supplied is None:
            selection = tempfile.TemporaryDirectory(prefix="wheel-selection-", dir=cache)
            subprocess.run([sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
                            "--no-deps", "--only-binary=:all:", "--index-url", "https://pypi.org/simple",
                            "--dest", selection.name, package + "==" + fixed["version"]], check=True)
            compatible = [p for p in Path(selection.name).glob(package + "-" + fixed["version"] + "-*.whl")
                          if p.name in fixed["wheels"]]
            if len(compatible) != 1:
                raise RuntimeError(f"Expected one downloaded {package} wheel, found {len(compatible)}")
            supplied = compatible[0]
        supplied = supplied.resolve()
        expected = fixed["wheels"].get(supplied.name)
        if expected is None or hashlib.sha256(supplied.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Wheel does not match the published baseline lock: {supplied}")
        target = downloads / supplied.name
        if target != supplied:
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise RuntimeError(f"Existing baseline artifact was modified: {target}")
            if not target.exists():
                shutil.copyfile(supplied, target)
        artifacts[package] = {"path": str(target), "filename": target.name, "sha256": expected,
                              "version": fixed["version"]}
        if selection is not None:
            selection.cleanup()
    identity = {"artifacts": artifacts, "python": sys.version, "executable": str(Path(sys.executable).resolve()),
                "baseline_lock_sha256": lock_identity["sha256"]}
    suffix = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    directory = cache / (lock["packages"]["zclick"]["version"] + "-" + suffix)
    manifest_path = directory / "snapshot.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        verify_published_snapshot(manifest, lock_path)
        return manifest
    if directory.exists():
        raise RuntimeError(f"Incomplete baseline directory exists; inspect it before retrying: {directory}")
    subprocess.run([sys.executable, "-m", "venv", str(directory / "venv")], check=True)
    python = python_in(directory / "venv")
    subprocess.run([str(python), "-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-index",
                    "--no-deps", artifacts["click"]["path"], artifacts["zclick"]["path"]], check=True)
    measured = probe(python)
    for package in ("click", "zclick"):
        record = measured["packages"][package]
        if record["version"] != lock["packages"][package]["version"]:
            raise RuntimeError("Installed baseline version differs from the lock")
        Path(record["package_path"]).relative_to(directory)
        # Do not chmod interpreter symlinks or files outside this new environment.
        for relative in record["source_files"]:
            path = Path(record["package_path"]) / relative
            if path.is_symlink():
                raise RuntimeError("Baseline runtime file unexpectedly uses a symlink")
            path.chmod(path.stat().st_mode & ~0o222)
    manifest = {"schema": 1, "purpose": "immutable-published-performance-baseline",
                "published_source_commit": lock["published_source_commit"],
                "baseline_lock": lock_identity,
                "python": str(python), "snapshot_path": str(manifest_path),
                "artifacts": artifacts, "runtime": measured["runtime"], "packages": measured["packages"],
                "integrity": "Runtime files are read-only and content hashes are checked before and after measurement."}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_path.chmod(manifest_path.stat().st_mode & ~0o222)
    verify_published_snapshot(manifest, lock_path)
    return manifest


def prepare_candidate(wheel: Path, cache: Path, baseline: dict) -> dict:
    """Install a candidate wheel into the same minimal environment layout."""
    wheel = wheel.resolve()
    raw = wheel.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(wheel) as archive:
        metadata = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise RuntimeError("Candidate wheel must contain one distribution")
        distribution = BytesParser().parsebytes(archive.read(metadata[0]))
        if distribution["Name"] != "zclick":
            raise RuntimeError("Candidate wheel is not the zclick distribution")
        version = distribution["Version"]
    cache = cache.resolve()
    key = hashlib.sha256((digest + "\n" + sys.version).encode()).hexdigest()[:16]
    directory = cache / ("candidate-" + key)
    manifest_path = directory / "snapshot.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        verify_snapshot(manifest)
        return manifest
    if directory.exists():
        raise RuntimeError(f"Incomplete candidate environment exists: {directory}")
    directory.mkdir(parents=True)
    frozen_wheel = directory / wheel.name
    frozen_wheel.write_bytes(raw)
    subprocess.run([sys.executable, "-m", "venv", str(directory / "venv")], check=True)
    python = python_in(directory / "venv")
    subprocess.run([str(python), "-I", "-m", "pip", "install", "--disable-pip-version-check", "--no-index",
                    "--no-deps", baseline["artifacts"]["click"]["path"], str(frozen_wheel)], check=True)
    measured = probe(python)
    if measured["packages"]["zclick"]["version"] != version:
        raise RuntimeError("Candidate installed with unexpected distribution version")
    if measured["packages"]["click"]["content_sha256"] != baseline["packages"]["click"]["content_sha256"]:
        raise RuntimeError("Candidate and baseline environments use different Click code")
    for package in measured["packages"].values():
        Path(package["package_path"]).relative_to(directory)
        for relative in package["source_files"]:
            path = Path(package["package_path"]) / relative
            if path.is_symlink():
                raise RuntimeError("Candidate runtime file unexpectedly uses a symlink")
            path.chmod(path.stat().st_mode & ~0o222)
    manifest = {"schema": 1, "purpose": "immutable-candidate-performance-snapshot",
                "python": str(python), "snapshot_path": str(manifest_path),
                "artifacts": {"click": baseline["artifacts"]["click"],
                              "zclick": {"path": str(frozen_wheel), "filename": wheel.name,
                                         "sha256": digest, "version": version}},
                "runtime": measured["runtime"], "packages": measured["packages"],
                "integrity": "Runtime files are read-only and content hashes are checked before and after measurement."}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_path.chmod(manifest_path.stat().st_mode & ~0o222)
    verify_snapshot(manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache/benchmark-baselines")
    parser.add_argument("--zclick-wheel", type=Path, help="Already downloaded published wheel")
    parser.add_argument("--click-wheel", type=Path, help="Already downloaded fixed Click wheel")
    parser.add_argument("--baseline-lock", type=Path,
                        help="Published release wheel lock; defaults to benchmarks/baseline-lock.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/benchmark-baseline.json")
    args = parser.parse_args()
    manifest = prepare(args.cache, args.zclick_wheel, args.click_wheel, lock_path=args.baseline_lock)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Verified immutable baseline:", manifest["snapshot_path"])
    print("Baseline interpreter:", manifest["python"])
