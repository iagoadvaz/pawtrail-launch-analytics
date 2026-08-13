# PawTrail Launch Dashboard

Published Tableau Public workbook: **Pending** — this workbook has not yet been published to Tableau Public. The control_*.csv files in this directory are ready; see Task 16 in the implementation plan for the steps to build and publish it.

Built from the semantic-layer metric exports in this directory
(`control_*.csv`), generated via `mf query` — see
`docs/superpowers/plans/2026-08-12-pawtrail-launch-analytics.md` Task 15.

## Views

1. Launch pulse — cumulative and weekly new subscriptions, attach rate trend
   (national and by region)
2. Activation — 7-day digital, kit SLA, and combined 30-day activation rates
   over time, with the mature cohort size behind each rate
3. Kit operations — on-time delivery rate by state
4. Acquisition efficiency — CAC and cost per activated account by channel,
   win rate by state
5. Customer Success queue — at-risk accounts split by failure driver

## Reading the activation rates

Activation rates are computed on the **mature cohort** only: accounts that have
had the full window (7, 10, or 30 days) to activate. Recent signups are excluded
from the denominator until their window closes rather than being counted as
failures, so the most recent weeks show a smaller cohort rather than an
artificially collapsing rate.

## Data freshness

This dashboard is a static snapshot of a simulated 0–120 day launch window,
not a live-refreshing operational dashboard. It was built from a one-time
export of the `control_*.csv` files in this directory; Tableau Public does
not support live connections to the local DuckDB warehouse. If the
generator, seed, or dbt models change after publishing, the CSVs and
published workbook must be regenerated and re-published manually (see
Task 20, Step 5 for the drift check).
