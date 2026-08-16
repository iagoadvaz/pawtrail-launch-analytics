-- Fails if any damage class is empty.
--
-- The whole deliverable is a queue an operator can triage into "remediate" and
-- "do not remediate". A classification with an empty class is a two-bucket list
-- wearing a three-bucket name, and every other test in this task passes on it:
-- accepted_values passes on a missing value, and the falsification test below
-- evaluates over an empty set and passes vacuously.
--
-- This is the one test in Task 10 that can fail on correct code with wrong
-- data, which is exactly why it is here.
select damage_class, count(*) as n
from (
    select unnest(['system_inflicted', 'self_selected', 'ambiguous']) as damage_class
) expected
left join {{ ref('fct_at_risk_accounts') }} actual using (damage_class)
group by 1
having count(actual.account_id) = 0
