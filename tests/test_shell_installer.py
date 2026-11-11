"""Provisioning failures must not silently replace real completion execution."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.error

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import install_test_shells as installer


def archive(name: str, value: bytes) -> bytes:
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w") as contents:
        info = tarfile.TarInfo(name)
        info.size = len(value)
        contents.addfile(info, io.BytesIO(value))
    return result.getvalue()


def test_download_rejects_wrong_archive_before_extracting(monkeypatch):
    monkeypatch.setattr(installer.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"changed"))
    with pytest.raises(ValueError, match="Checksum mismatch"):
        installer.download({"name": "zsh", "source": "https://example.invalid/zsh",
                            "sha256": hashlib.sha256(b"original").hexdigest()})


def test_transient_archive_failure_retries_then_still_checks_checksum(monkeypatch):
    calls = []
    failed_response = io.BytesIO(b"temporary server error")

    def fetch(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 503, "Temporary unavailable", {}, failed_response)
        return io.BytesIO(b"verified")

    monkeypatch.setattr(installer.urllib.request, "urlopen", fetch)
    monkeypatch.setattr(installer.time, "sleep", lambda _: None)
    value = installer.download({"name": "zsh", "source": "https://example.invalid/zsh",
                                "sha256": hashlib.sha256(b"verified").hexdigest()})
    assert value == b"verified" and len(calls) == 2
    assert failed_response.closed


def test_permanent_http_failure_closes_response_without_retry(monkeypatch):
    response = io.BytesIO(b"not found")
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        raise urllib.error.HTTPError(url, 404, "Not found", {}, response)

    monkeypatch.setattr(installer.urllib.request, "urlopen", fetch)
    with pytest.raises(urllib.error.HTTPError) as failure:
        installer.download({"name": "zsh", "source": "https://example.invalid/zsh"})
    assert failure.value.code == 404 and len(calls) == 1
    assert response.closed


def test_source_build_failure_removes_temporary_source_tree(tmp_path, monkeypatch):
    folder = tmp_path / "installed/zsh"
    folder.mkdir(parents=True)
    data = archive("zsh-5.9/configure", b"#!/bin/sh\nexit 1\n")
    source_paths = []

    def fail(command, **kwargs):
        source_paths.append(kwargs["cwd"])
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(installer.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        installer.build_zsh(data, {"version": "5.9"}, folder, 2)
    assert source_paths and all(not source.exists() for source in source_paths)
    assert (folder / "build.log").is_file()


def test_portable_binary_install_retains_archive_and_executable_identity(tmp_path, monkeypatch):
    data = archive("fish", b"a pinned test executable")
    runtime = {"name": "fish", "version": "fixed", "source": "https://example.invalid/fish",
               "sha256": hashlib.sha256(data).hexdigest()}
    monkeypatch.setattr(installer, "download", lambda _: data)
    result = installer.install(runtime, tmp_path)
    executable = Path(result["executable"])
    assert executable.read_bytes() == b"a pinned test executable"
    assert result["archive_sha256"] == runtime["sha256"]
    assert result["executable_sha256"] == hashlib.sha256(executable.read_bytes()).hexdigest()
    assert not list(tmp_path.rglob("runtime.tar"))
