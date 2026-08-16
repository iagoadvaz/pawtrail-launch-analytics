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
