-- Fails (returns rows) if the spend fct_weekly_channel_economics reports for a
-- (channel, week) differs from the spend fct_marketing_spend recorded for it.
--
-- The mart is built by joining spend onto the weeks that produced signups, so a
-- week with spend but no signups has no row to join onto and its spend leaves
-- the warehouse entirely -- silently, because every column that survives is
-- still internally consistent. The `cac not_null` test cannot see it either: it
-- only guards the opposite direction, a signup week whose spend failed to join.
-- A launch's last spend week is exactly the case that goes missing, since spend
-- is booked for a week that has not converted yet.
--
-- Every dollar in fct_marketing_spend must therefore appear exactly once here.
-- The three arms below are the three ways that can break: the mart dropped a
-- spend week, the mart reports spend the source does not have, or the two
-- disagree on the amount (a fanned-out join double-counts; a partial one
-- undercounts).
with source_spend as (
    select
        channel,
        date_trunc('week', week_start_date) as signup_week,
        sum(spend_usd) as source_spend_usd
    from {{ ref('fct_marketing_spend') }}
    group by 1, 2
),

reported_spend as (
    select
        channel,
        signup_week,
        sum(spend_usd) as mart_spend_usd
    from {{ ref('fct_weekly_channel_economics') }}
    group by 1, 2
)

select
    coalesce(s.channel, r.channel) as channel,
    coalesce(s.signup_week, r.signup_week) as signup_week,
    s.source_spend_usd,
    r.mart_spend_usd
from source_spend s
full outer join reported_spend r
    on s.channel = r.channel
   and s.signup_week = r.signup_week
-- A week the mart never carried. This is the arm that catches the dropped
-- final spend week.
where r.channel is null
   -- A week the mart carries with a spend figure the source cannot account for.
   -- A mart row with no source row is legitimate only while its spend stays
   -- null; a number there would be invented.
   or (s.channel is null and r.mart_spend_usd is not null)
   -- Both sides present and disagreeing. The tolerance is half a cent: these
   -- are doubles summed in a different order on each side, so exact equality
   -- would fail on floating-point noise rather than on a real leak.
   or abs(s.source_spend_usd - r.mart_spend_usd) > 0.005
