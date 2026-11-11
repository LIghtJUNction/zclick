"""Generate release notes that preserve disclosed compatibility gaps."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from bump_version import parse as parse_version


ROOT = Path(__file__).resolve().parents[1]


def render(version: str, commit: str, repository: str, benchmark: dict | None = None) -> str:
    phase = parse_version(version)[3]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Release notes require an immutable git SHA")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise ValueError("Repository must be owner/name")
    target = json.loads((ROOT / "compatibility/target.json").read_text(encoding="utf-8"))
    gaps = json.loads((ROOT / "compatibility/known-gaps.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "compatibility/test-manifest.json").read_text(encoding="utf-8"))
    unfinished = [gap for gap in gaps["gaps"] if gap["status"] != "RESOLVED"]
    if unfinished and phase is None:
        raise ValueError("Unfinished compatibility requires disclosed prerelease notes")
    base = f"https://github.com/{repository}"
    source = f"{base}/blob/{commit}"
    asset = f"{base}/releases/download/v{version}"
    lines = [f"# zclick {version}", ""]
    if unfinished:
        lines.extend(["**Prerelease. Full Click compatibility is not yet complete.**", "",
                      f"{len(unfinished)} known compatibility item remains unfinished:", ""])
        for gap in unfinished:
            lines.extend([f"### UNFINISHED: {gap['area']}", "", gap["candidate"], "",
                          "Reference behavior: " + gap["reference"], "", gap["reason"], ""])
        lines.append(f"The [complete disclosure]({source}/compatibility/known-gaps.json) and "
                     f"[compatibility report]({source}/COMPATIBILITY.md) record the limits and reproducer.")
        lines.append("")
    lines.extend(["## Validation and scope", "",
        f"The compatibility target is Click **{target['version']}**, source commit `{target['commit']}`. "
        f"Publishing requires evidence accounting for all **{manifest['test_count']:,} fixed upstream case IDs**, "
        "with the original platform skips and expected failures retained, plus API contracts, actual Shell "
        "completion, interpreter safety, dependency checks and executable distribution checks. "
        "These gates do not remove the unfinished item above.", "",
        f"- [Source for this release]({base}/tree/{commit})",
        f"- [API and behavior compatibility]({source}/COMPATIBILITY.md)",
        f"- [Performance results and method]({source}/docs/performance.md)",
        f"- [Build, platform and release details]({source}/docs/development.md)",
        f"- [Migration and third-party extension behavior]({source}/docs/extensions.md)", "",
        "## Evidence assets", "",
        f"[compatibility-evidence.zip]({asset}/compatibility-evidence.zip) contains the complete per-case "
        "reports, API audits, actual Shell results, subinterpreter difference and safe-rejection evidence, "
        "the known gap list, and wheel/source-archive execution checks. Original reference crashes or "
        "platform exclusions remain visible in those records.", "",
        f"[benchmarks.json]({asset}/benchmarks.json) contains raw measurements from this immutable release "
        "commit on a separate CI host. Timing is workload-specific: a ratio above 1 means lower zclick "
        "latency, and a ratio below 1 means a regression at that boundary.", ""])
    if benchmark is not None:
        if (benchmark["git_commit"] != commit
                or benchmark["measurements"]["zclick"]["version"] != version
                or benchmark["target"]["commit"] != target["commit"]):
            raise ValueError("Benchmark evidence does not match this release and target")
        lines.extend(["## Measurements on the release CI host", "",
                      "| Warm Python API workload | Click µs | zclick µs | Ratio |",
                      "| --- | ---: | ---: | ---: |"])
        for name, ratio in benchmark["ratios"].items():
            a = benchmark["measurements"]["click"]["cases"][name]["median_wall_us"]
            b = benchmark["measurements"]["zclick"]["cases"][name]["median_wall_us"]
            lines.append(f"| `{name}` | {a:.3f} | {b:.3f} | {ratio['wall_speedup']:.3f}× |")
        lines.extend(["", "| Fresh process, import, construction and action | Click ms | zclick ms | Ratio |",
                      "| --- | ---: | ---: | ---: |"])
        for name, ratio in benchmark.get("cold_command_ratios", {}).items():
            a = benchmark["measurements"]["click"]["cold_commands"][name]["median_wall_us"]
            b = benchmark["measurements"]["zclick"]["cold_commands"][name]["median_wall_us"]
            lines.append(f"| `{name}` | {a/1000:.3f} | {b/1000:.3f} | {ratio:.3f}× |")
        lines.extend(["", "Packages run in fixed order on a shared host, without CPU affinity or frequency "
                      "locking. Small timing differences are not claimed to be significant. "
                      "Python allocation samples do not measure every Rust allocation.", ""])
    lines.extend(["## Installation and publication", "",
        "Wheel assets are attached for the listed Python/platform combinations, together with a source "
        "archive. GitHub artifact publication and PyPI publication are separate jobs. The existence "
        "of this GitHub release does not by itself establish that the PyPI upload succeeded.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "LIghtJUNction/zclick"))
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    match = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    if match is None:
        parser.error("No project version")
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8")) if args.benchmark else None
    notes = render(match[1], args.ref, args.repository, benchmark)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes, encoding="utf-8")
    print(f"Generated disclosed release notes: {args.output}")


if __name__ == "__main__":
    main()
