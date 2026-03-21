from pathlib import Path

import cli


class FakeShazamResult:
    def __init__(self, name: str):
        self._name = name

    def get_filename_base(self):
        return self._name


class FakeShazamClient:
    def __init__(self, name: str | None):
        self.name = name

    async def identify(self, audio_path, timeout=30):
        if self.name is None:
            return None
        return FakeShazamResult(self.name)


def test_find_best_reference_name_prefers_exact_substring_match():
    best_match, score = cli.find_best_reference_name(
        "Taylor Swift - Love Story",
        [
            "Taylor Swift - Love Story.mp3",
            "Taylor Swift - Blank Space.mp3",
        ],
    )

    assert best_match == "Taylor Swift - Love Story.mp3"
    assert score == 100.0


def test_run_shazam_match_uses_reference_name_when_library_match_exists(tmp_path: Path):
    video_dir = tmp_path / "videos"
    video_dir.mkdir()

    success, new_name, info = cli.run_shazam_match(
        audio_path=str(tmp_path / "sample.wav"),
        shazam_client=FakeShazamClient("The Weeknd - Blinding Lights"),
        reference_names=["The Weeknd - Blinding Lights.mp3"],
        video_name="clip.mp4",
        video_dir=str(video_dir),
        proposed_names=set(),
        fixed_tags="",
        pool_tags="",
        preserve_exact=True,
        shazam_fallback_any=False,
    )

    assert success is True
    assert new_name == "The Weeknd - Blinding Lights.mp4"
    assert info["method"] == "shazam"
    assert info["reference"] == "The Weeknd - Blinding Lights.mp3"


def test_run_shazam_match_can_fallback_to_direct_shazam_name(tmp_path: Path):
    video_dir = tmp_path / "videos"
    video_dir.mkdir()

    success, new_name, info = cli.run_shazam_match(
        audio_path=str(tmp_path / "sample.wav"),
        shazam_client=FakeShazamClient("Doja Cat - Paint The Town Red"),
        reference_names=["Adele - Hello.mp3"],
        video_name="clip.mp4",
        video_dir=str(video_dir),
        proposed_names=set(),
        fixed_tags="",
        pool_tags="",
        preserve_exact=True,
        shazam_fallback_any=True,
    )

    assert success is True
    assert new_name == "Doja Cat - Paint The Town Red.mp4"
    assert info["method"] == "shazam_new"
    assert info["reference"] == "Doja Cat - Paint The Town Red"
