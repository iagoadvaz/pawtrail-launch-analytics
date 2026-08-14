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
        avg(contribution_margin) as contribution_margin_per_subscription
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

-- The estimate below is referenced twice in the final select, so it is computed
-- once here rather than repeated -- a select alias cannot be reused inside the
-- same select list.
joined as (
    select
        w.channel,
        w.signup_week,
        w.new_subscriptions,
        w.mature_subscriptions,
        w.activated_subscriptions,
        w.avg_price,
        w.mrr_usd,
        w.contribution_margin_per_subscription,
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
    from weekly_subs w
    left join spend s on w.channel = s.channel and w.signup_week = s.signup_week
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
    -- CAC payback in months (spec §6): acquisition cost divided by the monthly
    -- contribution margin it buys. Computed here rather than as a derived metric
    -- because both inputs already live at this grain, and nullif keeps a
    -- zero-or-negative-margin week from producing an infinite payback.
    (spend_usd / nullif(new_subscriptions, 0))
        / nullif(contribution_margin_per_subscription, 0) as cac_payback_months
from joined
