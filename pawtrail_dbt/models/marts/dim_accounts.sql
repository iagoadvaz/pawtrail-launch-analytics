-- Band boundaries are the standard subscription-tenure reads (under 6 months,
-- 6-12 months, 1-2 years, 2 years+) rather than equal-width buckets. Task 3
-- generates tenure decaying from ~900 days at launch to ~420 by day 120 with
-- 150-day noise, clipped to [30, 900], so all four bands are populated and the
-- adoption-order signal is visible across them.
select
    account_id,
    state,
    pet_tier,
    channel,
    premium_tenure_days,
    case
        when premium_tenure_days <= 180 then '0-180'
        when premium_tenure_days <= 365 then '181-365'
        when premium_tenure_days <= 730 then '366-730'
        else '731+'
    end as premium_tenure_band
from {{ ref('stg_subscriptions') }}
