-- How many accounts each rate excludes for immaturity, and what share of the
-- base that is.
--
-- The maturity gating already exists in int_activation_funnel and is CORRECT --
-- the problem is that it is invisible in the output. A 30-day rate computed over
-- the mature slice describes a different population from the subscriber count in
-- the headline, and without these numbers side by side the reader compares
-- incomparable denominators without knowing they are doing it.
--
-- Grain: one row per metric. This is a transparency model, not a fact table --
-- it exists to be published beside the numbers, which is why the metric name is
-- a literal rather than a foreign key.
with funnel as (
    select * from {{ ref('int_activation_funnel') }}
),

total as (
    select count(*) as base_accounts from funnel
),

registered as (
    select 'activation_rate_30d' as metric_name,
           sum(case when is_mature_30d then 1 else 0 end) as denominator_accounts
    from funnel
    union all
    select 'activation_rate_14d',
           sum(case when is_mature_combined_14d then 1 else 0 end)
    from funnel
    union all
    select 'activation_rate_7d',
           sum(case when is_mature_combined_7d then 1 else 0 end)
    from funnel
    union all
    select 'digital_activation_rate_7d',
           sum(case when is_mature_7d then 1 else 0 end)
    from funnel
    union all
    select 'kit_sla_rate',
           sum(case when is_mature_sla then 1 else 0 end)
    from funnel
)

select
    r.metric_name,
    r.denominator_accounts,
    t.base_accounts - r.denominator_accounts as excluded_accounts,
    (t.base_accounts - r.denominator_accounts) * 1.0 / nullif(t.base_accounts, 0)
        as excluded_share
from registered r
cross join total t
