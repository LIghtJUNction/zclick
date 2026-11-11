"""Inspect a wheel for namespace isolation, dependency, native and typing metadata."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import zipfile


def check(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if any(n.startswith("click/") or n == "click.py" for n in names):
            raise ValueError(f"{path.name} installs the original Click namespace")
        if "zclick/py.typed" not in names or not any(n.endswith(".pyi") for n in names):
            raise ValueError(f"{path.name} is missing typing artifacts")
        if not any(n.startswith("zclick/_native") and n.endswith((".so", ".pyd")) for n in names):
            raise ValueError(f"{path.name} is missing the native extension")
        meta_names = [n for n in names if n.endswith(".dist-info/METADATA")]
        if len(meta_names) != 1:
            raise ValueError("Wheel must contain exactly one distribution metadata file")
        metadata = BytesParser().parsebytes(archive.read(meta_names[0]))
        if metadata["Name"] != "zclick":
            raise ValueError(f"Unexpected distribution name {metadata['Name']}")
        requirements = metadata.get_all("Requires-Dist", [])
        runtime = [r for r in requirements if "extra ==" not in r and "extra==" not in r]
        if runtime:
            raise ValueError(f"Unexpected Python runtime requirements: {runtime}")
        declared_licenses = set(metadata.get_all("License-File", []))
        required_licenses = {"LICENSE", "THIRD_PARTY_LICENSES.md", "compatibility/CLICK_LICENSE.txt", "licenses/manifest.json"}
        if not required_licenses <= declared_licenses:
            raise ValueError(f"Missing license metadata: {sorted(required_licenses - declared_licenses)}")
        license_prefix = meta_names[0].removesuffix("METADATA") + "licenses/"
        for name in declared_licenses:
            if license_prefix + name not in names:
                raise ValueError(f"Declared license file is absent: {name}")
        inventory = json.loads(archive.read(license_prefix + "licenses/manifest.json"))
        notices = [item for package in inventory["packages"] for item in package["files"]]
        notices += inventory["rust_standard_library"]["files"]
        for notice in notices:
            name = notice["path"]
            if name not in declared_licenses:
                raise ValueError(f"License inventory entry is not included in metadata: {name}")
            if hashlib.sha256(archive.read(license_prefix + name)).hexdigest() != notice["sha256"]:
                raise ValueError(f"License content checksum mismatch: {name}")
    print(f"Wheel namespace, native module, runtime dependencies, typing and {len(notices)} third-party notices passed: {path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheels", nargs="+", type=Path)
    for wheel in parser.parse_args().wheels:
        check(wheel)
