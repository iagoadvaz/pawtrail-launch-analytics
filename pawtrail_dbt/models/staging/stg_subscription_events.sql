select
    account_id,
    cast(event_seq as integer) as event_seq,
    event_type,
    cast(event_date as date) as event_date,
    cast(cycle_index as integer) as cycle_index,
    nullif(reason_code, '') as reason_code,
    nullif(new_pet_tier, '') as new_pet_tier
from {{ ref('raw_subscription_events') }}
