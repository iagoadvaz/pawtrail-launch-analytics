-- Grain account x cycle, enriched with the segmentation dimensions. This is the
-- table behind rebill rate, churn, retention, skip and pause.
with state as (
    select * from {{ ref('int_subscription_state') }}
),

accounts as (
    select account_id, state as account_state, channel, premium_tenure_band
    from {{ ref('dim_accounts') }}
),

pricing as (
    select pet_tier, monthly_price_usd from {{ ref('dim_pricing') }}
)

select
    s.subscription_state_key,
    s.account_id,
    s.cycle_index,
    s.renewal_due_date,
    s.state,
    s.is_retained,
    s.churned_this_cycle,
    -- Carried so at_risk_accounts_this_cycle has a column to read. The
    -- at-risk denominator was added to int_subscription_state to fix the churn
    -- hazard, but stopped there: the measure that consumes it lives on this
    -- mart, so mf could not resolve it while dbt build stayed green.
    s.at_risk_this_cycle,
    s.pet_tier_at_cycle,
    a.account_state,
    a.channel,
    a.premium_tenure_band,
    -- Revenue recognised in the cycle. Skip and pause keep the subscription but
    -- do not bill, so cycle MRR is zero for them -- and that difference between
    -- "retained" and "billing" is exactly what the replenishment model makes
    -- material and a SaaS model would not have.
    case when s.state = 'active' then p.monthly_price_usd else 0 end as cycle_mrr_usd,
    -- What the subscription is WORTH this cycle, as distinct from what it
    -- billed. A skipped or paused account is still a subscriber at its tier;
    -- only a cancellation destroys value. The MRR movement bridge is built on
    -- this column rather than on cycle_mrr_usd, because a bridge built on cash
    -- books a one-cycle skip as a full-price contraction and its return as a
    -- reactivation -- reporting a customer as shrinking and then recovering
    -- when nothing about the subscription changed.
    case when s.state <> 'canceled' then p.monthly_price_usd else 0 end
        as subscription_value_usd,
    -- The gap between the two: revenue a live subscription did not bill this
    -- cycle. This is the replenishment-specific signal the cash bridge used to
    -- hide inside contraction, and it is more useful named -- "how much revenue
    -- did skip and pause defer" is an operational question with an owner, where
    -- a contraction line mixing it with genuine downgrades is not.
    case when s.state in ('skipped', 'paused') then p.monthly_price_usd else 0 end
        as deferred_billing_usd,
    -- Denominator of the cycle-1 rebill rate: accounts that reached the end of
    -- cycle 0 alive and whose cycle 1 has come due. Restricting here rather than
    -- in the metric stops a dimensional cut from accidentally changing the
    -- denominator.
    (s.cycle_index = 1) as is_cycle_one,
    (s.cycle_index = 1 and s.state = 'active') as rebilled_at_cycle_one
from state s
join accounts a on s.account_id = a.account_id
join pricing p on s.pet_tier_at_cycle = p.pet_tier
