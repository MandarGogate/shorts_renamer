# Bytebreed Product Roadmap

Date: 2026-03-21
Owner: Product Manager
Status: Planning

## Goal

Turn ShortsSync from a renaming utility into the first useful layer of a short-form content creation platform.

The product should help a creator move from "I have clips and audio" to "I have a ready-to-post batch with a clear reason to publish each variant."

## Product Call

Do not expand sideways into generic storage, team admin, or broad AI helpers yet.

The winning wedge is a fast creator loop:

1. Ingest source material.
2. Identify the reusable audio or format.
3. Package the best candidate into a remix brief.
4. Render clean variants.
5. Learn which variants earned another iteration.

## Current Starting Point

ShortsSync already does three useful jobs:

- It identifies audio across short-form video files.
- It renames and organizes batches across GUI, CLI, monitor, and web flows.
- It gives creators an asset-management utility for trend-heavy workflows.

What is missing is the layer above file management:

- No project or campaign concept.
- No structured remix workflow.
- No rendering system for variants.
- No growth loop that tells the creator what to make next.

## Roadmap

### 1. Creator Queue

Problem:
Creators can identify files, but they cannot decide what deserves production attention next.

User outcome:
A creator can review imported clips, see the strongest reusable assets, and move selected items into a working queue in one session.

Scope:

- Add a "review queue" on top of the current library and rename flow.
- Group assets by matched audio, source pattern, and recency.
- Let the user promote an asset into a named project or campaign.
- Store a status per asset: `new`, `shortlisted`, `ready_for_remix`, `done`.

Acceptance criteria:

- A creator can ingest a folder and see grouped candidates without leaving the product.
- A creator can shortlist at least 20 assets in one review session.
- The queue persists between sessions.
- The shortlist can be exported as structured JSON or CSV for downstream jobs.

Tradeoff:
Skip collaboration and permissions here. Single-user speed matters more than shared access.

### 2. Remix Briefs

Problem:
The product finds audio matches, but it does not help the creator turn a selected asset into a repeatable content brief.

User outcome:
A creator can turn any shortlisted asset into a structured brief that tells editing or automation exactly what to produce.

Scope:

- Add a remix brief object tied to a shortlisted asset.
- Capture the minimum fields that shape execution:
  - hook
  - format
  - target duration
  - caption direction
  - CTA
  - tags
  - notes on pacing or text overlays
- Add reusable brief templates for common short-form patterns.
- Allow one asset to generate multiple briefs when a creator wants to test variants.

Acceptance criteria:

- A creator can create a brief in under two minutes.
- A brief can be duplicated into a new variant without manual re-entry.
- Briefs can be exported as machine-readable input for rendering or editing pipelines.

Tradeoff:
Do not build LLM-generated creative ideation first. Structured inputs and templates are enough for V1.

### 3. Variant Rendering Pipeline

Problem:
The workflow stops before the creator has production-ready outputs.

User outcome:
A creator can generate several publishable variants from one brief without rebuilding each version manually.

Scope:

- Add a render job model with queued, running, failed, and complete states.
- Support template-driven outputs such as caption overlays, end cards, aspect-safe crops, and filename conventions.
- Save each output under the parent project, brief, and source asset.
- Keep the first version narrow: local rendering with deterministic templates.

Acceptance criteria:

- A creator can launch at least three output variants from one brief.
- Each render keeps an auditable link back to source asset and brief.
- Failed renders are visible and retryable.

Tradeoff:
Do not add social publishing in the first pass. Reliable output generation is the prerequisite.

### 4. Post-Publish Learning Loop

Problem:
The product does not close the loop between what was produced and what should be made next.

User outcome:
A creator can compare variants and see which hooks, formats, and audio patterns deserve another round.

Scope:

- Add lightweight result tracking per published variant.
- Capture metrics manually first if direct platform APIs are unavailable.
- Rank briefs and assets by outcome, not just by ingestion metadata.
- Feed winning patterns back into queue ranking and brief templates.

Acceptance criteria:

- A creator can record outcome data for each variant in one place.
- The system can surface top-performing hooks, formats, and source patterns.
- The review queue can sort by "patterns that already worked."

Tradeoff:
Manual entry is acceptable before direct TikTok, Reels, or Shorts integrations.

## Recommended Sequence

### Phase 1: 0 to 4 weeks

Ship the creator queue.

Why:
This is the first layer that converts file handling into a product workflow.

### Phase 2: 4 to 8 weeks

Ship remix briefs.

Why:
This creates a structured interface between creators and any future automation.

### Phase 3: 8 to 12 weeks

Ship local variant rendering.

Why:
This is the first point where Bytebreed starts acting like a creation platform instead of an organizer.

### Phase 4: after rendering is stable

Ship the post-publish learning loop.

Why:
Growth loops only matter once output creation is reliable.

## Not Now

Do not prioritize these yet:

- Multi-user collaboration
- Cloud storage integrations
- Direct social publishing
- Generic AI tag suggestion features
- Enterprise admin and permissions

These features increase scope faster than they improve the core creator loop.

## Engineering Handoff

If engineering needs one build order, use this:

1. Define the asset, project, brief, and render-job data model.
2. Add the creator queue to the web surface first.
3. Add remix brief creation and export.
4. Add deterministic local render jobs from briefs.
5. Add outcome tracking and queue ranking from results.

## Success Metric

The first platform-level success metric is:

"A creator can turn one batch of imported short-form assets into multiple tracked output variants inside Bytebreed."

Supporting metrics:

- Time from import to shortlist
- Number of briefs created per shortlisted asset
- Number of variants rendered per brief
- Percentage of rendered variants with recorded outcome data
