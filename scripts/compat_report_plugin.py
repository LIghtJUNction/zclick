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

# The fixed upstream test tree uses Enum members as parameter values. Python
# 3.10 formats IntEnum/IntFlag as member names; it also substitutes Enum for
# StrEnum in test_options.py. Python 3.11+ formats these five members as values.
# Map only their complete display IDs, never the test values or assertions.
_ENUM_IDS_PY310 = {
    "tests/test_options.py::test_choice_default_rendering[ColorInt-ColorInt.GREEN-GREEN]":
        "tests/test_options.py::test_choice_default_rendering[ColorInt-2-GREEN]",
    "tests/test_options.py::test_choice_default_rendering[Number-Number.TWO-TWO]":
        "tests/test_options.py::test_choice_default_rendering[Number-2-TWO]",
    "tests/test_options.py::test_choice_default_rendering[Letter-Letter.NAME_1-NAME_1]":
        "tests/test_options.py::test_choice_default_rendering[Letter-Value-1-NAME_1]",
    "tests/test_options.py::test_choice_default_rendering[Letter-Letter.NAME_2-NAME_2]":
        "tests/test_options.py::test_choice_default_rendering[Letter-Value_2-NAME_2]",
    "tests/test_options.py::test_choice_default_rendering[Letter-Letter.NAME_3-NAME_3]":
        "tests/test_options.py::test_choice_default_rendering[Letter-42_value-NAME_3]",
}


def key(nodeid: str, filename: str | None = None) -> str:
    # Normalize only the file path. Parameter IDs contain escaped ANSI bytes,
    # regexes and other literal backslashes whose identity must be retained.
    filepart, separator, parameterpart = nodeid.partition("::")
    nodeid = filepart.replace("\\", "/") + separator + parameterpart
    if nodeid.startswith("::") and filename:
        nodeid = filename.replace("\\", "/") + nodeid
    nodeid = "tests/" + nodeid.split("tests/", 1)[-1]
    # Older external-root pytest reports omitted this filename for explicit
    # parameter selectors. These three functions are unique in the fixed tree.
    if nodeid.startswith(tuple("tests/::test_stress_" + name for name in (
        "gc_between_invocations", "logging_sequential_invocations", "thread_pool_with_exit"
    ))):
        nodeid = "tests/test_stream_lifecycle.py" + nodeid[len("tests/"):]
    nodeid = re.sub(r"(?<!\w)zclick(?=[.\]\-])", "click", nodeid)
    if "test_attr_deprecated[" in nodeid and "-__version__-" in nodeid:
        nodeid = nodeid.split("-__version__-", 1)[0] + "-__version__-<distribution-version>]"
    if "test__detect_program_name.py::test_detect_program_name[" in nodeid:
        # These three upstream IDs use os.path.join. Normalize the displayed
        # platform separator while leaving the test arguments themselves intact.
        nodeid = nodeid.replace("\\\\", "/")
    return _ENUM_IDS_PY310.get(nodeid, nodeid)


def pytest_collection_finish(session):
    _collected.extend(key(item.nodeid, item.location[0]) for item in session.items)


def pytest_deselected(items):
    _deselected.extend(key(item.nodeid, item.location[0]) for item in items)


def pytest_collectreport(report):
    if report.failed:
        _collection_errors.append({"nodeid": key(report.nodeid), "error": str(report.longrepr)})


def pytest_runtest_logreport(report):
    item = _results.setdefault(key(report.nodeid, report.location[0]), {"outcome": "pending", "duration": 0.0})
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
    if len(_collected) != len(set(_collected)):
        _collection_errors.append({"nodeid": "", "error": "Canonical test IDs are not unique"})
    payload = {
        "schema": 1, "python": sys.version, "platform": platform.platform(),
        "exit_status": int(exitstatus), "collected": sorted(_collected),
        "deselected": sorted(_deselected),
        "collection_errors": _collection_errors, "results": dict(sorted(_results.items())),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
