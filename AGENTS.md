# ShortsSync coding-agent guide

## Scope

This file is the operating guide for coding agents working in this repository. Read it together with `PLAN.md`, `future.md`, and the relevant feature guide in `docs/` before changing code. Keep changes focused: this is a single-host Python application, not a networked microservice with a database.

## What this repository does

ShortsSync identifies the audio in short-form videos and generates safe, tagged filenames. It combines Chromaprint (`fpcalc`) fingerprint matching with optional ShazamIO identification. It supports a Tk desktop GUI, a command-line workflow, a folder monitor, and a Flask/Socket.IO web UI.

## Repository map

- `cli.py`: batch processing, monitor mode, Shazam modes, cache/history commands, and CLI entry point.
- `main.py`: Tkinter desktop GUI.
- `web_backend.py`: Flask REST API, Socket.IO events, web UI server, review/approval flow, and download routes.
- `web_frontend/`: bundled browser UI (`index.html`, `app.js`, `styles.css`).
- `shortssync/`: shared implementation:
  - `fingerprint.py`: `fpcalc` extraction, cache, and slowed-audio fingerprints.
  - `matcher.py`: vectorized BER matcher (`fingerprint_ber`, `find_best_match`).
  - `naming.py`: sanitization, tags, collision handling, and reference labels.
  - `shazam_client.py`: optional Shazam identification and JSON cache.
  - `index_cache.py`: resumable reference-index persistence.
  - `rename_logger.py`: rename commits and JSONL history.
  - `utils.py`: video/audio extraction and `fpcalc` discovery.
  - `web_security.py`: token, loopback, path-root, and download URL checks.
  - `web_state.py`: atomic web review/config state.
  - `constants.py` and `log.py`: shared media constants and logging helpers.
- `config.py`: committed defaults. Directory values resolve from environment first, then optional ignored `config_local.py`, then empty defaults.
- `config.example.py`: safe template for local overrides.
- `create_slowed_versions.py`, `download_mp3.py`, `rename_audio_files.py`, `find_unique.py`: focused helper workflows.
- `test_*.py`, `conftest.py`: pytest suite; integration tests may require media tooling.
- `docs/`: feature and operational background. `PLAN.md` is the current engineering roadmap.

## Setup and runtime dependencies

Use Python 3.8 or newer. Install Python dependencies with:

```bash
python3 -m pip install -r requirements.txt
```

For editable package metadata and development extras, the equivalent project definition is in `pyproject.toml` (`web`, `shazam`, `dev`, and `all` extras). Runtime media processing also needs:

- `ffmpeg` for extraction/conversion.
- `fpcalc` from Chromaprint for fingerprinting (`brew install chromaprint` on macOS or `sudo apt install libchromaprint-tools` on Debian/Ubuntu).
- Network access only when using Shazam or yt-dlp.

Do not commit `config_local.py`, `.env` values, credentials, media, caches, logs, or rename history.

## Main commands

From the repository root:

```bash
python3 cli.py --help
python3 cli.py -v /path/to/videos -a /path/to/audio --dry-run
python3 cli.py -v /path/to/videos -a /path/to/audio --shazam-only --dry-run
python3 cli.py --monitor --monitor-interval 5
python3 cli.py --history
python3 cli.py --stats
python3 cli.py --cache-stats
python3 cli.py --index-stats
python3 cli.py --clear-cache
python3 main.py                         # Tk GUI
./start_web.sh                          # installs requirements and starts web UI
python3 web_backend.py                  # starts on localhost, normally port 5001+
python3 create_slowed_versions.py --help
python3 download_mp3.py --help
python3 rename_audio_files.py --help
```

Use `--dry-run` before any batch that renames files. The web server is local-only by default (`127.0.0.1`) and chooses an available port starting at `5001`. To expose it beyond loopback, set `SHORTSSYNC_TOKEN`; also set `SHORTSSYNC_ROOTS` to restrict filesystem access. `SHORTSSYNC_CORS_ORIGINS` controls browser origins. Stop a foreground process with `Ctrl-C`; when backgrounding it, record its PID and stop that PID rather than killing every Python process.

### Known command caveat

At the current revision, `python3 find_unique.py --help` fails during import because the script requests a `compare_fingerprints` symbol that is not exported by `shortssync`. The shared matcher currently exports `fingerprint_ber` and `find_best_match`. Treat this as a real compatibility issue when modifying that workflow; do not document the helper as healthy until a code fix and regression test land.

## Development workflow

1. Read the relevant source, tests, `PLAN.md`, and feature docs before editing.
2. Identify the shared module that owns behavior. Do not copy matching, naming, cache, rename, or security logic into another entry point.
3. Preserve dry-run and review-before-rename behavior. File operations must be explicit, validated, and logged.
4. Keep web paths inside configured roots, validate download URLs, and preserve loopback/auth defaults. Never weaken these controls to make a test or demo pass.
5. Keep cache and state writes atomic and concurrency-safe. Treat `.fingerprints/`, `.shazam_cache/`, `.shortssync/`, and `rename_history.jsonl` as runtime state, not fixtures.
6. Add or update focused tests for changed behavior. Avoid tests that require personal media or live network access; mark network/integration cases appropriately.
7. Update the root `README.md`, this file, and `CHANGELOG.md` when user-facing behavior, agent workflow, or implementation behavior changes.

## Validation

Run the narrowest relevant checks, then the full suite when practical:

```bash
python3 -m pytest -q
python3 -m ruff check .
python3 -m compileall -q .
git diff --check
```

The test suite currently passes with some skips in environments without optional media/network dependencies. A lint or command failure must be reported rather than hidden. Review `git diff` and `git status --short` before handing work back; source changes should include tests unless the change is documentation-only.

## Coding conventions

- Support the Python version declared in `pyproject.toml` (`>=3.8`).
- Follow the configured Ruff rules (`E`, `F`, `W`, `I`, line length 100; E501 is ignored).
- Prefer small typed functions and shared utilities over entry-point-specific duplicates.
- Preserve existing user-visible CLI/API behavior unless a change is intentional and documented.
- Use clear error messages and structured logging where available; never log tokens or credential values.
- Do not silently swallow unexpected exceptions. Include paths and operation context in safe diagnostic logs.

## Change boundaries and safety

Agents may change application source, tests, and documentation when the task requires it, but must not modify secrets, generated caches, personal media, or unrelated repositories. Never commit or push unless explicitly requested. Before destructive renames, use a dry run and confirm the destination; before web changes, test both unauthenticated local behavior and token/allow-list behavior. If requirements conflict or a product/security decision is needed, stop and report the decision instead of inventing policy.
