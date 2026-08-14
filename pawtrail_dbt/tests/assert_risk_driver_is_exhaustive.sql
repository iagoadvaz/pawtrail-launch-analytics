-- Fails (returns rows) if an account's risk_driver is outside the known set, or
-- disagrees with the flags it is supposed to summarise. The driver column is
-- what makes the queue actionable — an account routed to the wrong team is
-- worse than one that was never flagged — so checking only that the value is a
-- member of the enum is not enough. Reordering the CASE arms in
-- fct_at_risk_accounts so the digital leg is tested before the dual-failure arm
-- would relabel every both_legs_failed account as digital_failure and send it
-- to onboarding instead of logistics, and a membership-only test would pass.
--
-- The expectation below is written with explicit AND/NOT conditions rather than
-- as an ordered fall-through, so it cannot inherit the same ordering bug it
-- exists to catch: each arm is true for exactly one combination of flags.
with expected as (
    select
        account_id,
        risk_driver,
        case
            when no_digital_access_14d and kit_failed_sla
                then 'both_legs_failed'
            when kit_failed_sla and not no_digital_access_14d
                then 'physical_failure'
            when no_digital_access_14d and not kit_failed_sla
                then 'digital_failure'
            when no_tasks_completed
                 and not no_digital_access_14d and not kit_failed_sla
                then 'onboarding_gap'
            else 'healthy'
        end as expected_driver,
        is_at_risk,
        (no_digital_access_14d or kit_failed_sla or no_tasks_completed)
            as expected_at_risk
    from {{ ref('fct_at_risk_accounts') }}
)

select account_id, risk_driver, expected_driver
from expected
where risk_driver not in (
        'healthy', 'digital_failure', 'physical_failure',
        'both_legs_failed', 'onboarding_gap'
      )
   or risk_driver is distinct from expected_driver
   -- is_at_risk and the driver are derived from one set of flags; if they can
   -- disagree, the queue size and the queue's routing came from different data.
   or is_at_risk is distinct from expected_at_risk
   or (is_at_risk and risk_driver = 'healthy')
   or (not is_at_risk and risk_driver <> 'healthy')
