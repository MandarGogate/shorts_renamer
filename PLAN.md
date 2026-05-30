# ShortsSync — Engineering Review & Implementation Roadmap

> Comprehensive architecture, security, performance, and product review.
> No code has been changed. This document is the roadmap for the work.
> Reviewer perspective: Principal Engineer / Security Auditor / Performance Engineer / PM / Solutions Architect.

---

# Executive Summary

## Project Overview
ShortsSync is a single-host Python tool for content creators that automatically renames
short-form videos (TikTok / Reels / Shorts) based on their audio track. It combines
**Chromaprint** audio fingerprinting (via the `fpcalc` binary) with **Shazam** identification
(via `shazamio`) to match a video's audio against a reference library and produce a
tagged filename like `Artist - Title #shorts #fyp.mp4`.

It ships **four entry points** over a shared package:
- `cli.py` (~1,500 lines) — batch CLI + a built-in `--monitor` watch loop.
- `main.py` (~750 lines) — Tkinter desktop GUI.
- `web_backend.py` (~1,200 lines) — Flask + Socket.IO server with a JS frontend (`web_frontend/`).
- Shared package `shortssync/` — `fingerprint`, `naming`, `shazam_client`, `utils`,
  `index_cache`, `rename_logger`, `web_state`.

There is **no database**; all state lives in JSON/JSONL files and `.npy`/`.npz` caches.

## Health Scores (0–100)

| Dimension | Score | One-line justification |
|-----------|-------|------------------------|
| **Overall Health** | **52** | Core works for a solo user, but it is not safe to "deploy at scale" as-is. |
| **Security** | **30** | Web server has zero auth, binds `0.0.0.0`, open CORS, arbitrary filesystem access, SSRF. |
| **Performance** | **40** | Pure-Python O(videos × refs × windows) matching; O(n²) cache/checkpoint disk writes. |
| **Maintainability** | **45** | The core index+match logic is duplicated **4×**; `cli.py` `main()` is ~700 lines. |
| **Test Coverage** | **28** | Good tests exist for `web_state` and a few helpers; the matching core, naming, utils, and endpoint security are untested. |

## Test Coverage Assessment
Five test files exist. They cover `web_state` persistence/validation, two CLI Shazam
helper functions, the fingerprint-cache reuse path, and the index checkpoint round-trip.
The single most important and most error-prone code — the **sliding-window matching
algorithm** — has **no tests at all**, and it is copy-pasted in four places, so a fix in
one place will silently not apply to the others. `test_slowed_audio.py` is not a test; it
is a manual script with a hardcoded personal path.

## The Five Things To Do First
1. **Lock down or localhost-bind the web server** (auth + `127.0.0.1` + path allow-list). Critical security.
2. **Extract one shared `matching`/`indexing` service** and delete the 4 duplicates. Stops bug drift.
3. **Vectorize the matching algorithm** (NumPy stride windows). 10–100× speedup.
4. **Stop O(n²) disk writes** during indexing (batch checkpoints, atomic single-write metadata).
5. **Untrack `rename_history.jsonl` and de-hardcode `config.py`** personal paths.

---

# Architecture Overview

## System Design Summary
```
                 ┌─────────────┐   ┌─────────────┐   ┌──────────────────┐
   Entry points  │  cli.py     │   │  main.py    │   │  web_backend.py  │
                 │ (CLI + mon) │   │ (Tk GUI)    │   │ (Flask+SocketIO) │
                 └──────┬──────┘   └──────┬──────┘   └────────┬─────────┘
                        │                 │                   │
                        └────────┬────────┴─────────┬─────────┘
                                 ▼                   ▼
                        ┌────────────────────────────────────┐
                        │           shortssync/               │
                        │  fingerprint  naming  shazam_client │
                        │  utils  index_cache  rename_logger  │
                        │  web_state                          │
                        └────────────────────────────────────┘
                                 │            │           │
                        fpcalc / ffmpeg   shazamio     yt-dlp
                        (subprocess)     (network)    (network)
```

## Key Components
- **`shortssync/fingerprint.py`** — runs `fpcalc -raw`, parses the fingerprint into a
  `uint32` array, caches `.npy` files keyed by `path:mtime:size`. Also generates slowed
  variants with `ffmpeg atempo`.
- **`shortssync/naming.py`** — `sanitize_filename`, `generate_name` (tag injection +
  uniqueness), `build_reference_label` (disambiguates duplicate labels). The cleanest module.
- **`shortssync/shazam_client.py`** — async `shazamio` wrapper with a per-file JSON cache.
- **`shortssync/index_cache.py`** — persists the reference index to `.npz` + JSON with a
  resumable checkpoint.
- **`shortssync/web_state.py`** — the **reference-quality** module: thread-locked, atomic
  writes (`tmp` + `replace`), strict filename validation. The rest of the codebase should
  look like this.
