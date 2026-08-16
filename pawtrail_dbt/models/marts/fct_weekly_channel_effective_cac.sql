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
