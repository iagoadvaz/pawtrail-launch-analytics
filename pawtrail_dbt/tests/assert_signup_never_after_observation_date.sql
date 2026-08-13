-- Fails (returns rows) if an account signed up after the analysis cutoff, which
-- would make days_observed negative and every maturity flag meaningless.
select account_id, pawtrail_signup_date, observation_date
from {{ ref('int_activation_funnel') }}
where pawtrail_signup_date > observation_date
   or days_observed < 0
