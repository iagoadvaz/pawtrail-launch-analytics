select
    account_id,
    pawtrail_signup_date,
    date_trunc('week', pawtrail_signup_date) as signup_week,
    -- Conversion lag (spec §6): days between becoming Premium and attaching
    -- PawTrail. That is exactly what premium_tenure_days measures, since tenure
    -- is recorded as of the attach date. It is carried here rather than measured
    -- off dim_accounts because a MetricFlow measure needs an aggregation time
    -- dimension, and this model is the one with signup_date.
    premium_tenure_days as conversion_lag_days
from {{ ref('stg_subscriptions') }}
