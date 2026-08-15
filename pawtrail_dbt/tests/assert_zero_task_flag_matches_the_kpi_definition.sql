-- Fails (returns rows) if the CS queue and the zero_task_accounts KPI disagree
-- about which accounts completed no first-cycle tasks.
--
-- They are one concept with two consumers: fct_at_risk_accounts routes on it,
-- the semantic layer publishes it. While the queue judged the flag at 14 days
-- and the KPI at 30, the two answered different questions under one name --
-- 467 accounts against 430 -- and both windows are independently tunable in
-- dbt_project.yml, so nothing would have caught them drifting further apart.
--
-- 30 days is the correct window for both: care_tasks_completed_first_cycle
-- counts tasks over the *first cycle*, so an account 14 days old still has half
-- its cycle left to complete one. Judging it at day 14 books an unfinished
-- cycle as a failed one, which is the same right-censoring error the activation
-- rates exist to avoid.
--
-- The comparison is written against int_activation_funnel rather than against
-- the measure's own SQL so that the two expressions stay independently authored:
-- a test that re-derived the flag from fct_at_risk_accounts would compare the
-- queue against itself and pass no matter which window either side used.
with kpi_population as (
    select
        account_id,
        (coalesce(care_tasks_completed_first_cycle, 0) = 0 and is_mature_30d)
            as kpi_zero_tasks
    from {{ ref('int_activation_funnel') }}
)

select
    q.account_id,
    q.days_observed,
    q.no_tasks_completed as queue_flag,
    k.kpi_zero_tasks as kpi_flag
from {{ ref('fct_at_risk_accounts') }} q
join kpi_population k on q.account_id = k.account_id
where q.no_tasks_completed is distinct from k.kpi_zero_tasks
