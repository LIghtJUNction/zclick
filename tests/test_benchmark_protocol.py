"""Guard fairness and immutable input identities in the measurement harness."""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "scripts"))
import compare
import prepare_baseline
import release_notes


def test_each_balanced_block_uses_every_package_order_once():
    schedule = compare.round_orders(compare.LABELS, 12, 20261111)
    expected = set(itertools.permutations(compare.LABELS))
    for block in (schedule[:6], schedule[6:]):
        assert {tuple(order) for order in block} == expected
        for position in range(3):
            assert {label: sum(order[position] == label for order in block)
                    for label in compare.LABELS} == dict.fromkeys(compare.LABELS, 2)
    assert schedule == compare.round_orders(compare.LABELS, 12, 20261111)
    assert schedule != compare.round_orders(compare.LABELS, 12, 20261112)


def test_partial_diagnostic_rounds_keep_requested_count():
    schedule = compare.round_orders(compare.LABELS, 1, 20261111)
    assert len(schedule) == 1 and set(schedule[0]) == set(compare.LABELS)


def test_snapshot_rejects_changed_wheel_before_import(tmp_path, monkeypatch):
    path = tmp_path / "baseline.whl"
    path.write_bytes(b"modified")
    manifest = {"artifacts": {"zclick": {"path": str(path), "sha256": hashlib.sha256(b"original").hexdigest()}}}
    monkeypatch.setattr(prepare_baseline, "probe", lambda _: pytest.fail("Changed wheel must fail before loading it"))
    with pytest.raises(RuntimeError, match="wheel changed"):
        prepare_baseline.verify_snapshot(manifest)


def test_snapshot_rejects_import_from_another_package_path(monkeypatch):
    manifest = {"artifacts": {}, "python": "python", "packages": {"zclick": {"package_path": "/fixed"}}}
    monkeypatch.setattr(prepare_baseline, "probe", lambda _: {"packages": {"zclick": {"package_path": "/candidate"}}})
    with pytest.raises(RuntimeError, match="another path"):
        prepare_baseline.verify_snapshot(manifest)


def test_snapshot_checks_manifest_files_against_the_actual_wheel(tmp_path, monkeypatch):
    path = tmp_path / "baseline.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("zclick/__init__.py", b"published code")
    manifest = {"artifacts": {"zclick": {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}},
                "packages": {"zclick": {"source_files": {"__init__.py": hashlib.sha256(b"changed code").hexdigest()}}}}
    monkeypatch.setattr(prepare_baseline, "probe", lambda _: pytest.fail("Invalid provenance must fail before import"))
    with pytest.raises(RuntimeError, match="manifest differs from its wheel"):
        prepare_baseline.verify_snapshot(manifest)


def test_release_notes_refuse_diagnostic_measurements():
    with pytest.raises(ValueError, match="Diagnostic benchmark"):
        release_notes.render("0.1.2a1", "a" * 40, "LIghtJUNction/zclick", {"diagnostic": True})


def test_candidate_must_include_new_python_modules_from_checkout(tmp_path, monkeypatch):
    package = tmp_path / "python/zclick"
    package.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('version = "0.1.1a2"\n', encoding="utf-8")
    (package / "__init__.py").write_bytes(b"unchanged")
    (package / "new_module.py").write_bytes(b"new implementation")
    monkeypatch.setattr(compare, "ROOT", tmp_path)
    status = compare.source_status({"packages": {"zclick": {
        "version": "0.1.1a2",
        "source_files": {"__init__.py": hashlib.sha256(b"unchanged").hexdigest()},
    }}})
    assert status["version_matches"]
    assert not status["wheel_python_source_matches_checkout"]
    assert status["different_python_files"] == ["new_module.py"]


@pytest.fixture
def three_way_report():
    """Synthetic units/identity fixture, never a performance-evidence artifact."""
    return {
        "schema": 2,
        "diagnostic": False,
        "git_commit": "a" * 40,
        "target": json.loads((ROOT / "compatibility/target.json").read_text(encoding="utf-8")),
        "measurements": {
            label: {"version": version, "cases": {"invoke/1": {"median_wall_us": warm}},
                    "cold_commands": {"command/1": {"median_wall_us": cold}}}
            for label, version, warm, cold in (
                ("click", "8.5.1", 40.0, 20000.0),
                ("zclick-baseline", "0.1.1a1", 80.0, 30000.0),
                ("zclick", "0.1.1a2", 20.0, 10000.0),
            )
        },
        "ratios": {"invoke/1": {"wall_speedup": 2.0}},
        "cold_command_ratios": {"command/1": 2.0},
        "improvement_over_baseline": {"invoke/1": {"wall_speedup": 4.0}},
        "method": {"repeats": 12, "seed": 20261111},
        "host_before": {"affinity": [2]},
    }


def test_release_notes_keep_three_way_identity_and_timing_units(three_way_report):
    text = release_notes.render("0.1.1a2", "a" * 40, "LIghtJUNction/zclick", three_way_report)
    assert "| `invoke/1` | 40.000 | 20.000 | 2.000× |" in text
    assert "| `command/1` | 20.000 | 10.000 | 2.000× |" in text
    assert "Change from published zclick 0.1.1a1" in text
    assert "| `invoke/1` | 80.000 | 20.000 | 4.000× |" in text
    assert "fresh isolated processes for 12 rounds, using two minimal wheel environments" in text
    assert "UNFINISHED: " in text


def test_release_notes_keep_legacy_fixed_order_caveat(three_way_report):
    three_way_report["schema"] = 1
    del three_way_report["measurements"]["zclick-baseline"]
    del three_way_report["improvement_over_baseline"]
    text = release_notes.render("0.1.1a2", "a" * 40, "LIghtJUNction/zclick", three_way_report)
    assert "Packages run in fixed order on a shared host" in text
    assert "Change from published zclick" not in text


@pytest.mark.parametrize("mismatch", ["commit", "version", "target"])
def test_three_way_notes_reject_evidence_for_another_release(three_way_report, mismatch):
    if mismatch == "commit":
        three_way_report["git_commit"] = "b" * 40
    elif mismatch == "version":
        three_way_report["measurements"]["zclick"]["version"] = "0.1.1a1"
    else:
        three_way_report["target"]["commit"] = "b" * 40
    with pytest.raises(ValueError, match="does not match this release and target"):
        release_notes.render("0.1.1a2", "a" * 40, "LIghtJUNction/zclick", three_way_report)


def test_release_notes_select_version_performance_without_rewriting_history(tmp_path, monkeypatch):
    compatibility = tmp_path / "compatibility"
    compatibility.mkdir()
    for name in ("target.json", "known-gaps.json", "test-manifest.json"):
        (compatibility / name).write_bytes((ROOT / "compatibility" / name).read_bytes())
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/performance-0.1.1a2.md").write_text("Version-specific evidence", encoding="utf-8")
    monkeypatch.setattr(release_notes, "ROOT", tmp_path)
    current = release_notes.render("0.1.1a2", "a" * 40, "LIghtJUNction/zclick")
    historical = release_notes.render("0.1.1a1", "b" * 40, "LIghtJUNction/zclick")
    assert "/blob/" + "a" * 40 + "/docs/performance-0.1.1a2.md" in current
    assert "/blob/" + "b" * 40 + "/docs/performance.md" in historical
