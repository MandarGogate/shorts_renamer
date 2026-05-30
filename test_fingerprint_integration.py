"""End-to-end fingerprint tests using synthetic audio (no personal media).

These shell out to fpcalc, so they skip when chromaprint is unavailable.
"""

import shutil

import pytest

from shortssync.fingerprint import compare_fingerprints, get_fingerprint

pytestmark = pytest.mark.integration

requires_fpcalc = pytest.mark.skipif(
    shutil.which("fpcalc") is None, reason="fpcalc (chromaprint) not installed"
)


@requires_fpcalc
def test_identical_audio_is_a_perfect_match(make_noise):
    clip = make_noise(seed=7, seconds=12)
    fp = get_fingerprint(clip)
    assert fp is not None and len(fp) > 0

    is_match, ber = compare_fingerprints(fp, fp, threshold=0.15)
    assert is_match is True
    assert ber == 0.0


@requires_fpcalc
def test_different_audio_differs(make_noise):
    fp_a = get_fingerprint(make_noise(seed=11, seconds=12))
    fp_b = get_fingerprint(make_noise(seed=99, seconds=12))
    assert fp_a is not None and fp_b is not None

    _, ber = compare_fingerprints(fp_a, fp_b, threshold=0.15)
    # Distinct audio content must not be bit-identical.
    assert ber > 0.0
