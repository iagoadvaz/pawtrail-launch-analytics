-- Fails (returns rows) if an account carries a risk flag but lands in the
-- 'healthy' bucket, or is tagged with a driver outside the known set. The
-- driver column is what makes the queue actionable — an account routed to the
-- wrong team is worse than one that was never flagged.
select account_id, risk_driver
from {{ ref('fct_at_risk_accounts') }}
where risk_driver not in (
        'healthy', 'digital_failure', 'physical_failure',
        'both_legs_failed', 'onboarding_gap'
      )
   or (risk_driver = 'healthy'
       and (no_digital_access_14d or kit_failed_sla or no_tasks_completed))
