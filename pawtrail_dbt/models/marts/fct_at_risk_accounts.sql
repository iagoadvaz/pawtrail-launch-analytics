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
        -- Gated on the 30-day cohort, not on this model's 14-day floor.
        -- care_tasks_completed_first_cycle counts tasks across the whole first
        -- cycle, so an account 14 days old still has half of it left. It also
        -- has to match the zero_task_accounts KPI exactly -- one concept, two
        -- consumers -- which assert_zero_task_flag_matches_the_kpi_definition
        -- enforces. This task replaces the whole model, so dropping the gate
        -- here silently reverts that fix: without it the test fails on 37 rows.
        (f.is_mature_30d and coalesce(f.care_tasks_completed_first_cycle, 0) = 0)
            as no_tasks_completed,
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
