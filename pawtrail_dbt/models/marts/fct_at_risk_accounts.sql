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
    case
        when no_digital_access_14d and kit_failed_sla then 'both_legs_failed'
        when kit_failed_sla then 'physical_failure'
        when no_digital_access_14d then 'digital_failure'
        when no_tasks_completed then 'onboarding_gap'
        else 'healthy'
    end as risk_driver,
    (no_digital_access_14d or kit_failed_sla or no_tasks_completed) as is_at_risk
from flagged
