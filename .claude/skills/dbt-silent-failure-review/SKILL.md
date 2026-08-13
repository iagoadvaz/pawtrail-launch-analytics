---
name: dbt-silent-failure-review
description: Use when writing or reviewing a dbt model that joins tables, aggregates an already-aggregated column, or joins on a date boundary computed two different ways — before committing, since dbt build passes green even when a join silently drops or nulls rows.
---

# dbt Silent-Failure Review

## Overview

A `dbt build` that passes proves your declared tests pass, not that your model is
correct. The recurring failure in this project: a `LEFT JOIN` matched zero rows,
nulled three columns, and built green because the schema tests only covered
columns that could never be null (the CAC join in `fct_weekly_channel_economics`,
fixed in `4bd1336`).

**Core principle:** row counts and null counts before/after a join are cheap to
print and expensive to skip. Print them every time.

## When to Use

- Any model with a `join` (especially `left join`) before marking the task done.
- Any model declaring a primary/unique entity — verify the grain, don't assume it.
- Any aggregate (`sum`, `count`) applied to a column that is itself already an
  aggregate (cumulative sums, snapshot counts) — double-aggregation inflates
  silently.
- Any join where the two sides derive a date boundary independently (e.g.
  `date_trunc('week', ...)` on one side, a generator-supplied week-start column
  on the other) — a one-day offset makes every row miss.

## Checklist

1. **Row count before/after every join.** A `LEFT JOIN` that changes the row
   count you didn't expect, or that adds no rows but nulls a joined-in column,
   is the dangerous case — nothing in a default `dbt build` surfaces it.
   ```sql
   select count(*) as row_count, count(cac_column) as non_null_cac
   from {{ ref('fct_weekly_channel_economics') }}
   ```
2. **Assert the grain.** Run `select <key>, count(*) from {{ ref(model) }} group
   by 1 having count(*) > 1` before trusting a `unique` test result you haven't
   looked at directly.
3. **Trace both sides of a date-boundary join** back to how each was computed.
   If one side is `date_trunc('week', signup_date)` and the other is a raw
   `week_start_date` seeded elsewhere, confirm both land on the same weekday —
   don't assume it.
4. **Add `not_null` to any derived column that can only be null if a join
   failed** (a computed rate, a joined-in price, a joined-in spend figure).
   That test is what turns the silent failure into a loud one on the next run.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Testing only columns that structurally can't be null | Add `not_null` on the columns a failed join *would* null |
| Trusting `unique` test without checking cardinality assumptions | Query `group by key having count(*) > 1` directly once |
| Assuming two date columns share a boundary because both are "weekly" | Diff the actual dates for a few rows |
| Summing a column that's already a running total | Check whether the source column is a snapshot/cumulative value first |

## Where This Applies in This Project

See `docs/superpowers/plans/2026-08-12-pawtrail-launch-analytics.md`: Tasks 7–13b
(every staging/intermediate/marts model), especially Task 13
(`fct_weekly_channel_economics`, the archetype CAC join) and Task 11 (the
`fct_marketing_spend` / `dim_pricing` joins).
