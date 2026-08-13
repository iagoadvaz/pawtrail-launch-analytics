select
    cast(week_start_date as date) as week_start_date,
    channel,
    cast(spend_usd as double) as spend_usd
from {{ ref('raw_marketing_spend') }}