- **`shortssync/rename_logger.py`** — append-only JSONL audit log of renames.

## Data Flow (match → rename)
1. Enumerate reference audio/video (`os.walk`), extract audio from videos via moviepy,
   fingerprint each, store **unpacked bits** in an in-memory dict `{label: bitarray}`.
2. For each query video: extract audio → fingerprint → slide the query bit-window across
   every reference, compute minimum Hamming distance → BER = dist / n_bits.
3. If `BER < threshold` (0.15) accept; else optionally fall back to Shazam.
4. Generate a unique tagged name, then `os.rename` (or move to `_Ready/`), and append to
   `rename_history.jsonl`.

## Authentication / External Integrations
- **Authentication: none anywhere.** The web server is unauthenticated.
- **External:** `fpcalc` (Chromaprint), `ffmpeg`, `moviepy`, `shazamio` (network), `yt-dlp` (network).

## Top Architectural Risks
- **R1 — Four divergent copies of the core algorithm.** Index + match logic is duplicated
  across `cli.main()`, `cli.process_single_video()`, `web_backend.match_task()`, and
  `main._run_matching()`. `future.md` itself flags this. Behavior already drifts (the GUI
  hardcodes `0.15`; only CLI has checkpoints/slowed handling).
- **R2 — Network-exposed, unauthenticated control plane** over the local filesystem and
  outbound downloads (see Security).
- **R3 — Algorithmic complexity** in matching and cache I/O makes "at scale" impractical.
- **R4 — Global mutable state in the web server** (`reference_fingerprints`,
  `processing_status`) makes it strictly single-user/single-task.

---

# Critical Findings

| Severity | Issue | Impact | Fix Priority |
|----------|-------|--------|--------------|
| Critical | Web server: no auth + binds `0.0.0.0` + open CORS | Anyone on the network can browse the filesystem, rename files, and trigger downloads | P0 |
| Critical | Arbitrary filesystem path access via `audio_dir`/`video_dir`/`output_dir` | Remote directory enumeration & file renames outside any sandbox | P0 |
| Critical | SSRF + arbitrary write via `/api/download` & `/api/download_mp3` | Server fetches attacker URLs; `filename` path-traversal into `outtmpl` | P0 |
| High | Matching is pure-Python O(videos × refs × windows × fp_len) | Minutes-to-hours at library scale; blocks a web thread | P1 |
| High | `save_checkpoint` after **every** file during indexing (full `.npz`+JSON) | O(n²) disk writes; indexing 1k+ files is painfully slow | P1 |
| High | Core index/match logic duplicated 4× | Fixes don't propagate; the GUI already ignores config threshold | P1 |
| High | `FingerprintCache` documented "Thread-safe" but has **no locks**; used from web threads | Metadata corruption / lost cache entries under concurrency | P1 |
| Medium | `extract_audio_safe` yields inside `try/except Exception` | Double-yield → `RuntimeError`; masks real errors | P2 |
| Medium | `find_unique.py --convert-to-mp3` passes `verbose=False` to moviepy 2.x | `TypeError`; feature is broken against pinned dependency | P2 |
| Medium | Non-atomic cache writes (`FingerprintCache`, `ShazamCache`, `index_cache`) | Crash mid-write corrupts caches | P2 |
| Medium | Tkinter widgets mutated from worker thread in `main.py` | Intermittent GUI crashes / hangs | P2 |
| Medium | `rename_history.jsonl` (428 KB personal data) committed to git | Privacy leak; repo bloat | P2 |
| Low | `config.py` hardcodes personal absolute paths; README/config drift | Broken first-run for anyone else | P3 |
| Low | `demo_shazam.py` (1 byte), `uploads/` + `MAX_CONTENT_LENGTH` unused | Dead code / misleading config | P3 |

---

# Bug Backlog

## BUG-001 — Web server is unauthenticated and network-exposed
- **Description:** `socketio.run(app, host='0.0.0.0', ...)` with `CORS(app)` and
  `cors_allowed_origins="*"`. No endpoint checks any token, session, or origin.
- **Files:** `web_backend.py` (`CORS(app)` ~L70; `SocketIO(..., cors_allowed_origins="*")`;
  `host='0.0.0.0'` in `__main__`).
- **Root Cause:** Built as a personal localhost tool but defaults to all-interfaces with
  permissive CORS; no auth layer was ever added.
- **Impact:** Any host on the LAN (or the internet if port-forwarded) can drive every
  endpoint. Combined with BUG-002/003 this is full filesystem read/rename + SSRF.
- **Recommended Fix:** Default `host='127.0.0.1'`; require a bearer token / shared secret
  (`SHORTSSYNC_TOKEN`) checked in a `before_request` hook; restrict CORS and
  `cors_allowed_origins` to an explicit localhost origin; document a reverse-proxy + auth
  pattern for any real network exposure.
