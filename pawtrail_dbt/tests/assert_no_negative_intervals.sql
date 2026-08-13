-- Spec §8 requires that no time interval in the marts is negative. Every
-- duration below feeds either a time-to-milestone metric or a maturity flag, so
-- a negative value would not surface as an error — it would quietly drag an
-- average down or mark an account mature before its window had opened.
-- Nulls are legitimate (never logged in, kit never arrived) and are not failures.
select 'fct_activation_events' as model, account_id, 'days_to_first_login' as col
from {{ ref('fct_activation_events') }} where days_to_first_login < 0
union all
select 'fct_activation_events', account_id, 'days_to_kit_delivery'
from {{ ref('fct_activation_events') }} where days_to_kit_delivery < 0
union all
select 'fct_activation_events', account_id, 'days_observed'
from {{ ref('fct_activation_events') }} where days_observed < 0
union all
select 'fct_kit_deliveries', account_id, 'delivery_duration_days'
from {{ ref('fct_kit_deliveries') }} where delivery_duration_days < 0
union all
select 'fct_kit_deliveries', account_id, 'days_late'
from {{ ref('fct_kit_deliveries') }} where days_late < 0
union all
select 'fct_subscriptions', account_id, 'conversion_lag_days'
from {{ ref('fct_subscriptions') }} where conversion_lag_days < 0
