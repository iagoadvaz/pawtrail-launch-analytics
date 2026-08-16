-- Fails (returns rows) if any account appears more than once in the waste model.
--
-- An account can simultaneously have lost its kit AND failed to activate within
-- 30 days. Counting it twice would inflate total waste and, by extension,
-- effective CAC -- which is precisely the headline this block produces. The
-- model resolves this with an ordered CASE (lost kit wins), and this test is the
-- guard that the ordering stays mutually exclusive.
select account_id, count(*) as rows_found
from {{ ref('fct_fulfillment_waste') }}
group by account_id
having count(*) > 1
