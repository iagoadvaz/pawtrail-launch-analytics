-- Fails (returns rows) if cumulative_subscriptions ever drops week over week
-- within a state. That can only happen if the state x week spine has gaps,
-- which in turn means any cross-state sum of this measure understates the
-- national total for the weeks where a state is missing.
with ordered as (
    select
        state,
        signup_week,
        cumulative_subscriptions,
        lag(cumulative_subscriptions) over (
            partition by state order by signup_week
        ) as previous_cumulative_subscriptions
    from {{ ref('fct_weekly_attach') }}
)

select state, signup_week, cumulative_subscriptions, previous_cumulative_subscriptions
from ordered
where previous_cumulative_subscriptions is not null
  and cumulative_subscriptions < previous_cumulative_subscriptions
