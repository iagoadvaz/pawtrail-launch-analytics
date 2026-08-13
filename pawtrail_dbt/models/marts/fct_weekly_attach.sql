with weekly_signups as (
    select
        state,
        date_trunc('week', pawtrail_signup_date) as signup_week,
        count(*) as new_subscriptions
    from {{ ref('stg_subscriptions') }}
    group by 1, 2
),

premium_base as (
    select * from {{ ref('fct_premium_base') }}
),

week_spine as (
    select distinct signup_week from weekly_signups
),

-- Every state must appear in every launch week. Without this spine, a state
-- with no signups in a given week produces no row at all, so summing
-- cumulative_subscriptions across states understates the national total for
-- that week and the cumulative line goes non-monotonic.
state_week_spine as (
    select
        p.state,
        w.signup_week
    from premium_base p
    cross join week_spine w
),

filled as (
    select
        sp.state,
        sp.signup_week,
        coalesce(s.new_subscriptions, 0) as new_subscriptions
    from state_week_spine sp
    left join weekly_signups s
        on sp.state = s.state
       and sp.signup_week = s.signup_week
),

cumulative as (
    select
        state,
        signup_week,
        new_subscriptions,
        sum(new_subscriptions) over (
            partition by state order by signup_week
            rows between unbounded preceding and current row
        ) as cumulative_subscriptions
    from filled
)

select
    -- Surrogate key. The grain is (state, week), so neither column alone is
    -- unique; declaring `state` as the semantic model's primary entity would be
    -- a false uniqueness claim and can fan out joins.
    c.state || '_' || cast(c.signup_week as varchar) as weekly_attach_key,
    c.state,
    c.signup_week,
    c.new_subscriptions,
    c.cumulative_subscriptions,
    p.eligible_premium_accounts,
    c.cumulative_subscriptions * 1.0 / nullif(p.eligible_premium_accounts, 0) as attach_rate
from cumulative c
left join premium_base p on c.state = p.state
