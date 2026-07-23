---
name: optimize-query
description: "Diagnose and optimize ORNA Atlas SQLAlchemy, PostgreSQL, and PostGIS queries. Use for slow endpoints, N+1 loading, unstable pagination, excessive rows or memory, missing indexes, spatial plans, or cache-query interactions."
---

# Optimize an ORNA Query

## Prove the bottleneck

1. Read the affected repository flow, service policy, tests, migrations, and relevant domain rules.
2. Preserve a regression test for result membership, ordering, pagination, visibility, and access before tuning.
3. Measure query count, returned and scanned rows, latency, and representative cardinality on disposable data.
4. Capture `EXPLAIN` output and use `EXPLAIN (ANALYZE, BUFFERS)` only against safe non-production data.

## Improve the query shape

- Keep SQL construction and loading policy in the repository; keep transactions and cache orchestration in the service.
- Push bounded filtering, ordering, pagination, and aggregation into PostgreSQL instead of hydrating unbounded ORM graphs.
- Eliminate N+1 loading deliberately and fetch only columns required by the explicit DTO projection.
- Preserve stable tie-breakers and one coherent SQL page for mixed search results.
- Preserve `published` and caller-access filters plus hidden-location exclusion in every optimized path.
- Keep public geometry separate from exact geometry and avoid exposing either storage column through ORM serialization.
- Keep bbox, clustering, and dawn-nearest work indexable with PostGIS; preserve anti-meridian handling and bounded adjacent-meridian KNN scans.
- Add or change indexes only through Alembic, and verify that representative plans use them.
- Include every policy-changing input in cache keys and invalidate only after a successful commit.

## Verify behavior and cost

1. Compare before-and-after plans and measurements at realistic cardinality.
2. Run the focused unit or integration regression first.
3. Run `python -m pytest` and `python -m ruff check .`.
4. Run the applicable opt-in PostgreSQL/PostGIS integration test, including upgrade and downgrade checks for index migrations.
5. Report the measured improvement, preserved semantics, dataset limits, and any unverified production assumptions.
