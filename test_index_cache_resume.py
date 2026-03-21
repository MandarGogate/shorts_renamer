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
