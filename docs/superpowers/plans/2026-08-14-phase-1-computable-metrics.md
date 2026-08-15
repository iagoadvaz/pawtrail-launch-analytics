# Phase 1 — Metrics computable from the current seeds — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 12+ metrics the spec identifies as computable from the current seeds but absent today, making the claim at `METRICS.md:265` true again.

**Architecture:** Additive dbt layers. One new intermediate model (`int_billing_cycles`) establishes the billing-cycle clock derived from `pawtrail_signup_date` alone; four new marts (`fct_subscription_unit_economics`, `fct_fulfillment_waste`, `fct_weekly_channel_effective_cac`, `fct_state_saturation`) plus two transparency marts (`fct_censoring_register`, `fct_login_timing_distribution`) and one change to `fct_at_risk_accounts`. No existing model is rewritten — `dim_accounts` gains columns, `fct_at_risk_accounts` gains a classification, and everything else is new. **The generator is not touched in this phase.**

**Tech Stack:** dbt-core >=1.8,<1.12 + dbt-duckdb, DuckDB (local file `pawtrail_dbt/pawtrail.duckdb`), dbt Semantic Layer / MetricFlow via the `mf` CLI, pytest.

**Spec:** `/home/iagoadvaz/projects/pawtrail-launch-analytics/docs/superpowers/specs/2026-08-14-subscription-analytics-gap-scope.md` (§2, Phase 1; §6 global acceptance criteria)

## Global Constraints

- **Branch/worktree:** all work happens in a new worktree created from `worktree-implement-pawtrail-launch`. `master` contains only `docs/`.
- **dbt working directory:** all `dbt` and `mf` commands run from inside `pawtrail_dbt/`.
- **Python:** use the project venv — `.venv/bin/python`, `.venv/bin/dbt`, `.venv/bin/mf`. Do not use the system python (it has no duckdb installed).
- **Non-negotiable naming constraint (spec §1.1):** nothing may be named `rebill_rate`, `renewal_revenue` or `retained_mrr`. The cycle clock measures **exposure** to renewal, never the charge. Violating this is the gravest failure available in this project.
- **Thresholds live in vars:** every new business number goes into `vars:` in `dbt_project.yml`, following the established pattern. Never hardcoded in SQL.
- **Baseline to preserve:** `dbt build` PASS=123 (7 seeds, 20 models, 96 tests, 0 errors); `pytest` 22 passed. Each task only raises those counts.
- **`mf validate-configs` passing is NOT sufficient acceptance** (spec §6.6): every new metric requires an `mf query` at the grain the dashboard uses.
- **No `dbt_utils`** — the project has no `packages.yml`. Composite uniqueness is tested with a surrogate key plus a `unique` test, which is the pattern already in use (`channel_week_key`, `weekly_attach_key`).
- **DuckDB trap, verified empirically:** `DATE + INTERVAL (n) MONTH` returns a **TIMESTAMP**, not a DATE — always cast with `::date`. And **do not use `date_diff('month', ...)`** to count completed cycles: it counts month boundaries crossed, not whole months, returning 3 for 2026-01-05 → 2026-04-04 where the correct answer is 2. The cycle spine filtered by due date is what avoids this.
- **Mandatory local skills:** `cohort-metric-definition` before any windowed-rate SQL; `dbt-silent-failure-review` in every task that adds a join; `metricflow-semantic-layer` in every task that declares a metric; `plan-consistency-sweep` in the final task.

---

## File Structure

**New — intermediate models**
- `pawtrail_dbt/models/intermediate/int_billing_cycles.sql` — grain account × cycle index; the billing clock.

**New — marts**
- `pawtrail_dbt/models/marts/fct_subscription_unit_economics.sql` — grain account; per-cycle margin, allocated CAC, cycles to breakeven.
- `pawtrail_dbt/models/marts/fct_fulfillment_waste.sql` — grain account; COGS + shipping with no return.
- `pawtrail_dbt/models/marts/fct_weekly_channel_effective_cac.sql` — grain channel × week; loaded CAC.
- `pawtrail_dbt/models/marts/fct_state_saturation.sql` — grain state; penetration vs. remaining base.
- `pawtrail_dbt/models/marts/fct_censoring_register.sql` — grain metric name; immaturity exclusions.
- `pawtrail_dbt/models/marts/fct_login_timing_distribution.sql` — grain time-to-login band.

**Modified**
- `pawtrail_dbt/dbt_project.yml` — new vars.
- `pawtrail_dbt/models/marts/dim_accounts.sql` — cycle-exposure columns.
- `pawtrail_dbt/models/marts/fct_at_risk_accounts.sql` — `damage_class` and `recoverable_mrr_usd`.
- `pawtrail_dbt/models/marts/_semantic_models.yml` — new semantic models.
- `pawtrail_dbt/models/marts/_metrics.yml` — new metrics.
- `pawtrail_dbt/models/marts/_marts__core.yml`, `_marts__business.yml`, `_marts__risk.yml` — schema tests.
- `pawtrail_dbt/models/intermediate/_intermediate__models.yml` — cycle-clock tests.
- `METRICS.md` — dictionary; correction of line 265.
- `dashboard/README.md` — new CSVs.

**New — dbt singular tests**
- `pawtrail_dbt/tests/assert_no_cycle_past_observation.sql`
- `pawtrail_dbt/tests/assert_cost_to_recover_exceeds_cac.sql`
- `pawtrail_dbt/tests/assert_waste_accounts_are_disjoint.sql`
- `pawtrail_dbt/tests/assert_self_selected_have_no_delivery_defect.sql`
- `pawtrail_dbt/tests/assert_damage_class_covers_all_at_risk.sql`
- `pawtrail_dbt/tests/assert_damage_classes_are_non_degenerate.sql`
- `pawtrail_dbt/tests/assert_system_inflicted_not_concentrated_in_short_tenure.sql`

---

### Task 1: Worktree and the billing-cycle clock

**Files:**
- Create: `pawtrail_dbt/models/intermediate/int_billing_cycles.sql`
- Create: `pawtrail_dbt/tests/assert_no_cycle_past_observation.sql`
- Modify: `pawtrail_dbt/dbt_project.yml` (the `vars:` block)
- Modify: `pawtrail_dbt/models/intermediate/_intermediate__models.yml`

**Interfaces:**
- Consumes: `ref('stg_subscriptions')` — columns `account_id`, `pawtrail_signup_date`.
- Produces: model `int_billing_cycles` with columns `billing_cycle_key` (varchar, surrogate), `account_id` (varchar), `cycle_index` (integer, 0 = initial purchase), `renewal_due_date` (date), `observation_date` (date), `days_since_renewal_due` (integer). Tasks 2 and 3 depend on these exact names.

- [ ] **Step 1: Create the working worktree**

```bash
cd /home/iagoadvaz/projects/pawtrail-launch-analytics
git worktree add .claude/worktrees/phase-1-metrics -b phase-1-computable-metrics worktree-implement-pawtrail-launch
cd .claude/worktrees/phase-1-metrics
ls pawtrail_dbt/models/marts/   # confirms the code came along
```

Expected: the directory lists `dim_accounts.sql`, `fct_weekly_channel_economics.sql`, and so on.

- [ ] **Step 2: Reuse the existing venv**

The venv lives in the old worktree. A symlink avoids reinstalling everything:

```bash
ln -s /home/iagoadvaz/projects/pawtrail-launch-analytics/.claude/worktrees/implement-pawtrail-launch/.venv .venv
.venv/bin/dbt --version
```

Expected: prints the dbt-core and duckdb adapter versions without error.

- [ ] **Step 3: Establish the green baseline before changing anything**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build 2>&1 | tail -5
```

Expected: `Done. PASS=123 WARN=0 ERROR=0 SKIP=0 TOTAL=123`. If it does not match, **stop and report** — this plan assumes that baseline.

- [ ] **Step 4: Add the billing-cycle vars**

In `pawtrail_dbt/dbt_project.yml`, inside the existing `vars:` block, right after the line `attach_rate_launch_target: 0.15`, add:

```yaml
  # The subscription's billing interval. PawTrail is monthly; the var exists so
  # that the cycle clock and the unit economics read the same cadence from one
  # source, and so that a scenario test (quarterly) is a one-line change rather
  # than a find-and-replace across SQL.
  billing_cycle_months: 1
  # Ceiling of the cycle spine. The simulated window is 120 days, so no account
  # can have more than 4 monthly renewals come due. It doubles as a guard: if the
  # window grows and this var does not, the model silently stops counting cycles
  # -- which is why Task 1 ships a check that fails if any account hits the
  # ceiling.
  max_billing_cycles: 4
```

- [ ] **Step 5: Write the failing test**

Create `pawtrail_dbt/tests/assert_no_cycle_past_observation.sql`:

```sql
-- Fails (returns rows) if any cycle has a due date later than the observation
-- date. The model exists to measure EXPOSURE to renewal: a cycle that has not
-- come due yet is not exposure, it is the future. If this assertion breaks, the
-- spine filter is gone and every exposure metric starts counting renewals
-- nobody has faced.
select account_id, cycle_index, renewal_due_date, observation_date
from {{ ref('int_billing_cycles') }}
where renewal_due_date > observation_date
```

- [ ] **Step 6: Run the test to verify it fails**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt test --select assert_no_cycle_past_observation 2>&1 | tail -10
```

Expected: FAIL with a compilation error — `Model 'model.pawtrail.int_billing_cycles' (depends on) not found` or equivalent. The test cannot pass because the model does not exist yet.

- [ ] **Step 7: Write the model**

Create `pawtrail_dbt/models/intermediate/int_billing_cycles.sql`:

```sql
-- The billing-cycle clock, derived from pawtrail_signup_date ALONE.
--
-- READ BEFORE EDITING: this model measures *exposure* to renewal -- the
-- opportunity to charge -- and never the charge itself. No payment event exists
-- in the seeds. Renaming anything here to rebill_rate, renewal_revenue or
-- retained_mrr would make the dashboard present modelled scheduling as observed
-- behaviour, which is the gravest failure available in this project. This
-- model's value is precisely the opposite: it computes the DENOMINATOR a churn
-- metric would need, turning the data's limitation into a measurable fact rather
-- than a prose caveat.
with subscriptions as (
    select account_id, pawtrail_signup_date
    from {{ ref('stg_subscriptions') }}
),

-- The same cutoff definition used in int_activation_funnel. Duplicating the
-- expression rather than importing it keeps the two models independent, but they
-- MUST agree -- which is why the existing singular test
-- assert_signup_never_after_observation_date covers the shared premise, and
-- Task 1 adds the check on this model's side.
observation as (
    select max(pawtrail_signup_date) as observation_date
    from {{ ref('stg_subscriptions') }}
),

cycle_spine as (
    select unnest(generate_series(0, {{ var('max_billing_cycles') }})) as cycle_index
),

candidate as (
    select
        s.account_id,
        c.cycle_index,
        o.observation_date,
        -- The ::date cast is mandatory: in DuckDB, DATE + INTERVAL MONTH returns
        -- a TIMESTAMP. Without the cast, the date_diff below and every
        -- downstream join start comparing timestamp against date.
        --
        -- DuckDB's month arithmetic clamps end-of-month deterministically
        -- (2026-01-31 + 1 month = 2026-02-28), which is exactly the behaviour a
        -- billing cycle needs.
        --
        -- DO NOT replace this spine with date_diff('month', signup, observation):
        -- that function counts month boundaries crossed, not whole months, and
        -- returns 3 for 2026-01-05 -> 2026-04-04 where the correct answer is 2.
        -- Verified empirically.
        (
            s.pawtrail_signup_date
            + interval (c.cycle_index * {{ var('billing_cycle_months') }}) month
        )::date as renewal_due_date
    from subscriptions s
    cross join cycle_spine c
    cross join observation o
)

select
    -- Surrogate key: the grain is (account, cycle), so account_id alone is not a
    -- valid primary entity for the semantic model. Same pattern as
    -- channel_week_key in fct_weekly_channel_economics.
    account_id || '_' || cast(cycle_index as varchar) as billing_cycle_key,
    account_id,
    cycle_index,
    renewal_due_date,
    observation_date,
    date_diff('day', renewal_due_date, observation_date) as days_since_renewal_due
from candidate
-- The filter that defines "exposure": only cycles that have already come due.
-- cycle_index = 0 is the initial purchase, whose due date is the signup itself,
-- so every account has at least one row.
where renewal_due_date <= observation_date
```

