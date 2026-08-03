# ADR-0015: Bound and service-own inbound support forwarding

- Status: accepted
- Date: 2026-08-03
- Supersedes: ADR-0014 where this record adds stricter service ownership and attachment bounds

## Context

ADR-0014 introduced the signed Resend inbound-support webhook. Exact-head review identified three
production lifecycle risks in the initial boundary: the HTTP router owned recipient policy and the
provider side effect directly, a forwarding destination equal to the inbound mailbox could create an
unbounded delivery loop, and attachment retrieval could silently omit another provider page or
buffer an unbounded aggregate payload.

These are integrity and resource-ownership concerns on the internet-facing webhook path. They must
remain fail-closed so Resend retries a valid event rather than receiving an acknowledgement for an
incomplete or unsafe forwarding attempt.

## Decision

The router verifies and translates HTTP/Svix input only. A support application service owns recipient
policy, stable idempotency-key construction and invocation of the Resend integration. Provider I/O
remains in the integration layer.

Startup validation rejects `SUPPORT_FORWARD_TO` when its parsed, case-normalized mailbox is
`support@orna.land`, including display-name forms. This prevents forwarded messages from re-entering
the same inbound route with new provider message IDs.

The integration requests one attachment page of at most 100 items. It fails retryably when Resend
reports another page, or when a full page omits pagination state and may therefore be truncated.
Attachment bodies are streamed through the unauthenticated download client and are limited to 25 MiB
in cumulative decoded content. A limit breach, non-2xx response or attachment transport failure is
raised as a sanitized retryable provider error before the outbound message is sent.

## Consequences

The support use case follows `router -> service -> integration`, recursive configuration fails at
startup, and a webhook cannot acknowledge silent attachment truncation or unbounded aggregate
buffering. Messages beyond the one-page or 25 MiB operational bounds remain retryable and require an
explicit future product decision rather than partial forwarding.

The synchronous webhook still depends on Resend availability and retains the stable provider
idempotency behavior established by ADR-0014. A future durable inbox/worker design may replace these
operational bounds, but must preserve signature verification, recipient restriction, sanitized
provider failures and exact attachment inventory semantics.