- **Effort:** M (0.5–1 day).

## BUG-002 — Arbitrary filesystem path access (no allow-list)
- **Description:** `audio_dir`, `video_dir`, and `output_dir` come straight from request
  JSON. Validation is only `os.path.abspath(os.path.normpath(...))` + existence check.
- **Files:** `web_backend.py` `index_reference_audio()`, `match_videos()`, `download_video()`,
  `download_mp3()`.
- **Root Cause:** `normpath`/`abspath` normalize traversal but impose **no boundary**; any
  absolute path on the host is accepted.
- **Impact:** A caller can enumerate/scan any directory (e.g., `/Users`, `/etc`) and rename
  files anywhere the process user can write.
- **Recommended Fix:** Introduce a configured root allow-list (e.g., `SHORTSSYNC_ROOTS`)
  and reject any resolved path not under an allowed root (`os.path.commonpath`).
- **Effort:** M.

## BUG-003 — SSRF and path traversal in download endpoints
- **Description:** `/api/download` and `/api/download_mp3` pass user URLs directly to
  `yt-dlp` and write to a user-supplied directory; `download_mp3` interpolates the
  user-supplied `filename` into `outtmpl` (`f'{filename}.%(ext)s'`).
- **Files:** `web_backend.py` `download_video()`, `download_mp3()`.
- **Root Cause:** No URL scheme/host validation; no sanitization of `filename`.
- **Impact:** Server-side request forgery (fetch internal URLs / `file:`-style abuse via
  yt-dlp extractors), and `filename="../../x"` writing outside `audio_dir`.
- **Recommended Fix:** Validate URL is `http(s)`; block private/link-local hosts;
  `sanitize_filename(filename)` and confirm the resolved output path stays under the
  allowed root.
- **Effort:** M.

## BUG-004 — `extract_audio_safe` can raise `RuntimeError` (double yield) and swallows errors
- **Description:** The `@contextmanager` wraps the `yield` in `try/except Exception: yield None`.
  If the **consumer** body raises, the exception is thrown back into the generator at the
  `yield`, caught by `except Exception`, and a **second** `yield None` runs → Python raises
  `RuntimeError: generator didn't stop after throw()`, masking the original error.
- **Files:** `shortssync/utils.py` `extract_audio_safe()`.
- **Root Cause:** Error handling placed around the `yield` instead of around extraction only.
- **Impact:** Confusing crashes; genuine extraction failures are silently turned into `None`.
- **Recommended Fix:** Only wrap the extraction (pre-yield) in `try/except`; do not catch
  around the `yield`. Distinguish "no audio" (`yield None`) from "extraction failed" (raise/log).
- **Effort:** S.

## BUG-005 — `find_unique.py --convert-to-mp3` is broken on moviepy 2.x
- **Description:** Calls `video.audio.write_audiofile(dest, logger=None, codec='mp3', bitrate='192k', verbose=False)`.
  `verbose` was removed in moviepy 2.0; `requirements.txt` pins `moviepy>=2.0.0`.
- **Files:** `find_unique.py` (copy branch).
- **Root Cause:** API not updated after the moviepy 2.x pin.
- **Impact:** `TypeError` whenever `--convert-to-mp3` is used → feature unusable.
- **Recommended Fix:** Remove `verbose=False`; use `codec='libmp3lame'`; route through the
  shared extraction helper in `utils.py` instead of re-importing moviepy here.
- **Effort:** S.

## BUG-006 — `FingerprintCache` is not thread-safe despite docstring
- **Description:** Class docstring says "Thread-safe fingerprint cache"; `_metadata` (a dict)
  is mutated in `set`/`_remove_cache_entry` with no lock. The web backend calls it from
  background threads.
- **Files:** `shortssync/fingerprint.py` `FingerprintCache`.
- **Root Cause:** Lock never implemented; global `_global_cache` shared across threads.
- **Impact:** Lost writes / corrupted `.cache_metadata.json` under concurrent indexing.
- **Recommended Fix:** Add a `threading.RLock` around metadata mutations and writes; make
  writes atomic (tmp + `replace`). Correct the docstring otherwise.
- **Effort:** S–M.

## BUG-007 — GUI mutates Tkinter widgets from a worker thread
- **Description:** `_run_matching()` runs in a `threading.Thread` but calls
  `self.status_var.set(...)`, `self.fixed_tags_entry.get()`, `self.preserve_exact_names.get()`
  directly. Tkinter is not thread-safe off the main loop.
