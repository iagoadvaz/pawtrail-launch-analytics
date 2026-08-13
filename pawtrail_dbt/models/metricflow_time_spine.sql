-- Required scaffolding for the dbt Semantic Layer: `dbt parse` refuses to
-- parse any project that declares semantic models unless a day-grain (or
-- finer) time spine model exists (see
-- https://docs.getdbt.com/docs/build/metricflow-time-spine). This project has
-- no dbt_utils dependency, so the spine is built with DuckDB's native
-- generate_series rather than dbt_utils.date_spine. The range comfortably
-- brackets the launch window (LAUNCH_DATE = 2026-01-05, observed signup dates
-- run 2026-01-06 through 2026-05-03) with slack on both sides for metrics
-- using `offset_window`.
{{
    config(
        materialized = 'table',
    )
}}

select
    cast(generate_series as date) as date_day
from generate_series(cast('2020-01-01' as date), cast('2030-12-31' as date), interval 1 day)