- [ ] **Step 8: Add the schema tests**

In `pawtrail_dbt/models/intermediate/_intermediate__models.yml`, append to the `models:` list:

```yaml
  - name: int_billing_cycles
    columns:
      - name: billing_cycle_key
        tests:
          - unique
          - not_null
      - name: account_id
        tests:
          - not_null
          - relationships:
              arguments:
                to: ref('stg_subscriptions')
                field: account_id
      - name: cycle_index
        tests:
          - not_null
      - name: renewal_due_date
        tests:
          - not_null
```

- [ ] **Step 9: Run and verify it passes**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select int_billing_cycles+ 2>&1 | tail -12
```

Expected: the model builds and 5 tests pass (`unique`, `not_null` ×3, `relationships`) plus the singular test.

- [ ] **Step 10: Check magnitude against the spec's Appendix A**

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
print(c.sql('''
  select cycles_elapsed, count(*) as accounts
  from (select account_id, max(cycle_index) as cycles_elapsed
        from main.int_billing_cycles group by 1)
  group by 1 order by 1
''').fetchall())
print('accounts at ceiling:', c.sql('select count(*) from main.int_billing_cycles where cycle_index = 4').fetchone())
"
```

Expected: a decreasing distribution across 4 buckets (0 to 3), with bucket 0 around 300–400 accounts. The spec (Appendix A) predicts ~357 / 1,143 / 1,143 / 357. **If any account reaches `cycle_index = 4`, stop and report** — it means the window grew beyond what `max_billing_cycles` covers.

- [ ] **Step 11: Commit**

```bash
git add pawtrail_dbt/models/intermediate/int_billing_cycles.sql \
        pawtrail_dbt/models/intermediate/_intermediate__models.yml \
        pawtrail_dbt/tests/assert_no_cycle_past_observation.sql \
        pawtrail_dbt/dbt_project.yml
git commit -m "feat: add billing-cycle clock derived from signup date only

Measures exposure to renewal, never the charge -- no payment event exists
in the seeds. Gives the denominator a churn metric would need."
```

---

### Task 2: Cycle exposure as a segmentation axis

**Files:**
- Modify: `pawtrail_dbt/models/marts/dim_accounts.sql`
- Modify: `pawtrail_dbt/models/marts/_marts__core.yml`

**Interfaces:**
- Consumes: `int_billing_cycles` (Task 1) — `account_id`, `cycle_index`.
- Produces: `dim_accounts` gains `cycles_elapsed` (integer), `has_faced_renewal` (boolean), `cycle_exposure_cohort` (varchar, exact values `'0'`, `'1'`, `'2'`, `'3+'`). Task 3 declares a dimension over `cycle_exposure_cohort`; Task 4 reads `cycles_elapsed`.

- [ ] **Step 1: Write the failing test**

In `pawtrail_dbt/models/marts/_marts__core.yml`, inside `- name: dim_accounts`, append to the existing `columns:`:

```yaml
      - name: cycles_elapsed
        tests:
          - not_null
      - name: has_faced_renewal
        tests:
          - not_null
      - name: cycle_exposure_cohort
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['0', '1', '2', '3+']
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt test --select dim_accounts 2>&1 | tail -10
```

Expected: FAIL — the columns do not exist, and dbt reports an unknown-column error while compiling the tests.

- [ ] **Step 3: Modify the model**

Replace the entire contents of `pawtrail_dbt/models/marts/dim_accounts.sql` with:

```sql
-- Band boundaries are the standard subscription-tenure reads (under 6 months,
-- 6-12 months, 1-2 years, 2 years+) rather than equal-width buckets. Task 3
-- generates tenure decaying from ~900 days at launch to ~420 by day 120 with
-- 150-day noise, clipped to [30, 900], so all four bands are populated and the
-- adoption-order signal is visible across them.
with base as (
    select
        account_id,
        state,
        pet_tier,
        channel,
        premium_tenure_days,
        -- Carried through solely so the `accounts` semantic model has a time
        -- dimension. MetricFlow requires an agg_time_dimension for EVERY
        -- measure, and Task 3 attaches the first measures this model has ever
        -- had. Without a date column here, `dbt parse` fails outright --
        -- not `mf validate-configs`, but parse, which gates every build.
        pawtrail_signup_date,
        case
            when premium_tenure_days <= 180 then '0-180'
            when premium_tenure_days <= 365 then '181-365'
            when premium_tenure_days <= 730 then '366-730'
            else '731+'
        end as premium_tenure_band
    from {{ ref('stg_subscriptions') }}
),

-- How many billing cycles the account has seen come due. The count is the
-- maximum cycle_index, not count(*), because the spine starts at 0 (the initial
-- purchase): an account with rows 0 and 1 has faced ONE renewal, not two.
cycle_exposure as (
    select
        account_id,
        max(cycle_index) as cycles_elapsed
    from {{ ref('int_billing_cycles') }}
    group by 1
)

select
    b.*,
    coalesce(c.cycles_elapsed, 0) as cycles_elapsed,
    coalesce(c.cycles_elapsed, 0) >= 1 as has_faced_renewal,
    -- Banded so it works as a segmentation axis: grouping by the raw integer
    -- would produce one column per distinct value, and the analytical interest
    -- lies in the contrast between "never renewed" and everything else.
    case
        when coalesce(c.cycles_elapsed, 0) = 0 then '0'
        when c.cycles_elapsed = 1 then '1'
        when c.cycles_elapsed = 2 then '2'
        else '3+'
    end as cycle_exposure_cohort
from base b
left join cycle_exposure c on b.account_id = c.account_id
```

- [ ] **Step 4: Run and verify it passes**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select dim_accounts+ 2>&1 | tail -12
```

Expected: `dim_accounts` rebuilds, the 3 new tests pass, and no pre-existing test breaks (`fct_at_risk_accounts`, `fct_kit_deliveries` and `fct_subscriptions` all reference `dim_accounts.account_id`).

- [ ] **Step 5: Verify the row count did not change**

The left join must not duplicate accounts. Confirm:

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
print('dim_accounts:', c.sql('select count(*), count(distinct account_id) from main.dim_accounts').fetchone())
print('stg_subscriptions:', c.sql('select count(*) from main.stg_subscriptions').fetchone())
"
```

Expected: all three counts equal (3000, 3000, 3000). If `dim_accounts` has more rows, the `group by` in the `cycle_exposure` CTE failed and the join fanned out.

- [ ] **Step 6: Commit**

```bash
git add pawtrail_dbt/models/marts/dim_accounts.sql pawtrail_dbt/models/marts/_marts__core.yml
git commit -m "feat: expose billing-cycle exposure as a segmentation axis on dim_accounts"
```

---

### Task 3: Renewal-exposure metrics

**Files:**
- Modify: `pawtrail_dbt/models/marts/_semantic_models.yml`
- Modify: `pawtrail_dbt/models/marts/_metrics.yml`

**Interfaces:**
- Consumes: `dim_accounts.cycle_exposure_cohort`, `dim_accounts.has_faced_renewal` (Task 2).
- Produces: metrics `renewal_exposed_accounts`, `renewal_unexposed_accounts`, `pct_base_never_rebilled`. Task 12 exports the two counts by cohort to `control_cycle_exposure.csv` and the share ungrouped to `control_base_never_rebilled.csv` — the share is tautological at the cohort grain (see Task 12), so the two are deliberately not exported together.

**INVOKE FIRST:** the `metricflow-semantic-layer` skill, before editing the YAMLs.

- [ ] **Step 1: Add the measures to the `accounts` semantic model**

In `pawtrail_dbt/models/marts/_semantic_models.yml`, inside `- name: accounts`, after the `premium_tenure_band` dimension, add the dimension and the measures block:

```yaml
      - name: cycle_exposure_cohort
        type: categorical
      # REQUIRED, not optional. `accounts` has never carried a measure before,
      # so it has no time dimension and no `defaults` block. Attaching the
      # measures below without this pair makes `dbt parse` fail with
      # "Aggregation time dimension for measure renewal_exposed_accounts is not
      # set!", which gates dbt build and stops every pre-existing test running.
      #
      # The name is qualified because the `subscriptions` semantic model already
      # owns the bare `signup_date`; this matches the convention already used by
      # activation_signup_date, kit_signup_date and at_risk_signup_date.
      - name: accounts_signup_date
        type: time
        expr: pawtrail_signup_date
        type_params:
          time_granularity: day
    defaults:
      agg_time_dimension: accounts_signup_date
    measures:
      # Accounts that have already faced at least one due renewal. This is NOT a
      # billing measure: it counts how many accounts had the *opportunity* to
      # renew inside the observed window. See the header of
      # int_billing_cycles.sql.
      - name: renewal_exposed_accounts
        agg: sum
        expr: case when has_faced_renewal then 1 else 0 end
        create_metric: true
      - name: renewal_unexposed_accounts
        agg: sum
        expr: case when has_faced_renewal then 0 else 1 end
        create_metric: true
      - name: assessable_base_accounts
        agg: count
        expr: account_id
        create_metric: true
```

- [ ] **Step 2: Add the ratio metric**

In `pawtrail_dbt/models/marts/_metrics.yml`, append to the `metrics:` list:

```yaml
  # The share of the base that has not yet faced any renewal inside the 120-day
  # window. This is the number that converts "churn is out of scope because we
  # only have 120 days" from a prose caveat into a computed fact -- which is why
  # it belongs on the dashboard rather than in a footnote.
  - name: pct_base_never_rebilled
    type: ratio
    label: "Share of Base That Has Never Faced a Renewal"
    type_params:
      numerator: renewal_unexposed_accounts
      denominator: assessable_base_accounts
```