- **Files:** `main.py` `_run_matching()` (status updates and entry reads inside the thread).
- **Root Cause:** Worker thread touches widgets without marshaling via `root.after(...)`.
- **Impact:** Intermittent crashes/hangs, especially on Linux/Windows Tk builds.
- **Recommended Fix:** Snapshot widget values on the main thread before starting the worker;
  push all UI updates through `root.after(0, ...)` (the completion path already does this).
- **Effort:** M.

## BUG-008 — GUI ignores the configured threshold
- **Description:** Match acceptance is hardcoded `if best_ref and best_ber < 0.15`.
- **Files:** `main.py` `_run_matching()`.
- **Root Cause:** Threshold not surfaced from config/UI.
- **Impact:** GUI behaves differently from CLI/web; `--threshold` and config have no effect there.
- **Recommended Fix:** Read threshold from config/UI; share via the extracted matching service.
- **Effort:** S.

## BUG-009 — `get_fingerprint` swallows all exceptions
- **Description:** Final `except Exception: return None` hides every failure mode (bad file,
  fpcalc crash, parse error) as an indistinguishable `None`.
- **Files:** `shortssync/fingerprint.py` `get_fingerprint()`.
- **Root Cause:** Over-broad catch with no logging.
- **Impact:** Silent data loss; impossible to diagnose why a file failed.
- **Recommended Fix:** Catch specific exceptions; log at debug/warning with the path; let
  truly unexpected exceptions propagate or be reported.
- **Effort:** S.

## BUG-010 — `sanitize_filename` can return an empty string / reserved names
- **Description:** After stripping invalid chars, control chars, and `' .'`, the result can
  be empty (e.g., a title of only `"..."` or punctuation). No handling of Windows reserved
  names (`CON`, `PRN`, `NUL`, `COM1`...).
- **Files:** `shortssync/naming.py` `sanitize_filename()`.
- **Root Cause:** No fallback for empty / reserved results.
- **Impact:** Empty/invalid target filenames; cross-platform rename failures.
- **Recommended Fix:** Fall back to a safe default (e.g., the original stem or `track_<rand>`);
  guard reserved basenames.
- **Effort:** S.

## BUG-011 — Monitor mode keys "processed" files by inode (reuse hazard)
- **Description:** Processed files are tracked by `st_ino`. Inodes are reused after deletion;
  a brand-new file can reuse a retired inode and be skipped.
- **Files:** `cli.py` `monitor_mode()` (`get_file_inode`, `processed_inodes`).
- **Root Cause:** Inode chosen as identity without accounting for reuse.
- **Impact:** Occasional silently-skipped new uploads in long-running monitor sessions.
- **Recommended Fix:** Track `(inode, mtime, size)` or a content/name+mtime tuple; expire
  entries for files no longer present.
- **Effort:** S.

## BUG-012 — Config/README/GUI default drift
- **Description:** `config.py` sets `shazam_only_mode=True` and `preserve_exact_titles=True`,
  but the README documents `shazam_only_mode=False` and never documents `preserve_exact_titles`.
  `move_files` default differs between README and config too.
- **Files:** `config.py`, `README.md`.
- **Root Cause:** Config evolved; docs not updated.
- **Impact:** Users get behavior that contradicts the docs (e.g., fingerprinting silently skipped).
- **Recommended Fix:** Reconcile defaults; document every key; add a config schema/validation.
- **Effort:** S.

---

# Performance Improvements
Ranked by ROI (impact ÷ effort).

### PERF-1 — Vectorize the sliding-window matcher *(highest ROI)*
- **Where:** the matching loop duplicated in `cli.py` (×2), `web_backend.py`, `main.py`.
- **Now:** triple nested Python loop — per reference, per 32-bit window, NumPy XOR over the
  window. Complexity ≈ `O(num_videos × num_refs × num_windows × fp_bits)` executed in the
  interpreter.
- **Fix:** Build windows with `numpy.lib.stride_tricks.sliding_window_view` and compute all
  window Hamming distances in one vectorized op; precompute `np.packbits` popcount via a
  256-entry lookup; keep references **packed** (see PERF-3). Optionally short-circuit on
  length mismatch with array ops.
- **Expected improvement:** **10–100×** on realistic libraries; turns "minutes" into "seconds".
- **Complexity:** M. **Risk:** Medium (needs the matcher test harness from TEST-1 first).

### PERF-2 — Stop O(n²) disk writes during indexing
- **Where:** `cli.py` indexing loop calls `index_cache.save_checkpoint(...)` **every file**;
  each call rewrites the full compressed `.npz` + JSON. `FingerprintCache._save_metadata`
  and `ShazamCache._save_index` rewrite the entire file on **every** `set()`
  (`.shazam_cache/index.json` is already 337 KB / 1,236 entries).
- **Fix:** Checkpoint every N files or every T seconds; debounce/flush metadata once at the
  end (and periodically), or move to an append-only / SQLite store. Write atomically.
