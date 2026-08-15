with subs as (
    select account_id, channel, pet_tier, date_trunc('week', pawtrail_signup_date) as signup_week
    from {{ ref('stg_subscriptions') }}
),

activation as (
    select account_id, combined_activated_30d, is_mature_30d
    from {{ ref('int_activation_funnel') }}
),

-- Contribution margin is joined per account at its own pet tier. Averaging the
-- three tier prices unweighted (the earlier approach) produced the same constant
-- in every channel and week, so the metric drew a flat line that no amount of
-- segmentation could move.
subs_priced as (
    select
        s.channel,
        s.signup_week,
        s.account_id,
        a.combined_activated_30d,
        a.is_mature_30d,
        p.monthly_price_usd,
        p.monthly_price_usd - p.kit_cogs_usd - p.shipping_cost_usd as contribution_margin
    from subs s
    left join activation a on s.account_id = a.account_id
    left join {{ ref('dim_pricing') }} p on s.pet_tier = p.pet_tier
),

weekly_subs as (
    select
        channel,
        signup_week,
        count(*) as new_subscriptions,
        -- Restricted to the mature cohort for the same reason the activation
        -- metrics are: a week-old signup that has not activated yet is not a
        -- failed acquisition, and counting it as one inflates recent CPA.
        sum(case when is_mature_30d then 1 else 0 end) as mature_subscriptions,
        sum(case when combined_activated_30d and is_mature_30d then 1 else 0 end)
            as activated_subscriptions,
        avg(monthly_price_usd) as avg_price,
        -- Incremental MRR added by the attach (spec §6, business signals). Summed
        -- at each account's own tier price, so the pet-tier mix moves it; a
        -- headcount times a blended price would not.
        sum(monthly_price_usd) as mrr_usd,
        avg(contribution_margin) as contribution_margin_per_subscription,
        -- The total the per-subscription average is drawn from. Both payback and
        -- the reported margin per subscription are built from this rather than
        -- from the average above: averaging an already-averaged column across
        -- weeks weights a week of three signups the same as a week of three
        -- hundred, and a launch's earliest weeks are its smallest.
        sum(contribution_margin) as total_contribution_margin_usd
    from subs_priced
    group by 1, 2
),

-- date_trunc is defensive here: the generator already emits Monday-aligned week
-- starts, so this is a no-op on correct data. It keeps the join below from
-- silently matching zero rows if the launch date ever moves off a Monday.
spend as (
    select channel, date_trunc('week', week_start_date) as signup_week, spend_usd
    from {{ ref('fct_marketing_spend') }}
),

-- The grain is every (channel, week) either side knows about, not just the weeks
-- that produced signups. Driving the model off the signup weeks alone and
-- left-joining spend onto them drops any week that spent money without
-- converting anyone -- and the week that always fits that description is the
-- last one, because its spend has not had time to convert yet. That is 7% of
-- this launch's spend leaving the warehouse silently: every surviving row stays
-- internally consistent, so nothing fails. `union` and not `union all`: a
-- channel-week present on both sides must yield one row, or the surrogate key
-- stops being unique and every measure double-counts.
channel_weeks as (
    select channel, signup_week from weekly_subs
    union
    select channel, signup_week from spend
),

-- The estimate below is referenced twice in the final select, so it is computed
-- once here rather than repeated -- a select alias cannot be reused inside the
-- same select list.
joined as (
    select
        cw.channel,
        cw.signup_week,
        -- Counts coalesce to 0: a week that acquired nobody acquired zero, and
        -- leaving these null would make `sum` skip the row and quietly restore
        -- the same understatement in the semantic layer. The per-subscription
        -- averages below deliberately stay null -- a week with no subscriptions
        -- has no average price or margin, and coalescing those to 0 would drag
        -- every roll-up of them toward zero.
        coalesce(w.new_subscriptions, 0) as new_subscriptions,
        coalesce(w.mature_subscriptions, 0) as mature_subscriptions,
        coalesce(w.activated_subscriptions, 0) as activated_subscriptions,
        w.avg_price,
        coalesce(w.mrr_usd, 0) as mrr_usd,
        w.contribution_margin_per_subscription,
        coalesce(w.total_contribution_margin_usd, 0) as total_contribution_margin_usd,
        s.spend_usd,
        -- Estimated eventual activations across the whole acquired cohort: the
        -- activation rate observed among the week's *mature* accounts, applied
        -- to every account the week acquired. Spend is counted for the full
        -- cohort, so dividing it by activated-and-mature alone puts a complete
        -- numerator over a partial denominator and reports an artificially
        -- catastrophic cost per activated account in exactly the most recent
        -- weeks -- the ones a launch dashboard is read for. Null while no
        -- account in the week is mature: the activation rate is unestimable
        -- then, and an absent number is honest where a censored one is not.
        (w.activated_subscriptions * 1.0 / nullif(w.mature_subscriptions, 0))
            * w.new_subscriptions as estimated_activated_subscriptions
    from channel_weeks cw
    left join weekly_subs w
        on cw.channel = w.channel and cw.signup_week = w.signup_week
    left join spend s
        on cw.channel = s.channel and cw.signup_week = s.signup_week
)

select
    -- Surrogate key: the grain is (channel, week), so `channel` alone is not a
    -- valid primary entity for the semantic model.
    channel || '_' || cast(signup_week as varchar) as channel_week_key,
    channel,
    signup_week,
    new_subscriptions,
    mature_subscriptions,
    activated_subscriptions,
    estimated_activated_subscriptions,
    spend_usd,
    -- The spend that pairs with the estimate above. Nulled for weeks no account
    -- has matured in, so that rolling cost per activated account up across weeks
    -- cannot add spend to the numerator whose activations are missing from the
    -- denominator. `spend_usd` stays intact for cac and channel_spend, which are
    -- whole-cohort figures and correctly count every dollar.
    case when mature_subscriptions > 0 then spend_usd end
        as activation_measurable_spend_usd,
    spend_usd / nullif(new_subscriptions, 0) as cac,
    spend_usd / nullif(estimated_activated_subscriptions, 0)
        as cost_per_activated_account,
    avg_price,
    mrr_usd,
    contribution_margin_per_subscription,
    total_contribution_margin_usd,
    -- CAC payback in months (spec §6): acquisition cost divided by the monthly
    -- contribution margin it buys. Expressed as the week's whole spend over the
    -- week's whole margin rather than as cac divided by the per-subscription
    -- average -- the two are equal at this grain, but only this form sums
    -- correctly when the semantic layer rolls weeks or channels together.
    -- nullif keeps a zero-or-negative-margin week from producing an infinite
    -- payback.
    spend_usd / nullif(total_contribution_margin_usd, 0) as cac_payback_months
from joined
