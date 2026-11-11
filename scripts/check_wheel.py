"""Inspect a wheel for namespace isolation, dependency, native and typing metadata."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
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
    print(f"Wheel namespace, native module, runtime dependencies and typing passed: {path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheels", nargs="+", type=Path)
    for wheel in parser.parse_args().wheels:
        check(wheel)
