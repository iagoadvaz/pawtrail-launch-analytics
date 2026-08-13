select
    account_id,
    state,
    pet_tier,
    channel,
    cast(premium_tenure_days as integer) as premium_tenure_days,
    cast(pawtrail_signup_date as date) as pawtrail_signup_date
from {{ ref('raw_subscriptions') }}
