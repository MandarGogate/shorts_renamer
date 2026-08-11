# Changelog

All notable ShortsSync implementation changes reconstructed from the Git history are recorded here. The repository has no formal release tags, so entries use commit dates and short commit IDs. This file complements the more detailed historical notes in `docs/CHANGES.md`.

## [Unreleased]

- Documentation baseline added/updated for users and coding agents.

## 2026-05-30

- **`d49b2cd` — Shazam timeout handling:** made identification timeouts configurable and added timeout logging.
- **`4b9a4e0` — Status dashboard:** added the project status dashboard in `tasks.html`.
- **`178eb54` — Phase 3 engineering work:** added architecture/DX/observability improvements, GUI safety changes, shared constants/logging exports, and project tooling configuration.
- **`1fd57e3` — Cache and rename reliability:** added atomic/locked cache writes, batched index checkpoints, and consolidated filename sanitization and rename handling.
- **`45a5216` — Shared matcher:** extracted the vectorized fingerprint matcher into `shortssync/matcher.py` and updated CLI, GUI, and web callers; added matcher coverage.
- **`3d18730` — Security and correctness:** hardened the web server with loopback/auth/path/download protections, fixed audio/fingerprint handling, added CI and focused tests, removed tracked personal rename history, and added safe configuration defaults.

## 2026-05-17

- **`0aecd00` — Safe rename and web flow:** improved rename safety and logging consistency, added the Shazam-only web path, and updated the naming/web frontend behavior.

## 2026-05-12

- **`e383530` — Persistent web review:** added durable match-review state, API review operations, and browser review UI/tests.

## 2026-04-10

- **`6abb471` — Cleanup:** removed dead code and lint noise.
- **`eca105d` — `updated`:** historical commit retained; its implementation scope cannot be reconstructed confidently from the subject alone.

## 2026-03-22

- **`e6a52c7` — Web startup:** switched the web startup helper to use system Python instead of a virtual environment.
- **`d02fb2b` — Roadmap focus:** refocused the engineering roadmap on ShortsSync workflow improvements.
- **`c7a39aa` — Platform roadmap:** added the focused Bytebreed platform roadmap.

## 2026-03-21

- **`f39a7df` — Index recovery:** persisted reference-index checkpoints during CLI builds.
- **`ba7e242` — `test pending`:** historical test-related commit; no more specific implementation change is identifiable from the commit subject.
- **`f7fc9cf` — Resumable indexing:** added interrupted-index resume behavior and stabilized fingerprint caching.
- **`7d94433` — Reindexing:** historical reindexing bug fix; the subject does not identify a precise behavior, so no narrower claim is made.

## 2026-02-22

- **`19532fd` — Shazam fallback:** added Shazam fallback matching for videos without a fingerprint-library match.
- **`31d1546` — Web Shazam:** added the Shazam option to the web UI.
- **`334f3c9` — Web bug fix:** fixed a variable-scope error in the web backend.
- **`b1baf6d` — Audio renaming:** added Shazam-based reference-audio renaming.
- **`c5d4665` — Shazam and modular architecture:** integrated ShazamIO, introduced the shared `shortssync` package, added slowed-audio support and feature guides, and reorganized the README/dependencies.

## 2025-11-24

- **`b64067a` — Downloading and caching:** added MP3 downloading and fingerprint caching across CLI, GUI, and web workflows.

## 2025-11-23

- **`ddeea56` — Web UI organization:** moved download controls into a separate UI tab.
- **`d6785e1` — Video downloading:** added yt-dlp video download support.
- **`ae3324c` — Web progress:** fixed the UI getting stuck during indexing by ensuring completion status reaches the frontend.
- **`7423d3c` — Socket.IO/ports:** fixed Socket.IO broadcasting and added dynamic port selection.
- **`4806360` — Default port:** changed the default web port from 5000 to 5001 to avoid the macOS AirPlay conflict.
- **`05c87de` — Web application:** added the comprehensive feature plan, startup helper, and complete Flask/Socket.IO web interface.
- **`28d39f5` — Merge:** merged the feature-build branch; no separate implementation change is recorded here.

## 2025-11-20

- **`54d48b2`, `4f083bf`, `c170068`, `27f6be2`, `3a9c181` — Initial development:** established the original ShortsSync implementation and iterative working versions. The commit subjects are generic, so individual changes cannot be reconstructed reliably.

## Notes

- No tests, source files, dependencies, or runtime state were changed to create this changelog.
- Commit subjects and repository files were used as evidence; uncertain historical entries are explicitly labeled rather than guessed.
