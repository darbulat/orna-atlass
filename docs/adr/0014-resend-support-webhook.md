# ADR-0014: Forward inbound support e-mail through a signed Resend webhook

- Status: accepted
- Date: 2026-08-03

## Context

ORNA publishes `support@orna.land` as the customer-support address in its legal and purchase
journeys. Resend provides inbound routing for that address, but an inbound event contains only
provider identifiers and metadata; the application must retrieve the received message before it can
forward the complete body and attachments to the operational owner.

The webhook is internet-facing, has no ORNA user session, and can trigger an outbound e-mail side
effect. A forged event, a valid event for another recipient, or an ambiguous retry after a successful
send must not produce unsolicited or duplicate forwarding. Conversely, an outage while retrieving or
forwarding a valid support message must remain visible to Resend as a retryable failure rather than
being acknowledged as success.

## Decision

The API owns a hidden `POST /api/v1/support/webhooks/resend` integration boundary. It verifies the
Svix message ID, timestamp and signature over the exact raw request body using the configured Resend
webhook secret and a five-minute tolerance. Invalid or stale requests fail before any provider API
call. A valid event is actionable only when its type is `email.received` and its recipient allowlist
contains exactly `support@orna.land` after case and surrounding-whitespace normalization; other valid
events are acknowledged without side effects.

For an actionable event, the Resend integration retrieves the received body and a bounded attachment
page, then downloads the recorded attachments through a separate client that never carries the
Resend API authorization header. It sends a new message from the configured ORNA support sender to
the configured operational owner. The original sender becomes `Reply-To`. The outbound request uses
a stable idempotency key derived from the verified Svix message ID, so retries after an ambiguous
send do not create a second forwarded message. Provider retrieval, download or send failures
propagate as non-success webhook responses and remain eligible for Resend retry.

`RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET` and `SUPPORT_FORWARD_TO` are an all-or-none configuration;
the webhook secret must decode from the provider `whsec_` format to at least 16 key bytes.
`SUPPORT_FROM_EMAIL` is separately configurable. Secrets remain environment-only, HTTPX success logs
are suppressed because provider download URLs may contain query credentials, and attachment-download
failures are re-raised without the credential-bearing URL. The webhook is excluded from the generated
public OpenAPI contract. This integration adds no database state or migration.

## Consequences

Inbound support forwarding is recipient-restricted, signature-authenticated and fail-closed. The API
does not acknowledge a valid support message until Resend has accepted the idempotent outbound send,
which gives simple recovery without introducing a queue or a new persistence lifecycle.

The synchronous provider calls increase webhook latency and couple availability to Resend's receive,
attachment and send APIs. This is acceptable for the expected low support-mail volume, but sustained
volume or provider retry-window requirements may justify a future durable inbox/worker design. The
initial attachment fetch is bounded to one provider page of at most 100 items; messages beyond that
operational bound require an explicit pagination decision rather than silent broad resource use.

Direct mailbox forwarding was rejected because it cannot enforce the application-level recipient,
signature and retry contract. Acknowledge-then-process was rejected because, without durable queue
state, process failure would lose the support message. Logging message bodies, addresses, API keys,
webhook secrets or attachment contents remains forbidden.
