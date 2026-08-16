-- Fails (returns rows) if any metric declared in the semantic layer has no
-- threshold, action and owner in the decision contract.
--
-- This mechanises global acceptance criterion 6.4 of the spec. Without it,
-- "every metric has a row in the contract" is a good intention that dissolves
-- on the first new metric. The practical effect: adding a metric without
-- deciding what to do when it moves now breaks the build.
--
-- Proxy metrics auto-registered by `create_metric: true` are excluded: they
-- exist so that ratio metrics resolve in MetricFlow, not to be read by a human,
-- and demanding a contract from them would be bureaucracy with no decision
-- behind it.
select p.metric_name
from {{ ref('raw_published_metrics') }} p
left join {{ ref('stg_decision_contract') }} c on p.metric_name = c.metric_name
where c.metric_name is null
