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
)

select
    -- Surrogate key: the grain is (channel, week), so `channel` alone is not a
    -- valid primary entity for the semantic model.
    w.channel || '_' || cast(w.signup_week as varchar) as channel_week_key,
    w.channel,
    w.signup_week,
    w.new_subscriptions,
    w.mature_subscriptions,
    w.activated_subscriptions,
    s.spend_usd,
    s.spend_usd / nullif(w.new_subscriptions, 0) as cac,
    -- Denominator is activated_subscriptions as-is (activated AND mature), not
    -- rescaled to the full acquired cohort. A week that is only partially
    -- mature therefore reads a high, not-yet-comparable cost per activated
    -- account -- there just aren't many activated+mature accounts yet to divide
    -- spend by, even though spend for the week is already fully counted. When
    -- comparing CPA across weeks, treat the most recent 1-2 weeks as still
    -- settling rather than as directly comparable to fully-mature earlier weeks.
    s.spend_usd / nullif(w.activated_subscriptions, 0) as cost_per_activated_account,
    w.avg_price,
    w.mrr_usd,
    w.contribution_margin_per_subscription,
    -- CAC payback in months (spec §6): acquisition cost divided by the monthly
    -- contribution margin it buys. Computed here rather than as a derived metric
    -- because both inputs already live at this grain, and nullif keeps a
    -- zero-or-negative-margin week from producing an infinite payback.
    (s.spend_usd / nullif(w.new_subscriptions, 0))
        / nullif(w.contribution_margin_per_subscription, 0) as cac_payback_months
from weekly_subs w
left join spend s on w.channel = s.channel and w.signup_week = s.signup_week
