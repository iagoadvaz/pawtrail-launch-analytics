-- Fails if the movement bridge does not close: starting MRR + new + expansion -
-- contraction - churned must equal ending MRR exactly.
--
-- This is the model's only real guard. A decomposition that does not reconcile
-- produces an NRR that looks plausible and is wrong, and no schema test would
-- catch it.
--
-- There is no reactivation term because the bridge is built on subscription
-- VALUE, not on cash billed. A skip does not reduce the value of a live
-- subscription, so there is nothing for a return-from-skip to add back. On a
-- cash-billed bridge the term is mandatory and this test fails by -$2,629.07 at
-- cycle 2 without it; on a value bridge a non-zero reactivation would mean a
-- cancelled account had come back, which cancellation being absorbing makes
-- impossible.
select
    cycle_index,
    starting_mrr_usd,
    new_mrr_usd,
    expansion_mrr_usd,
    contraction_mrr_usd,
    churned_mrr_usd,
    ending_mrr_usd
from {{ ref('fct_mrr_movement') }}
where abs(
    (starting_mrr_usd + new_mrr_usd + expansion_mrr_usd
     - contraction_mrr_usd - churned_mrr_usd)
    - ending_mrr_usd
) > 0.01