- [ ] **Step 3: Validate the configs**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt parse && ../.venv/bin/mf validate-configs 2>&1 | tail -8
```

Expected: no errors. If `The metric 'X' does not exist` appears, a measure referenced by the ratio is missing `create_metric: true`.

- [ ] **Step 4: Query at the grain the dashboard uses — this is the real acceptance**

`validate-configs` passing does not prove the number is right (spec §6.6):

```bash
cd pawtrail_dbt && ../.venv/bin/mf query --metrics pct_base_never_rebilled
cd pawtrail_dbt && ../.venv/bin/mf query --metrics renewal_exposed_accounts,renewal_unexposed_accounts --group-by account__cycle_exposure_cohort --order account__cycle_exposure_cohort
```

Expected: `pct_base_never_rebilled` around 0.10–0.14 (the spec predicts ~0.119). The cohort cut returns 4 rows: `0`, `1`, `2`, `3+`, with `renewal_unexposed_accounts` non-zero only on row `0`.

- [ ] **Step 5: Commit**

```bash
git add pawtrail_dbt/models/marts/_semantic_models.yml pawtrail_dbt/models/marts/_metrics.yml
git commit -m "feat: add renewal-exposure metrics incl. pct_base_never_rebilled"
```

---

### Task 4: Per-cycle unit economics and cycles to breakeven

**Files:**
- Create: `pawtrail_dbt/models/marts/fct_subscription_unit_economics.sql`
- Create: `pawtrail_dbt/tests/assert_cost_to_recover_exceeds_cac.sql`
- Modify: `pawtrail_dbt/models/marts/_marts__business.yml`

**Interfaces:**
- Consumes: `dim_accounts` (`account_id`, `channel`, `pet_tier`, `cycles_elapsed`), `fct_subscriptions` (`pawtrail_signup_date`), `dim_pricing` (`pet_tier`, `monthly_price_usd`, `kit_cogs_usd`, `shipping_cost_usd`), `fct_weekly_channel_economics` (`channel`, `signup_week`, `cac`).
- Produces: model `fct_subscription_unit_economics`, grain account, columns `account_id`, `channel`, `pet_tier`, `signup_week` (date), `monthly_price_usd`, `recurring_cost_per_cycle`, `contribution_margin_per_cycle`, `allocated_cac_usd`, `renewals_faced` (integer), `cycles_billed` (integer, `renewals_faced + 1`), `breakeven_cycles` (integer, null when margin ≤ 0), `total_cost_to_recover_usd`, `breakeven_within_window` (boolean). Task 5 declares metrics over these columns.

**INVOKE FIRST:** the `dbt-silent-failure-review` skill — this task adds three joins.

- [ ] **Step 1: Verify the premise before writing any SQL**

The spec (§1.2, Acceptance) requires confirming the per-cycle margin is positive across all three tiers **before** building the model. If any tier is ≤ 0, `breakeven_cycles` is undefined and the model needs a documented "never pays back" branch.

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
for row in c.sql('''
  select pet_tier, monthly_price_usd, kit_cogs_usd, shipping_cost_usd,
         monthly_price_usd - kit_cogs_usd - shipping_cost_usd as margin_per_cycle
  from main.dim_pricing order by monthly_price_usd
''').fetchall():
    print(row)
"
```

Expected: `small 9.49`, `medium 15.49`, `large 21.49` — all positive. **If any is ≤ 0, stop and report before continuing.**

- [ ] **Step 2: Write the failing test**

Create `pawtrail_dbt/tests/assert_cost_to_recover_exceeds_cac.sql`:

```sql
-- Fails (returns rows) if the total cost to recover does not exceed bare CAC on
-- an account whose per-cycle margin is positive.
--
-- This is the structural guard on the model's central claim: loading in
-- recurring COGS and shipping MUST raise the cost of recovery above naked CAC.
-- If it does not, the join against dim_pricing or fct_weekly_channel_economics
-- dropped rows and returned null -- the "green build, wrong numbers" failure
-- mode dbt joins produce silently.
select
    account_id,
    allocated_cac_usd,
    total_cost_to_recover_usd,
    contribution_margin_per_cycle
from {{ ref('fct_subscription_unit_economics') }}
where contribution_margin_per_cycle > 0
  and (
      total_cost_to_recover_usd is null
      or total_cost_to_recover_usd <= allocated_cac_usd
  )
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt test --select assert_cost_to_recover_exceeds_cac 2>&1 | tail -8
```

Expected: FAIL at compilation — the referenced model does not exist.

- [ ] **Step 4: Write the model**

Create `pawtrail_dbt/models/marts/fct_subscription_unit_economics.sql`:

```sql
-- Per-account unit economics, correcting the single-shipment assumption.
--
-- WHY THIS MODEL EXISTS: fct_weekly_channel_economics computes
-- contribution_margin_per_subscription ONCE, as though the kit shipped a single
-- time. PawTrail is a physical-box subscription: COGS and shipping are incurred
-- EVERY cycle. The two readings are different and both legitimate -- the old one
-- is first-cycle margin, this one is steady state -- which is why the names are
-- deliberately distinct and neither should be renamed to resemble the other.
--
-- AND WHAT IT DELIVERS: breakeven_cycles answers "how many renewals must this
-- account survive to pay for its own acquisition" using ONLY observed facts --
-- zero survival assumptions, zero retention curve. It is the honest substitute
-- for LTV:CAC in this window (spec §5.2).
with accounts as (
    select
        a.account_id,
        a.channel,
        a.pet_tier,
        -- Named `renewals_faced`, NOT `observable_cycles`. The billing spine is
        -- 0-based: cycle_index 0 IS the initial purchase, so cycles_elapsed
        -- counts RENEWALS faced, while breakeven_cycles counts CHARGES needed.
        -- Comparing the two directly is an off-by-one that reports every
        -- account at cycles_elapsed = 0 as "not broken even" even when a single
        -- charge already covered its CAC. The vaguer name is what made that bug
        -- invisible, so the name carries the distinction.
        a.cycles_elapsed as renewals_faced,
        date_trunc('week', s.pawtrail_signup_date) as signup_week
    from {{ ref('dim_accounts') }} a
    join {{ ref('fct_subscriptions') }} s on a.account_id = s.account_id
),

pricing as (
    select
        pet_tier,
        monthly_price_usd,
        kit_cogs_usd + shipping_cost_usd as recurring_cost_per_cycle,
        monthly_price_usd - kit_cogs_usd - shipping_cost_usd as contribution_margin_per_cycle
    from {{ ref('dim_pricing') }}
),

-- The CAC of the week and channel the account was acquired in. This is the
-- finest allocation the existing data supports: spend is generated per week x
-- channel, so there is no way to attribute it to an individual account more
-- precisely.
channel_cac as (
    select channel, signup_week, cac
    from {{ ref('fct_weekly_channel_economics') }}
),

joined as (
    select
        a.account_id,
        a.channel,
        a.pet_tier,
        a.signup_week,
        a.observable_cycles,
        p.monthly_price_usd,
        p.recurring_cost_per_cycle,
        p.contribution_margin_per_cycle,
        c.cac as allocated_cac_usd
    from accounts a
    join pricing p on a.pet_tier = p.pet_tier
    left join channel_cac c
        on a.channel = c.channel
       and a.signup_week = c.signup_week
),

-- Breakeven is referenced three times in the final select, so it is computed
-- once here: a select alias cannot be reused inside the same select. Same
-- pattern as the `joined` CTE in fct_weekly_channel_economics.
derived as (
    select
        *,
        -- NULL, not zero and not infinity, when the per-cycle margin is <= 0: an
        -- account that never pays back does not have "0 cycles to breakeven", it
        -- has no breakeven. Zero would read as "already paid back".
        case
            when contribution_margin_per_cycle > 0
            then cast(ceil(allocated_cac_usd / contribution_margin_per_cycle) as integer)
        end as breakeven_cycles
    from joined
)

select
    account_id,
    channel,
    pet_tier,
    signup_week,
    monthly_price_usd,
    recurring_cost_per_cycle,
    contribution_margin_per_cycle,
    allocated_cac_usd,
    renewals_faced,
    -- Charges collected so far = renewals faced + the initial purchase.
    renewals_faced + 1 as cycles_billed,
    breakeven_cycles,
    -- The total cost of recovering the account: acquisition plus all the COGS
    -- and shipping that will be spent up to the break-even point. It is the
    -- first time this project states a complete cost to serve.
    allocated_cac_usd + breakeven_cycles * recurring_cost_per_cycle
        as total_cost_to_recover_usd,
    -- Turns right-censoring into a COLUMN rather than a prose caveat. An account
    -- that signed up in week 17 cannot have completed 3 cycles inside a 120-day
    -- window; without this column, a per-channel breakeven average silently
    -- mixes proven with unproven accounts.
    breakeven_cycles <= renewals_faced + 1 as breakeven_within_window
from derived
```

- [ ] **Step 5: Add the schema tests**

In `pawtrail_dbt/models/marts/_marts__business.yml`, append to the `models:` list:

```yaml
  - name: fct_subscription_unit_economics
    columns:
      - name: account_id
        tests:
          - unique
          - not_null
          - relationships:
              arguments:
                to: ref('dim_accounts')
                field: account_id
      - name: channel
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['self_serve', 'sales_assisted']
      - name: contribution_margin_per_cycle
        tests:
          - not_null
      - name: allocated_cac_usd
        tests:
          - not_null
      - name: breakeven_cycles
        tests:
          - not_null
```

Note: `breakeven_cycles` is `not_null` because Step 1 confirmed positive margin across all three tiers. If a tier ever goes loss-making, this test fails loudly — which is the desired behaviour.

- [ ] **Step 6: Run and verify it passes**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select fct_subscription_unit_economics+ 2>&1 | tail -12
```

Expected: the model builds; the 5 schema tests and the singular `assert_cost_to_recover_exceeds_cac` pass.

- [ ] **Step 7: Check magnitude against Appendix A**

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
print(c.sql('''
  select channel,
         round(avg(allocated_cac_usd),2)             as avg_cac,
         round(avg(contribution_margin_per_cycle),2) as cycle_margin,
         max(breakeven_cycles)                       as max_breakeven,
         round(avg(case when breakeven_within_window then 1.0 else 0.0 end),3) as share_in_window
  from main.fct_subscription_unit_economics group by 1 order by 1
''').fetchall())
"
```

Expected, measured against the current warehouse: `self_serve` average CAC
**$7.14** with breakeven of **1** cycle; `sales_assisted` **$26.55** with
breakeven of **2**. Average per-cycle margin **$14.27**. `share_in_window`
should read about **0.93** for self_serve and **0.79** for sales_assisted.

**If `sales_assisted` comes out with a lower breakeven than `self_serve`, stop
and report** — the CAC join allocated the wrong week or channel.

**Two caveats on the CAC figures.** (1) They assume the `fct_weekly_channel_economics`
spend leak is fixed — see finding F1 in the metric-correctness review. Against
the unfixed mart these read $6.56 and $24.87, which is 7% low across the board.
(2) `share_in_window` reads 0.887 / 0.633 if the `breakeven_within_window`
comparison is written against `renewals_faced` instead of `renewals_faced + 1`;
those are the off-by-one values, not the correct ones.

- [ ] **Step 8: Commit**

```bash
git add pawtrail_dbt/models/marts/fct_subscription_unit_economics.sql \
        pawtrail_dbt/models/marts/_marts__business.yml \
        pawtrail_dbt/tests/assert_cost_to_recover_exceeds_cac.sql
git commit -m "feat: add per-cycle unit economics and breakeven_cycles

Replaces LTV:CAC in this window: uses only observed facts, with no survival
assumption. Corrects the single-shipment assumption in the old margin."
```

---

### Task 5: Unit-economics metrics

**Files:**
- Modify: `pawtrail_dbt/models/marts/_semantic_models.yml`
- Modify: `pawtrail_dbt/models/marts/_metrics.yml`

