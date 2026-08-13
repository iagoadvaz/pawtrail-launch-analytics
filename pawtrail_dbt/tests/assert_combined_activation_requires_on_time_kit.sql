-- Fails (returns rows) if an account counts as combined-activated while its kit
-- missed the SLA. This is the guard on spec §6's North Star definition: an
-- earlier draft tested "kit delivered within 30 days" instead of "kit delivered
-- on time", which let a region with a severe delivery problem still register as
-- fully activated because almost every kit arrives inside 30 days.
select account_id
from {{ ref('int_activation_funnel') }}
where (combined_activated_30d or combined_activated_14d or combined_activated_7d)
  and not kit_activated_sla
