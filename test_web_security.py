"""Tests for shortssync.web_security (BUG-001/002/003 helpers)."""

import os

import pytest

from shortssync import web_security as ws

# ---------------- auth token ----------------

def test_token_matches_disabled_when_no_expected():
    assert ws.token_matches(None, None) is True
    assert ws.token_matches("anything", None) is True


def test_token_matches_requires_exact_token():
    assert ws.token_matches("secret", "secret") is True
    assert ws.token_matches("wrong", "secret") is False
    assert ws.token_matches(None, "secret") is False
    assert ws.token_matches("", "secret") is False


def test_get_auth_token_reads_env(monkeypatch):
    monkeypatch.delenv("SHORTSSYNC_TOKEN", raising=False)
    assert ws.get_auth_token() is None
    monkeypatch.setenv("SHORTSSYNC_TOKEN", "  abc  ")
    assert ws.get_auth_token() == "abc"


# ---------------- loopback ----------------

@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "127.5.0.1"])
def test_is_loopback_host_true(host):
    assert ws.is_loopback_host(host) is True


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com", "8.8.8.8"])
def test_is_loopback_host_false(host):
    assert ws.is_loopback_host(host) is False


# ---------------- path allow-list ----------------

def test_resolve_within_roots_no_roots_allows_any(tmp_path):
    target = tmp_path / "videos"
    target.mkdir()
    resolved = ws.resolve_within_roots(str(target), [])
    assert resolved == target.resolve()


def test_resolve_within_roots_accepts_path_inside_root(tmp_path):
    root = tmp_path / "media"
    inside = root / "sub"
    inside.mkdir(parents=True)
    resolved = ws.resolve_within_roots(str(inside), [root.resolve()])
    assert resolved == inside.resolve()


def test_resolve_within_roots_rejects_path_outside_root(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    outside = tmp_path / "secret"
    outside.mkdir()
    assert ws.resolve_within_roots(str(outside), [root.resolve()]) is None


def test_resolve_within_roots_rejects_traversal(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    traversal = str(root / ".." / "secret")
    assert ws.resolve_within_roots(traversal, [root.resolve()]) is None


def test_resolve_within_roots_rejects_empty():
    assert ws.resolve_within_roots("", []) is None
    assert ws.resolve_within_roots(None, []) is None


def test_get_allowed_roots_parses_pathsep(tmp_path, monkeypatch):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("SHORTSSYNC_ROOTS", f"{a}{os.pathsep}{b}")
    roots = ws.get_allowed_roots()
    assert a.resolve() in roots and b.resolve() in roots
    monkeypatch.delenv("SHORTSSYNC_ROOTS", raising=False)
    assert ws.get_allowed_roots() == []


# ---------------- download URL validation ----------------

@pytest.mark.parametrize("url", [
    "ftp://example.com/x",
    "file:///etc/passwd",
    "http://127.0.0.1/admin",
    "http://localhost:5001/api",
    "http://169.254.169.254/latest/meta-data",  # cloud metadata
    "http://10.0.0.5/internal",
    "http://192.168.1.1/router",
    "not a url",
    "",
])
def test_is_safe_download_url_rejects_unsafe(url):
    assert ws.is_safe_download_url(url) is False


def test_is_safe_download_url_allows_public(monkeypatch):
    # Avoid real DNS in CI: force a public resolution.
    monkeypatch.setattr(
        ws.socket, "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    assert ws.is_safe_download_url("https://example.com/video") is True


def test_is_safe_download_url_blocks_private_resolution(monkeypatch):
    monkeypatch.setattr(
        ws.socket, "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("10.1.2.3", 0))],
    )
    assert ws.is_safe_download_url("https://sneaky.example.com/x") is False


# ---------------- endpoint integration (requires Flask stack) ----------------

def _import_web_backend():
    pytest.importorskip("flask")
    pytest.importorskip("flask_cors")
    pytest.importorskip("flask_socketio")
    import web_backend
    return web_backend


def test_api_requires_token_when_configured(monkeypatch):
    web_backend = _import_web_backend()
    monkeypatch.setattr(web_backend, "AUTH_TOKEN", "s3cret")
    client = web_backend.app.test_client()

    assert client.get("/api/health").status_code == 401
    ok = client.get("/api/health", headers={"X-Auth-Token": "s3cret"})
    assert ok.status_code == 200
    bearer = client.get("/api/health", headers={"Authorization": "Bearer s3cret"})
    assert bearer.status_code == 200


def test_api_open_when_no_token(monkeypatch):
    web_backend = _import_web_backend()
    monkeypatch.setattr(web_backend, "AUTH_TOKEN", None)
    client = web_backend.app.test_client()
    assert client.get("/api/health").status_code == 200


def test_index_rejects_directory_outside_allow_list(tmp_path, monkeypatch):
    web_backend = _import_web_backend()
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(web_backend, "AUTH_TOKEN", None)
    monkeypatch.setattr(web_backend, "ALLOWED_ROOTS", [allowed.resolve()])
    client = web_backend.app.test_client()

    resp = client.post("/api/reference/index", json={"audio_dir": str(outside)})
    assert resp.status_code == 400

    web_backend.processing_status["is_processing"] = False
    ok = client.post("/api/reference/index", json={"audio_dir": str(allowed)})
    assert ok.status_code == 200
    web_backend.processing_status["is_processing"] = False


def test_download_rejects_unsafe_url(monkeypatch):
    web_backend = _import_web_backend()
    if not web_backend.YT_DLP_AVAILABLE:
        pytest.skip("yt-dlp not installed")
    monkeypatch.setattr(web_backend, "AUTH_TOKEN", None)
    client = web_backend.app.test_client()
    resp = client.post("/api/download", json={"url": "http://127.0.0.1/secret"})
    assert resp.status_code == 400

