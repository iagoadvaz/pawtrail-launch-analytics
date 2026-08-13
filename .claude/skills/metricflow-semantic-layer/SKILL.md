---
name: metricflow-semantic-layer
description: Use when editing a dbt Semantic Layer file (_semantic_models.yml or _metrics.yml), declaring a MetricFlow entity/measure/metric, or running mf validate-configs or mf query — since validate-configs passing does not mean a metric returns correct numbers at every grain the dashboard uses.
---

# MetricFlow Semantic Layer

## Overview

This area produced four independent failures across two review passes in this
project: a semi-additive measure aggregated with `agg: max` and mislabeled one
state's rate as the national trend, three semantic models missing
`agg_time_dimension` (which `mf validate-configs` rejects outright), and a
missing `DBT_PROFILES_DIR` export that made every `mf` command fail with a
misleading "no profile" error.

**Core principle:** `mf validate-configs` proves the YAML is well-formed and
every reference resolves. It does not prove a metric returns a sane number when
grouped the way the dashboard actually groups it — that requires querying it.

## When to Use

- Editing `_semantic_models.yml` or `_metrics.yml`.
- Declaring an `entity: type: primary` — before you do, prove uniqueness.
- Adding a measure — before you do, classify it additive / semi-additive /
  non-additive and record which `--group-by` dimensions are valid for it.
- Adding a `ratio` or `derived` metric — before you do, confirm numerator and
  denominator (or all referenced metrics) live in the same semantic model or
  have a valid join path.
- Any `mf` command — check `DBT_PROFILES_DIR` is set first.

## Checklist

1. **Prove entity uniqueness before declaring `type: primary`:**
   ```sql
   select account_id, count(*) from {{ ref('dim_accounts') }} group by 1 having count(*) > 1
   ```
2. **Every semantic model with measures needs `defaults: agg_time_dimension:`.**
   `mf validate-configs` rejects a measure-bearing semantic model without one —
   this is a hard requirement, not a style preference.
3. **Classify each measure's additivity and write down valid groupings as a
   comment.** Semi-additive measures (e.g. a rate already aggregated to
   `agg: max` or `agg: min`) sum correctly along time but not across the
   dimension they were pre-aggregated over — grouping by anything else silently
   mislabels one segment's value as the whole population's.
4. **Numerator/denominator of a ratio metric need a valid join path.** Same
   semantic model is simplest; cross-model requires entities that actually
   join.
5. **Always export before running `mf`:**
   ```bash
   export DBT_PROFILES_DIR="$PWD"
   ```
   `mf` has no `--profiles-dir` flag and silently falls back to
   `~/.dbt/profiles.yml`, which doesn't exist in this project.
6. **Don't stop at `mf validate-configs`. Query every metric at every grain the
   dashboard will actually use** before considering the task done:
   ```bash
   mf query --metrics <name> --group-by <dashboard_dimension>
   ```
   A metric that validates but returns a flat line or a single dominant row
   across a segment is a calibration or join bug, not a finished metric.

## Common Mistakes

| Mistake | Fix |
|---|---|
| Declaring `type: primary` without checking cardinality | Run the uniqueness query first |
| Missing `agg_time_dimension` on a measure-bearing model | Add `defaults: agg_time_dimension:` even if the dashboard never filters by time |
| `agg: max`/`agg: min` measure grouped by an unrelated dimension | Document valid groupings; add a comment explaining what the aggregation actually represents |
| Treating `mf validate-configs` as sufficient proof | Run `mf query` at each real dashboard grain before marking done |
| Forgetting `DBT_PROFILES_DIR` | Export it in the same shell session as every `mf` invocation |

## Where This Applies in This Project

See `docs/superpowers/plans/2026-08-12-pawtrail-launch-analytics.md`: Task 14
(`_semantic_models.yml`) and Task 15 (`_metrics.yml`, `mf validate-configs`,
the acceptance queries in Step 3, and the CSV exports in Step 4).
