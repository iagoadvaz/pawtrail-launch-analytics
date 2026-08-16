# Code Review: PR #1 vs. Launch Analytics Plan

- **PR:** https://github.com/iagoadvaz/pawtrail-launch-analytics/pull/1 (`worktree-implement-pawtrail-launch` → `master`)
- **Reviewed against:** `docs/superpowers/plans/2026-08-12-pawtrail-launch-analytics.md`
- **Effort:** medium
- **Date:** 2026-08-14

## Summary

The two most severe findings are the same class of bug: a metric averaging an
already-aggregated per-week ratio instead of weighting by volume. This biases
the CAC-payback and contribution-margin unit-economics numbers toward
low-volume early weeks. There's also a genuine cross-model mismatch in how
"zero tasks completed" is defined between the CS-facing at-risk queue and the
semantic-layer KPI. The remainder are a stale plan-doc acceptance check and
minor duplication cleanups.

`--comment` was requested but the findings were not posted to the GitHub PR —
recorded here instead.

## Findings

### 1. `avg_cac_payback_months` averages per-week ratios, not totals

- **File:** `pawtrail_dbt/models/marts/_semantic_models.yml:302`
- **Category:** correctness
- **Verdict:** CONFIRMED

`avg_cac_payback_months` averages the already-computed per-(channel, week)
ratio `cac_payback_months` instead of computing total spend / total
contribution margin — an average-of-ratios bug.

**Failure scenario:** Early launch weeks have tiny `new_subscriptions`
denominators (`fct_weekly_channel_economics.sql:82-85`), producing huge or
erratic per-week payback values. Averaging those weeks equally with
high-volume later weeks pulls the dashboard's "Estimated CAC Payback" metric
well above the economically correct volume-weighted figure, with no test
bounding payback to catch it.

### 2. `avg_contribution_margin` is an average-of-averages

- **File:** `pawtrail_dbt/models/marts/_semantic_models.yml:293`
- **Category:** correctness
- **Verdict:** CONFIRMED

`avg_contribution_margin` averages
`fct_weekly_channel_economics.contribution_margin_per_subscription`, which is
itself `avg(contribution_margin)` already computed per (channel, week) — the
same unweighted-by-volume bias as finding #1.

**Failure scenario:** Weeks with very few subscriptions get equal weight to
weeks with hundreds when `contribution_margin_per_subscription` is aggregated
across weeks, biasing the reported per-account margin toward whatever
pet-tier mix occurred in sparse early weeks rather than the true
volume-weighted average.

### 3. `onboarding_gap` and the `zero_task_accounts` KPI use different maturity windows

- **File:** `pawtrail_dbt/models/marts/fct_at_risk_accounts.sql:20`
- **Category:** correctness
- **Verdict:** CONFIRMED

The at-risk queue gates the "no tasks completed" flag on
`days_observed >= at_risk_no_login_days` (14), while the semantic layer's
`zero_task_accounts` KPI gates the identical zero-tasks condition on
`is_mature_30d`.

**Failure scenario:** An account with `days_observed=20` and zero completed
tasks is included in `fct_at_risk_accounts` and routed to the CS queue as
`risk_driver='onboarding_gap'`, while the same account is excluded from the
`zero_task_accounts` KPI (needs 30-day maturity) — the CS queue and the
reported KPI disagree on which accounts count as "did zero tasks," for two
windows independently tunable in `dbt_project.yml`.

### 4. `zero_digital_access_accounts` mixes two independently-tunable windows

- **File:** `pawtrail_dbt/models/marts/_semantic_models.yml:128`
- **Category:** correctness
- **Verdict:** PLAUSIBLE

`zero_digital_access_accounts` combines `no_digital_access_14d` (from
`var('at_risk_no_login_days')`) with `is_mature_combined_14d` (from
`combined_activation_mid_window_days` / `kit_sla_days`) — two vars
`dbt_project.yml` documents as intentionally independent, currently both 14.

**Failure scenario:** Retuning either `at_risk_no_login_days` or
`combined_activation_mid_window_days` independently — a plausible future edit
per the `dbt_project.yml` comments — silently misaligns the no-login window
against the maturity gate with no compile error, quietly corrupting this
early-warning metric's cohort.

### 5. Exhaustiveness test ignores which risk flag is true

- **File:** `pawtrail_dbt/tests/assert_risk_driver_is_exhaustive.sql:11`
- **Category:** test-coverage
- **Verdict:** CONFIRMED

The test only fails when a row with any risk flag is labeled `'healthy'`; it
never checks that `risk_driver` matches which specific flag is true, so it
can't catch a mislabeled-but-non-healthy row.

**Failure scenario:** If the `CASE` branch order in
`fct_at_risk_accounts.sql:39-43` is ever reordered (e.g. `no_tasks_completed`
checked before `kit_failed_sla`), an account with a physical delivery failure
could be routed to `'onboarding_gap'` instead of `'physical_failure'`,
misdirecting it to the wrong CS team — and this "exhaustive" test would still
pass.

### 6. Plan's acceptance commands reference stale (pre-rename) identifiers

- **File:** `docs/superpowers/plans/2026-08-12-pawtrail-launch-analytics.md:3562`
- **Category:** documentation
- **Verdict:** CONFIRMED

Task 15's acceptance-verification/CSV-export command blocks still reference
pre-rename group-by identifiers (e.g. `kit_deliveries__state`) even though
Task 14's own note renamed these to entity-qualified forms (e.g.
`account__state`) earlier in the same document.

**Failure scenario:** The shipped CSVs are correct, but the plan's own
literal acceptance gate for the SLA-based North Star can't be re-run
verbatim; a future reseed hits `mf query` errors on these group-bys, and the
natural workaround of dropping/substituting the group-by means this
regression check silently stops being exercised.

### 7. Propensity sampler duplicated across generators

- **File:** `generator/generate_subscriptions.py:72`
- **Category:** reuse
- **Verdict:** CONFIRMED

The deterministic-spread propensity sampler
(`rng.permutation(np.linspace(*range, num=len(x)))`) is duplicated verbatim
in `generator/generate_business_data.py:80` instead of a shared helper.

**Failure scenario:** If the sampling strategy needs a fix (e.g. an
off-by-one in `num=len(...)`, or switching distributions), it must be changed
in both files in lockstep; a third propensity-driven field is likely to get a
third hand-copy rather than reuse.

### 8. Surrogate-key construction duplicated across marts

- **File:** `pawtrail_dbt/models/marts/fct_weekly_channel_economics.sql:61`
- **Category:** reuse
- **Verdict:** CONFIRMED

Composite surrogate-key construction
(`<col> || '_' || cast(<week_col> as varchar)`) is duplicated in
`fct_weekly_attach.sql:57` instead of a shared macro.

**Failure scenario:** If the key format needs to change (e.g. to
`dbt_utils.generate_surrogate_key` to avoid collisions when state/channel
values contain underscores), both mart models must be edited identically,
and a missed edit would silently produce inconsistent key formats between
the two marts.