**Interfaces:**
- Consumes: `fct_subscription_unit_economics` (Task 4).
- Produces: metrics `avg_breakeven_cycles`, `contribution_margin_per_cycle`, `share_breakeven_cycle_exposed`.

**INVOKE FIRST:** the `metricflow-semantic-layer` skill.

- [ ] **Step 1: Declare the semantic model**

In `pawtrail_dbt/models/marts/_semantic_models.yml`, append to the `semantic_models:` list:

```yaml
  - name: subscription_unit_economics
    model: ref('fct_subscription_unit_economics')
    defaults:
      agg_time_dimension: unit_economics_signup_week
    entities:
      - name: account
        type: primary
        expr: account_id
    dimensions:
      # Model-qualified name: MetricFlow forbids the same (primary entity,
      # dimension name) pair on more than one semantic model, and `subscriptions`
      # already owns `signup_date`. Same reason as the rename in
      # activation_events.
      - name: unit_economics_signup_week
        type: time
        expr: signup_week
        type_params:
          time_granularity: week
    measures:
      - name: breakeven_cycles_sum
        agg: sum
        expr: breakeven_cycles
        create_metric: true
      - name: unit_economics_accounts
        agg: count
        expr: account_id
        create_metric: true
      - name: total_cost_to_recover_usd
        agg: sum
        expr: total_cost_to_recover_usd
        create_metric: true
      - name: cycle_margin_usd
        agg: sum
        expr: contribution_margin_per_cycle
        create_metric: true
      - name: accounts_breakeven_within_window
        agg: sum
        expr: case when breakeven_within_window then 1 else 0 end
        create_metric: true
```

- [ ] **Step 2: Declare the metrics**

In `pawtrail_dbt/models/marts/_metrics.yml`, append:

```yaml
  # Cycles the average account must survive to pay for its own acquisition.
  # Expressed as a sum over a count rather than `agg: average` over the column so
  # that the metric sums correctly when the semantic layer rolls channels or
  # weeks together -- an average of averages would weight a week of 3 signups the
  # same as a week of 300, and a launch's earliest weeks are its smallest.
  - name: avg_breakeven_cycles
    type: ratio
    label: "Average Cycles to Break Even"
    type_params:
      numerator: breakeven_cycles_sum
      denominator: unit_economics_accounts

  - name: contribution_margin_per_cycle
    type: ratio
    label: "Contribution Margin per Billing Cycle (steady state)"
    type_params:
      numerator: cycle_margin_usd
      denominator: unit_economics_accounts

  # What share of accounts reaches breakeven inside the horizon the 120-day
  # window actually observed. Below 1.0, the remainder is an unproven bet, not
  # measured payback.
  - name: share_breakeven_cycle_exposed
    type: ratio
    label: "Share of Accounts Whose Breakeven Cycle Has Already Come Due"
    type_params:
      numerator: accounts_breakeven_within_window
      denominator: unit_economics_accounts
```

- [ ] **Step 3: Validate**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt parse && ../.venv/bin/mf validate-configs 2>&1 | tail -6
```

Expected: no errors.

- [ ] **Step 4: Query at the grains the dashboard uses**

```bash
cd pawtrail_dbt && ../.venv/bin/mf query --metrics avg_breakeven_cycles,contribution_margin_per_cycle,share_breakeven_cycle_exposed --group-by account__channel --order account__channel
```

Expected: 2 rows (`self_serve`, `sales_assisted`). `avg_breakeven_cycles` higher for `sales_assisted`. `contribution_margin_per_cycle` near $14 for both (margin depends on tier, not channel).

- [ ] **Step 5: Commit**

```bash
git add pawtrail_dbt/models/marts/_semantic_models.yml pawtrail_dbt/models/marts/_metrics.yml
git commit -m "feat: expose breakeven-cycle metrics through the semantic layer"
```

---

### Task 6: Fulfillment waste

**Files:**
- Create: `pawtrail_dbt/models/marts/fct_fulfillment_waste.sql`
- Create: `pawtrail_dbt/tests/assert_waste_accounts_are_disjoint.sql`
- Modify: `pawtrail_dbt/models/marts/_marts__business.yml`

**Interfaces:**
- Consumes: `int_activation_funnel` (`account_id`, `pet_tier`, `channel`, `kit_lost`, `combined_activated_30d`, `is_mature_30d`), `dim_pricing`.
- Produces: model `fct_fulfillment_waste`, grain account (only accounts carrying waste), columns `account_id`, `channel`, `pet_tier`, `signup_week`, `waste_reason` (varchar: `'kit_lost'`, `'late_kit_no_activation'` or `'never_logged_in'`), `wasted_fulfillment_usd`. Task 7 aggregates by channel × week.

**INVOKE FIRST:** the `dbt-silent-failure-review` skill.

- [ ] **Step 1: Write the failing test**

Create `pawtrail_dbt/tests/assert_waste_accounts_are_disjoint.sql`:

```sql
-- Fails (returns rows) if any account appears more than once in the waste model.
--
-- An account can simultaneously have lost its kit AND failed to activate within
-- 30 days. Counting it twice would inflate total waste and, by extension,
-- effective CAC -- which is precisely the headline this block produces. The
-- model resolves this with an ordered CASE (lost kit wins), and this test is the
-- guard that the ordering stays mutually exclusive.
select account_id, count(*) as rows_found
from {{ ref('fct_fulfillment_waste') }}
group by account_id
having count(*) > 1
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt test --select assert_waste_accounts_are_disjoint 2>&1 | tail -8
```

Expected: FAIL at compilation — the model does not exist.

- [ ] **Step 3: Write the model**

Create `pawtrail_dbt/models/marts/fct_fulfillment_waste.sql`:

```sql
-- COGS and shipping spent with no return: kits lost in transit, and kits
-- delivered to accounts that never activated.
--
-- Today this cost appears nowhere in the project. cac_by_channel counts only
-- marketing spend, so the channel that buys cheap bad accounts looks like the
-- most efficient one. Loading in the waste is what reveals the opposite.
with funnel as (
    select
        account_id,
        channel,
        pet_tier,
        pawtrail_signup_date,
        kit_lost,
        combined_activated_30d,
        is_mature_30d
    from {{ ref('int_activation_funnel') }}
),

pricing as (
    select
        pet_tier,
        kit_cogs_usd + shipping_cost_usd as fulfillment_cost_usd
    from {{ ref('dim_pricing') }}
),

classified as (
    select
        f.account_id,
        f.channel,
        f.pet_tier,
        date_trunc('week', f.pawtrail_signup_date) as signup_week,
        p.fulfillment_cost_usd,
        f.kit_lost,
        -- Only MATURE accounts count as "never activated". A five-day-old account
        -- that has not activated is not waste, it is a new account -- the same
        -- mature-cohort discipline the activation rates already apply.
        (f.is_mature_30d and not f.combined_activated_30d) as never_activated_30d,
        -- combined_activated_30d requires BOTH a login within 30 days AND an
        -- on-time kit, so "not activated" silently includes customers who
        -- logged in and engaged but whose kit missed the SLA. In the current
        -- seeds that is 283 of 695 accounts -- 40.7% of this bucket. Booking
        -- their full COGS as "spent with no return" is wrong twice over: the
        -- money did buy an engaged customer, and the two groups lead to
        -- opposite decisions (demand problem vs carrier problem).
        (f.first_login_date is not null and f.days_to_first_login <= 30)
            as logged_in_within_30d
    from funnel f
    join pricing p on f.pet_tier = p.pet_tier
)

select
    account_id,
    channel,
    pet_tier,
    signup_week,
    -- An ordered CASE, not two rows: an account that lost its kit AND failed to
    -- activate consumed ONE kit, not two. Lost kit wins because it is the root
    -- cause -- the account failed to activate precisely because the kit never
    -- arrived.
    case
        when kit_lost then 'kit_lost'
        when logged_in_within_30d then 'late_kit_no_activation'
        else 'never_logged_in'
    end as waste_reason,
    fulfillment_cost_usd as wasted_fulfillment_usd
from classified
where kit_lost or never_activated_30d
```

- [ ] **Step 4: Add the schema tests**

In `pawtrail_dbt/models/marts/_marts__business.yml`, append:

```yaml
  - name: fct_fulfillment_waste
    columns:
      - name: account_id
        tests:
          - unique
          - not_null
          - relationships:
              arguments:
                to: ref('dim_accounts')
                field: account_id
      - name: waste_reason
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['kit_lost', 'late_kit_no_activation', 'never_logged_in']
      - name: wasted_fulfillment_usd
        tests:
          - not_null
```

- [ ] **Step 5: Run and verify it passes**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select fct_fulfillment_waste+ 2>&1 | tail -10
```

Expected: the model builds; the 4 schema tests and the singular test pass.

- [ ] **Step 6: Check magnitude and reconciliation**

The spec (§1.3, Acceptance) requires the waste to reconcile with its source counts:

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
print('waste by reason:', c.sql('''
  select waste_reason, count(*) as accounts, round(sum(wasted_fulfillment_usd),2) as usd
  from main.fct_fulfillment_waste group by 1 order by 1
''').fetchall())
print('lost kits at source:', c.sql('select count(*) from main.int_activation_funnel where kit_lost').fetchone())
print('mature non-activated at source:', c.sql('''
  select count(*) from main.int_activation_funnel
  where is_mature_30d and not combined_activated_30d and not kit_lost
''').fetchone())
"
```

Expected, measured against the current warehouse:

| `waste_reason` | accounts |
|---|---|
| `never_logged_in` | **412** |
| `late_kit_no_activation` | **283** |
| `kit_lost` | **84** |
| total | **779** |

The three classes are disjoint by the ordered CASE, so 412 + 283 + 84 must equal
the 695 non-lost non-activated accounts plus the 84 lost ones. **If
`late_kit_no_activation` comes out at zero, the `logged_in_within_30d` flag is
not reaching the CASE** — that class is 36% of the non-lost waste, and collapsing
it back into `never_logged_in` is the F16 defect the split exists to remove.

```bash
:
```

Expected: the model's `kit_lost` count matches the source `kit_lost` count exactly; `never_activated` matches mature-non-activated-and-not-lost. Total in the $10k–14k range (the spec predicts ~$12,124).

- [ ] **Step 7: Commit**

```bash
git add pawtrail_dbt/models/marts/fct_fulfillment_waste.sql \
        pawtrail_dbt/models/marts/_marts__business.yml \
        pawtrail_dbt/tests/assert_waste_accounts_are_disjoint.sql
