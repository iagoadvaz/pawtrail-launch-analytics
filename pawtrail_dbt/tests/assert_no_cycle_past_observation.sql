-- Fails (returns rows) if any cycle has a due date later than the observation
-- date. The model exists to measure EXPOSURE to renewal: a cycle that has not
-- come due yet is not exposure, it is the future. If this assertion breaks, the
-- spine filter is gone and every exposure metric starts counting renewals
-- nobody has faced.
select account_id, cycle_index, renewal_due_date, observation_date
from {{ ref('int_billing_cycles') }}
where renewal_due_date > observation_date
