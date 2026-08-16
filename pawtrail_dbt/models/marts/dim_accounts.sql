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
