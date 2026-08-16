-- Fails if 'system_inflicted' accounts skew short-tenure by more than 10
-- percentage points against the at-risk base.
--
-- Without this, the classification could be re-encoding the same self-selection
-- it claims to separate: if the accounts we call "damaged by the company" are
-- simply the newest accounts, the split carries no information.
--
-- Expect this to PASS with a wide margin on the current generator: mean tenure
-- is ~661 days in every class against a base median of 660. That null result is
-- itself the finding -- tenure does not discriminate in this dataset -- and it
-- belongs in METRICS.md rather than being silently discarded.
with base as (
    select
        avg(case when premium_tenure_days <= {{ var('self_selected_tenure_days') }}
            then 1.0 else 0.0 end) as base_short_share
    from {{ ref('fct_at_risk_accounts') }}
    where is_at_risk
),
system_inflicted as (
    select
        avg(case when premium_tenure_days <= {{ var('self_selected_tenure_days') }}
            then 1.0 else 0.0 end) as class_short_share
    from {{ ref('fct_at_risk_accounts') }}
    where damage_class = 'system_inflicted'
)
select b.base_short_share, s.class_short_share
from base b cross join system_inflicted s
where s.class_short_share - b.base_short_share > 0.10
