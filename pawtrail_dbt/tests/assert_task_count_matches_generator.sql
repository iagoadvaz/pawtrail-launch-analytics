-- Fails (returns rows) if any account completed more first-cycle tasks than
-- var('first_cycle_task_count') allows, which means that var has drifted from
-- FIRST_CYCLE_TASK_COUNT in the generator (Task 4). The var is the denominator
-- of task_completion_rate, so drift would not raise an error anywhere — it
-- would quietly report a completion percentage against the wrong total.
select account_id, care_tasks_completed_first_cycle
from {{ ref('stg_digital_engagement') }}
where care_tasks_completed_first_cycle > {{ var('first_cycle_task_count') }}
