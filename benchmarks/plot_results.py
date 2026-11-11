"""Plot complete warm-workload ratios from two formal benchmark reports.

Documentation tool only. Tested with Matplotlib 3.10.8; Matplotlib is not a
zclick runtime or benchmark-worker dependency. Whiskers show observed paired
round ranges, not confidence intervals. No workload is omitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedFormatter, FixedLocator


def read_report(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("schema") != 2 or report.get("diagnostic"):
        raise ValueError("Only complete, formal schema-2 measurements may be plotted")
    if report["method"]["repeats"] < 12 or report["method"]["partial_block_rounds"]:
        raise ValueError("A formal report must include at least two balanced blocks")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("local", type=Path)
    parser.add_argument("release_ci", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="Output stem; writes SVG and PNG")
    args = parser.parse_args()
    reports = [read_report(args.local), read_report(args.release_ci)]
    version = reports[0]["measurements"]["zclick"]["version"]
    reference = reports[0]["measurements"]["click"]["version"]
    workloads = [f"{kind}/{size}" for kind in ("construct", "parse", "invoke", "help")
                 for size in (1, 10, 100, 1000)] + ["nested-command", "wrap-text"]
    for report in reports:
        if (report["measurements"]["zclick"]["version"] != version
                or report["measurements"]["click"]["version"] != reference
                or set(report["ratios"]) != set(workloads)):
            raise ValueError("Reports must compare the same releases and all 18 workloads")

    labels = {"construct": "Construct", "parse": "Reuse parser", "invoke": "Command.main",
              "help": "Render help", "nested-command": "Nested command", "wrap-text": "Unicode / ANSI wrapping"}
    names = [f"{labels[key.split('/')[0]]}  ·  {int(key.split('/')[1]):,} "
             + ("option" if key.endswith("/1") else "options")
             if "/" in key else labels[key] for key in workloads]
    colors = ["#1a73e8", "#188038"]
    markers = ["o", "D"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "svg.hashsalt": f"zclick-{version}-formal-comparison"})
    fig, ax = plt.subplots(figsize=(12.0, 9.0))
    fig.subplots_adjust(left=0.28, right=0.96, top=0.86, bottom=0.13)
    ranges = [value for report in reports for key in workloads
              for value in report["ratios"][key]["paired_wall_speedups"]]
    low, high = min(0.4, min(ranges) * 0.9), max(10.0, max(ranges) * 1.1)
    ax.axvspan(low, 1, color="#f5f6f8", zorder=0)
    ax.axvline(1, color="#5f6368", linewidth=1.1, zorder=1)
    for group_end in (3.5, 7.5, 11.5, 15.5):
        ax.axhline(group_end, color="#e8eaed", linewidth=0.7, zorder=0)
    for index, (report, color, marker) in enumerate(zip(reports, colors, markers)):
        offset = (-0.14, 0.14)[index]
        runtime = report["python"].split()[0]
        label = ("Local" if index == 0 else "Release CI") + f" · CPython {runtime}"
        for position, key in enumerate(workloads):
            ratio = report["ratios"][key]
            paired = ratio["paired_wall_speedups"]
            y = position + offset
            ax.plot([min(paired), max(paired)], [y, y], color=color, alpha=0.5, linewidth=1.5)
            ax.scatter(ratio["wall_speedup"], y, s=30, marker=marker, color=color,
                       edgecolors="white", linewidths=0.5, zorder=3,
                       label=label if position == 0 else None)
    ax.set_xscale("log")
    ax.set_xlim(low, high)
    ticks = [value for value in (0.25, 0.5, 1, 2, 4, 8, 16) if low <= value <= high]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FixedFormatter([f"{value:g}×" for value in ticks]))
    ax.minorticks_off()
    ax.set_yticks(range(len(workloads)), names)
    ax.set_ylim(len(workloads) - 0.45, -0.65)
    ax.tick_params(axis="y", length=0, pad=13)
    ax.tick_params(axis="x", length=0, pad=8)
    ax.grid(axis="x", color="#e8eaed", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlabel("Click median / zclick median · logarithmic scale · above 1 means lower zclick latency", labelpad=13)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=2, frameon=False, borderaxespad=0)
    fig.text(0.04, 0.965, f"zclick {version} versus Click {reference}", fontsize=21, weight="bold", color="#202124")
    fig.text(0.04, 0.925, "All 18 warm workloads · 12 balanced rounds per host · full Python API boundaries", fontsize=12, color="#5f6368")
    fig.text(0.04, 0.052, "Dots: ratio of medians. Lines: full observed paired-round range, not confidence intervals.", fontsize=9, color="#5f6368")
    fig.text(0.04, 0.027, "Different interpreters, hosts and build environments; compare each host independently. See the report for cold startup and memory.", fontsize=9, color="#5f6368")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    provenance = "\n".join(f"{path.name}: {hashlib.sha256(path.read_bytes()).hexdigest()}"
                           for path in (args.local, args.release_ci))
    svg = args.output.with_name(args.output.name + ".svg")
    png = args.output.with_name(args.output.name + ".png")
    fig.savefig(svg, metadata={"Date": None, "Description": provenance})
    fig.savefig(png, dpi=160, metadata={"Description": provenance})
    plt.close(fig)
    print(svg)
    print(png)


if __name__ == "__main__":
    main()
