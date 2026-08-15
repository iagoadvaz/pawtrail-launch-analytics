-- Fails (returns rows) if on-time, late and lost do not partition the mature
-- kit cohort exactly once each.
--
-- kits_on_time, kits_late and kits_lost are three independently written
-- expressions over the same population, and kit_late_rate divides one of them
-- by kits_shipped, which counts the whole of it. Nothing else in the project
-- checks that they add up: a kit could fall into two buckets (inflating the
-- late rate) or into none (deflating it) and every measure would still return a
-- plausible number.
--
-- This guards the definition of lateness in particular. It is stated as "the
-- SLA window closed and no kit arrived on time" rather than as "days_late is
-- not null", so that it stops depending on a delivery date that may postdate
-- the observation cutoff -- see assert_days_late_never_reads_a_future_delivery.
-- A future edit that reverted it to the delivery-derived form would have to
-- keep the partition intact to get past this test.
with outcomes as (
    select
        account_id,
        case when kit_activated_sla then 1 else 0 end as on_time,
        case when kit_late_sla then 1 else 0 end as late,
        case when kit_lost then 1 else 0 end as lost
    from {{ ref('fct_kit_deliveries') }}
    where is_mature_sla
)

select account_id, on_time, late, lost
from outcomes
where on_time + late + lost <> 1
