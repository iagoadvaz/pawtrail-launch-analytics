-- Fails (returns rows) if the total cost to recover does not exceed bare CAC on
-- an account whose per-cycle margin is positive.
--
-- This is the structural guard on the model's central claim: loading in
-- recurring COGS and shipping MUST raise the cost of recovery above naked CAC.
-- If it does not, the join against dim_pricing or fct_weekly_channel_economics
-- dropped rows and returned null -- the "green build, wrong numbers" failure
-- mode dbt joins produce silently.
select
    account_id,
    allocated_cac_usd,
    total_cost_to_recover_usd,
    contribution_margin_per_cycle
from {{ ref('fct_subscription_unit_economics') }}
where contribution_margin_per_cycle > 0
  and (
      total_cost_to_recover_usd is null
      or total_cost_to_recover_usd <= allocated_cac_usd
  )
