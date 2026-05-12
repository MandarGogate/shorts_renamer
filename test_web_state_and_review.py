from pathlib import Path

import pytest

from shortssync.web_state import WebStateStore, validate_review_filename


def make_defaults() -> dict:
    return {
        "video_dir": "",
        "audio_dir": "",
        "fixed_tags": "#shorts",
        "pool_tags": "#fyp #viral",
        "move_files": False,
        "preserve_exact_names": False,
    }


def make_match() -> dict:
    return {
        "original": "clip.mp4",
        "new_name": "Artist - Track.mp4",
        "matched_ref": "Artist - Track.mp3",
        "ber": 0.012,
        "confidence": 0.988,
        "match_type": "fingerprint",
    }


def make_second_match() -> dict:
    match = make_match()
    match["original"] = "clip-2.mp4"
    match["new_name"] = "Artist - Track 2.mp4"
    return match


def import_web_backend():
    pytest.importorskip("flask")
    pytest.importorskip("flask_cors")
    pytest.importorskip("flask_socketio")

    import web_backend

    return web_backend


def test_web_state_store_persists_config_and_review_batch(tmp_path: Path):
    state_path = tmp_path / "web_state.json"
    store = WebStateStore(state_path, make_defaults())

    updated = store.update_config({"video_dir": "/tmp/videos", "move_files": True})
    assert updated["video_dir"] == "/tmp/videos"
    assert updated["move_files"] is True

    batch = store.set_review_batch("/tmp/videos", [make_match()])
    match_id = batch["matches"][0]["id"]

    store.update_match(match_id, decision="approved", new_name="Custom Name.mp4")

    reloaded = WebStateStore(state_path, make_defaults())
    persisted_config = reloaded.get_config()
    persisted_batch = reloaded.get_review_batch()

    assert persisted_config["video_dir"] == "/tmp/videos"
    assert persisted_batch is not None
    assert persisted_batch["video_dir"] == "/tmp/videos"
    assert persisted_batch["summary"]["approved"] == 1
    assert persisted_batch["matches"][0]["decision"] == "approved"
    assert persisted_batch["matches"][0]["new_name"] == "Custom Name.mp4"


def test_web_state_store_approve_all_keeps_skipped_matches_skipped(tmp_path: Path):
    store = WebStateStore(tmp_path / "web_state.json", make_defaults())
    batch = store.set_review_batch("/tmp/videos", [make_match(), make_second_match()])
    skipped_id = batch["matches"][1]["id"]

    store.update_match(skipped_id, decision="skipped")
    approved_batch = store.approve_all()

    assert approved_batch is not None
    assert approved_batch["summary"]["approved"] == 1
    assert approved_batch["summary"]["skipped"] == 1
    assert approved_batch["matches"][0]["decision"] == "approved"
    assert approved_batch["matches"][1]["decision"] == "skipped"


def test_web_state_store_remove_matches_clears_only_successful_items(tmp_path: Path):
    store = WebStateStore(tmp_path / "web_state.json", make_defaults())
    batch = store.set_review_batch("/tmp/videos", [make_match(), make_second_match()])

    remaining_batch = store.remove_matches([batch["matches"][0]["id"]])

    assert remaining_batch is not None
    assert remaining_batch["summary"]["total"] == 1
    assert remaining_batch["matches"][0]["original"] == "clip-2.mp4"


def test_web_state_store_ignores_malformed_persisted_state(tmp_path: Path):
    state_path = tmp_path / "web_state.json"
    state_path.write_text('{"config": "bad", "review_batch": []}', encoding="utf-8")

    store = WebStateStore(state_path, make_defaults())

    assert store.get_config()["fixed_tags"] == "#shorts"
    assert store.get_review_batch() is None


def test_web_state_store_rejects_non_string_review_name(tmp_path: Path):
    store = WebStateStore(tmp_path / "web_state.json", make_defaults())
    batch = store.set_review_batch("/tmp/videos", [make_match()])

    with pytest.raises(ValueError, match="New name must be a string"):
        store.update_match(batch["matches"][0]["id"], new_name=42)


@pytest.mark.parametrize("filename", ["../x.mp4", "/tmp/x.mp4", "dir/x.mp4", "dir\\x.mp4", "", "."])
def test_review_filename_validation_rejects_paths(filename: str):
    assert validate_review_filename(filename, "New name") is not None


def test_review_filename_validation_accepts_plain_filename():
    assert validate_review_filename("Artist - Track #shorts.mp4", "New name") is None


def test_web_api_config_and_match_review_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    web_backend = import_web_backend()
    state_store = WebStateStore(tmp_path / "web_state.json", make_defaults())
    monkeypatch.setattr(web_backend, "state_store", state_store)

    client = web_backend.app.test_client()

    response = client.post(
        "/api/config",
        json={"video_dir": "/tmp/source", "audio_dir": "/tmp/audio", "move_files": True},
    )
    assert response.status_code == 200

    config_response = client.get("/api/config")
    config_payload = config_response.get_json()
    assert config_payload["config"]["video_dir"] == "/tmp/source"
    assert config_payload["config"]["audio_dir"] == "/tmp/audio"
    assert config_payload["config"]["move_files"] is True

    batch = state_store.set_review_batch("/tmp/source", [make_match()])
    match_id = batch["matches"][0]["id"]

    patch_response = client.patch(
        f"/api/matches/{match_id}",
        json={"decision": "approved", "new_name": "Approved Name.mp4"},
    )
    assert patch_response.status_code == 200

    matches_response = client.get("/api/matches")
    matches_payload = matches_response.get_json()
    assert matches_payload["summary"]["approved"] == 1
    assert matches_payload["matches"][0]["decision"] == "approved"
    assert matches_payload["matches"][0]["new_name"] == "Approved Name.mp4"


def test_rename_endpoint_rejects_when_no_matches_are_approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    web_backend = import_web_backend()
    state_store = WebStateStore(tmp_path / "web_state.json", make_defaults())
    monkeypatch.setattr(web_backend, "state_store", state_store)

    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    state_store.set_review_batch(str(video_dir), [make_match()])

    client = web_backend.app.test_client()
    response = client.post("/api/videos/rename", json={"video_dir": str(video_dir), "move_files": False})

    assert response.status_code == 400
    assert response.get_json()["error"] == "No approved matches to rename"


def test_rename_endpoint_rejects_mismatched_review_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    web_backend = import_web_backend()
    state_store = WebStateStore(tmp_path / "web_state.json", make_defaults())
    monkeypatch.setattr(web_backend, "state_store", state_store)

    video_dir = tmp_path / "videos"
    other_dir = tmp_path / "other"
    video_dir.mkdir()
    other_dir.mkdir()
    batch = state_store.set_review_batch(str(video_dir), [make_match()])
    state_store.update_match(batch["matches"][0]["id"], decision="approved")

    client = web_backend.app.test_client()
    response = client.post("/api/videos/rename", json={"video_dir": str(other_dir), "move_files": False})

    assert response.status_code == 409
    assert response.get_json()["error"] == "Staged review batch belongs to a different video directory"
