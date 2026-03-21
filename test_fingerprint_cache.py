import numpy as np

from shortssync import fingerprint as fingerprint_module


def test_temp_extracted_audio_reuses_cache_for_same_source(tmp_path, monkeypatch):
    source_video = tmp_path / "source.mp4"
    source_video.write_bytes(b"video")

    temp_audio_one = tmp_path / "temp-1.wav"
    temp_audio_one.write_bytes(b"audio")

    temp_audio_two = tmp_path / "temp-2.wav"
    temp_audio_two.write_bytes(b"audio")

    cache_dir = tmp_path / "cache"
    fingerprint_module._global_cache = None

    calls = []
    expected = np.array([1, 2, 3], dtype=np.uint32)

    def fake_get_fingerprint(path, fpcalc_path=None, timeout=30):
        calls.append(path)
        return expected

    monkeypatch.setattr(fingerprint_module, "get_fingerprint", fake_get_fingerprint)

    first = fingerprint_module.get_fingerprint_cached(
        str(temp_audio_one),
        cache_dir=str(cache_dir),
        cache_key_source=str(source_video),
    )
    second = fingerprint_module.get_fingerprint_cached(
        str(temp_audio_two),
        cache_dir=str(cache_dir),
        cache_key_source=str(source_video),
    )

    assert len(calls) == 1
    assert np.array_equal(first, expected)
    assert np.array_equal(second, expected)
