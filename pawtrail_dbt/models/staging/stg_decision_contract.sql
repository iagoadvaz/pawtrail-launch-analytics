select
    metric_name,
    cast(threshold_value as double) as threshold_value,
    threshold_direction,
    action,
    owner,
    decision_question
from {{ ref('raw_decision_contract') }}
