"""Standard-library-only provenance for isolated benchmark interpreters."""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
import time


def fingerprints(package_path: Path) -> dict[str, str]:
    return {
        path.relative_to(package_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(package_path.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
        and (path.suffix in (".py", ".so", ".pyd", ".dll") or ".so." in path.name)
    }


def package_record(package: str) -> dict:
    module = importlib.import_module(package)
    path = Path(module.__file__).resolve().parent
    files = fingerprints(path)
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"package": package, "version": importlib.metadata.version(package),
            "package_path": str(path), "source_files": files, "content_sha256": digest}


def affinity() -> list[int] | None:
    if hasattr(os, "sched_getaffinity"):
        return sorted(os.sched_getaffinity(0))
    return None


def cpu_model() -> list[str]:
    path = Path("/proc/cpuinfo")
    if path.is_file():
        values = {line.split(":", 1)[1].strip() for line in path.read_text().splitlines()
                  if line.split(":", 1)[0].strip() in ("model name", "Hardware")}
        if values:
            return sorted(values)
    if sys.platform == "darwin":
        try:
            return [subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()]
        except (OSError, subprocess.CalledProcessError):
            pass
    return [platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "unavailable")]


def load_average() -> list[float] | None:
    return list(os.getloadavg()) if hasattr(os, "getloadavg") else None


def runtime_details() -> dict:
    allowed = affinity()
    frequency = {}
    if allowed:
        base = Path(f"/sys/devices/system/cpu/cpu{allowed[0]}/cpufreq")
        for name in ("scaling_governor", "scaling_cur_freq", "scaling_min_freq", "scaling_max_freq"):
            path = base / name
            if path.is_file():
                frequency[name] = path.read_text().strip()
    clock = time.get_clock_info("perf_counter")
    return {"python": sys.version, "executable": sys.executable,
            "implementation": sys.implementation.name, "cache_tag": sys.implementation.cache_tag,
            "gil_disabled_build": bool(sysconfig.get_config_var("Py_GIL_DISABLED")),
            "platform": platform.platform(), "machine": platform.machine(),
            "cpu_count": os.cpu_count(), "cpu_model": cpu_model(), "affinity": allowed,
            "load_average": load_average(), "frequency_observation_khz": frequency,
            "flags": {name: getattr(sys.flags, name, None) for name in
                      ("isolated", "ignore_environment", "no_user_site", "optimize", "hash_randomization", "safe_path")},
            "clock": {"implementation": clock.implementation, "resolution_seconds": clock.resolution,
                      "monotonic": clock.monotonic, "adjustable": clock.adjustable}}


if __name__ == "__main__":
    if any(package not in ("click", "zclick") for package in sys.argv[1:]):
        raise SystemExit("Only the two locked benchmark packages can be inspected")
    print(json.dumps({"runtime": runtime_details(),
                      "packages": {name: package_record(name) for name in sys.argv[1:]}}))
