select
    pet_tier,
    cast(monthly_price_usd as double) as monthly_price_usd,
    cast(kit_cogs_usd as double) as kit_cogs_usd,
    cast(shipping_cost_usd as double) as shipping_cost_usd
from {{ ref('raw_pricing') }}
