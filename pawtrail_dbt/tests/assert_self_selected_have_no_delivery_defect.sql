-- Fails (returns rows) if any account classified as self-selected has a delivery
-- defect.
--
-- This is the assertion that keeps the classification from being useless. All
-- the value of separating healthy pruning from operational damage rests on
-- 'self_selected' genuinely meaning "the account did not want this", not "the
-- account did not want this AND the kit was also lost". Without this test, the
-- classification may simply be re-encoding the same self-selection it claims to
-- separate.
select account_id, damage_class, kit_failed_sla
from {{ ref('fct_at_risk_accounts') }}
where damage_class = 'self_selected'
  and kit_failed_sla
