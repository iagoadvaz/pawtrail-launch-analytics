-- Fails (returns rows) if any at-risk account falls outside the three damage
-- classes, or if any healthy account receives a damage class.
--
-- An exhaustiveness guard: a CASE with a misplaced ELSE produces a silently
-- empty class, and the prioritised queue starts omitting accounts without
-- anything failing.
select account_id, is_at_risk, damage_class
from {{ ref('fct_at_risk_accounts') }}
where (is_at_risk and damage_class not in ('system_inflicted', 'self_selected', 'ambiguous'))
   or (not is_at_risk and damage_class <> 'healthy')
