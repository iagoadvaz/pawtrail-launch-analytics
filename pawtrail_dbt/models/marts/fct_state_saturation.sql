-- Penetration against remaining base, per state -- plus margin concentration.
--
-- WHY IT MATTERS: today the dashboard reads slowing growth as a performance
-- signal. A state approaching the carrying capacity of its own niche decelerates
-- for reasons no marketing spend can fix, and confusing that with a channel
-- problem is the classic launch-window misdiagnosis. Both readings require
-- seeing penetration and remaining base side by side, which is what this model
-- delivers.
with latest_week as (
    select max(signup_week) as final_week from {{ ref('fct_weekly_attach') }}
),

-- The portfolio's state at the end of the window.
final_state as (
    select
        w.state,
        w.cumulative_subscriptions,
        w.eligible_premium_accounts
    from {{ ref('fct_weekly_attach') }} w
    cross join latest_week l
    where w.signup_week = l.final_week
),

-- How many accounts the state acquired in the last week. This is the numerator
-- of the "is it still growing?" reading.
last_week_new as (
    select
        a.state,
        count(*) as new_subscriptions_last_week
    from {{ ref('fct_subscriptions') }} s
    join {{ ref('dim_accounts') }} a on s.account_id = a.account_id
    cross join latest_week l
    where s.signup_week = l.final_week
    group by 1
),

-- Aggregated to state grain BEFORE the join, so it cannot fan out the
-- fct_weekly_attach rows.
margin_by_state as (
    select
        a.state,
        sum(u.contribution_margin_per_cycle) as cycle_margin_usd
    from {{ ref('fct_subscription_unit_economics') }} u
    join {{ ref('dim_accounts') }} a on u.account_id = a.account_id
    group by 1
),

total_margin as (
    select sum(cycle_margin_usd) as all_states_margin from margin_by_state
)

select
    f.state,
    -- The snapshot's own date, carried so the semantic model has a time
    -- dimension: MetricFlow requires an agg_time_dimension for every measure,
    -- and this model has three. Declaring it in _semantic_models.yml without
    -- producing it here leaves `dbt build` green and fails 17 checks at
    -- `mf validate-configs` -- the model is a single snapshot at the final
    -- week, so every row carries the same value by construction.
    l.final_week as snapshot_date,
    f.cumulative_subscriptions,
    f.eligible_premium_accounts,
    f.cumulative_subscriptions * 1.0 / nullif(f.eligible_premium_accounts, 0) as penetration,
    f.eligible_premium_accounts - f.cumulative_subscriptions as remaining_eligible_accounts,
    (f.eligible_premium_accounts - f.cumulative_subscriptions) * 1.0
        / nullif(f.eligible_premium_accounts, 0) as remaining_share,
    coalesce(n.new_subscriptions_last_week, 0) as new_subscriptions_last_week,
    m.cycle_margin_usd,
    -- Concentration: how much of total margin depends on this state. A
    -- concentrated book is worth less than a diversified one at the same MRR.
    m.cycle_margin_usd / nullif(t.all_states_margin, 0) as margin_share
from final_state f
left join last_week_new n on f.state = n.state
left join margin_by_state m on f.state = m.state
cross join total_margin t
cross join latest_week l