git commit -m "feat: account for COGS and shipping spent with no return"
```

---

### Task 7: Effective CAC per channel and week

**Files:**
- Create: `pawtrail_dbt/models/marts/fct_weekly_channel_effective_cac.sql`
- Modify: `pawtrail_dbt/models/marts/_marts__business.yml`
- Modify: `pawtrail_dbt/models/marts/_semantic_models.yml`
- Modify: `pawtrail_dbt/models/marts/_metrics.yml`

**Interfaces:**
- Consumes: `fct_weekly_channel_economics` (`channel`, `signup_week`, `new_subscriptions`, `spend_usd`, `cac`), `fct_fulfillment_waste` (Task 6).
- Produces: model `fct_weekly_channel_effective_cac`, grain channel × week, columns `effective_cac_key` (surrogate), `channel`, `signup_week`, `new_subscriptions`, `spend_usd`, `wasted_fulfillment_usd`, `loaded_spend_usd`, `cac`, `effective_cac`, `cac_uplift_pct`. Metrics `effective_cac`, `cac_uplift_pct`.

**INVOKE FIRST:** the `dbt-silent-failure-review` and `metricflow-semantic-layer` skills.

- [ ] **Step 1: Write the model**

A separate model rather than a change to `fct_weekly_channel_economics`: that model already backs 8 published metrics, and adding columns there would risk the existing numbers for no reason.

Create `pawtrail_dbt/models/marts/fct_weekly_channel_effective_cac.sql`:

```sql
-- CAC loaded with fulfillment waste.
--
-- The headline this model produces: real CAC is materially higher than reported,
-- and the channel that suffers most is self-serve -- exactly the one that looked
-- cheap. A low CAC with high volume absorbs more waste per acquired account than
-- a high CAC with low volume.
with economics as (
    select
        channel,
        signup_week,
        new_subscriptions,
        spend_usd,
        cac
    from {{ ref('fct_weekly_channel_economics') }}
),

-- Aggregated to the SAME grain as the left side before the join. Joining the
-- waste model (account grain) directly against the economics model (channel x
-- week grain) would fan out the spend rows and multiply CAC.
waste as (
    select
        channel,
        signup_week,
        sum(wasted_fulfillment_usd) as wasted_fulfillment_usd
    from {{ ref('fct_fulfillment_waste') }}
    group by 1, 2
),

joined as (
    select
        e.channel,
        e.signup_week,
        e.new_subscriptions,
        e.spend_usd,
        e.cac,
        -- coalesce to zero, not null: a week with no waste is a week with zero
        -- waste, and leaving it null would make loaded_spend_usd null and drop
        -- it out of the sum.
        coalesce(w.wasted_fulfillment_usd, 0) as wasted_fulfillment_usd
    from economics e
    left join waste w
        on e.channel = w.channel
       and e.signup_week = w.signup_week
)

select
    channel || '_' || cast(signup_week as varchar) as effective_cac_key,
    channel,
    signup_week,
    new_subscriptions,
    spend_usd,
    wasted_fulfillment_usd,
    spend_usd + wasted_fulfillment_usd as loaded_spend_usd,
    cac,
    (spend_usd + wasted_fulfillment_usd) / nullif(new_subscriptions, 0) as effective_cac,
    -- How much the reported CAC understates the real one, as a share of its own
    -- base. This is the number that goes to the dashboard headline.
    (wasted_fulfillment_usd / nullif(spend_usd, 0)) as cac_uplift_pct
from joined
```

- [ ] **Step 2: Add the schema tests**

In `pawtrail_dbt/models/marts/_marts__business.yml`, append:

```yaml
  - name: fct_weekly_channel_effective_cac
    columns:
      - name: effective_cac_key
        tests:
          - unique
          - not_null
      - name: channel
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['self_serve', 'sales_assisted']
      - name: new_subscriptions
        tests:
          - not_null
      - name: effective_cac
        tests:
          - not_null
      - name: wasted_fulfillment_usd
        tests:
          - not_null
```

- [ ] **Step 3: Run and verify it passes**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select fct_weekly_channel_effective_cac 2>&1 | tail -10
```

Expected: the model builds, 5 tests pass.

- [ ] **Step 4: Confirm the row count matches the source model**

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
print('economics:', c.sql('select count(*) from main.fct_weekly_channel_economics').fetchone())
print('effective:', c.sql('select count(*) from main.fct_weekly_channel_effective_cac').fetchone())
"
```

Expected: **identical** counts. If `effective` has more rows, the `group by` in the `waste` CTE failed and the join fanned out — exactly the silent-failure mode the `dbt-silent-failure-review` skill covers.

- [ ] **Step 5: Declare the semantic model and the metrics**

In `_semantic_models.yml`, append:

```yaml
  - name: weekly_channel_effective_cac
    model: ref('fct_weekly_channel_effective_cac')
    defaults:
      agg_time_dimension: effective_cac_signup_week
    entities:
      - name: effective_cac_row
        type: primary
        expr: effective_cac_key
    dimensions:
      - name: effective_cac_signup_week
        type: time
        expr: signup_week
        type_params:
          time_granularity: week
      - name: channel
        type: categorical
    measures:
      - name: loaded_spend_usd
        agg: sum
        expr: loaded_spend_usd
        create_metric: true
      - name: fulfillment_waste_usd
        agg: sum
        expr: wasted_fulfillment_usd
        create_metric: true
      - name: effective_cac_new_subscriptions
        agg: sum
        expr: new_subscriptions
        create_metric: true
      - name: nominal_spend_usd
        agg: sum
        expr: spend_usd
        create_metric: true
```

In `_metrics.yml`, append:

```yaml
  # CAC loaded with the COGS and shipping that never earned anything. Built as a
  # sum over a sum (rather than an average of an already-divided column) so that
  # it rolls up correctly when aggregating weeks or channels.
  - name: effective_cac
    type: ratio
    label: "Effective CAC (loaded with fulfillment waste)"
    type_params:
      numerator: loaded_spend_usd
      denominator: effective_cac_new_subscriptions

  - name: cac_uplift_pct
    type: ratio
    label: "How Much Reported CAC Understates the Real One"
    type_params:
      numerator: fulfillment_waste_usd
      denominator: nominal_spend_usd
```

- [ ] **Step 6: Validate and query at the dashboard grain**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt parse && ../.venv/bin/mf validate-configs 2>&1 | tail -4
cd pawtrail_dbt && ../.venv/bin/mf query --metrics effective_cac,cac_uplift_pct --group-by effective_cac_row__channel --order effective_cac_row__channel
cd pawtrail_dbt && ../.venv/bin/mf query --metrics effective_cac,cac_uplift_pct
```

Expected: blended `cac_uplift_pct` around 0.25–0.35 (the spec predicts ~0.305). **The spec's sanity signal: `self_serve`'s uplift must be HIGHER than `sales_assisted`'s.** If it comes out inverted, the waste join is attributing kits to the wrong channel — stop and report.

- [ ] **Step 7: Commit**

```bash
git add pawtrail_dbt/models/marts/fct_weekly_channel_effective_cac.sql \
        pawtrail_dbt/models/marts/_marts__business.yml \
        pawtrail_dbt/models/marts/_semantic_models.yml \
        pawtrail_dbt/models/marts/_metrics.yml
git commit -m "feat: add effective CAC loaded with fulfillment waste"
```

---

### Task 8: Censoring register

**Files:**
- Create: `pawtrail_dbt/models/marts/fct_censoring_register.sql`
- Modify: `pawtrail_dbt/models/marts/_marts__core.yml`

**Interfaces:**
- Consumes: `int_activation_funnel` (flags `is_mature_7d`, `is_mature_sla`, `is_mature_combined_7d`, `is_mature_combined_14d`, `is_mature_30d`).
- Produces: model `fct_censoring_register`, grain metric name, columns `metric_name` (varchar), `denominator_accounts` (integer), `excluded_accounts` (integer), `excluded_share` (double). Task 12 exports it to CSV.

- [ ] **Step 1: Write the model**

Create `pawtrail_dbt/models/marts/fct_censoring_register.sql`:

```sql
-- How many accounts each rate excludes for immaturity, and what share of the
-- base that is.
--
-- The maturity gating already exists in int_activation_funnel and is CORRECT --
-- the problem is that it is invisible in the output. A 30-day rate computed over
-- the mature slice describes a different population from the subscriber count in
-- the headline, and without these numbers side by side the reader compares
-- incomparable denominators without knowing they are doing it.
--
-- Grain: one row per metric. This is a transparency model, not a fact table --
-- it exists to be published beside the numbers, which is why the metric name is
-- a literal rather than a foreign key.
with funnel as (
    select * from {{ ref('int_activation_funnel') }}
),

total as (
    select count(*) as base_accounts from funnel
),

registered as (
    select 'activation_rate_30d' as metric_name,
           sum(case when is_mature_30d then 1 else 0 end) as denominator_accounts
    from funnel
    union all
    select 'activation_rate_14d',
           sum(case when is_mature_combined_14d then 1 else 0 end)
    from funnel
    union all
    select 'activation_rate_7d',
           sum(case when is_mature_combined_7d then 1 else 0 end)
    from funnel
    union all
    select 'digital_activation_rate_7d',
           sum(case when is_mature_7d then 1 else 0 end)
    from funnel
    union all
    select 'kit_sla_rate',
           sum(case when is_mature_sla then 1 else 0 end)
    from funnel
)

select
    r.metric_name,
    r.denominator_accounts,
    t.base_accounts - r.denominator_accounts as excluded_accounts,
    (t.base_accounts - r.denominator_accounts) * 1.0 / nullif(t.base_accounts, 0)
        as excluded_share
from registered r
cross join total t
```

- [ ] **Step 2: Add the schema tests**

In `pawtrail_dbt/models/marts/_marts__core.yml`, append:

```yaml
  - name: fct_censoring_register
    columns:
      - name: metric_name
        tests:
          - unique
          - not_null
          - accepted_values:
              arguments:
                values:
                  - 'activation_rate_30d'
                  - 'activation_rate_14d'
                  - 'activation_rate_7d'
                  - 'digital_activation_rate_7d'
                  - 'kit_sla_rate'
      - name: denominator_accounts
        tests:
          - not_null
      - name: excluded_accounts
        tests:
          - not_null
```

- [ ] **Step 3: Run and verify it passes**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select fct_censoring_register 2>&1 | tail -8
```

Expected: the model builds, 4 tests pass.

- [ ] **Step 4: Cross-check against the metrics' real denominators**

The register is only worth having if it matches what the semantic layer actually uses:

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
for r in c.sql('select * from main.fct_censoring_register order by excluded_accounts desc').fetchall(): print(r)
"
cd pawtrail_dbt && ../.venv/bin/mf query --metrics mature_accounts_30d,mature_accounts_sla
```

Expected: `denominator_accounts` for `activation_rate_30d` **identical** to `mature_accounts_30d` from `mf query`; likewise for `kit_sla_rate` vs `mature_accounts_sla`. If they diverge, the register is lying — stop and report.

- [ ] **Step 5: Commit**

```bash
git add pawtrail_dbt/models/marts/fct_censoring_register.sql pawtrail_dbt/models/marts/_marts__core.yml
git commit -m "feat: publish per-metric maturity-gating exclusions"
```

---

### Task 9: Time-to-first-login distribution

**Files:**
- Create: `pawtrail_dbt/models/marts/fct_login_timing_distribution.sql`
- Modify: `pawtrail_dbt/models/marts/_marts__core.yml`

**Interfaces:**
- Consumes: `int_activation_funnel` (`days_to_first_login`, `first_login_date`, `is_mature_30d`).
- Produces: model `fct_login_timing_distribution`, grain band, columns `login_timing_band` (varchar, exact values `'0-2'`, `'3-7'`, `'8-14'`, `'15-30'`, `'never'`), `band_order` (integer), `accounts` (integer), `share` (double).

- [ ] **Step 1: Write the model**

Create `pawtrail_dbt/models/marts/fct_login_timing_distribution.sql`:

