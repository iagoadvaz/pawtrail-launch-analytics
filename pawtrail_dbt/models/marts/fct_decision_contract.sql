-- The decision contract crossed with each metric's current value.
--
-- 33 correct metrics with no declared consequence are indistinguishable from a
-- data dictionary. Without a threshold there is no falsifiability: the project
-- can never be shown to be right or wrong about anything. This model is where
-- each number earns its "so what".
with contract as (
    select * from {{ ref('stg_decision_contract') }}
),

values_ as (
    select
        metric_name,
        -- Which segment produced the value. A categorical threshold is written
        -- to catch the worst state or channel, so the board has to name it: a
        -- row reading "kit_lost_rate 0.072, triggered, audit the carrier" is
        -- an instruction nobody can act on until it says OH.
        nullif(segment, '') as segment,
        -- Empty becomes null, not zero: a semi-additive metric that cannot be
        -- queried without a group-by does not have a value of "zero", it has no
        -- value at this grain. Zero would trip every `below` threshold by
        -- mistake.
        -- cast to varchar FIRST. Once the export is fixed and the column holds
        -- real numbers, dbt-duckdb infers it as DOUBLE, and nullif against a
        -- DOUBLE raises "Could not convert string '' to DOUBLE". The model only
        -- appears to work while the export is broken and the column is VARCHAR.
        try_cast(nullif(cast(current_value as varchar), '') as double)
            as current_value
    from {{ ref('raw_metric_values') }}
)

select
    c.metric_name,
    c.decision_question,
    c.threshold_value,
    c.threshold_direction,
    v.current_value,
    v.segment,
    c.action,
    c.owner,
    case
        when v.current_value is null then 'no_data'
        when c.threshold_direction = 'below' and v.current_value < c.threshold_value
            then 'triggered'
        when c.threshold_direction = 'above' and v.current_value > c.threshold_value
            then 'triggered'
        -- `at_or_above` exists because breakeven_cycles is ceil()'d and therefore
        -- an integer. `avg_breakeven_cycles > 2.0` is false for sales_assisted,
        -- which lands on exactly 2.0 -- so a strict comparison gives the flagship
        -- LTV:CAC substitute an alarm that cannot fire on its own expected value.
        when c.threshold_direction = 'at_or_above' and v.current_value >= c.threshold_value
            then 'triggered'
        else 'ok'
    end as status
from contract c
left join values_ v on c.metric_name = v.metric_name
