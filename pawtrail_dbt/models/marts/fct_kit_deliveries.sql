select
    k.account_id,
    a.state,
    f.pawtrail_signup_date,
    k.kit_delivered_date,
    k.kit_lost,
    k.delivery_duration_days,
    -- Days past the SLA, null for on-time and lost kits. Averaging this gives
    -- "how late are the late ones", which is the operationally useful read; a
    -- version that coalesced on-time kits to 0 would instead report a diluted
    -- fleet-wide average that moves with volume rather than with lateness.
    f.days_late,
    f.kit_activated_sla,
    -- The SLA window closed with no on-time kit. Carried alongside days_late
    -- rather than derived from it: days_late is null while a late kit is still
    -- in transit, so a count built on it would undercount lateness at exactly
    -- the observation boundary.
    f.kit_late_sla,
    -- Carried so the on-time rate can exclude accounts whose SLA window has not
    -- closed yet, matching the cohort treatment of the activation rates.
    f.is_mature_sla
from {{ ref('stg_kit_deliveries') }} k
left join {{ ref('dim_accounts') }} a on k.account_id = a.account_id
left join {{ ref('int_activation_funnel') }} f on k.account_id = f.account_id
