with funnel as (
    select * from {{ ref('int_activation_funnel') }}
),

flagged as (
    select
        account_id,
        state,
        channel,
        pet_tier,
        pawtrail_signup_date,
        days_observed,
        no_digital_access_14d,
        (kit_lost or kit_delivered_date is null or not kit_activated_sla) as kit_failed_sla,
        (coalesce(care_tasks_completed_first_cycle, 0) = 0) as no_tasks_completed
    from funnel
    -- Only accounts that have actually had the chance to fail. Flagging a
    -- two-day-old signup as "no digital access in 14 days" would fill the CS
    -- queue with accounts that are simply new.
    where days_observed >= {{ var('at_risk_no_login_days') }}
)

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
    -- is a real ~86.5% per-seed outcome (Poisson, expected count ~0.145 among
    -- accounts with confirmed on-time digital + kit), not a bug in this case
    -- branch. Do not "fix" an empty bucket here by editing this condition,
    -- and do not add a non-degeneracy test asserting this branch is
    -- populated -- it would fail on most re-seeds.
    case
        when no_digital_access_14d and kit_failed_sla then 'both_legs_failed'
        when kit_failed_sla then 'physical_failure'
        when no_digital_access_14d then 'digital_failure'
        when no_tasks_completed then 'onboarding_gap'
        else 'healthy'
    end as risk_driver,
    (no_digital_access_14d or kit_failed_sla or no_tasks_completed) as is_at_risk
from flagged
