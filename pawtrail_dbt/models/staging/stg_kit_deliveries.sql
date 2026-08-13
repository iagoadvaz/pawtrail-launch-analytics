select
    account_id,
    cast(kit_delivered_date as date) as kit_delivered_date,
    cast(kit_lost as boolean) as kit_lost,
    cast(delivery_duration_days as integer) as delivery_duration_days
from {{ ref('raw_kit_deliveries') }}
