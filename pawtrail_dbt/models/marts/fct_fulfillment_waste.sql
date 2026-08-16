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
        is_mature_30d,
        -- Both carried for the waste_reason split below, which separates a
        -- customer who engaged but whose kit missed the SLA from one who never
        -- showed up at all. Without them the split cannot be computed and the
        -- model does not build.
        first_login_date,
        days_to_first_login
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
