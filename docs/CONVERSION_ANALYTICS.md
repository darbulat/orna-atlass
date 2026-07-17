# Conversion analytics

ORNA Atlas measures the public listening funnel with privacy-bounded counters. The browser sends allowlisted event names and placements to `POST /api/v1/analytics/events`; the API exposes the aggregate through `/metrics` as `orna_conversion_events_total`.

## Funnel

| Stage | Event | Placement |
|---|---|---|
| Homepage sample starts | `sample_play_started` | `hero_sample` |
| Thirty seconds listened | `listening_30_seconds` | `global_player` |
| Five minutes listened | `listening_5_minutes` | `global_player` |
| Early-access CTA selected | `membership_cta_clicked` or `final_cta_clicked` | Allowlisted CTA placement |
| Account registration succeeds | `registration_completed` | `membership_form` |

Listening milestones are emitted once per threshold for the selected playback session. Seeking is not counted as listening.

## PromQL examples

Events accumulated over the selected dashboard range:

```promql
sum by (name) (increase(orna_conversion_events_total[$__range]))
```

Thirty-second retention among sample starts:

```promql
sum(increase(orna_conversion_events_total{name="listening_30_seconds"}[$__range]))
/
clamp_min(sum(increase(orna_conversion_events_total{name="sample_play_started"}[$__range])), 1)
```

Five-minute depth among thirty-second listeners:

```promql
sum(increase(orna_conversion_events_total{name="listening_5_minutes"}[$__range]))
/
clamp_min(sum(increase(orna_conversion_events_total{name="listening_30_seconds"}[$__range])), 1)
```

Registration completions:

```promql
sum(increase(orna_conversion_events_total{name="registration_completed"}[$__range]))
```

These are event ratios, not unique-user conversion rates. The implementation intentionally does not create a user or device identifier.

## Privacy and cardinality rules

The ingestion contract accepts only `name` and `placement`, both as closed enums. Additional properties are rejected. The browser bridge strips navigation destinations, session slugs and any unknown properties before sending. Cookies are omitted from analytics requests.

Do not add email addresses, user IDs, IP addresses, arbitrary URLs, session slugs or free-form campaign values as Prometheus labels. Any new label value must be bounded in the API schema and covered by contract tests.

## Operational limits

The counters are suitable for aggregate product signals and deployment dashboards. They are not an audit log, billing source, attribution system or proof of unique users. Public counters can be influenced by automated traffic; bot filtering and a hosted analytics backend remain deployment concerns.
