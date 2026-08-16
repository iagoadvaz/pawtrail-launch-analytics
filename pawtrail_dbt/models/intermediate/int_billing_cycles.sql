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
