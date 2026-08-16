-- Subscription state at every cycle that actually came due.
--
-- THE SPINE COMES FROM int_billing_cycles, NOT FROM THE EVENTS. This is
-- deliberate: an account that canceled at cycle 1 emits no events at cycles 2
-- and 3, and deriving the grain from the events would make those accounts simply
-- vanish from the denominator -- which is exactly how a retention rate starts
-- rising while the business shrinks. The spine guarantees that those who left
-- stay counted.
with cycles as (
    select account_id, cycle_index, renewal_due_date
    from {{ ref('int_billing_cycles') }}
),

events as (
    select * from {{ ref('stg_subscription_events') }}
),

-- Which cycle the account canceled at, if it canceled.
cancellation as (
    select account_id, min(cycle_index) as canceled_at_cycle
    from events
    where event_type = 'canceled'
    group by 1
),

-- The state-defining event for the cycle. An account can have both a
-- tier_changed and a renewed in the same cycle; the state event is the one with
-- the highest event_seq among those that define state.
cycle_event as (
    select
        account_id,
        cycle_index,
        event_type,
        row_number() over (
            partition by account_id, cycle_index order by event_seq desc
        ) as recency
    from events
    where event_type in ('renewed', 'skipped', 'paused', 'canceled', 'activated')
),

-- The tier in force at the cycle: the last tier_changed up to here, or the
-- original tier.
tier_at_cycle as (
    select
        c.account_id,
        c.cycle_index,
        coalesce(
            (
                select e.new_pet_tier
                from events e
                where e.account_id = c.account_id
                  and e.event_type = 'tier_changed'
                  and e.cycle_index <= c.cycle_index
                order by e.event_seq desc
                limit 1
            ),
            s.pet_tier
        ) as pet_tier_at_cycle
    from cycles c
    join {{ ref('stg_subscriptions') }} s on c.account_id = s.account_id
),

-- Pause carried forward: an account is paused at cycle n if its most recent
-- pause/resume event at or before cycle n was a 'paused'. This is what makes a
-- still-paused cycle -- which emits no event -- resolve to 'paused' rather than
-- falling through to 'active'.
paused_state as (
    select
        c.account_id,
        c.cycle_index,
        coalesce(
            (
                select ev.event_type = 'paused'
                from {{ ref('stg_subscription_events') }} ev
                where ev.account_id = c.account_id
                  and ev.cycle_index <= c.cycle_index
                  and ev.event_type in ('paused', 'resumed')
                order by ev.cycle_index desc, ev.event_seq desc
                limit 1
            ),
            false
        ) as is_paused
    from cycles c
)

select
    c.account_id || '_' || cast(c.cycle_index as varchar) as subscription_state_key,
    c.account_id,
    c.cycle_index,
    c.renewal_due_date,
    case
        when x.canceled_at_cycle is not null and c.cycle_index >= x.canceled_at_cycle
            then 'canceled'
        when e.event_type = 'skipped' then 'skipped'
        when e.event_type = 'paused' then 'paused'
        -- A STILL-PAUSED cycle emits no event at all: when the resume draw
        -- fails, the generator `continue`s without writing a record. Reading
        -- pause from a single event therefore loses it, and the `else` branch
        -- below silently reports the account as active -- and bills it. In the
        -- generated data that is 21 rows and $629.79 of phantom MRR, and it
        -- understates paused volume by 17%, which is precisely the number
        -- Shopify asks for.
        --
        -- So pause is carried FORWARD from the last pause/resume event rather
        -- than read from this cycle's event.
        when p.is_paused then 'paused'
        else 'active'
    end as state,
    -- Retained = still paying. A skipped or paused account is still a subscriber
    -- but does NOT generate revenue that cycle -- which is why is_retained is
    -- narrower than "not canceled", and why the two readings must exist
    -- separately.
    (x.canceled_at_cycle is null or c.cycle_index < x.canceled_at_cycle)
        as is_retained,
    -- coalesce, because `x.canceled_at_cycle = c.cycle_index` is NULL (not
    -- false) for every account that never cancelled -- 72% of rows. The column
    -- is declared boolean and its sibling is_retained is null-safe; leaving
    -- this one three-valued means any future `where not churned_this_cycle`
    -- silently drops those rows.
    coalesce(x.canceled_at_cycle = c.cycle_index, false) as churned_this_cycle,
    -- Alive ENTERING this cycle, and therefore able to churn during it. This is
    -- the denominator a hazard rate needs: an account that cancelled at cycle 1
    -- is carried forward as 'canceled' at cycles 2 and 3, and counting it in
    -- those denominators understates the hazard by 24% at cycle 2 and 31% at
    -- cycle 3 -- and steepens the apparent decline, which is the one shape
    -- spec section 5.2(b) says matters.
    (x.canceled_at_cycle is null or c.cycle_index <= x.canceled_at_cycle)
        as at_risk_this_cycle,
    t.pet_tier_at_cycle
from cycles c
left join cancellation x on c.account_id = x.account_id
left join cycle_event e
    on c.account_id = e.account_id
   and c.cycle_index = e.cycle_index
   and e.recency = 1
left join paused_state p
    on c.account_id = p.account_id and c.cycle_index = p.cycle_index
left join tier_at_cycle t
    on c.account_id = t.account_id
   and c.cycle_index = t.cycle_index
