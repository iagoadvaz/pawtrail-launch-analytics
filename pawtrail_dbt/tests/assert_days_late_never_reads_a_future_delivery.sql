-- Fails (returns rows) if days_late was computed from a delivery that had not
-- happened yet as of the observation date.
--
-- int_activation_funnel declares observation_date as the analysis cutoff -- "in
-- a scheduled pipeline this would be current_date" -- and every maturity flag is
-- measured against it. The generator applies no such cutoff to the events
-- themselves, so kit_delivered_date runs past it for some accounts. A days_late
-- computed from one of those dates is a magnitude nobody could know yet, and it
-- flows straight into avg_days_late, which reports "when a kit is late, how
-- late" over delays that have not been observed.
--
-- The sibling of assert_signup_never_after_observation_date, which enforces the
-- same cutoff in the other direction. Lateness itself is knowable without the
-- delivery date -- once the SLA window has closed and no kit has arrived, the
-- kit is late -- which is what kit_late_sla is for; this test constrains only
-- the *duration*, the part that genuinely requires the delivery to have landed.
select
    account_id,
    pawtrail_signup_date,
    observation_date,
    kit_delivered_date,
    days_late
from {{ ref('int_activation_funnel') }}
where days_late is not null
  and kit_delivered_date > observation_date