```sql
-- The full shape of time-to-first-login, with the censored tail accounted for
-- separately.
--
-- WHY THIS REPLACES THE MEAN: avg_days_to_first_login silently discards accounts
-- that never logged in (the generator makes 15% of them never log in), so the
-- mean IMPROVES as the product gets WORSE -- the more people give up, the
-- cleaner the average of those who remain. A metric that moves the wrong way
-- under failure is worse than no metric.
--
-- The 'never' band is not a null bucket: it is the answer, and its size is the
-- number that matters.
with funnel as (
    select
        account_id,
        first_login_date,
        days_to_first_login,
        is_mature_30d
    from {{ ref('int_activation_funnel') }}
    -- Mature cohort only: a 3-day-old account that has not logged in does not
    -- belong in the 'never' band, it belongs to the future.
    where is_mature_30d
),

banded as (
    select
        case
            when first_login_date is null then 'never'
            when days_to_first_login <= 2 then '0-2'
            when days_to_first_login <= 7 then '3-7'
            when days_to_first_login <= 14 then '8-14'
            else '15-30'
        end as login_timing_band,
        case
            when first_login_date is null then 5
            when days_to_first_login <= 2 then 1
            when days_to_first_login <= 7 then 2
            when days_to_first_login <= 14 then 3
            else 4
        end as band_order
    from funnel
),

total as (
    select count(*) as mature_accounts from banded
)

select
    b.login_timing_band,
    b.band_order,
    count(*) as accounts,
    count(*) * 1.0 / nullif(t.mature_accounts, 0) as share
from banded b
cross join total t
group by b.login_timing_band, b.band_order, t.mature_accounts
order by b.band_order
```

- [ ] **Step 2: Add the schema tests**

In `pawtrail_dbt/models/marts/_marts__core.yml`, append:

```yaml
  - name: fct_login_timing_distribution
    columns:
      - name: login_timing_band
        tests:
          - unique
          - not_null
          - accepted_values:
              arguments:
                values: ['0-2', '3-7', '8-14', '15-30', 'never']
      - name: accounts
        tests:
          - not_null
```

- [ ] **Step 3: Run and verify it passes**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select fct_login_timing_distribution 2>&1 | tail -8
```

Expected: the model builds, 3 tests pass.

- [ ] **Step 4: Confirm the censored tail shows up**

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
for r in c.sql('select * from main.fct_login_timing_distribution order by band_order').fetchall(): print(r)
"
```

Expected: 5 bands, with `never` around 13–17% (the generator uses `NEVER_LOGS_IN_RATE = 0.15`). **If `never` comes out at zero or absent, stop and report** — the `where` clause filtered out the very tail this model exists to expose.

- [ ] **Step 5: Commit**

```bash
git add pawtrail_dbt/models/marts/fct_login_timing_distribution.sql pawtrail_dbt/models/marts/_marts__core.yml
git commit -m "feat: replace mean time-to-login with a distribution that keeps the censored tail"
```

---

### Task 10: Healthy pruning vs. operational damage in the risk queue

**Files:**
- Modify: `pawtrail_dbt/models/marts/fct_at_risk_accounts.sql`
- Modify: `pawtrail_dbt/models/marts/_marts__risk.yml`
- Create: `pawtrail_dbt/tests/assert_self_selected_have_no_delivery_defect.sql`
- Create: `pawtrail_dbt/tests/assert_damage_class_covers_all_at_risk.sql`
- Modify: `pawtrail_dbt/models/marts/_semantic_models.yml`

**Interfaces:**
- Consumes: `int_activation_funnel`, `dim_pricing` (for recoverable revenue).
- Produces: `fct_at_risk_accounts` gains `damage_class` (varchar: `'system_inflicted'`, `'self_selected'`, `'ambiguous'`, `'healthy'`) and `recoverable_mrr_usd` (double). Metrics `system_inflicted_at_risk_accounts` and `recoverable_mrr_usd`.

**IMPORTANT:** `risk_driver` **stays** in the table. `damage_class` is an additional and orthogonal classification, not a replacement — the CSV `control_at_risk_by_driver.csv` and the corresponding `METRICS.md` section both depend on `risk_driver`, and removing it would break the existing dashboard. The spec says "replace the flat enum"; the correct reading is to replace its **use in prioritisation** while keeping it as an operational descriptor.

- [ ] **Step 1: Write the falsification tests first**

Create `pawtrail_dbt/tests/assert_self_selected_have_no_delivery_defect.sql`:

```sql
-- Fails (returns rows) if any account classified as self-selected has a delivery
-- defect.
--
-- This is the assertion that keeps the classification from being useless. All
-- the value of separating healthy pruning from operational damage rests on
-- 'self_selected' genuinely meaning "the account did not want this", not "the
-- account did not want this AND the kit was also lost". Without this test, the
-- classification may simply be re-encoding the same self-selection it claims to
-- separate.
select account_id, damage_class, kit_failed_sla
from {{ ref('fct_at_risk_accounts') }}
where damage_class = 'self_selected'
  and kit_failed_sla
```

Create `pawtrail_dbt/tests/assert_damage_class_covers_all_at_risk.sql`:

```sql
-- Fails (returns rows) if any at-risk account falls outside the three damage
-- classes, or if any healthy account receives a damage class.
--
-- An exhaustiveness guard: a CASE with a misplaced ELSE produces a silently
-- empty class, and the prioritised queue starts omitting accounts without
-- anything failing.
select account_id, is_at_risk, damage_class
from {{ ref('fct_at_risk_accounts') }}
where (is_at_risk and damage_class not in ('system_inflicted', 'self_selected', 'ambiguous'))
   or (not is_at_risk and damage_class <> 'healthy')
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt test --select assert_self_selected_have_no_delivery_defect assert_damage_class_covers_all_at_risk 2>&1 | tail -10
```

Expected: both FAIL — the `damage_class` column does not exist yet.

- [ ] **Step 3: Modify the model**

Replace the entire contents of `pawtrail_dbt/models/marts/fct_at_risk_accounts.sql` with:

```sql
with funnel as (
    select * from {{ ref('int_activation_funnel') }}
),

pricing as (
    select pet_tier, monthly_price_usd from {{ ref('dim_pricing') }}
),

flagged as (
    select
        f.account_id,
        f.state,
        f.channel,
        f.pet_tier,
        f.pawtrail_signup_date,
        f.days_observed,
        f.premium_tenure_days,
        f.first_login_date,
        f.no_digital_access_14d,
        (f.kit_lost or f.kit_delivered_date is null or not f.kit_activated_sla) as kit_failed_sla,
        (coalesce(f.care_tasks_completed_first_cycle, 0) = 0) as no_tasks_completed,
        p.monthly_price_usd
    from funnel f
    left join pricing p on f.pet_tier = p.pet_tier
    -- Only accounts that have actually had the chance to fail. Flagging a
    -- two-day-old signup as "no digital access in 14 days" would fill the CS
    -- queue with accounts that are simply new.
    where f.days_observed >= {{ var('at_risk_no_login_days') }}
),

classified as (
    select
        *,
        -- onboarding_gap ("logged in fine, but did no first-cycle tasks") is
        -- expected to be rare-to-empty at this project's scale, not dead code.
        -- Task 4's generator (generate_activity.py, generate_digital_engagement)
        -- draws task_rate = clip(1 - days_to_first_login/30, 0.05, 1.0): the 0.05
        -- floor is only reached as days_to_first_login approaches 30, but
        -- no_digital_access_14d already excludes anyone past day 14 -- so the
        -- window where an account both "has digital access" and "was likely to
        -- draw zero tasks" barely overlaps. On a run with zero occurrences, that
        -- is a real ~86.5% per-seed outcome, not a bug in this case branch.
        -- Do not "fix" an empty bucket here by editing this condition.
        case
            when no_digital_access_14d and kit_failed_sla then 'both_legs_failed'
            when kit_failed_sla then 'physical_failure'
            when no_digital_access_14d then 'digital_failure'
            when no_tasks_completed then 'onboarding_gap'
            else 'healthy'
        end as risk_driver,
        (no_digital_access_14d or kit_failed_sla or no_tasks_completed) as is_at_risk
    from flagged
)

select
    *,
    -- The classification that makes the queue workable.
    --
    -- risk_driver describes WHICH leg failed; damage_class answers WHETHER IT IS
    -- WORTH ACTING ON. The two are orthogonal and both stay in the table: the
    -- CSV control_at_risk_by_driver.csv and METRICS.md depend on risk_driver, and
    -- removing it would break the published dashboard.
    --
    -- The distinction: an account whose kit was lost suffered system-inflicted
    -- damage -- it is recoverable and the company caused it. An account that
    -- never logged in, with short Premium tenure and no delivery defect,
    -- self-selected out: remediating it means spending retention effort on
    -- someone who never wanted the product. Treating the two as the same thing is
    -- what makes today's ~944 accounts a list nobody can work.
    case
        when not is_at_risk then 'healthy'
        -- Any physical defect is system damage, regardless of anything else: the
        -- company charged and failed to deliver.
        when kit_failed_sla then 'system_inflicted'
        -- No physical defect, never logged in, and joined with little Premium
        -- tenure: the profile of someone who tried and walked away.
        --
        -- THE THRESHOLD IS CALIBRATED, NOT ASSUMED. An absolute 180-day cut
        -- yields FOUR accounts base-wide (the generator decays tenure from ~900
        -- to ~420 with 150-day noise clipped to [30, 900]; min 56, median 660).
        -- That collapses this class to zero and leaves the queue an unworkable
        -- two-bucket list, which is the exact failure this task exists to fix.
        -- var('self_selected_tenure_days') defaults to 365, which puts the
        -- '0-180' and '181-365' bands (140 accounts) in scope.
        when first_login_date is null
             and premium_tenure_days <= {{ var('self_selected_tenure_days') }}
             then 'self_selected'
        else 'ambiguous'
    end as damage_class,
    -- The monthly revenue remediation recovers if it succeeds. Turns the queue
    -- from a count into a prioritised budget.
    case
        when is_at_risk then monthly_price_usd
    end as recoverable_mrr_usd
from classified
```

- [ ] **Step 3b: Declare the threshold as a var and guard against degeneracy**

In `pawtrail_dbt/dbt_project.yml`, under `vars:`:

```yaml
  # Tenure below which a never-logged-in account with no delivery defect reads
  # as self-selected rather than as damage the company inflicted. Calibrated
  # against the observed tenure distribution, NOT taken from a rule of thumb --
  # see the comment in fct_at_risk_accounts.sql.
  self_selected_tenure_days: 365
```

Create `pawtrail_dbt/tests/assert_damage_classes_are_non_degenerate.sql`:

```sql
-- Fails if any damage class is empty.
--
-- The whole deliverable is a queue an operator can triage into "remediate" and
-- "do not remediate". A classification with an empty class is a two-bucket list
-- wearing a three-bucket name, and every other test in this task passes on it:
-- accepted_values passes on a missing value, and the falsification test below
-- evaluates over an empty set and passes vacuously.
--
-- This is the one test in Task 10 that can fail on correct code with wrong
-- data, which is exactly why it is here.
select damage_class, count(*) as n
from (
    select unnest(['system_inflicted', 'self_selected', 'ambiguous']) as damage_class
) expected
left join {{ ref('fct_at_risk_accounts') }} actual using (damage_class)
group by 1
having count(actual.account_id) = 0
```

Run it:

