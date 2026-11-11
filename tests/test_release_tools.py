"""Release invariants that prevent publishing stale or inconsistent artifacts."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bump_version", ROOT / "scripts/bump_version.py")
bump_version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump_version)


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
