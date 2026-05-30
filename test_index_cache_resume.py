import numpy as np

from shortssync.index_cache import ReferenceIndexCache


def test_checkpoint_round_trip(tmp_path):
    cache = ReferenceIndexCache(str(tmp_path / "cache"))

    audio_dir = "/tmp/audio"
    config = {"detect_slowed": True, "slowed_speeds": [0.75, 0.5]}
    all_files = ["a.mp3", "nested/b.mp4"]
    completed_files = ["a.mp3"]
    ref_fps = {"track-a.mp3": np.array([1, 2, 3], dtype=np.uint8)}
    shazam_names = {"a.mp3": "Artist - Track"}

    saved = cache.save_checkpoint(
        audio_dir,
        ref_fps,
        shazam_names,
        config,
        all_files,
        completed_files,
    )

    loaded = cache.load_checkpoint(audio_dir, config, all_files)

    assert saved is True
    assert loaded is not None

    loaded_ref_fps, loaded_shazam_names, loaded_completed_files = loaded
    assert loaded_completed_files == completed_files
    assert loaded_shazam_names == shazam_names
    assert np.array_equal(loaded_ref_fps["track-a.mp3"], ref_fps["track-a.mp3"])


def test_checkpoint_rejected_on_format_version_mismatch(tmp_path):
    import json

    cache = ReferenceIndexCache(str(tmp_path / "cache"))
    audio_dir = "/tmp/audio"
    config = {"detect_slowed": False, "slowed_speeds": []}
    all_files = ["a.mp3"]
    cache.save_checkpoint(
        audio_dir,
        {"track-a.mp3": np.array([1, 2, 3], dtype=np.uint32)},
        {},
        config,
        all_files,
        ["a.mp3"],
    )

    # Simulate a checkpoint written by an older, incompatible version.
    info = json.loads(cache.checkpoint_file.read_text())
    assert info["format_version"] == ReferenceIndexCache.CACHE_FORMAT_VERSION
    info["format_version"] = 1
    cache.checkpoint_file.write_text(json.dumps(info))

    assert cache.load_checkpoint(audio_dir, config, all_files) is None
    # Stale checkpoint is cleared on rejection.
    assert not cache.checkpoint_file.exists()


def test_save_index_records_current_format_version(tmp_path):
    import json

    cache = ReferenceIndexCache(str(tmp_path / "cache"))
    ok = cache.save_index(
        str(tmp_path),  # empty dir -> valid signature computation
        {"track-a.mp3": np.array([1, 2, 3], dtype=np.uint32)},
        {},
        {"detect_slowed": False, "slowed_speeds": []},
    )
    assert ok is True
    info = json.loads(cache.index_file.read_text())
    assert info["format_version"] == ReferenceIndexCache.CACHE_FORMAT_VERSION
