"""Release invariants that prevent publishing stale or inconsistent artifacts."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bump_version", ROOT / "scripts/bump_version.py")
bump_version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump_version)
sys.path.insert(0, str(ROOT / "scripts"))
from release_gate import verify


@pytest.mark.parametrize(("current", "part", "expected"), [
    ("0.1.0a1", "prerelease", "0.1.0a2"),
    ("0.1.0a1", "patch", "0.1.0"),
    ("0.1.0", "patch", "0.1.1"),
    ("1.2.3", "minor", "1.3.0"),
    ("1.2.3", "major", "2.0.0"),
    ("1.2.3", "prerelease", "1.2.4a1"),
])
def test_bump_versions(current, part, expected):
    assert bump_version.next_version(current, part) == expected


def test_bump_updates_python_rust_and_internal_requirement(tmp_path):
    (tmp_path / "crates/ext").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0a1"\n')
    (tmp_path / "Cargo.toml").write_text('[workspace.package]\nversion = "0.1.0"\n')
    (tmp_path / "crates/ext/Cargo.toml").write_text(
        '[dependencies]\nzclick-core = { path = "../core", version = "=0.1.0" }\n'
    )
    bump_version.bump(tmp_path, "prerelease")
    assert 'version = "0.1.0a2"' in (tmp_path / "pyproject.toml").read_text()
    assert 'version = "0.1.0-alpha.2"' in (tmp_path / "Cargo.toml").read_text()
    assert 'version = "=0.1.0-alpha.2"' in (tmp_path / "crates/ext/Cargo.toml").read_text()


@pytest.mark.parametrize("value", ["1.0.0;echo bad", "v1.2.3", "01.2.3", "1.2.3.dev1", ""])
def test_invalid_version_rejected(value):
    with pytest.raises(ValueError):
        bump_version.parse(value)


@pytest.fixture
def release_evidence(tmp_path):
    ids = ["tests/test_a.py::test_one", "tests/test_a.py::test_two"]
    report = {"passed": True, "target": {"commit": "pinned-click"},
              "implementation_commit": "release-sha", "validated_test_ids": ids,
              "deselected": []}
    api = {"complete": True, "target": report["target"], "implementation_commit": "release-sha"}
    manifest = {"target_commit": "pinned-click", "test_count": len(ids),
                "test_ids_sha256": hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()}
    paths = [tmp_path / name for name in ("report.json", "api.json", "manifest.json")]
    for path, value in zip(paths, (report, api, manifest)):
        path.write_text(json.dumps(value), encoding="utf-8")
    return paths


def test_release_gate_requires_exact_test_inventory(release_evidence):
    report, api, manifest = release_evidence
    verify([report], [api], implementation="release-sha", manifest=manifest)
    value = json.loads(report.read_text(encoding="utf-8"))
    value["validated_test_ids"].pop()
    report.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="exact pinned"):
        verify([report], [api], implementation="release-sha", manifest=manifest)


def test_release_gate_rejects_stale_source(release_evidence):
    report, api, manifest = release_evidence
    with pytest.raises(ValueError, match="release commit"):
        verify([report], [api], implementation="different-sha", manifest=manifest)


def test_release_gate_rejects_new_skips_or_failures(release_evidence):
    report, api, manifest = release_evidence
    value = json.loads(report.read_text(encoding="utf-8"))
    value["passed"] = False
    report.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="Compatibility failed"):
        verify([report], [api], manifest=manifest)
