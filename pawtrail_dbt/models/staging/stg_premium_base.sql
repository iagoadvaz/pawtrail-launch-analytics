select
    state,
    cast(eligible_premium_accounts as integer) as eligible_premium_accounts
from {{ ref('raw_premium_base') }}
