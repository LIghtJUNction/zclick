"""Windows console data paths and platform-independent filename contracts."""
from __future__ import annotations

import ctypes
import errno
import importlib
import io
import sys

import pytest

import zclick


def test_file_error_keeps_windows_backslashes(monkeypatch: pytest.MonkeyPatch) -> None:
    name = r"C:\Users\someone\a file.txt"

    def denied(*args, **kwargs):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr("zclick.utils._open_stream", denied)
    with pytest.raises(zclick.BadParameter) as captured:
        zclick.File(lazy=False).convert(name, None, None)
    assert captured.value.message == f"'{name}': Permission denied"


def test_composite_generic_supports_default_input_type() -> None:
    from zclick.types import CompositeParamType

    class Coordinates(CompositeParamType[tuple[int, int]]):
        arity = 2

    assert Coordinates().arity == 2


@pytest.fixture
def console():
    if sys.platform != "win32":
        pytest.skip("Exercises the Windows wide-character console backend")
    return importlib.import_module("zclick._winconsole")


def test_windows_console_writer_keeps_surrogate_pairs(console, monkeypatch: pytest.MonkeyPatch) -> None:
    writes = []

    def write(handle, data, units, written, reserved):
        assert handle == 123
        writes.append(ctypes.string_at(data, units * 2))
        written._obj.value = units
        return True

    monkeypatch.setattr(console, "WriteConsoleW", write)
    monkeypatch.setattr(console, "MAX_BYTES_WRITTEN", 4)
    raw = console._WindowsConsoleWriter(123)
    payload = "a😀字b".encode("utf-16-le")
    remaining = payload
    while remaining:
        count = raw.write(remaining)
        assert count > 0
        remaining = remaining[count:]
    assert b"".join(writes) == payload
    # Each API call independently contains valid Unicode.
    assert "".join(chunk.decode("utf-16-le") for chunk in writes) == "a😀字b"
    raw.close()
    assert raw.closed


def test_windows_console_reader_transfers_utf16(console, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = "字😀\r\n".encode("utf-16-le")

    def read(handle, data, units, received, reserved):
        assert handle == 456
        assert units * 2 >= len(payload)
        ctypes.memmove(data, payload, len(payload))
        received._obj.value = len(payload) // 2
        return True

    monkeypatch.setattr(console, "ReadConsoleW", read)
    raw = console._WindowsConsoleReader(456)
    target = bytearray(32)
    assert raw.readinto(target) == len(payload)
    assert target[:len(payload)] == payload


def test_windows_console_facade_preserves_caller_bytes(console) -> None:
    text = io.StringIO()
    binary = io.BytesIO()
    stream = console.ConsoleStream(text, binary)
    assert stream.write("字😀") == 2
    assert stream.write(b"\xff") == 1
    assert text.getvalue() == "字😀"
    assert binary.getvalue() == b"\xff"
    assert stream.buffer is binary
    stream.close()
    assert not binary.closed


def test_windows_console_does_not_wrap_redirected_streams(console) -> None:
    assert console._get_windows_console_stream(io.StringIO(), None, None) is None
