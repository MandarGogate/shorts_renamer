"""Shared pytest fixtures.

Provides a synthetic-audio generator so tests can exercise the real
fingerprinting pipeline without shipping any personal media. Tests that need
ffmpeg/fpcalc skip automatically when those binaries are absent.
"""

import shutil
import subprocess

import pytest


def have_tool(name: str) -> bool:
    return shutil.which(name) is not None


@pytest.fixture
def make_tone(tmp_path):
    """Factory fixture: render a synthetic sine-wave WAV via ffmpeg.

    Usage:
        path = make_tone(freq=440, seconds=8)
    """
    if not have_tool("ffmpeg"):
        pytest.skip("ffmpeg not installed")

    counter = {"n": 0}

    def _make(freq: int = 440, seconds: float = 8.0, name: str | None = None) -> str:
        counter["n"] += 1
        out = tmp_path / (name or f"tone_{counter['n']}.wav")
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"sine=frequency={freq}:duration={seconds}",
            "-ar", "44100", "-ac", "1",
            str(out),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return str(out)

    return _make


@pytest.fixture
def make_noise(tmp_path):
    """Factory fixture: render distinct pink-noise WAVs (differ by seed).

    Pure tones can collapse to identical Chromaprint fingerprints, so noise is
    used whenever a test needs two genuinely different audio signals.
    """
    if not have_tool("ffmpeg"):
        pytest.skip("ffmpeg not installed")

    counter = {"n": 0}

    def _make(seed: int = 1, seconds: float = 10.0, name: str | None = None) -> str:
        counter["n"] += 1
        out = tmp_path / (name or f"noise_{counter['n']}.wav")
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anoisesrc=d={seconds}:c=pink:s={seed}:r=44100",
            "-ac", "1",
            str(out),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return str(out)

    return _make

