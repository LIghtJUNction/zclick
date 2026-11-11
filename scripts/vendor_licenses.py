"""Collect exact locked-crate notices without changing dependency resolution."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def collect() -> dict[str, bytes]:
    lock_before = (ROOT / "Cargo.lock").read_bytes()
    metadata = json.loads(subprocess.check_output(["cargo", "metadata", "--locked", "--format-version", "1"], cwd=ROOT, text=True))
    if (ROOT / "Cargo.lock").read_bytes() != lock_before:
        raise RuntimeError("Dependency metadata unexpectedly changed Cargo.lock")
    checksums = {}
    for block in lock_before.decode("utf-8").split("[[package]]")[1:]:
        fields = {key: json.loads(value) for key, value in re.findall(r'^(name|version|checksum) = ("[^"\n]*")$', block, re.MULTILINE)}
        if "checksum" in fields:
            checksums[fields["name"], fields["version"]] = fields["checksum"]
    files: dict[str, bytes] = {}
    packages = []
    for package in sorted(metadata["packages"], key=lambda item: (item["name"], item["version"])):
        if package["source"] is None:
            continue
        source = Path(package["manifest_path"]).parent
        notices = []
        for path in sorted(source.rglob("*")):
            if path.is_file() and any(word in path.name.casefold() for word in ("license", "licence", "copying", "notice", "copyright")):
                relative = path.relative_to(source)
                destination = f"licenses/rust/{package['name']}-{package['version']}/{relative.as_posix()}"
                content = path.read_bytes()
                files[destination] = content
                notices.append({"source_path": relative.as_posix(), "path": destination, "sha256": sha256(content)})
        if not notices:
            raise RuntimeError(f"No packaged license notice found for {package['name']} {package['version']}")
        checksum = checksums[package["name"], package["version"]]
        archive = source.parent.parent.parent / "cache" / source.parent.name / f"{package['name']}-{package['version']}.crate"
        if not archive.exists() or sha256(archive.read_bytes()) != checksum:
            raise RuntimeError(f"Registry archive checksum mismatch for {package['name']} {package['version']}")
        packages.append({
            "name": package["name"], "version": package["version"], "license": package["license"],
            "source": package["source"], "registry_archive_sha256": checksum,
            "url": f"https://crates.io/crates/{package['name']}/{package['version']}",
            "files": notices,
        })
    toolchain = dict(line.split(": ", 1) for line in subprocess.check_output(["rustc", "-Vv"], cwd=ROOT, text=True).splitlines() if ": " in line)
    release = toolchain["release"]
    standard_directory = f"licenses/rust-standard-library/{release}"
    sysroot = Path(subprocess.check_output(["rustc", "--print", "sysroot"], cwd=ROOT, text=True).strip())
    standard_notice = sysroot / "share/doc/rust/COPYRIGHT-library.html"
    if not standard_notice.exists():
        raise RuntimeError("The pinned Rust toolchain's COPYRIGHT-library.html is required")
    files[f"{standard_directory}/COPYRIGHT-library.html"] = standard_notice.read_bytes()
    for name in ("LICENSE-MIT", "LICENSE-APACHE", "COPYRIGHT"):
        path = ROOT / standard_directory / name
        if not path.exists():
            raise RuntimeError(f"Fetch the unmodified Rust {release} {name} before regenerating: https://raw.githubusercontent.com/rust-lang/rust/{release}/{name}")
        files[f"{standard_directory}/{name}"] = path.read_bytes()
    standard_files = [{"path": path, "sha256": sha256(content)} for path, content in files.items() if path.startswith(standard_directory)]
    inventory = {
        "schema": 1,
        "cargo_lock_sha256": sha256(lock_before),
        "scope": "All registry crates resolved by locked workspace metadata, including build-only dependencies; complete Rust standard-library notices for the pinned release.",
        "packages": packages,
        "rust_standard_library": {
            "version": release, "source_commit": toolchain["commit-hash"],
            "source": f"https://github.com/rust-lang/rust/tree/{toolchain['commit-hash']}",
            "files": standard_files,
        },
    }
    files["licenses/manifest.json"] = (json.dumps(inventory, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    rows = []
    for package in packages:
        references = ", ".join(f"[{Path(item['source_path']).name}]({item['path']})" for item in package["files"])
        rows.append(f"| [{package['name']} {package['version']}]({package['url']}) | `{package['license']}` | {references} |")
    notice = """# Third-party licenses and notices

zclick's own implementation is licensed under the MIT license in [LICENSE](LICENSE).
The native extension is built from Rust crates whose unmodified license and
copyright notices are included below. Both alternatives of dual-license notices
are retained. SPDX expressions, exact registry versions, archive checksums, and
copied-file checksums are recorded in [licenses/manifest.json](licenses/manifest.json).

## Locked Rust crates

This inventory covers every registry crate resolved by `cargo metadata --locked`,
including host build dependencies and procedural macros. Inclusion of a notice
does not imply that every listed crate contributes executable code to every wheel.
The semantic core directly depends on zclap; the Python binding depends on PyO3.
These native/build dependencies are distinct from Python installation dependencies.

| Package | Upstream SPDX expression | Unmodified notices |
| --- | --- | --- |
""" + "\n".join(rows) + f"""

## Rust standard library {release}

Native wheels can contain statically linked parts of Rust's standard library.
The pinned compiler is built from commit `{toolchain['commit-hash']}`.
The complete [standard-library copyright inventory]({standard_directory}/COPYRIGHT-library.html)
is retained, including its in-tree and third-party notices. The upstream
[MIT license]({standard_directory}/LICENSE-MIT),
[Apache 2.0 license]({standard_directory}/LICENSE-APACHE), and
[copyright overview]({standard_directory}/COPYRIGHT) are also included.
The inventory is deliberately broader than one platform's linked symbol set.

## Click interface declarations and comparison material

The `.pyi` interface declarations are extracted from the fixed Click 8.5.1 public
interface. Their source project's BSD-3-Clause notice is distributed at
[compatibility/CLICK_LICENSE.txt](compatibility/CLICK_LICENSE.txt).
The Python runtime implementation is independent; original Click is not a runtime
dependency and is not embedded as a fallback. Vendored comparison source used by
development tests is excluded from the wheel.

## Python dependency boundary

The default distribution declares zero third-party Python runtime dependencies.
Click, pytest, Hypothesis, Maturin, type-checking tools, and optional extension-test
packages belong to development environments. Optional test extras remain explicitly
marked in distribution metadata and are not installed by `pip install zclick`.

## Maintenance and verification

Run `python scripts/vendor_licenses.py --check` after fetching the pinned Cargo
dependencies. To refresh generated notices, run the script without `--check`.
It uses locked metadata and refuses changes to `Cargo.lock`; it adds no dependency.
When the Rust toolchain changes, fetch the three indicated upstream license files
for that release before regeneration. Wheel verification checks that every notice
recorded in the manifest is present with the same checksum.
"""
    files["THIRD_PARTY_LICENSES.md"] = notice.encode("utf-8")
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = collect()
    differences = []
    for name, content in expected.items():
        path = ROOT / name
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                differences.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    if differences:
        raise SystemExit("License notices need regeneration: " + ", ".join(differences))
    print(f"{'Verified' if args.check else 'Wrote'} {len(expected)} license inventory files; Cargo.lock unchanged")


if __name__ == "__main__":
    main()