```bash
cd pawtrail_dbt && ../.venv/bin/dbt test --select assert_damage_classes_are_non_degenerate 2>&1 | tail -5
```

If it fails, raise `self_selected_tenure_days` — do **not** delete the test.

- [ ] **Step 3c: Write the falsification test the spec actually asked for**

Spec §1.8 demands two tests, and Step 1 wrote only the first. The second one —
"accounts classified as system damage are **not** concentrated in short tenure" —
is the one that can actually fail, because the first merely re-asserts the CASE's
own branch ordering.

Create `pawtrail_dbt/tests/assert_system_inflicted_not_concentrated_in_short_tenure.sql`:

```sql
-- Fails if 'system_inflicted' accounts skew short-tenure by more than 10
-- percentage points against the at-risk base.
--
-- Without this, the classification could be re-encoding the same self-selection
-- it claims to separate: if the accounts we call "damaged by the company" are
-- simply the newest accounts, the split carries no information.
--
-- Expect this to PASS with a wide margin on the current generator: mean tenure
-- is ~661 days in every class against a base median of 660. That null result is
-- itself the finding -- tenure does not discriminate in this dataset -- and it
-- belongs in METRICS.md rather than being silently discarded.
with base as (
    select
        avg(case when premium_tenure_days <= {{ var('self_selected_tenure_days') }}
            then 1.0 else 0.0 end) as base_short_share
    from {{ ref('fct_at_risk_accounts') }}
    where is_at_risk
),
system_inflicted as (
    select
        avg(case when premium_tenure_days <= {{ var('self_selected_tenure_days') }}
            then 1.0 else 0.0 end) as class_short_share
    from {{ ref('fct_at_risk_accounts') }}
    where damage_class = 'system_inflicted'
)
select b.base_short_share, s.class_short_share
from base b cross join system_inflicted s
where s.class_short_share - b.base_short_share > 0.10
```

- [ ] **Step 4: Update the schema tests**

In `pawtrail_dbt/models/marts/_marts__risk.yml`, inside `- name: fct_at_risk_accounts`, append to `columns:`:

```yaml
      - name: damage_class
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['healthy', 'system_inflicted', 'self_selected', 'ambiguous']
```

- [ ] **Step 5: Run and verify it passes**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select fct_at_risk_accounts+ 2>&1 | tail -12
```

Expected: the model rebuilds; the new tests and the pre-existing ones (including `assert_risk_driver_is_exhaustive`) pass.

- [ ] **Step 6: Check magnitude and orthogonality**

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
print('by damage class:')
for r in c.sql('''
  select damage_class, count(*) as accounts, round(sum(recoverable_mrr_usd),2) as mrr
  from main.fct_at_risk_accounts where is_at_risk group by 1 order by 2 desc
''').fetchall(): print(' ', r)
print('driver x class cross-tab:')
for r in c.sql('''
  select risk_driver, damage_class, count(*) from main.fct_at_risk_accounts
  where is_at_risk group by 1,2 order by 1,2
''').fetchall(): print(' ', r)
"
```

Expected: total at risk near 944 (unchanged — the classification does not change who is at risk). `system_inflicted` in the 400–500 range with recoverable MRR of $10k–15k. **If `self_selected` comes out empty, stop and report** — the tenure condition may be too restrictive for this seed.

- [ ] **Step 7: Declare the metrics**

In `_semantic_models.yml`, inside the existing `at_risk_accounts` semantic model, add the dimension:

```yaml
      - name: damage_class
        type: categorical
```

and to that model's `measures:`:

```yaml
      - name: system_inflicted_at_risk_accounts
        agg: sum
        expr: case when is_at_risk and damage_class = 'system_inflicted' then 1 else 0 end
        create_metric: true
      - name: recoverable_mrr_usd
        agg: sum
        expr: recoverable_mrr_usd
        create_metric: true
```

- [ ] **Step 8: Validate and query**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt parse && ../.venv/bin/mf validate-configs 2>&1 | tail -4
cd pawtrail_dbt && ../.venv/bin/mf query --metrics at_risk_accounts,recoverable_mrr_usd --group-by account__damage_class --order account__damage_class
```

Expected: 4 class rows, with `healthy` showing `at_risk_accounts` equal to zero.

- [ ] **Step 9: Commit**

```bash
git add pawtrail_dbt/models/marts/fct_at_risk_accounts.sql \
        pawtrail_dbt/models/marts/_marts__risk.yml \
        pawtrail_dbt/models/marts/_semantic_models.yml \
        pawtrail_dbt/tests/assert_self_selected_have_no_delivery_defect.sql \
        pawtrail_dbt/tests/assert_damage_class_covers_all_at_risk.sql
git commit -m "feat: split at-risk queue into healthy pruning vs system-inflicted damage"
```

---

### Task 11: Saturation and portfolio concentration

**Files:**
- Create: `pawtrail_dbt/models/marts/fct_state_saturation.sql`
- Modify: `pawtrail_dbt/models/marts/_marts__business.yml`
- Modify: `pawtrail_dbt/models/marts/_semantic_models.yml`
- Modify: `pawtrail_dbt/models/marts/_metrics.yml`

**Interfaces:**
- Consumes: `fct_weekly_attach` (`state`, `signup_week`, `cumulative_subscriptions`, `eligible_premium_accounts`), `fct_subscriptions`, `dim_accounts`, `fct_subscription_unit_economics` (Task 4).
- Produces: model `fct_state_saturation`, grain state, columns `state`, `cumulative_subscriptions`, `eligible_premium_accounts`, `penetration`, `remaining_eligible_accounts`, `remaining_share`, `new_subscriptions_last_week`, `cycle_margin_usd`, `margin_share`.

- [ ] **Step 1: Write the model**

Create `pawtrail_dbt/models/marts/fct_state_saturation.sql`:

```sql
-- Penetration against remaining base, per state -- plus margin concentration.
--
-- WHY IT MATTERS: today the dashboard reads slowing growth as a performance
-- signal. A state approaching the carrying capacity of its own niche decelerates
-- for reasons no marketing spend can fix, and confusing that with a channel
-- problem is the classic launch-window misdiagnosis. Both readings require
-- seeing penetration and remaining base side by side, which is what this model
-- delivers.
with latest_week as (
    select max(signup_week) as final_week from {{ ref('fct_weekly_attach') }}
),

-- The portfolio's state at the end of the window.
final_state as (
    select
        w.state,
        w.cumulative_subscriptions,
        w.eligible_premium_accounts
    from {{ ref('fct_weekly_attach') }} w
    cross join latest_week l
    where w.signup_week = l.final_week
),

-- How many accounts the state acquired in the last week. This is the numerator
-- of the "is it still growing?" reading.
last_week_new as (
    select
        a.state,
        count(*) as new_subscriptions_last_week
    from {{ ref('fct_subscriptions') }} s
    join {{ ref('dim_accounts') }} a on s.account_id = a.account_id
    cross join latest_week l
    where s.signup_week = l.final_week
    group by 1
),

-- Aggregated to state grain BEFORE the join, so it cannot fan out the
-- fct_weekly_attach rows.
margin_by_state as (
    select
        a.state,
        sum(u.contribution_margin_per_cycle) as cycle_margin_usd
    from {{ ref('fct_subscription_unit_economics') }} u
    join {{ ref('dim_accounts') }} a on u.account_id = a.account_id
    group by 1
),

total_margin as (
    select sum(cycle_margin_usd) as all_states_margin from margin_by_state
)

select
    f.state,
    f.cumulative_subscriptions,
    f.eligible_premium_accounts,
    f.cumulative_subscriptions * 1.0 / nullif(f.eligible_premium_accounts, 0) as penetration,
    f.eligible_premium_accounts - f.cumulative_subscriptions as remaining_eligible_accounts,
    (f.eligible_premium_accounts - f.cumulative_subscriptions) * 1.0
        / nullif(f.eligible_premium_accounts, 0) as remaining_share,
    coalesce(n.new_subscriptions_last_week, 0) as new_subscriptions_last_week,
    m.cycle_margin_usd,
    -- Concentration: how much of total margin depends on this state. A
    -- concentrated book is worth less than a diversified one at the same MRR.
    m.cycle_margin_usd / nullif(t.all_states_margin, 0) as margin_share
from final_state f
left join last_week_new n on f.state = n.state
left join margin_by_state m on f.state = m.state
cross join total_margin t
```

- [ ] **Step 2: Add the schema tests**

In `pawtrail_dbt/models/marts/_marts__business.yml`, append:

```yaml
  - name: fct_state_saturation
    columns:
      - name: state
        tests:
          - unique
          - not_null
          - relationships:
              arguments:
                to: ref('fct_premium_base')
                field: state
      - name: penetration
        tests:
          - not_null
      - name: margin_share
        tests:
          - not_null
```

- [ ] **Step 3: Run and verify it passes**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select fct_state_saturation 2>&1 | tail -8
```

Expected: the model builds, 4 tests pass, 12 rows (one per state).

- [ ] **Step 4: Verify the shares sum to 1**

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
print('rows:', c.sql('select count(*) from main.fct_state_saturation').fetchone())
print('sum of margin_share:', c.sql('select round(sum(margin_share),6) from main.fct_state_saturation').fetchone())
print('top 3 concentration:')
for r in c.sql('select state, round(penetration,4), round(margin_share,4) from main.fct_state_saturation order by margin_share desc limit 3').fetchall(): print(' ', r)
"
```

Expected: 12 rows; `sum(margin_share)` = 1.0 (rounding tolerance); the largest state is **CA at ~0.509**, and the top 3 sum to **~0.768**. (An earlier draft of the spec said 0.449 / 0.687 — those were CA's share of the *eligible base*, a different quantity. Corrected in Appendix A.)

- [ ] **Step 5: Declare the semantic model and the metric**

In `_semantic_models.yml`, append:

```yaml
  - name: state_saturation
    model: ref('fct_state_saturation')
    entities:
      - name: saturation_state
        type: primary
        expr: state
    dimensions:
      - name: state
        type: categorical
      # Same MetricFlow requirement as the `accounts` model in Task 3: measures
      # need an agg_time_dimension or `dbt parse` fails. fct_state_saturation is
      # a single snapshot at the final week, so add a `snapshot_date` column to
      # the model (`select ... max(signup_week) over () as snapshot_date`) and
      # declare it here.
      - name: snapshot_date
        type: time
        expr: snapshot_date
        type_params:
          time_granularity: day
    defaults:
      agg_time_dimension: snapshot_date
    measures:
      - name: remaining_eligible_accounts
        agg: sum
        expr: remaining_eligible_accounts
        create_metric: true
      - name: state_cycle_margin_usd
        agg: sum
        expr: cycle_margin_usd
        create_metric: true
      - name: saturation_cumulative_subscriptions
        agg: sum
        expr: cumulative_subscriptions
        create_metric: true
      - name: saturation_eligible_accounts
        agg: sum
        expr: eligible_premium_accounts
        create_metric: true
```

In `_metrics.yml`, append:

```yaml
  - name: state_penetration
    type: ratio
    label: "Penetration of the Eligible Base (by state)"
    type_params:
      numerator: saturation_cumulative_subscriptions
      denominator: saturation_eligible_accounts
```

- [ ] **Step 6: Validate and query**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt parse && ../.venv/bin/mf validate-configs 2>&1 | tail -4
cd pawtrail_dbt && ../.venv/bin/mf query --metrics state_penetration,remaining_eligible_accounts --group-by saturation_state__state --order state_penetration
```

