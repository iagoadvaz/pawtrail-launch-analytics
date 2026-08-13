-- Fails (returns rows) if attach_rate is ever negative or exceeds 100% —
-- either would indicate a broken join or a premium-base assumption that's
-- too small relative to the generated subscription volume.
select state, signup_week, attach_rate
from {{ ref('fct_weekly_attach') }}
where attach_rate < 0 or attach_rate > 1
