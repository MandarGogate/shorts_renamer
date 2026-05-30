"""Regression tests for shortssync.utils.extract_audio_safe (BUG-004)."""

import os

import pytest

from shortssync import utils


class _FakeAudio:
    def write_audiofile(self, path, logger=None, codec=None):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("audio")


class _FakeClip:
    closed = False

    def __init__(self, path, has_audio=True):
        self.audio = _FakeAudio() if has_audio else None

    def close(self):
        type(self).closed = True


@pytest.fixture(autouse=True)
def _enable_moviepy(monkeypatch):
    monkeypatch.setattr(utils, "MOVIEPY_AVAILABLE", True)


def test_extract_audio_safe_yields_path_and_cleans_up(tmp_path, monkeypatch):
    out = tmp_path / "out.wav"
    monkeypatch.setattr(utils, "VideoFileClip", lambda p: _FakeClip(p, has_audio=True))

    with utils.extract_audio_safe("video.mp4", str(out)) as audio_path:
        assert audio_path == str(out)
        assert os.path.exists(out)

    # Temp file removed on exit.
    assert not os.path.exists(out)


def test_extract_audio_safe_yields_none_when_no_audio(monkeypatch):
    monkeypatch.setattr(utils, "VideoFileClip", lambda p: _FakeClip(p, has_audio=False))

    with utils.extract_audio_safe("video.mp4") as audio_path:
        assert audio_path is None


def test_consumer_exception_propagates_without_runtime_error(tmp_path, monkeypatch):
    out = tmp_path / "out.wav"
    monkeypatch.setattr(utils, "VideoFileClip", lambda p: _FakeClip(p, has_audio=True))

    # Before the fix this raised "generator didn't stop after throw()"
    # instead of the caller's ValueError.
    with pytest.raises(ValueError, match="boom"):
        with utils.extract_audio_safe("video.mp4", str(out)) as audio_path:
            assert audio_path == str(out)
            raise ValueError("boom")

    # Cleanup still happened despite the exception.
    assert not os.path.exists(out)


def test_extraction_failure_yields_none(monkeypatch):
    def _raise(_path):
        raise RuntimeError("decode failed")

    monkeypatch.setattr(utils, "VideoFileClip", _raise)

    with utils.extract_audio_safe("video.mp4") as audio_path:
        assert audio_path is None
