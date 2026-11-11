"""Guard fairness and immutable input identities in the measurement harness."""
from __future__ import annotations

import hashlib
import itertools
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
