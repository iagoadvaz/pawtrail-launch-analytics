-- Fails (returns rows) if any account is flagged digitally activated
-- without an actual first_login_date — a business-rule consistency check
-- that generic schema tests can't express.
select account_id
from {{ ref('int_activation_funnel') }}
where digital_activated_7d = true
  and first_login_date is null