Expected: 12 rows ordered by ascending penetration.

- [ ] **Step 7: Commit**

```bash
git add pawtrail_dbt/models/marts/fct_state_saturation.sql \
        pawtrail_dbt/models/marts/_marts__business.yml \
        pawtrail_dbt/models/marts/_semantic_models.yml \
        pawtrail_dbt/models/marts/_metrics.yml
git commit -m "feat: separate demand exhaustion from execution failure via saturation curve"
```

---

### Task 12: Benchmarks, exports and the METRICS.md correction

**Files:**
- Modify: `pawtrail_dbt/dbt_project.yml` (benchmark vars)
- Modify: `pawtrail_dbt/models/marts/_metrics.yml` (benchmark derived metric)
- Create: 8 new CSVs in `dashboard/`
- Modify: `METRICS.md`, `dashboard/README.md`

**Interfaces:**
- Consumes: every metric from Tasks 3, 5, 7, 10, 11.
- Produces: 8 new CSVs in `dashboard/` (total rises from 11 to 19) and a correct `METRICS.md`.

**INVOKE FIRST:** the `plan-consistency-sweep` skill before editing `METRICS.md` — the file has hardcoded counts (33 metrics, 8 semantic models) that will drift.

- [ ] **Step 1: Add the benchmark var**

In `pawtrail_dbt/dbt_project.yml`, inside `vars:`:

```yaml
  # Market benchmark cited by Crystallize (spec §1.6). It lives here rather than
  # in a dashboard constant for the same reason as attach_rate_launch_target: the
  # target on the chart and the target quoted in the memo cannot disagree.
  activation_rate_benchmark: 0.70
```

- [ ] **Step 2: Add the benchmark derived metric**

In `pawtrail_dbt/models/marts/_metrics.yml`, append:

```yaml
  # 30-day activation against the market benchmark. Same pattern as
  # attach_rate_vs_target: 1.0 means exactly at benchmark, so the dashboard needs
  # no separate reference line that could drift from the number in the memo.
  #
  # This project runs BELOW 1.0 across most of the window -- which is precisely
  # why the metric exists. `activation_rate_30d` has always been on the dashboard
  # and has never been compared against anything.
  - name: activation_rate_30d_vs_benchmark
    type: derived
    label: "30-Day Activation vs. Market Benchmark (1.0 = at benchmark)"
    type_params:
      expr: rate / {{ var('activation_rate_benchmark') }}
      metrics:
        - name: activation_rate_30d
          alias: rate
```

- [ ] **Step 3: Validate and check the number**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt parse && ../.venv/bin/mf validate-configs 2>&1 | tail -4
cd pawtrail_dbt && ../.venv/bin/mf query --metrics activation_rate_30d,activation_rate_30d_vs_benchmark --group-by metric_time__week --order metric_time__week
```

Expected: the ratio crosses 1.0 downward somewhere in the window — the spec describes `activation_rate_30d` moving from 75.2% to 60.3%.

- [ ] **Step 4: Run the full build**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build 2>&1 | tail -6
```

Expected: `ERROR=0`. The total rises from 123 to roughly 165–175 (7 new models plus ~30 new tests). Record the exact number — it becomes the new baseline.

- [ ] **Step 5: Generate the new CSVs**

```bash
cd pawtrail_dbt
# The distribution only: how many accounts sit at each level of renewal
# exposure (expect 339 / 1256 / 1099 / 306). Every other metric on this model is
# tautological at this grain and is deliberately left out. cohort '0' *is* the
# definition of has_faced_renewal = false, so within it renewal_unexposed
# equals the cohort size, renewal_exposed is 0, and pct_base_never_rebilled --
# whose numerator is its own denominator there -- reads 1.0, i.e. "100% of the
# base has never been rebilled". Identical in kind to at_risk_account_rate
# grouped by risk_driver, which METRICS.md documents and which was removed from
# that export for the same reason.
../.venv/bin/mf query --metrics assessable_base_accounts --group-by account__cycle_exposure_cohort --order account__cycle_exposure_cohort --csv ../dashboard/control_cycle_exposure.csv
# The share itself, ungrouped -- the only grain at which it answers "what
# fraction of the base has never faced a renewal", and the grain both the
# band-2 card and the decision contract read it at.
../.venv/bin/mf query --metrics pct_base_never_rebilled,renewal_unexposed_accounts,assessable_base_accounts --csv ../dashboard/control_base_never_rebilled.csv
../.venv/bin/mf query --metrics avg_breakeven_cycles,contribution_margin_per_cycle,share_breakeven_cycle_exposed --group-by account__channel --order account__channel --csv ../dashboard/control_breakeven_by_channel.csv
../.venv/bin/mf query --metrics effective_cac,cac_uplift_pct,fulfillment_waste_usd --group-by effective_cac_row__channel --order effective_cac_row__channel --csv ../dashboard/control_effective_cac.csv
../.venv/bin/mf query --metrics at_risk_accounts,recoverable_mrr_usd --group-by account__damage_class --order account__damage_class --csv ../dashboard/control_at_risk_by_damage_class.csv
../.venv/bin/mf query --metrics state_penetration,remaining_eligible_accounts --group-by saturation_state__state --order state_penetration --csv ../dashboard/control_state_saturation.csv
```

The two transparency models carry no metrics (they are publication tables, not aggregable facts), so they are written straight from the warehouse:

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
c.sql('select * from main.fct_censoring_register order by excluded_accounts desc').write_csv('../dashboard/control_censoring_register.csv')
c.sql('select * from main.fct_login_timing_distribution order by band_order').write_csv('../dashboard/control_login_timing.csv')
print('ok')
"
ls -1 ../dashboard/control_*.csv | wc -l
```

Expected: `18`.

- [ ] **Step 6: Vanity-metric audit**

Spec §1.7 requires an explicit decision for the 10 metrics that never reach a CSV. In this phase the decision is to **document**, because the decision-contract table belongs to Phase 3. Append a new section to `METRICS.md`:

```markdown
## Vanity-metric audit

Crystallize's test: *if the number does not help you decide the next step, it
belongs in a campaign report, not the core KPI set.* Ten metrics are declared in
the semantic layer but reach no CSV and no dashboard. Each is listed here with
the decision taken; the thresholds that justify keeping them land with the
decision-contract table (Phase 3).

| Metric | Decision | Rationale |
|---|---|---|
| `wow_subscription_growth` | keep — promote to dashboard | Growth momentum is one of Crystallize's four decision questions |
| `eligible_premium_accounts` | keep — denominator | Published beside `attach_rate` per the censoring rule |
| `channel_spend` | keep — denominator | Feeds `cac_uplift_pct` |
| `contribution_margin_per_subscription` | keep — renamed context | First-cycle margin; now explicitly distinct from `contribution_margin_per_cycle` |
| `task_completion_rate` | keep — promote to dashboard | The only engagement-depth signal the data supports |
| `task_engagement_rate` | keep — promote to dashboard | Same |
| `zero_digital_access_accounts` | keep — feeds the CS queue | Now readable through `damage_class` |
| `zero_task_accounts` | keep — feeds the CS queue | Same |
| `avg_delivery_delay_days` | keep — operations | Pairs with `kit_late_rate` in the OH story |
| `kit_late_rate` | keep — operations | Same |

No metric was removed. The audit's finding is that all ten are decision-relevant
and the gap was in **publication**, not in the metric set — which is itself the
answer to Crystallize's test, and is why the Phase 3 decision contract assigns
each a threshold rather than deleting it.
```

- [ ] **Step 7: Correct the false claim in METRICS.md**

Locate line 265 (`Every metric computable from the existing generator output is already implemented above.`) and replace the paragraph with:

```markdown
Every metric computable from the existing generator output is implemented above.
This claim was **false** between the initial build and the Phase 1 gap-closure
work: twelve metrics computable from the same seeds — the billing-cycle clock,
per-cycle contribution margin, breakeven cycles, fulfillment waste, effective
CAC, the censoring register, the login-timing distribution, the damage-class
split, state saturation, portfolio concentration, and the two renewal-exposure
counts — were absent. They are now implemented; the table below is the set that
remains genuinely blocked on new synthetic data.
```

- [ ] **Step 8: Run the consistency sweep**

`METRICS.md` claims "33 metrics" and "8 semantic models" in its header. Update to the real numbers:

```bash
cd pawtrail_dbt && ../.venv/bin/python -c "
import yaml
m = yaml.safe_load(open('models/marts/_metrics.yml'))
s = yaml.safe_load(open('models/marts/_semantic_models.yml'))
print('declared metrics:', len(m['metrics']))
print('semantic models:', len(s['semantic_models']))
"
```

Update both counts in the `METRICS.md` header and document each new metric in its corresponding section, following the existing format (**Definition**, **Formula**, **Source**).

- [ ] **Step 9: Update dashboard/README.md**

Add the 8 new CSVs to the views list and record that the four-question structure arrives in Phase 3.

- [ ] **Step 10: Final build and acceptance check**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build 2>&1 | tail -4
cd /home/iagoadvaz/projects/pawtrail-launch-analytics/.claude/worktrees/phase-1-metrics && .venv/bin/pytest -q 2>&1 | tail -4
```

Expected: `dbt build` with `ERROR=0`; `pytest` with 22 passed (this phase does not touch the generator, so the count is unchanged).

- [ ] **Step 11: Commit**

```bash
git add pawtrail_dbt/dbt_project.yml pawtrail_dbt/models/marts/_metrics.yml \
        dashboard/ METRICS.md
git commit -m "feat: add benchmark reference metric, export new CSVs, correct METRICS.md

Closes the spec's global acceptance criterion 1: the claim on line 265 is no
longer false."
```

---

## Self-Review

**Spec coverage (§2, Phase 1):**

| Requirement | Task |
|---|---|
| 1.1 Billing-cycle clock | 1, 2, 3 |
| 1.2 Breakeven bridge | 4, 5 |
| 1.3 Loaded cost and effective CAC | 6, 7 |
| 1.4 Censoring register and distributions | 8, 9 |
| 1.5 Cross-cuts — quality-adjusted CAC | 7 (per-channel uplift) + 10 (`damage_class` crossable with `account__channel`) |
| 1.5 Cross-cuts — saturation curve | 11 |
| 1.5 Cross-cuts — concentration | 11 |
| 1.5 Cross-cuts — MRR and CAC on one timeline | **Phase 3** (a visual composition, not a metric; both metrics already exist) |
| 1.6 Benchmark reference lines | 12 |
| 1.7 Vanity audit | 12 |
| 1.8 Pruning vs. damage | 10 |

**Global acceptance:** §6.1 → Task 12 Step 7. §6.2 → the naming constraint sits in Global Constraints and in the header of `int_billing_cycles.sql`. §6.3 → Tasks 8 and 12. §6.4 → partially (Task 12 Step 6 documents it; the contract table is Phase 3). §6.5 → every task build. §6.6 → every task's `mf query`. §6.7 → Task 12 Step 5.

**Known, deliberate gaps:** acceptance criterion §6.4 ("every metric has a row in the decision contract") only closes with Phase 3, because the contract table is that plan's deliverable. Item 1.5's "MRR and CAC on the same timeline" likewise. Both are noted above rather than forced into this phase.