- **Expected improvement:** Indexing wall-clock drops dramatically for 1k+ libraries; far
  less SSD wear.
- **Complexity:** S–M. **Risk:** Low.

### PERF-3 — Keep reference fingerprints packed in memory
- **Where:** all index builders do `ref_fps[name] = np.unpackbits(fp.view(np.uint8))`.
- **Now:** Storing **unpacked bits** uses ~8× the memory of packed `uint8`.
- **Fix:** Store packed bytes; unpack lazily or compute Hamming distance with a popcount
  lookup over packed bytes. Pairs naturally with PERF-1.
- **Expected improvement:** ~8× lower RAM for the reference index; better cache locality.
- **Complexity:** M. **Risk:** Medium.

### PERF-4 — Parallelize / batch Shazam and fingerprinting
- **Where:** Indexing calls `asyncio.run(client.identify(...))` **serially per file**; each
  call spins up a fresh event loop and is network-bound.
- **Fix:** Use `ShazamClient.identify_batch` with bounded concurrency (semaphore) inside one
  event loop; fingerprint extraction can use a process/thread pool (CPU + subprocess bound).
- **Expected improvement:** Large reduction in indexing time when Shazam is enabled
  (network latency hidden by concurrency).
- **Complexity:** M. **Risk:** Medium (respect Shazam rate limits).

### PERF-5 — Don't block the web request/worker on CPU matching without backpressure
- **Where:** `web_backend.match_task` runs the heavy loop in one global-locked thread.
- **Fix:** After PERF-1, the loop is short; longer-term, move heavy work to a task queue and
  stream progress. Also add an early-exit "good enough" threshold to stop scanning once a
  near-zero BER is found (already partially done with `best_ber == 0`).
- **Expected improvement:** Responsive UI; supports more than one logical job safely.
- **Complexity:** M–L. **Risk:** Medium.

---

# Security Improvements
Ranked by risk reduction. Classifications: **Critical / High / Medium / Low**.

1. **[Critical] Add authentication + bind localhost (BUG-001).** Bearer token via
   `before_request`; default `127.0.0.1`; tighten CORS and Socket.IO origins. Biggest single
   risk reduction.
2. **[Critical] Path allow-list for all directory inputs (BUG-002).** Reject paths outside
   configured roots using `os.path.commonpath`.
3. **[Critical] Harden download endpoints (BUG-003).** Validate URL scheme/host (block
   private ranges), sanitize `filename`, confirm output path is inside the allowed root.
4. **[High] Run a real WSGI/ASGI server in production.** Today `allow_unsafe_werkzeug=not is_production`
   defaults to **True** and the dev server is used. Document `gunicorn`/`eventlet` and set
   `FLASK_ENV=production` semantics correctly.
5. **[High] Concurrency safety for shared caches (BUG-006).** Locks + atomic writes prevent
   corruption that could also be triggered remotely by parallel requests.
6. **[Medium] Stop leaking absolute filesystem paths in API errors.** `rename_videos` returns
   `FileNotFoundError(src)` (full path) to clients; return generic messages, log details
   server-side.
7. **[Medium] Add rate limiting** (e.g., `flask-limiter`) on `index`, `match`, `download*`.
8. **[Medium] Regenerated `SECRET_KEY` every boot** (`secrets.token_hex(32)` at import) — fine
   while sessions are unused, but make it configurable before adding any auth/session state.
9. **[Low] Remove unused upload surface** (`UPLOAD_FOLDER`, `MAX_CONTENT_LENGTH`) until a real,
   validated upload endpoint exists, to avoid implying capabilities that aren't guarded.
10. **[Low] Dependency hygiene.** Pin exact versions / add a lockfile; run `pip-audit` in CI.

---

# Refactoring Opportunities
Ranked by maintainability gain.

### REF-1 — Extract a shared `matching` + `indexing` service *(do this first)*
The same ~60-line index builder and ~30-line matcher exist in **four** places
(`cli.main`, `cli.process_single_video`, `web_backend.match_task`, `main._run_matching`).
Create `shortssync/matcher.py` (`build_reference_index()`, `match_video()`,
`MatchResult` dataclass) and have all entry points call it. This is explicitly requested in
`future.md` ("Use a shared matching and rename service for CLI, GUI, and web"). Unblocks
PERF-1/PERF-3 (fix once) and removes the GUI threshold drift (BUG-008).

### REF-2 — Consolidate `sanitize_filename`
Reimplemented **three** times: `cli.rename_audio_command` (inner `sanitize`),
`find_unique.py` (inline comprehension), `rename_audio_files.py` (`sanitize_filename`), plus
the canonical one in `naming.py`. Keep only `naming.sanitize_filename` and import it everywhere.

