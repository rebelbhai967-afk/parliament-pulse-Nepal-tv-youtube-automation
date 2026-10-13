# Remaining Automation + Posting Project

This workstream is isolated from the existing pipeline. Do not edit or replace existing files under `.github/workflows/` or `src/` as part of this workstream unless a change is explicitly reviewed and proven safe.

## Goal
Complete a zero-budget, Android-manageable GitHub Actions pipeline that:
1. Discovers current videos from official Nepal Parliament sources only.
2. Downloads media from those official source pages (not YouTube as a fallback).
3. Preserves the original Nepali audio and creates English subtitles.
4. Selects and renders 2 Long videos + 2 Shorts with metadata, thumbnails, and automated quality checks.
5. Uploads and schedules the approved outputs to YouTube.
6. Keeps run logs, audit records, and artifacts so failures can be diagnosed from a phone.

## Verified blockers from the existing pipeline audit
- The latest known V2 test run failed in the download stage because the downloader selected a YouTube URL and the GitHub-hosted runner received a YouTube bot-verification challenge.
- `src/download_multi.py` has an explicit Digital Parliament branch that searches for a YouTube “meeting video” link and then falls back to the first YouTube link. This conflicts with the official-source-only requirement.
- `.github/workflows/production.yml` already contains a manual YouTube publishing workflow and uses `YOUTUBE_CLIENT_SECRET_JSON` and `YOUTUBE_TOKEN_JSON`. It intentionally requires subtitle-review approval before publishing.
- The production workflow builds and uploads new videos itself; it does not consume the V2 test artifacts as a reusable input. Avoid running production until official-source download and a fresh build have passed quality checks.
- The current production workflow schedules YouTube uploads as private videos with a future `publishAt` time. The YouTube API credentials and token must remain repository secrets and must never be committed.

## Implementation order
1. Resolve official media URL extraction for both House of Representatives and National Assembly archive pages. Support the official video-page HTML/embedded player/API data; fail closed rather than silently choosing YouTube.
2. Add an isolated official-source download test that validates the final media URL's host and file signature before any expensive transcription/render work.
3. Run source discovery and download smoke tests; require source diversity from both Houses.
4. Run the complete build and validate exactly 2 Long + 2 Shorts, source attribution, English subtitle timing/readability, original audio retention, render integrity, and metadata.
5. Keep posting disabled until the test run is green and subtitles are reviewed. Then validate YouTube upload and scheduled-publication verification.
6. Add scheduled automatic runs only after the end-to-end workflow is proven. Add duplicate-publication protection using the publication ledger before enabling recurring posting.

## Acceptance criteria
- No changes to the existing `main` branch as part of this isolated workstream.
- Official Parliament source pages are recorded for every story.
- No YouTube downloader fallback is used for official-source downloads.
- Both Houses are represented; outputs are exactly 2 Long + 2 Shorts.
- QC passes before upload.
- Upload IDs and scheduled publication times are verified and stored in the audit artifact.
- Re-running a workflow does not accidentally publish duplicates.
- Any unresolved media/source failure stops the pipeline and produces an actionable error, not a fake-success artifact.

## Current status
This is a workstream definition, not a claim that the blockers have already been fixed. The next implementation task is official media URL extraction and a safe smoke test.
