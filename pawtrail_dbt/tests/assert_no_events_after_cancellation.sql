-- Fails if any BILLABLE EVENT is recorded at or after an account's
-- cancellation. Charging an account after it left is the most expensive
-- mistake this generator can make.
--
-- THE ASSERTION RUNS AGAINST THE EVENT STREAM, NOT THE DERIVED STATE. An
-- earlier version of this test compared int_subscription_state.state against a
-- cancellation cycle derived from the same expression the state column itself
-- is built from -- so it compared a value against itself and could not fail.
-- Injecting 20 post-cancellation `renewed` events into the stream left it
-- returning zero rows. Anything downstream of int_subscription_state is
-- disqualified as the subject of this test for that reason.
with canceled as (
    select
        account_id,
        min(cycle_index) as canceled_at_cycle,
        min(event_seq)   as canceled_at_seq
    from {{ ref('stg_subscription_events') }}
    where event_type = 'canceled'
    group by 1
)

select e.account_id, e.cycle_index, e.event_seq, e.event_type, c.canceled_at_cycle
from {{ ref('stg_subscription_events') }} e
join canceled c on e.account_id = c.account_id
where e.event_seq > c.canceled_at_seq
  and e.event_type in ('renewed', 'tier_changed', 'skipped', 'resumed', 'paused')
