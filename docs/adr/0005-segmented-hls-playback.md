# ADR-0005: Segmented sources produce inventory-gated private HLS

- Status: accepted
- Date: 2026-07-15

## Context

Long recording sessions can arrive as several immutable WAV objects whose combined size makes concatenating or materializing every source on one worker unsafe. HLS clients also request a manifest, initialization sections and many media fragments independently, while the bucket remains private.

## Decision

A recording session owns an ordered set of `RecordingSegment` rows, each permanently linked to one source `MediaAsset`. A session-scoped processing job fingerprints the ordered source set and processes one WAV at a time. Each source becomes AAC/fMP4 HLS with its own initialization section; the final VOD uses a continuous fragment namespace and `EXT-X-DISCONTINUITY` at source boundaries.

Every immutable output is uploaded and verified before `index.m3u8` is published. The rendition records the exact verified inventory and is activated only after manifest verification. Cleanup may delete only keys from such an inventory; unrestricted prefix deletion is forbidden.

Playback grants retain the existing authorization and audit checks. HLS grants issue a short-lived HMAC token scoped to the active rendition asset and expiry. A same-origin gateway validates the token, rendition readiness and exact inventory membership before proxying an object from private storage. Relative playlist URIs keep every child request under that scoped route. Legacy direct-file grants continue to use presigned object URLs.

BirdNET runs per source; local intervals are translated by the authoritative cumulative ffprobe duration before session-level persistence.

## Consequences

Workers need temporary capacity for one source plus its generated HLS part, not the whole session. A source boundary may be audible and requires an HLS discontinuity. Gateway traffic crosses the API until a compatible CDN signed-token boundary replaces it. Tokens in paths can appear in access logs, so they must be short-lived and logs must not be treated as public data.

## Rejected alternatives

- A combined WAV duplicates large source data and exceeds the bounded-disk requirement.
- Public bucket prefixes violate fail-closed playback.
- Thousands of embedded presigned fragment URLs create oversized manifests and cannot be refreshed coherently.
- Prefix-wide cleanup can delete unrelated or concurrently generated objects.

## Rollback

Stop creating segmented jobs and retain legacy direct-file playback. Existing HLS renditions remain immutable and can be archived using their recorded inventories. Schema downgrade is permitted only while the segmented tables are empty.
