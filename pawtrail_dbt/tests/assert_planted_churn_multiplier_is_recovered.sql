-- Fails if the pipeline does NOT recover, within a loose band, the relationship
-- between non-activation and churn that the generator plants.
--
-- READ CAREFULLY: this test does not exist to "discover" that non-activation
-- causes churn -- that relationship was planted on purpose and is documented in
-- generate_subscription_lifecycle.py. It exists to verify that the models, joins
-- and aggregations between the generator and the metric preserve the
-- relationship. If the multiplier arrives distorted, some join is dropping or
-- duplicating rows -- exactly the kind of error that produces a green build and
-- wrong numbers.
--
-- No narrative text may present this result as a finding.
with by_activation as (
    select
        f.combined_activated_30d,
        count(*) as accounts,
        sum(case when l.ever_churned then 1 else 0 end) as churned
    from {{ ref('int_activation_funnel') }} f
    join (
        select account_id, max(case when churned_this_cycle then 1 else 0 end) = 1
            as ever_churned
        from {{ ref('fct_subscription_lifecycle') }}
        group by 1
    ) l on f.account_id = l.account_id
    where f.is_mature_30d
    group by 1
),

rates as (
    select
        max(case when combined_activated_30d then churned * 1.0 / nullif(accounts, 0) end)
            as rate_activated,
        max(case when not combined_activated_30d then churned * 1.0 / nullif(accounts, 0) end)
            as rate_not_activated
    from by_activation
)

select
    rate_activated,
    rate_not_activated,
    rate_not_activated / nullif(rate_activated, 0) as observed_multiplier
from rates
-- A deliberately loose band. The planted multiplier acts on the per-cycle
-- hazard, while what is observed here is "canceled at any point" -- the two
-- quantities are related but not equal, and compounding across 2 to 4 cycles
-- compresses the ratio. A tight band would fail on legitimate re-seeds.
where rate_activated is null
   or rate_not_activated is null
   or rate_not_activated <= rate_activated
   or rate_not_activated / nullif(rate_activated, 0)
        > {{ var('planted_non_activated_churn_multiplier') }} * 1.6
