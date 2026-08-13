select
    account_id,
    cast(first_login_date as date) as first_login_date,
    cast(care_tasks_completed_first_cycle as integer) as care_tasks_completed_first_cycle
from {{ ref('raw_digital_engagement') }}
