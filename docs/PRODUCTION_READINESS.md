# Parliament Pulse Nepal TV — Production Readiness

## Purpose
This repository should produce 2 Long + 2 Short per day, split between morning and evening, while optimizing for accuracy, provenance, audience value, platform compliance and sustainable operations rather than maximum clip volume.

## Current V2 pipeline
1. Discover both Parliament Houses.
2. Download a bounded source pool.
3. Transcribe with Faster-Whisper.
4. Clean transcripts.
5. Select transcript-grounded story windows.
6. Normalize exact rendered windows.
7. Translate subtitles and topic summaries.
8. Generate English-first metadata.
9. Validate neutrality, titles, source attribution and hooks.
10. Run editorial/repetition gate.
11. Build human review queue.
12. Create publication ledger.
13. Render cold-open hooks and story windows.
14. Assemble masters and thumbnails.
15. Run technical QC.
16. Upload test artifacts.

## Major production gaps to close

### 1. Source provenance
- Preserve the exact official Parliament source URL for every story.
- Preserve source page title, collection, House, discovery timestamp and downloaded-file hash.
- Never infer a member name from a procedural label.
- If a member name is unavailable, use House + source-page attribution rather than inventing one.

### 2. Editorial quality
- Reject low-confidence or garbled transcript windows.
- Prefer substantive parliamentary discussion over procedural-only clips.
- Prefer both Houses across the daily Long set when eligible material exists.
- Keep Long and Short source pools separate.
- Add topic diversity so four daily posts do not become four versions of one issue.
- Keep ambiguous attribution or weak transcript quality in the human-review queue.

### 3. Duplicate protection
Add persistent protection against the same source window being published twice, near-identical hooks/titles, repeated clips across days, and excessive reuse of one Parliament recording.
Use source URL + timestamps + transcript similarity + perceptual audio/video fingerprints.

### 4. Copyright and rights record
Store source URL, download timestamp, source title, edit timestamps, transformation notes, publication URLs and claim/takedown status. Do not assume that official-source status automatically means every downstream use is unrestricted.

### 5. YouTube monetization safety
YouTube says monetized content should be original/authentic and not generic, repetitive, mass-produced or manipulative. Similar formats can be monetizable when the substance materially varies and provides viewer value. citeturn0search0
For this project: distinct topic selection, meaningful editing/context, accurate attribution, no invented identities, no sensational metadata, no fake engagement, and no automatic publication after a failed gate.
No system can guarantee YPP approval or monetization.

### 6. YouTube publication state machine
Use: GENERATED -> QC_PASS -> EDITORIAL_REVIEW -> APPROVED -> UPLOADED_PRIVATE -> SCHEDULED -> PUBLISHED -> VERIFIED.
YouTube supports scheduled publication through a private video publishAt value, and OAuth is required for upload/channel-management operations. Unverified API projects can be restricted to private uploads until the required audit is completed. citeturn0search1turn0search2turn0search3

### 7. Cross-platform adapters
Current repository has YouTube upload capability. Facebook, Instagram and TikTok should be separate adapters with credential checks, platform-specific media validation, metadata mapping, upload/schedule, retry, idempotency, returned post ID/URL, status reconciliation and failure reporting.
Never mark a platform as published until the platform returns a verified post identifier.

### 8. Analytics feedback loop
Build publish -> metrics -> analysis -> selection-weight update -> publish.
Track reach/impressions, views, watch time, retention, completion rate for Shorts, CTR where available, likes/comments/shares/saves, subscribers gained, traffic source, slot, topic, House, source speaker and hook strategy.
The system should learn from content performance without learning political preferences or ranking politicians.

### 9. Audience/community layer
Add comment moderation, spam filtering, factual-correction workflow, source-link reply templates, viewer-question collection and a topic backlog. Do not automate political persuasion or replies that impersonate a human political commentator.

### 10. Thumbnail system
Use a consistent visual identity with story-specific variation: one clear subject, short readable text, no fake quotes, no misleading imagery and mobile-first composition.

### 11. Scheduling
GitHub Actions supports scheduled workflows and timezone-aware schedules. citeturn1search0turn1search2
Target: morning = 1 Long + 1 Short; evening = 1 Long + 1 Short. Exact times should later be chosen from audience analytics rather than assumed.

### 12. Compute/cost — critical
Current V2 runs take roughly 1–3 hours because CPU transcription dominates.
If this repository is private, GitHub-hosted runners consume the account's included Actions minutes; GitHub Free currently includes 2,000 minutes/month. Public repositories using standard hosted runners are free. citeturn2search0turn2search2
Long-term, move heavy media processing to a self-hosted GPU, dedicated GPU VM or other batch compute service. GitHub Actions should primarily orchestrate the pipeline.

### 13. Storage
Do not use GitHub Actions artifacts as the permanent media archive. Keep code/config in GitHub, media in object storage, state/analytics in a database or durable ledger, and temporary files only on the processing runner.

### 14. Secrets
Keep all platform credentials in GitHub Secrets/Environment Secrets, never in the repository. Rotate any credential that was previously exposed. Use least-privilege scopes and separate staging/production credentials. Production publishing should use an environment approval gate.

### 15. Reliability
Add retries/backoff, partial-run resume, cached Whisper assets, idempotent content IDs, concurrency locking, failure notifications, post-publish verification and rollback/takedown procedures.

### 16. Audit trail
Every published item should answer: what was published, why it was selected, which official source produced it, which timestamps were used, what edits were made, what approved it, where it was published, and what happened afterward.

## Target architecture
Parliament discovery -> source manifest -> download -> transcription -> transcript QC -> editorial selection -> duplicate/fingerprint gate -> metadata/subtitles -> human review -> render -> technical QC -> publication ledger -> platform adapters -> publish/schedule -> verification -> analytics -> editorial learning.

## Do not automate blindly
- Speaker identity
- factual claims not present in the source
- political persuasion
- winner/loser framing
- allegations presented as facts
- comments pretending to be a human
- publication after failed QC
- monetization guarantees

## Production-ready checklist
- [ ] V2 2+2 build passes repeatedly
- [ ] Both Houses represented in Long content when eligible material exists
- [ ] No procedural label treated as a person's name
- [ ] Every story has an official source page
- [ ] Transcript quality gate passes
- [ ] No duplicate/near-duplicate source windows
- [ ] Human review can approve/reject each item
- [ ] YouTube private upload works reliably
- [ ] Scheduled YouTube publishing is verified
- [ ] Facebook adapter verified
- [ ] Instagram adapter verified
- [ ] TikTok adapter verified
- [ ] Publication ledger stores platform post IDs
- [ ] Post-publish verification works
- [ ] Analytics collection works
- [ ] Failure alerts work
- [ ] Secrets are protected and rotated
- [ ] Heavy compute cost is sustainable
- [ ] Rollback/takedown process exists

## Earning and growth reality
Automation can reduce production effort but cannot guarantee growth or monetization. The durable value comes from consistent publishing, accurate and useful editorial selection, recognizable channel identity, strong viewer satisfaction, repeat viewers and an analytics feedback loop.
Future revenue layers can include platform ads where eligible, sponsorships, memberships, licensing/partnerships and other clearly disclosed commercial relationships. Build these only after the editorial and platform foundations are stable.