-- Fails (returns rows) if any kit was recorded as delivered before the
-- account even signed up — a data-quality guard on the generated dates.
select
    k.account_id
from {{ ref('fct_kit_deliveries') }} k
left join {{ ref('fct_subscriptions') }} s on k.account_id = s.account_id
where k.kit_delivered_date is not null
  and k.kit_delivered_date < s.pawtrail_signup_date
