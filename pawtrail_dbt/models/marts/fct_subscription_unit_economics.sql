-- Per-account unit economics, correcting the single-shipment assumption.
--
-- WHY THIS MODEL EXISTS: fct_weekly_channel_economics computes
-- contribution_margin_per_subscription ONCE, as though the kit shipped a single
-- time. PawTrail is a physical-box subscription: COGS and shipping are incurred
-- EVERY cycle. The two readings are different and both legitimate -- the old one
-- is first-cycle margin, this one is steady state -- which is why the names are
-- deliberately distinct and neither should be renamed to resemble the other.
--
-- AND WHAT IT DELIVERS: breakeven_cycles answers "how many renewals must this
-- account survive to pay for its own acquisition" using ONLY observed facts --
-- zero survival assumptions, zero retention curve. It is the honest substitute
-- for LTV:CAC in this window (spec §5.2).
with accounts as (
    select
        a.account_id,
        a.channel,
        a.pet_tier,
        -- Named `renewals_faced`, NOT `observable_cycles`. The billing spine is
        -- 0-based: cycle_index 0 IS the initial purchase, so cycles_elapsed
        -- counts RENEWALS faced, while breakeven_cycles counts CHARGES needed.
        -- Comparing the two directly is an off-by-one that reports every
        -- account at cycles_elapsed = 0 as "not broken even" even when a single
        -- charge already covered its CAC. The vaguer name is what made that bug
        -- invisible, so the name carries the distinction.
        a.cycles_elapsed as renewals_faced,
        date_trunc('week', s.pawtrail_signup_date) as signup_week
    from {{ ref('dim_accounts') }} a
    join {{ ref('fct_subscriptions') }} s on a.account_id = s.account_id
),

pricing as (
    select
        pet_tier,
        monthly_price_usd,
        kit_cogs_usd + shipping_cost_usd as recurring_cost_per_cycle,
        monthly_price_usd - kit_cogs_usd - shipping_cost_usd as contribution_margin_per_cycle
    from {{ ref('dim_pricing') }}
),

-- The CAC of the week and channel the account was acquired in. This is the
-- finest allocation the existing data supports: spend is generated per week x
-- channel, so there is no way to attribute it to an individual account more
-- precisely.
channel_cac as (
    select channel, signup_week, cac
    from {{ ref('fct_weekly_channel_economics') }}
),

joined as (
    select
        a.account_id,
        a.channel,
        a.pet_tier,
        a.signup_week,
        a.renewals_faced,
        p.monthly_price_usd,
        p.recurring_cost_per_cycle,
        p.contribution_margin_per_cycle,
        c.cac as allocated_cac_usd
    from accounts a
    join pricing p on a.pet_tier = p.pet_tier
    left join channel_cac c
        on a.channel = c.channel
       and a.signup_week = c.signup_week
),

-- Breakeven is referenced three times in the final select, so it is computed
-- once here: a select alias cannot be reused inside the same select. Same
-- pattern as the `joined` CTE in fct_weekly_channel_economics.
derived as (
    select
        *,
        -- NULL, not zero and not infinity, when the per-cycle margin is <= 0: an
        -- account that never pays back does not have "0 cycles to breakeven", it
        -- has no breakeven. Zero would read as "already paid back".
        case
            when contribution_margin_per_cycle > 0
            then cast(ceil(allocated_cac_usd / contribution_margin_per_cycle) as integer)
        end as breakeven_cycles
    from joined
)

select
    account_id,
    channel,
    pet_tier,
    signup_week,
    monthly_price_usd,
    recurring_cost_per_cycle,
    contribution_margin_per_cycle,
    allocated_cac_usd,
    renewals_faced,
    -- Charges collected so far = renewals faced + the initial purchase.
    renewals_faced + 1 as cycles_billed,
    breakeven_cycles,
    -- The total cost of recovering the account: acquisition plus all the COGS
    -- and shipping that will be spent up to the break-even point. It is the
    -- first time this project states a complete cost to serve.
    allocated_cac_usd + breakeven_cycles * recurring_cost_per_cycle
        as total_cost_to_recover_usd,
    -- Turns right-censoring into a COLUMN rather than a prose caveat. An account
    -- that signed up in week 17 cannot have completed 3 cycles inside a 120-day
    -- window; without this column, a per-channel breakeven average silently
    -- mixes proven with unproven accounts.
    breakeven_cycles <= renewals_faced + 1 as breakeven_within_window
from derived
