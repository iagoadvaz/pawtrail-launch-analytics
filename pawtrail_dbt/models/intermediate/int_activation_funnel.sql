with subscriptions as (
    select * from {{ ref('stg_subscriptions') }}
),

kit_deliveries as (
    select * from {{ ref('stg_kit_deliveries') }}
),

digital_engagement as (
    select * from {{ ref('stg_digital_engagement') }}
),

-- The analysis cutoff. In a scheduled pipeline this would be current_date; here
-- the dataset is a fixed simulated window, so the latest signup stands in for
-- "as of today". Every maturity flag below is measured against it.
observation as (
    select max(pawtrail_signup_date) as observation_date
    from {{ ref('stg_subscriptions') }}
),

joined as (
    select
        s.account_id,
        s.state,
        s.pet_tier,
        s.channel,
        s.premium_tenure_days,
        s.pawtrail_signup_date,
        o.observation_date,
        d.first_login_date,
        d.care_tasks_completed_first_cycle,
        k.kit_delivered_date,
        k.kit_lost,
        date_diff('day', s.pawtrail_signup_date, d.first_login_date) as days_to_first_login,
        date_diff('day', s.pawtrail_signup_date, k.kit_delivered_date) as days_to_kit_delivery,
        date_diff('day', s.pawtrail_signup_date, o.observation_date) as days_observed
    from subscriptions s
    cross join observation o
    left join digital_engagement d on s.account_id = d.account_id
    left join kit_deliveries k on s.account_id = k.account_id
),

flagged as (
    select
        *,
        (first_login_date is not null
            and days_to_first_login <= {{ var('digital_activation_window_days') }}
        ) as digital_activated_7d,
        (kit_delivered_date is not null
            and not kit_lost
            and days_to_kit_delivery <= {{ var('kit_sla_days') }}
        ) as kit_activated_sla,
        (first_login_date is null
            or days_to_first_login > {{ var('at_risk_no_login_days') }}
        ) as no_digital_access_14d,
        -- Cohort maturity. An account that signed up four days before the
        -- observation date has not yet had 30 days to activate, so counting it
        -- as a failure would understate activation in exactly the most recent
        -- weeks — the ones a launch dashboard leans on hardest. These flags let
        -- the metric layer restrict each rate to accounts that have actually had
        -- the full window.
        (days_observed >= {{ var('digital_activation_window_days') }}) as is_mature_7d,
        (days_observed >= {{ var('kit_sla_days') }}) as is_mature_sla,
        (days_observed >= {{ var('combined_activation_window_days') }}) as is_mature_30d,
        -- A *combined* rate needs both legs to have had their chance, so its
        -- maturity is the later of the digital window and the kit SLA, not the
        -- digital window alone. At the 7-day point the SLA (10 days) is the
        -- binding constraint: an account 8 days old could still receive an
        -- on-time kit, so judging it at day 7 would book a pending kit as a
        -- failure. This is why is_mature_combined_7d is not is_mature_7d.
        -- The 30-day flag needs no such treatment because 30 already exceeds
        -- every window.
        (days_observed >= greatest(
            {{ var('digital_activation_window_days') }}, {{ var('kit_sla_days') }}
        )) as is_mature_combined_7d,
        (days_observed >= greatest(
            {{ var('combined_activation_mid_window_days') }}, {{ var('kit_sla_days') }}
        )) as is_mature_combined_14d,
        -- Days past the SLA, null when the kit arrived on time or never came.
        -- Feeds the delay-distribution metric (spec §6, kit operations).
        case
            when kit_delivered_date is not null
                 and not kit_lost
                 and days_to_kit_delivery > {{ var('kit_sla_days') }}
            then days_to_kit_delivery - {{ var('kit_sla_days') }}
        end as days_late
    from joined
)

select
    *,
    -- The launch North Star, per spec §6: confirmed digital usage AND an
    -- ON-TIME first kit, inside 30 days. Reusing kit_activated_sla rather than
    -- re-testing "delivered within 30 days" matters — nearly every kit arrives
    -- inside 30 days, so the looser rule would let a region with a severe
    -- delivery problem still score as fully activated.
    (
        first_login_date is not null
        and days_to_first_login <= {{ var('combined_activation_window_days') }}
        and kit_activated_sla
    ) as combined_activated_30d,
    -- The 7- and 14-day readings of the same definition. Only the digital leg's
    -- window shortens; the physical leg stays "hit the SLA" at every horizon,
    -- because the spec's on-time constraint is a property of the delivery
    -- promise, not of the reporting window.
    (
        first_login_date is not null
        and days_to_first_login <= {{ var('digital_activation_window_days') }}
        and kit_activated_sla
    ) as combined_activated_7d,
    (
        first_login_date is not null
        and days_to_first_login <= {{ var('combined_activation_mid_window_days') }}
        and kit_activated_sla
    ) as combined_activated_14d
from flagged
