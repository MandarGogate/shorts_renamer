# Bytebreed Product Roadmap

Date: 2026-03-22
Owner: Product Manager
Status: Planning

## Goal

Turn ShortsSync into the control layer for short-form audio-led content operations.

The next step is not a generic content platform. The next step is a product that helps a creator move from "I downloaded or exported a batch" to "I reviewed it, renamed it, organized it, and know what to reuse next."

## Product Call

Stay close to the current wedge:

1. ingest short-form assets
2. identify the audio and the likely trend source
3. review and approve rename decisions fast
4. package outputs into a clean upload queue
5. learn which audio patterns deserve another batch

Do not jump to rendering, collaboration, or direct publishing yet. ShortsSync still has headroom inside its existing workflow.

## Current Starting Point

ShortsSync already has a real base:

- CLI, GUI, monitor mode, and web access
- Chromaprint matching plus Shazam lookup
- slowed-audio support
- download helpers and MP3 workflows
- rename history and fingerprint caching

The weak point is the layer after matching:

- match results are hard to triage at batch scale
- the reference library can get messy and drift away from canonical naming
- naming is too flat for campaign-based output workflows
- automation is present but not packaged as an always-on intake system
- rename history does not tell the creator what to reuse next

## Roadmap

### 1. Match Review Queue

Problem:
The product can find matches, but batch review is still a log-and-table workflow. That slows down creators when confidence is mixed or multiple videos map to the same audio trend.

User outcome:
A creator can process a large batch, review only the files that need judgment, and approve the rest in one session.

Scope:

- Add a dedicated review queue above the current match results table.
- Group results by confidence band, matched audio, and processing batch.
- Add actions for `approve`, `skip`, `needs manual rename`, and `send to retry`.
- Keep approved items staged until the creator commits the rename batch.
- Show the reason behind low-confidence matches so the creator knows what to inspect.

Acceptance criteria:

- A creator can review 50 videos in one queue without scanning raw logs.
- High-confidence matches can be approved in bulk.
- Low-confidence matches are visually separated from ready-to-commit items.
- The staged batch survives page reloads until the user commits or clears it.

Tradeoff:
Do not build a full project system here. The first win is faster review inside the existing rename flow.

### 2. Reference Library Manager

Problem:
The reference library is the product's core asset, but today it is still folder-first. Duplicate tracks, Shazam naming drift, slowed variants, and weak metadata reduce matching quality over time.

User outcome:
A creator can keep one clean, trustworthy audio library that improves matching and reuse every week.

Scope:

- Add a reference-library view with canonical title, source file, variant type, and last-used time.
- Detect duplicates, near-duplicates, and slowed variants under one canonical track.
- Add "promote Shazam result to canonical name" and "merge into existing track" actions.
- Surface tracks that frequently power renamed outputs.
- Let creators mark tracks as `active`, `archive`, or `ignore`.

Acceptance criteria:

- A creator can clean up duplicate reference entries without leaving the product.
- Slowed and original variants can be grouped under one canonical track.
- New Shazam-discovered audio can be reviewed before it pollutes the main library.
- The system can rank the most reused reference tracks from rename history.

Tradeoff:
Skip third-party cloud sync. Better local library quality is the leverage point right now.

### 3. Naming Recipes And Output Packs

Problem:
The current rename flow is useful for organization, but it does not reflect the way creators prepare batches for different accounts, campaigns, or testing lanes.

User outcome:
A creator can turn one matched batch into output-ready files for a specific posting workflow without manual cleanup.

Scope:

- Add reusable naming recipes with variables such as artist, title, slowed label, hook tag, account, campaign, and sequence number.
- Add output pack presets that combine naming recipe, destination folder, and move/copy behavior.
- Support a preflight preview for the entire batch before rename.
- Add a post-rename summary with final filenames, destination folders, and conflicts resolved.

Acceptance criteria:

- A creator can save multiple output recipes and switch between them without editing config values manually.
- The rename preview clearly shows the final filename and destination for every item.
- Batch conflicts are surfaced before files move.
- A creator can send approved files straight into a defined upload queue folder.

Tradeoff:
Do not add platform publishing. The goal is to hand creators a clean upload-ready batch.

### 4. Always-On Intake Automation

Problem:
Monitor mode exists, but the product still feels like a tool the creator has to babysit. Download, match, rename, and queue placement are not yet one clear intake pipeline.

User outcome:
A creator can point ShortsSync at an intake folder or download source and trust it to keep the upload queue fresh.

Scope:

- Package monitor mode as a first-class workflow in the web app.
- Add named intake pipelines that define source, matching mode, naming recipe, and destination.
- Add pipeline-level status, recent runs, failures, and retry actions.
- Connect download helpers to the same intake pipeline instead of leaving them as isolated utilities.

Acceptance criteria:

- A creator can configure one saved pipeline and rerun it without re-entering settings.
- New files entering the intake source are processed into the correct queue automatically.
- Failed items are visible with a retry path.
- Recent pipeline runs show inputs, outputs, and skipped files.

Tradeoff:
Avoid multi-step workflow builders. One saved pipeline per use case is enough for V1.

### 5. Experiment Ledger

Problem:
Rename history proves what happened, but it does not help the creator decide which audio patterns or naming approaches deserve another batch.

User outcome:
A creator can review past renamed outputs, record lightweight performance signals, and identify which source audio to reuse next.

Scope:

- Extend rename history into an experiment ledger.
- Let the creator record simple outcome fields such as posted, platform, views bucket, and keep/retire decision.
- Group outcomes by reference track, slowed/original variant, and naming recipe.
- Add a lightweight "reuse this audio" recommendation based on recent wins.

Acceptance criteria:

- A creator can attach outcome data to renamed batches without leaving the product.
- The product can show which reference tracks led to the most reused or successful outputs.
- A creator can filter history by track, date, or recipe.
- The system can generate a shortlist of tracks worth another batch.

Tradeoff:
Manual entry is acceptable. Direct TikTok, Reels, or Shorts integrations are not required for the first version.

## Recommended Sequence

### Now

Ship `Match Review Queue`.

Why:
This is the highest-leverage fix to the current workflow. It makes the existing engine easier to trust and easier to use at batch scale.

### Next

Ship `Reference Library Manager`.

Why:
Better library quality improves matching, naming, and long-term reuse without introducing a new product surface.

### Then

Ship `Naming Recipes And Output Packs`.

Why:
This turns rename output into a creator-specific operating workflow instead of a one-size-fits-all filename change.

### Later

Ship `Always-On Intake Automation`, then `Experiment Ledger`.

Why:
Automation and learning loops matter more after review, naming, and library quality are stable.

## Not Now

Do not prioritize these in the next cycle:

- video rendering templates
- direct social publishing
- team collaboration and permissions
- cloud storage integrations
- generic AI content ideation
- enterprise reporting

These features expand surface area faster than they improve the product's current core loop.

## Engineering Handoff

Use this build order:

1. add a persistent batch-review model on top of current match results
2. add bulk review actions and staged commits in the web app
3. add a canonical reference-library model and merge/archive actions
4. add naming recipes plus destination presets
5. add saved intake pipelines
6. add lightweight outcome fields on rename history

## Success Metric

The next product milestone is:

"A creator can move from raw batch to approved upload queue inside ShortsSync with less manual cleanup."

Supporting metrics:

- review time per 50-file batch
- approval rate without manual rename
- percentage of renamed files sent into a saved output pack
- percentage of reference tracks with canonical metadata
- number of repeat batches created from previously successful tracks
