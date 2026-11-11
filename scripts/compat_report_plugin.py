"""Pytest result recording without changing collection or outcomes."""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
import re
import sys

_results: dict[str, dict[str, object]] = {}
_collection_errors: list[dict[str, object]] = []
_collected: list[str] = []
_deselected: list[str] = []


def key(nodeid: str) -> str:
    nodeid = "tests/" + nodeid.split("tests/", 1)[-1]
    nodeid = re.sub(r"(?<!\w)zclick(?=[.\]\-])", "click", nodeid)
    if "test_attr_deprecated[" in nodeid and "-__version__-" in nodeid:
        nodeid = nodeid.split("-__version__-", 1)[0] + "-__version__-<distribution-version>]"
    return nodeid


def pytest_collection_finish(session):
    _collected.extend(key(item.nodeid) for item in session.items)


def pytest_deselected(items):
    _deselected.extend(key(item.nodeid) for item in items)


def pytest_collectreport(report):
    if report.failed:
        _collection_errors.append({"nodeid": key(report.nodeid), "error": str(report.longrepr)})


def pytest_runtest_logreport(report):
    item = _results.setdefault(key(report.nodeid), {"outcome": "pending", "duration": 0.0})
    item["duration"] += report.duration
    if report.failed or report.skipped or report.when == "call":
        item["outcome"] = report.outcome
        if report.failed or report.skipped:
            item["details"] = str(report.longrepr)
        if hasattr(report, "wasxfail"):
            item["xfail"] = report.wasxfail


def pytest_sessionfinish(session, exitstatus):
    target = os.environ.get("ZCLICK_COMPAT_REPORT")
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1, "python": sys.version, "platform": platform.platform(),
        "exit_status": int(exitstatus), "collected": sorted(_collected),
        "deselected": sorted(_deselected),
        "collection_errors": _collection_errors, "results": dict(sorted(_results.items())),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