### REF-3 — Decompose `cli.main()` (~700 lines)
Split into argument handling, config resolution, index orchestration, match loop, and the
rename/commit step (ideally delegating to REF-1's service). Improves testability and reduces
the single-function cognitive load.

### REF-4 — Centralize file enumeration & extension constants
`audio_exts`/`video_exts` tuples and the `os.walk` + hidden/temp-skip pattern are repeated in
~6 places. Extract `iter_media_files(root)` and shared constant tuples.

### REF-5 — Make all cache writes atomic + locked, like `web_state.py`
`web_state.py` is the model: `tmp` + `replace`, `RLock`, validation. Bring
`FingerprintCache`, `ShazamCache`, and `ReferenceIndexCache` up to that standard.

### REF-6 — Unify rename-commit logic
The "check `lexists`, `samefile`, skip-or-rename, log" block is duplicated across CLI,
monitor, GUI, and web. Extract `commit_rename(src, dst, logger, ...)` with the web backend's
stronger path validation as the canonical version.

### REF-7 — Remove dead/misleading artifacts
Delete `demo_shazam.py` (1 byte); remove unused `uploads/` + `MAX_CONTENT_LENGTH` until used;
convert `test_slowed_audio.py` into a real test or move it to `scripts/`.

---

# Testing Roadmap
Prioritized. Target: a runnable `pytest` suite that covers the core and the security boundary.

### TEST-1 — Matching algorithm (highest priority)
Unit-test the (to-be-extracted) matcher with synthetic fingerprints: exact match (BER≈0),
no match, offset/windowed match, query-longer-than-reference, empty fingerprint, threshold
boundaries. This is the prerequisite safety net for PERF-1/PERF-3.

### TEST-2 — `naming.generate_name` / `sanitize_filename`
Tag injection, length truncation that preserves song metadata (the exact bug `future.md`
calls out), uniqueness against `used_names` and existing files, `preserve_exact`, empty/
reserved-name inputs (BUG-010), unicode.

### TEST-3 — Web security/endpoint tests
Path-traversal and outside-root rejection for `index`/`match`/`download*`; download URL
validation; auth required once added; error responses don't leak absolute paths. Extends the
existing `test_web_state_and_review.py` patterns (which already use `app.test_client()`).

### TEST-4 — `utils.extract_audio_safe`
Regression test for the double-yield bug (BUG-004): consumer raises → exactly one yield,
original exception surfaces; "no audio" path yields `None`; temp file always cleaned up.

### TEST-5 — Cache concurrency & atomicity
Hammer `FingerprintCache`/`ShazamCache` from multiple threads; assert no lost entries and
valid JSON after simulated mid-write interruption.

### TEST-6 — `find_unique` dedup + convert
Cover the moviepy-2.x convert path (BUG-005) and the O(n²) grouping logic with small fixtures.

### Automation
Add `pytest` config, a tiny **synthetic audio fixture generator** (sine waves via numpy/ffmpeg)
so tests need no personal media, and wire it into CI (see CI-1). Mark Shazam/network tests
with `@pytest.mark.network` and skip by default.

---

# Feature Roadmap

## Quick Wins (< 1 day)

### Real dry-run + safe-commit parity across entry points
- **Description:** CLI already has `--dry-run`/`-y`; ensure GUI and web share the same staged
  preview→approve→commit flow (web already stages via `web_state`).
- **User Value:** Trust before renaming. **Business Value:** Fewer destructive mistakes.
- **Complexity:** Low. **Effort:** 0.5 day.

### "Save New Audio" visibility + Shazam-only in web (from `future.md`)
- **Description:** Surface the hidden web options; web already accepts `shazam_only_mode`.
- **User Value:** Web reaches CLI parity. **Complexity:** Low. **Effort:** 0.5–1 day.

### De-hardcode config + untrack personal data
- **Description:** Empty/example defaults in `config.py`; `git rm --cached rename_history.jsonl`
  and add to `.gitignore`; add `config.example.py`.
- **User Value:** Clean first-run. **Complexity:** Low. **Effort:** 0.5 day.

### Cache maintenance command
- **Description:** `--cache-stats` / `--clear-cache` for fingerprint + Shazam caches (stats
  methods already exist).
- **User Value:** Visibility/control. **Complexity:** Low. **Effort:** 0.5 day.

## Medium Features (1–7 days)

### Naming templates + per-platform tag presets (from `future.md`)
- **Description:** `{artist} - {title} {tags}` style templates; YouTube/TikTok/Reels/no-tags presets.
- **User Value:** High — matches real creator workflow. **Complexity:** Medium. **Effort:** 2–3 days.
- **Dependencies:** REF-1/REF-2 (single naming path).

### Rename undo from `rename_history.jsonl` (from `future.md`)
- **Description:** Restore selected files using the existing audit log.
- **User Value:** High (safety net). **Complexity:** Medium. **Effort:** 2–4 days.
- **Dependencies:** Reliable, complete logging from **all** entry points (web/GUI currently log; verify).

### Confidence bands + batch keyboard review (from `future.md`)
- **Description:** Auto-approve high-confidence, queue ambiguous; keyboard approve/skip/edit
  with an audio-snippet preview.
- **User Value:** High throughput. **Complexity:** Medium. **Effort:** 3–5 days.

### Duplicate-song grouping / repeat warnings (from `future.md`)
- **Description:** Group clips using the same song; warn on recently-used songs.
- **User Value:** Avoids over-posting similar clips. **Complexity:** Medium. **Effort:** 3–5 days.
- **Dependencies:** A correct dedup core (fix `find_unique` first).

## Major Features (> 1 week)

### One-click "Process Upload Queue" pipeline (from `future.md`)
- **Description:** Scan → identify → stage → approve → rename → move to `_Ready`, with a
  dashboard of unprocessed/staged/approved/renamed counts.
- **User Value:** The headline daily workflow. **Complexity:** High. **Effort:** 1–2 weeks.
- **Dependencies:** REF-1, PERF-1/2, web auth (BUG-001).

### Shared matching/rename service + true multi-job web backend
- **Description:** Replace the four duplicates with one service; add a task queue so the web
  server isn't single-global-job.
- **User/Business Value:** Stops behavior drift; enables scaling. **Complexity:** High. **Effort:** 1–2 weeks.

### Pluggable matching backend (packed-bit / optional native acceleration)
- **Description:** Abstract the matcher so a fast packed-bit (or optional C/Numba) backend can
  replace the Python loop.
- **User Value:** Large-library performance. **Complexity:** High. **Effort:** 1–2 weeks.
- **Dependencies:** TEST-1, PERF-1/PERF-3.

---

# Technical Debt Register

| ID | Description | Impact | Priority |
|----|-------------|--------|----------|
| TD-1 | Core index+match logic duplicated across 4 entry points | Bug drift; GUI ignores config threshold | P1 |
| TD-2 | `sanitize_filename` reimplemented 3× outside `naming.py` | Inconsistent sanitization | P2 |
| TD-3 | `cli.main()` ~700 lines; mixed concerns | Hard to test/modify | P2 |
| TD-4 | Non-atomic, unlocked cache writes (`fingerprint`, `shazam_client`, `index_cache`) | Corruption risk | P1 |
| TD-5 | O(n²) checkpoint + metadata rewrites during indexing | Slow indexing, SSD wear | P1 |
| TD-6 | Reference fingerprints stored unpacked (8× memory) | RAM pressure at scale | P2 |
| TD-7 | `config.py` hardcodes personal absolute paths; tracked in git | Broken first-run; privacy | P2 |
| TD-8 | `rename_history.jsonl` (428 KB personal data) committed | Privacy / repo bloat | P2 |
| TD-9 | No packaging (`pyproject.toml`/`setup.py`), no `pytest.ini`, no ruff config (despite `.ruff_cache`), no Makefile | Poor DX; inconsistent tooling | P2 |
| TD-10 | No CI (`.github/` absent) | Regressions ship silently | P1 |
| TD-11 | Dead/misleading artifacts: `demo_shazam.py` (1 byte), unused `uploads/`/`MAX_CONTENT_LENGTH` | Confusion | P3 |
| TD-12 | README ↔ config ↔ GUI default drift | Misleading docs | P3 |
| TD-13 | Global mutable state in web backend (single job/user) | Not concurrent-safe | P2 |
| TD-14 | Broad `except Exception` swallowing across modules | Hard to debug failures | P2 |
| TD-15 | No observability (structured logs/metrics); ad-hoc `print`/emoji output | Hard to operate/monitor | P2 |

---

# Monitoring & Observability Gaps
- **No structured logging.** Output is `print()` with emoji across CLI/web; the web backend
  prints to stdout and emits Socket.IO strings. Adopt the `logging` module with levels and a
  consistent format; keep the user-facing emoji layer separate from logs.
- **No metrics.** No counts/latencies for index time, match time, Shazam hit-rate, cache
  hit-rate. Add lightweight counters (and a `/api/metrics` or stats endpoint) — most data is
  already computable (`get_cache_stats`, rename stats).
- **No error tracking.** Swallowed exceptions (BUG-004/009) hide failures. After narrowing
  catches, log with context; consider optional Sentry for the web server.
- **Health endpoint is shallow.** `/api/health` reports dependency presence but not queue
  depth, last-error, or index freshness. Extend it.
- **No audit of remote actions.** Once auth exists, log who triggered renames/downloads.

---

# Developer Experience & Tooling Gaps
- **No packaging:** add `pyproject.toml` (deps, entry points `shortssync-cli`/`shortssync-web`,
  ruff/pytest config in one place).
- **No test config / fixtures:** add `pytest.ini`/`[tool.pytest]`, a synthetic-audio fixture,
  and network markers so `pytest` runs offline.
- **Ruff is used but unconfigured** (`.ruff_cache` exists, no config): add a `ruff` section and
  a `pre-commit` config (ruff + format + basic checks).
- **No Makefile/justfile:** add `make setup/test/lint/run-web` for one-command onboarding.
- **Docs drift:** consolidate `README.md`, `future.md`, and `docs/*` (`FEATURE_PLAN`,
  `PLATFORM_ROADMAP`, `WEB_README`, `CHANGES`) — reconcile defaults with `config.py`.
- **No CONTRIBUTING / setup guide** beyond README install snippets.

---

# Implementation Roadmap

## Phase 1 — Immediate (security + safety net) — ~1 week
Highest-impact fixes; mostly independent.
1. **BUG-001/002/003** — web auth + localhost bind + path allow-list + download hardening.
2. **TD-8/TD-7** — untrack `rename_history.jsonl`; de-hardcode `config.py`; add `config.example.py`.
3. **TEST-1 scaffold + CI-1** — stand up `pytest` config, synthetic audio fixture, GitHub
   Actions running lint + tests. (Prereq for safe refactors.)
4. **BUG-004, BUG-005, BUG-009** — quick correctness fixes (contextmanager, moviepy convert, error swallowing).

## Phase 2 — Short-Term (performance + stability) — ~1–2 weeks
5. **REF-1** — extract the shared `matching`/`indexing` service (also fixes BUG-008 drift).
6. **PERF-1 + PERF-3** — vectorize matcher + packed-bit references (guarded by TEST-1).
7. **PERF-2 + TD-4/TD-5** — batch checkpoints; atomic+locked cache writes (BUG-006).
8. **REF-2/REF-6** — single `sanitize_filename`; single `commit_rename`.
9. **TEST-2/3/4/5** — naming, endpoint-security, contextmanager, cache-concurrency tests.

## Phase 3 — Medium-Term (architecture + DX) — ~2–3 weeks
10. **REF-3/REF-4/REF-5/REF-7** — decompose `cli.main`, centralize enumeration, finish atomic
    caches, remove dead code.
11. **BUG-007** — make the GUI thread-safe via the shared service + `root.after`.
12. **TD-15/observability** — structured logging, basic metrics, richer health endpoint.
13. **TD-9** — packaging, pre-commit, Makefile; reconcile docs (TD-12).
14. **Quick-win features** — naming templates, cache maintenance, web Shazam-only visibility.

## Phase 4 — Long-Term (product + scale) — ~3–6 weeks
15. **One-click Upload Queue pipeline** + dashboard.
16. **Multi-job web backend** (task queue) on top of the shared service (TD-13).
17. **Rename undo**, confidence bands + keyboard review, duplicate grouping/repeat warnings.
18. **Pluggable/native matching backend** for very large libraries.

---

# Estimated Impact (after roadmap completion)

| Area | Before | After (target) |
|------|--------|----------------|
| Security | 30 — unauthenticated, network-exposed, arbitrary FS + SSRF | 80+ — authenticated, localhost-default, allow-listed paths, validated downloads |
| Performance | 40 — Python O(n) matcher, O(n²) cache I/O | 80+ — vectorized matcher (10–100×), batched atomic I/O, ~8× less RAM |
| Maintainability | 45 — 4× duplicated core, 700-line `main()` | 80+ — single shared service, decomposed, deduped helpers |
| Test Coverage | 28 — core/security untested, one non-test script | 75+ — matcher/naming/endpoint/cache suites in CI with offline fixtures |
| Overall Health | 52 | 80+ — safe to run beyond a single trusted machine, fast at library scale, change-safe |

**Headline outcomes:** the matcher goes from minutes-to-hours to seconds on large libraries;
the web interface becomes safe to run on a shared network; a regression in the matching core
can no longer silently ship; and the four divergent copies of the core become one tested,
reusable service that every entry point shares.

---

## Assumptions & Caveats
- I read every source file but did **not execute** the matcher against real media or run the
  test suite; performance estimates are reasoned from the algorithms/complexity, not benchmarked.
- "At scale" is interpreted per the brief (the tool is currently a solo-creator, single-host
  app); several Critical findings are about exposure that only matters once it leaves localhost.
- Effort sizes (S/M/L, day ranges) assume one experienced engineer familiar with this stack.
- `.shazam_cache/` (1,236 entries) and `.fingerprints/` are correctly gitignored; only
  `rename_history.jsonl` and personal paths in `config.py` are the tracked-data concerns.
