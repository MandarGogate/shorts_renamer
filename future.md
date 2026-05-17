# Future Roadmap

ShortsSync is mainly used by a solo creator to rename short dance videos from the
audio track. The next work should reduce rename mistakes, speed up daily batches,
and make the final upload queue easier to trust.

## Fix First

- Preserve full song titles before adding tags. Current generated names can cut
  parenthetical credits such as featured artists when the title plus tags exceeds
  the length limit.
- Add a real dry-run and confirmation mode to CLI video renaming. The CLI prints
  proposed names but currently proceeds automatically.
- Support Shazam-only matching in the web app. The CLI supports it, but the web
  flow still requires a reference index and `fpcalc`.
- Make the web "Save New Audio" option visible when Shazam is available.
- Avoid overwriting or failing late when two files resolve to the same target in
  monitor mode, GUI mode, or CLI commit mode.
- Log web and GUI renames to `rename_history.jsonl` so all rename history is in
  one place.

## Daily Creator Workflow

- One-click "Process Upload Queue" mode:
  scan the configured video folder, identify audio, stage proposed names, approve,
  rename, and optionally move to `_Ready`.
- Batch review with keyboard shortcuts:
  approve, skip, edit title, replay audio snippet, and commit selected items.
- Shazam-only quick mode:
  skip reference-library indexing and name videos directly from Shazam results.
- Confidence bands:
  separate high-confidence auto-approvals from ambiguous matches that need review.
- Duplicate audio grouping:
  show clips using the same song so the creator can avoid posting too many similar
  dance videos close together.

## Naming Features

- Naming templates:
  examples: `{artist} - {title} {tags}`, `{title} - dance trend {date}`,
  `{artist} {title} #dance #shorts`.
- Stable tag presets per platform:
  YouTube Shorts, TikTok, Instagram Reels, and no-tags archive mode.
- Smart title cleanup:
  keep featured artists, remove "TikTok version", normalize remixes, and preserve
  non-English characters when supported by the filesystem.
- Collision strategy settings:
  append `_2`, append date, append source clip id, or ask during review.
- Maximum filename length setting:
  reserve space for extension and tags instead of truncating song metadata first.

## Audio Matching

- Better Shazam result matching:
  use artist/title token scoring in web mode, not just substring matching.
- Optional "accept any Shazam result" in web mode:
  useful when the creator does not maintain a reference library.
- Slowed/sped-up detection presets:
  common dance edit speeds such as 0.75x, 0.8x, 1.1x, and 1.25x.
- Audio snippet preview:
  play the extracted audio next to the proposed Shazam result before approval.
- Cache maintenance tools:
  show cache size, clear stale entries, and explain why a cache was reused.

## Queue And History

- Rename undo:
  restore selected files from `rename_history.jsonl`.
- Upload queue dashboard:
  show unprocessed, staged, approved, renamed, and moved-to-ready counts.
- History search filters:
  by artist, song, date, method, and output folder.
- Repeat-song warnings:
  warn when a newly renamed clip uses a song that appeared in recent batches.
- Export batch report:
  CSV or markdown list of original filename, new filename, song, method, and date.

## Quality And Safety

- Add tests around long Shazam names, parentheses, duplicate targets, CLI dry-run,
  web Shazam-only mode, and hidden web options.
- Use a shared matching and rename service for CLI, GUI, and web so behavior does
  not drift between entry points.
- Validate target paths consistently in CLI and GUI, matching the safer web
  validation.
- Store user-specific config outside tracked source files so personal directory
  changes do not dirty the repo.
- Add an example sample-media test fixture or synthetic audio generator for
  repeatable local smoke tests.

