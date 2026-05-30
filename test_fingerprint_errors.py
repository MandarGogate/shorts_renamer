"""Tests for get_fingerprint error handling + logging (BUG-009)."""

import subprocess

import numpy as np
import pytest

from shortssync import fingerprint as fp


class _Result:
    def __init__(self, stdout):
        self.stdout = stdout


def test_get_fingerprint_parses_valid_output(monkeypatch):
    monkeypatch.setattr(fp.subprocess, "run", lambda *a, **k: _Result("FINGERPRINT=1,2,3\n"))
    out = fp.get_fingerprint("x.wav", fpcalc_path="/bin/fpcalc")
    assert np.array_equal(out, np.array([1, 2, 3], dtype=np.uint32))


def test_get_fingerprint_timeout_returns_none_and_logs(monkeypatch, caplog):
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="fpcalc", timeout=30)

    monkeypatch.setattr(fp.subprocess, "run", _raise)
    with caplog.at_level("WARNING"):
        assert fp.get_fingerprint("x.wav", fpcalc_path="/bin/fpcalc") is None
    assert "timed out" in caplog.text


def test_get_fingerprint_calledprocesserror_returns_none_and_logs(monkeypatch, caplog):
    def _raise(*a, **k):
        raise subprocess.CalledProcessError(returncode=2, cmd="fpcalc", stderr="bad file")

    monkeypatch.setattr(fp.subprocess, "run", _raise)
    with caplog.at_level("WARNING"):
        assert fp.get_fingerprint("x.wav", fpcalc_path="/bin/fpcalc") is None
    assert "exited 2" in caplog.text


def test_get_fingerprint_malformed_data_returns_none_and_logs(monkeypatch, caplog):
    monkeypatch.setattr(fp.subprocess, "run", lambda *a, **k: _Result("FINGERPRINT=1,abc,3\n"))
    with caplog.at_level("WARNING"):
        assert fp.get_fingerprint("x.wav", fpcalc_path="/bin/fpcalc") is None
    assert "Malformed fingerprint" in caplog.text


def test_get_fingerprint_no_fingerprint_line_returns_none(monkeypatch):
    monkeypatch.setattr(fp.subprocess, "run", lambda *a, **k: _Result("DURATION=10\n"))
    assert fp.get_fingerprint("x.wav", fpcalc_path="/bin/fpcalc") is None


def test_get_fingerprint_raises_when_fpcalc_missing(monkeypatch):
    monkeypatch.setattr(fp, "get_fpcalc_path", lambda: None)
    with pytest.raises(RuntimeError, match="fpcalc not found"):
        fp.get_fingerprint("x.wav")
