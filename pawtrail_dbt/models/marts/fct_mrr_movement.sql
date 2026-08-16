-- The MRR movement decomposition: new, expansion, contraction, churned -- plus
-- deferred billings, which sits beside the bridge rather than inside it.
--
-- THE BRIDGE IS BUILT ON SUBSCRIPTION VALUE, NOT ON CASH BILLED, and that is
-- the whole design. An earlier version summed cycle_mrr_usd, so a one-cycle
-- skip booked the subscription's full price as contraction and its return the
-- next cycle booked as reactivation. At cycle 1 that put $4,795 of skip and
-- pause inside $6,387.79 of "contraction" -- reported as customers shrinking,
-- when the tier never moved and the revenue was deferred by a matter of weeks.
-- It also forced a reactivation bucket into existence purely to make the
-- arithmetic close (65 return-from-skip plus 28 return-from-pause rows at cycle
-- 2 alone).
--
-- On a value basis none of that arises: a skip does not change what the
-- subscription is worth, so it never enters the bridge, and there is no
-- reactivation term because cancellation is absorbing -- a non-zero one would
-- mean a cancelled account had come back. Contraction now means exactly one
-- thing, a tier downgrade, which is what makes it comparable to a published
-- NRR at all.
--
-- WHAT THE DEFERRED LINE IS FOR: skipped and paused revenue is the signal a
-- replenishment business actually has and a SaaS business does not. Published
-- on its own line it answers "how much revenue did skip and pause defer this
-- cycle" -- a question with an owner. Buried inside contraction it answered
-- nothing and corrupted a benchmark metric on the way.
--
-- WHY THE EXPANSION ARM MATTERS: without upgrade events, expansion MRR is
-- always zero and NRR is capped at 100% by construction. An indicator
-- structurally incapable of exceeding 100% is misleading, not incomplete. That
-- is why spec item 2.7 (tier change) is a prerequisite for this model. Note
-- that clearing the structural cap does not lift NRR above 100% on this seed --
-- see Task 5 Step 5 -- it makes the number mean what its name says.
with lifecycle as (
    select
        account_id,
        cycle_index,
        -- The grain is (cycle, due week), not cycle alone. cycle_index spans
        -- ~120 distinct due dates, so a semantic model keyed on it cannot carry
        -- a time dimension -- and MetricFlow requires one for every measure.
        -- Regraining is the better fix regardless: it is what lets the bridge
        -- be read as a time series rather than as four opaque buckets.
        date_trunc('week', renewal_due_date) as cycle_due_week,
        subscription_value_usd,
        deferred_billing_usd,
        state
    from {{ ref('fct_subscription_lifecycle') }}
),

-- The account's subscription value at the previous cycle, so the change can be
-- classified.
with_previous as (
    select
        account_id,
        cycle_index,
        cycle_due_week,
        subscription_value_usd,
        deferred_billing_usd,
        state,
        lag(subscription_value_usd) over (
            partition by account_id order by cycle_index
        ) as previous_value_usd
    from lifecycle
),

classified as (
    select
        cycle_index,
        cycle_due_week,
        -- New: the account's first appearance, carrying value.
        sum(case
            when previous_value_usd is null and subscription_value_usd > 0
            then subscription_value_usd else 0
        end) as new_mrr_usd,
        -- Expansion: moved up a tier while alive.
        sum(case
            when previous_value_usd is not null
                 and subscription_value_usd > previous_value_usd
                 and previous_value_usd > 0
            then subscription_value_usd - previous_value_usd else 0
        end) as expansion_mrr_usd,
        -- Contraction: moved DOWN a tier while alive. Nothing else reaches this
        -- bucket -- a skip leaves subscription_value_usd untouched, and a
        -- cancellation is churn.
        sum(case
            when previous_value_usd is not null
                 and subscription_value_usd < previous_value_usd
                 and state <> 'canceled'
            then previous_value_usd - subscription_value_usd else 0
        end) as contraction_mrr_usd,
        -- Churned: cancelled this cycle, and the value it carried is gone.
        sum(case
            when state = 'canceled' and coalesce(previous_value_usd, 0) > 0
            then previous_value_usd else 0
        end) as churned_mrr_usd,
        sum(coalesce(previous_value_usd, 0)) as starting_mrr_usd,
        sum(subscription_value_usd) as ending_mrr_usd,
        -- Beside the bridge, deliberately not inside it: this revenue was not
        -- lost, it was not billed this cycle.
        sum(deferred_billing_usd) as deferred_billings_usd
    from with_previous
    group by 1, 2
)

select
    -- Surrogate key: the grain is (cycle, week), so cycle_index alone is not
    -- unique and declaring it the primary entity would be a false uniqueness
    -- claim that can fan out joins. Same pattern as channel_week_key.
    cast(cycle_index as varchar) || '_' || cast(cycle_due_week as varchar)
        as mrr_movement_key,
    cycle_index,
    cycle_due_week,
    starting_mrr_usd,
    new_mrr_usd,
    expansion_mrr_usd,
    contraction_mrr_usd,
    churned_mrr_usd,
    ending_mrr_usd,
    deferred_billings_usd
from classified
