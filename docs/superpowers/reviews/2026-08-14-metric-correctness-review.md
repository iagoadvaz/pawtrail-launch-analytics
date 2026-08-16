# Metric correctness review — implemented metrics and the three phase plans

**Date:** 2026-08-14
**Scope:** every metric the project publishes today, plus every metric the three
Phase plans propose.
**Method:** four independent reviewers with disjoint scopes, each working
read-only. Findings marked CONFIRMED were verified by executing something —
recomputing a metric from the raw seed CSVs, querying the built
`pawtrail.duckdb`, running `dbt parse` against a scratch copy of the project,
reconstructing a plan's generator and running its own tests, or mutation-testing
those tests. Findings marked PLAUSIBLE were reasoned from reading.
**Nothing in the repository or the warehouse was modified.**

**A second validation pass** re-verified the critical findings independently of
the reviewers who raised them — see "Validation pass" at the end. One finding
(F23) was corrected as a result; one (F9) was found to be worse than reported.

| Reviewer | Scope | Findings |
|---|---|---|
| A | The 33 metrics implemented today | 1 critical · 2 high · 3 medium · 2 low |
| B | Phase 1 plan (computable metrics) | 3 critical · 2 high · 7 medium · 7 low |
| C | Phase 2 plan (subscription lifecycle) | 1 critical · 5 high · 5 medium · 3 low |
| D | Spec arithmetic + Phase 3 plan (decision layer) | 4 critical · 6 high · 13 medium · 8 low |

---

## Verdict

**The metric *definitions* are largely sound; the *plumbing around them* is where
the defects are.** Reviewer A recomputed 22 of the 33 live metrics straight from
the raw seeds and matched MetricFlow to full precision. Reviewer B confirmed that
the part of Phase 1 the spec itself flagged as most likely to be broken — the
fulfilment-waste join behind effective CAC — is correct, in both direction and
magnitude. Reviewer D reproduced all 16 cells of the §5.2 LTV:CAC table exactly,
so the spec's most contrarian decision rests on arithmetic that checks out.

Against that, three things are true and need action before any implementation
starts:

1. **One defect is in shipped code and is corrupting published numbers today.**
   `fct_weekly_channel_economics` silently drops 7% of all marketing spend (F1).
2. **Both Phase 1 and Phase 2 would fail at `dbt parse`** — independently, for
   the same reason — and halt partway through (F2, F3). Neither plan is
   executable as written.
3. **The Phase 3 decision layer would render an empty board and one inverted
   headline alarm** (F4, F5, F8, F9).

Counting merges, 68 distinct findings: **9 critical, 14 high, 26 medium, 19 low.**

---

## The five defect classes

Most individual findings are instances of five recurring mistakes. Fixing the
class is cheaper than fixing the instances one at a time.

### 1. Semi-additivity — summing a snapshot across time
The single largest class. A measure captured as a per-week snapshot gets `sum`ed
across 17 weeks, and MetricFlow answers with a plausible-looking number instead
of refusing. **F5, F18, M14, M21, plus C-13 and A6.** The published CSVs mostly
escape it because they are grouped by week; the interactive `mf query` path and
the Phase 3 decision contract do not.

### 2. Denominators that include a population which had no opportunity
A rate whose denominator carries accounts that could not possibly have produced
the numerator event. **F12** (churned accounts left in the churn denominator),
**F15** (maturity gate on the numerator but not the denominator), **F6**
(a 1-based count of charges compared against a 0-based count of renewals). Each
one moves a headline number by 15–30%.

### 3. Tests that cannot fail
Eleven separate assertions across the three plans compare a value against
itself, or evaluate over an empty set, or assert a property the model guarantees
by construction. **F14, F17, M-B6, M-C7, M-C8, F8's fixture.** Two of these were
proven unfailable by mutation testing: Reviewer C injected 20 post-cancellation
charges and the test still returned zero rows; it also replaced a declining churn
hazard with a flat constant and all nine tests still passed. As *regression*
guards these are cheap and legitimate — the problem is that the plans present
them as TDD red-green cycles and as satisfying the spec's falsification
requirements. They do neither.

### 4. Expectations in the plans that are false
Several "Expected:" lines instruct the implementer to look for something the data
does not do — a decreasing distribution that actually peaks in the middle, a
benchmark crossing that is really a censoring artefact, a rebill rate outside its
reachable range. **F22, M-B4, M-C11, L-B1, L-B3.** These are worse than harmless:
each pairs with a "stop and report" or "revise the thresholds" instruction, so a
literal implementer either halts on correct code or tunes the generator to hit a
number that was never derived correctly.

### 5. Appendix A drift
The spec's illustrative magnitudes are mostly close enough to serve their stated
purpose (order-of-magnitude tripwires), but two are structural errors rather than
rounding: **F23** (the waste decomposition double-counts, and an acceptance
criterion instructs the implementer to reproduce the double-count) and **M22**
(the 14-day censoring figure was computed with a 20-day window). See Appendix B
for the full spec-vs-warehouse table.

---

## CRITICAL

### F1 — `fct_weekly_channel_economics` silently drops 7% of all marketing spend
**Reviewer A · CONFIRMED · shipped code, not a plan**
`pawtrail_dbt/models/marts/fct_weekly_channel_economics.sql:90-91`

The mart is driven off `weekly_subs` and left-joins spend onto it, so any
`(channel, week)` that has spend but no signups produces no row and its spend
disappears. The last signup is 2026-05-03, so the final spend week has no
signups at all.

I re-verified this independently of the reviewer:

| | staging | mart | lost |
|---|---|---|---|
| total | $38,876.40 | $36,144.02 | **$2,732.38 (7.0%)** |
| self_serve | $15,003.64 | $13,784.91 | $1,218.73 |
| sales_assisted | $23,872.76 | $22,359.11 | $1,513.65 |

Every spend-derived metric is wrong today:

| metric | published | true |
|---|---|---|
| `channel_spend` | 36,144 | 38,876 |
| `cac_by_channel` self_serve | 6.561 | **7.141** |
| `cac_by_channel` sales_assisted | 24.871 | **26.555** |
| `cac_payback_months` blended | 0.844 | **0.908** |

The existing `cac not_null` test (`_marts__business.yml:89-91`) only guards the
opposite direction — a subs-week with no spend — so this builds green.

**Fix:** drive the join off a full `(channel, week)` spine (full outer join, or a
union of distinct channel-weeks from both sides) and `coalesce` subscription
counts to 0. Add a reconciliation test asserting the mart's `sum(spend_usd)`
equals staging's.

**Consequence worth noting:** this bug makes the *spec* look wrong when it isn't.
Reviewer D flagged Appendix A's nominal CAC as ~10% high against the warehouse.
Once F1 is fixed the true blended CAC is **$12.96**, not $12.05, and the spec's
$13.26 is 2.3% high — well inside "illustrative". Same for the per-channel
figures: spec $7.20/$27.40 vs true $7.14/$26.55.

### F2 — The Phase 1 plan fails `dbt parse` at Task 3 and never reaches Tasks 4–12
**Reviewer B · CONFIRMED (reproduced)**
`plans/2026-08-14-phase-1-computable-metrics.md:376-397` (Task 3 Step 1) and `:1926-1943` (Task 11 Step 5)

Task 3 attaches a `measures:` block to the `accounts` semantic model and Task 11
declares `state_saturation` with measures, but neither semantic model has a time
dimension or a `defaults.agg_time_dimension`, which MetricFlow requires for every
measure. `dim_accounts` has no date column at all, and Task 2 adds only integers
and booleans.

Applying Task 3 Steps 1–2 verbatim to a scratch copy:

```
An error occurred while checking aggregation time dimension for a semantic model -
AssertionError: Aggregation time dimension for measure renewal_exposed_accounts is not set!
Encountered an error: Parsing Error — Semantic Manifest validation failed.
```

Same for `remaining_eligible_accounts`. This is a **parse** error, not a
`validate-configs` warning: it gates `dbt build`, so from the moment
`_semantic_models.yml` is edited every model and every pre-existing test stops
running.

**Fix:** carry `pawtrail_signup_date` into `dim_accounts`, declare it as a
name-qualified time dimension (`accounts_signup_date` — `subscriptions` owns the
bare `signup_date`), and set `defaults: {agg_time_dimension: accounts_signup_date}`.
For `fct_state_saturation` add a `snapshot_date` and the same pair. The reviewer
verified state-saturation parses cleanly once a time dimension is present, and
that a `saturation_state` entity coexisting with a `state` dimension is *not* a
problem.

### F3 — The Phase 2 plan fails `dbt parse` at Task 5, for the same reason
**Reviewer C · CONFIRMED (ran `dbt parse`)**
`plans/2026-08-14-phase-2-subscription-lifecycle.md:1283-1314` (Task 5 Step 4)

`fct_mrr_movement` is at grain `cycle_index` with no date column, so its semantic
model declares five measures and no `agg_time_dimension`:

```
AssertionError: Aggregation time dimension for measure starting_mrr_usd is not set!
```

Task 5 Step 5 says "Expected: `assert_mrr_movement_reconciles` passes"; nothing
will run at all. Every other semantic model in the project that has measures
declares `defaults: agg_time_dimension` — the new model breaks an established
pattern that F2 breaks independently in the other plan.

**Fix:** regrain the mart to `(cycle_index, cycle_due_week)` and declare that as
the agg time dimension. Keeping the cycle grain and adding a representative
`cycle_period_date` also works, but regraining is better anyway — see F10.

### F4 — The contract export parser reads MetricFlow's footer, so all 34 rows become `no_data`
**Reviewer D · CONFIRMED (executed)**
`plans/2026-08-14-phase-3-decision-layer.md:371`

`value = lines[-1].split(',')[-1]` against `mf query --csv /dev/stdout`, whose
stdout is:

```
['⠋ Initiating query…', '⠙ Initiating query…',
 '✔ Success 🦄 - query completed after 0.06 seconds',
 'attach_rate_vs_target', '0.6990849673202614',
 '🖨 Wrote query output to /dev/stdout']
```

`lines[-1]` is `🖨 Wrote query output to /dev/stdout`. `try_cast` yields NULL, so
**every row of the decision table renders "no data"** and the header's triggered
counter reads 0. Task 4 Step 3's remedy — *"If nothing triggers, the thresholds
are too loose to be useful; revise them"* — then sends the implementer off tuning
thresholds to chase a string-parsing bug.

Secondary: `.split(',')[-1]` takes the last *column*, not the metric column, so
the moment anyone adds a second metric or a `--group-by` it silently returns the
wrong column.

**Fix:** write to a real temp file, parse with `csv.DictReader`, index by metric
name, and assert exactly one row.

### F5 — `attach_rate` / `attach_rate_vs_target` invert the launch verdict
**Reviewers A and D · CONFIRMED (both, independently)**
`_metrics.yml:14`, `:24`, `:8`, `:207`; measures `_semantic_models.yml:276-282`;
contract seed `phase-3:79`

Both sides of the ratio are `agg: sum` over a `(state, week)` snapshot, so any
roll-up spanning more than one week sums 17 weekly snapshots of a base that is
constant.

| query | returns | truth |
|---|---|---|
| `attach_rate` ungrouped | 0.1049 | **0.20** |
| `attach_rate_vs_target` ungrouped | **0.699** | **1.333** |
| `attach_rate` by state, CA | 0.1166 | 0.2256 |
| `eligible_premium_accounts` | 255,000 | 15,000 |

The ungrouped `attach_rate_vs_target` of 0.699 reads as *30% below the launch
target*. The launch actually finished **33% above** it. `METRICS.md:242-248` only
forbids "grouped by region alone"; `METRICS.md:6` explicitly invites bare
`mf query --metrics <name>` for every metric.

Two consequences, from two reviewers:
- **Interactive queries** return the inverted number (Reviewer A).
- **The Phase 3 decision contract** puts `attach_rate_vs_target, 1.0, below` on
  that ungrouped value, so the board's most visible card fires
  *"Review channel mix in the weekly launch review"* on a launch 33% ahead of
  plan (Reviewer D).

The published CSVs are safe — both attach exports are grouped by week.

**Fix:** make the semi-additive side non-additive (`non_additive_dimension` on
`signup_week` with `window_choice: max`), or move the eligible base to a
state-grain semantic model. The contract's values seed must additionally carry a
`group_by` per metric and query at each metric's declared valid grain.

### F6 — `breakeven_within_window` is off by one, understating the flagship metric by 15.7 points
**Reviewer B · CONFIRMED**
`plans/2026-08-14-phase-1-computable-metrics.md:637-641` (Task 4 Step 4)

`breakeven_cycles <= observable_cycles` compares a 1-based count of *charges*
against a 0-based count of *renewals*. `observable_cycles = max(cycle_index)`,
and the plan itself states `cycle_index = 0` is the initial purchase — so an
account at `cycles_elapsed = 0` has been charged once and has collected one cycle
of margin. A self-serve account with `allocated_cac = $7.20` and margin `$14.29`
has `breakeven_cycles = 1` and has already paid back, but `1 <= 0` is false.

| channel | as planned | corrected |
|---|---|---|
| self_serve | 0.887 | 0.929 |
| sales_assisted | **0.633** | **0.790** |

339 accounts sit at `observable_cycles = 0` and are forced to `false` regardless
of CAC. This is `breakeven_cycles`' companion metric — the spec's designated
replacement for LTV:CAC.

**Fix:** rename `observable_cycles` to `renewals_faced` and compare against
`cycles_billed = renewals_faced + 1`. The name is what made the bug invisible, so
fix the name, not just the arithmetic.

### F7 — The `self_selected` damage class is structurally empty: 0 of 944, not 360
**Reviewer B · CONFIRMED**
`plans/2026-08-14-phase-1-computable-metrics.md:1596-1600` (Task 10 Step 3)

`self_selected` requires `premium_tenure_days <= 180`. The entire base has **4**
such accounts (min 56, median 660, max 900 — the generator decays tenure from
~900 to ~420 with 150-day noise clipped to [30, 900]).

| class | plan's output | Appendix A target |
|---|---|---|
| system_inflicted | 448 ($12,455.52) | 448 |
| ambiguous | 496 ($13,925.04) | 136 |
| self_selected | **0** | 360 |

390 of the 496 "ambiguous" accounts are exactly the profile the class was meant
to name. The queue stays an unworkable two-bucket list, which is the
deliverable's entire point. Nothing tests it: `accepted_values` passes on a
missing value, and the falsification test passes vacuously (F17).

The plan anticipates this at `:1673` — *"If `self_selected` comes out empty, stop
and report"* — which means it knowingly ships a rule it cannot show works.

**Fix:** define short tenure relative to the observed distribution
(`var('self_selected_tenure_days')`, calibrated — the 181–365 band holds 136
accounts), put it in `vars:` as the plan's own global constraint requires, and
add a non-degeneracy test.

### F8 — Band 2's one real number renders 100.0% instead of 11.3%
**Reviewer D · CONFIRMED (by construction)**
`plans/2026-08-14-phase-3-decision-layer.md:876-881`, reading a CSV produced by
`phase-1:1991` with `--group-by account__cycle_exposure_cohort`

`pct_base_never_rebilled = renewal_unexposed_accounts / assessable_base_accounts`,
and `cycle_exposure_cohort = '0'` is *defined* as `has_faced_renewal = false`, so
within that group numerator equals denominator. The card prints **"100.0%"** as
"Base that has not yet faced a single renewal". The true value is **11.3%**.

This is the same tautology `METRICS.md:254-262` already documents for
`at_risk_account_rate` by `risk_driver`. Worse, the plan's own test fixture
(`phase-3:498`) hardcodes `["0","357","0.119"]`, so
`test_renders_real_numbers_from_the_csvs` asserting `"11.9" in html` **passes on
fabricated data** and can never catch it.

This is the single card the spec designates as band 2's only measurable number —
the one that turns "churn is out of scope" from a caveat into a computed fact.

**Fix:** read the ungrouped `pct_base_never_rebilled`, and correct the fixture to
reflect what `mf` actually emits.

### F9 — The headline attach rate is whichever row MetricFlow happened to return last
**Reviewer D · CONFIRMED (re-ran the documented export)**
`plans/2026-08-14-phase-3-decision-layer.md:838` (`final_attach = attach[-1]`)

The documented regeneration command for `control_attach_rate.csv` has no
`--order`, and MetricFlow returns hash order. Re-running it returned
`2026-03-30, 2026-03-02, 2026-03-23, … 2026-01-19`. `attach[-1]` is then the
**2026-01-19** row, so the card renders **1.0%** and **0.07× the launch target**
instead of 20.0% and 1.33×. The table below it renders weeks scrambled.

**Verified worse than reported:** running the same query twice in succession
returned two *different* orders (first row `0.00453` then `0.110867`). The order
is non-deterministic between runs, not merely unsorted — so the headline figure
is unstable across regenerations, and a diff of the CSV would show spurious
churn on every export.

The committed CSV happens to be sorted today, which is exactly why this would
survive review.

**Fix:** `max(attach, key=lambda r: r["weekly_attach_row__signup_week__week"])`,
sort before rendering the table, and add `--order` to the export.

---

## HIGH

### F10 — The MRR movement bridge does not reconcile: there is no reactivation bucket
**Reviewer C · CONFIRMED (ran the plan's own SQL and its own test)** · `phase-2:1214-1248`

A row whose previous cycle billed $0 (skipped or paused) and which bills again
this cycle falls into no bucket: `expansion` requires `previous_cycle_mrr > 0`,
`new` requires it to be null.

| cycle | starting | new | expansion | contraction | churned | ending | gap |
|---|---|---|---|---|---|---|---|
| 2 | 27,250.41 | 0 | 190.00 | 2,539.13 | 3,048.96 | 24,481.39 | **−2,629.07** |
| 3 | 5,348.09 | 0 | 20.00 | 669.74 | 399.86 | 4,778.32 | **−479.83** |

The gap decomposes exactly: at cycle 2, 65 return-from-skip rows ($1,769.35) plus
28 return-from-pause rows ($859.72). With `PER_CYCLE_SKIP_RATE = 0.08` this is
guaranteed at scale.

The plan's reconciliation test *is* present and *does* fire — so this will not
ship silently — but the plan has no reactivation term anywhere and Step 5 asserts
the test passes, so the implementer hits a hard stop with no prescribed fix.

**Fix:** add `reactivation_mrr_usd` (`previous_cycle_mrr = 0 and cycle_mrr > 0 and
state <> 'canceled'`) to the mart, the reconciliation test and the NRR
expression. The `state <> 'canceled'` guard is load-bearing, since
`previous_cycle_mrr = 0` also matches post-cancellation rows.

### F11 — A subscription that stays paused is reported `active` and is billed
**Reviewer C · CONFIRMED (21 rows, $629.79 of phantom MRR)** · `phase-2:827-833`

When the resume draw fails the generator emits no event for that cycle, so
`e.event_type` is NULL and the state CASE falls through its `else` to `'active'`,
which is then priced at full `monthly_price_usd`. `acct_00412` pauses at cycle 1,
fails its resume draw at cycles 2 and 3, and appears active and billed at both.

This understates paused volume by 21 of 124 true paused-cycles (17%) — and
Shopify's ask, quoted at `phase-2:1493`, is specifically for pause *volume* —
inflates `rebill_rate`, and contributes $1,029.66 of F10's reconciliation gap as
spurious "return from pause".

**Fix:** carry pause state forward with a window flag rather than reading it from
a single event, and make the CASE's `else` explicit rather than a catch-all.

### F12 — `monthly_churn_rate`'s denominator includes accounts that already churned
**Reviewer C · CONFIRMED** · `phase-2:1085-1090`

The denominator is every row of the spine at that cycle, including accounts that
cancelled earlier and are carried forward as `state = 'canceled'`. Those accounts
had no opportunity to churn in that window.

| cycle | as planned | correct hazard | planted value |
|---|---|---|---|
| 1 | 0.2244 | 0.2278 | 0.232 |
| 2 | **0.0776** | **0.1023** | 0.11 |
| 3 | **0.0458** | **0.0664** | 0.075 |

24% below the true hazard at cycle 2, 31% below at cycle 3. The distortion grows
with cycle index, so the *shape* of the hazard curve — the one thing spec §5.2(b)
says matters — is systematically steepened.

Compounding it: the verification step at `:1119` says *"If churn does not decline
across cycles, stop and report."* The broken number declines **faster** than the
correct one, because the dead-account share grows monotonically. The check passes
precisely on the bug it exists to catch.

**Fix:** add an `at_risk_this_cycle` flag (alive entering the cycle), use it as
the denominator, and replace the check with a comparison against the planted
hazards.

### F13 — NRR still cannot exceed 100%, and transient skips depress both GRR and NRR
**Reviewer C · CONFIRMED (GRR 0.68/0.79/0.80; NRR 0.69/0.80/0.80)** · `phase-2:1229-1238`, `:1337-1351`

The plan *does* deliver spec item 2.7 mechanically — 55 upgrades, 22 downgrades,
expansion MRR nonzero at every cycle, NRR > GRR everywhere — so the Step-5 check
passes. But the structural cap is replaced by a numerical one, because
contraction is defined as *cash not billed this cycle* rather than *subscription
value lost*: a one-cycle skip books the full price as contraction, and (per F10)
the return books nothing.

At cycle 1, expansion is $340 against $6,387.79 of contraction — of which $4,795
is skip and pause that mostly returns next cycle — and $16,734 of churn.
NRR = 0.6896. There is no parameterisation of a 2.2% upgrade rate on a ~$10 tier
delta that offsets a 20%+ churn hazard, so NRR reads 0.69–0.80 forever and is not
comparable to any published benchmark. Meanwhile the METRICS.md text the plan
asks to write at `:1494` implies to the reader that the upgrade arm resolved the
problem.

**Fix:** define contraction and churn on *subscription value at the tier in
force*, not cash billed, so a skip is a billing event and not a downgrade. Publish
skipped/paused revenue as its own "deferred billings" line — that is the
replenishment-specific signal, and it is more interesting named than smuggled
inside contraction. Then label NRR as a launch-cohort reading over ≤4 cycles.

### F14 — `assert_no_events_after_cancellation` cannot fail
**Reviewer C · CONFIRMED (injected 20 violating events; test returned 0 rows)** · `phase-2:688-706`

The test derives `canceled_at_cycle` from `stg_subscription_events`, and
`int_subscription_state.state` is derived from the *identical* expression at
`:828`. Any cycle at or after the first cancellation is hardcoded to
`'canceled'`, so the test compares a value against itself.

The reviewer appended 20 `renewed` events at cycle 3 to accounts that had
cancelled at cycle 1 — exactly what the plan's own comment calls *"the most
expensive mistake this generator can make"* — and the test returned **0 rows**.

**Fix:** assert against the event stream, not the derived state: fail if any
account has `event_type in ('renewed','tier_changed','skipped','resumed')` at
`cycle_index >= canceled_at_cycle`.

### F15 — `kits_late` reads the future; `avg_delivery_delay_days` has no maturity gate
**Reviewer A · CONFIRMED** · `_semantic_models.yml:236-241`

"Did this kit arrive late?" is only answerable after an unbounded wait, but
`kits_late` gates on `is_mature_sla` (10 days) and `avg_days_late` has no gate at
all. 36 deliveries have `kit_delivered_date > 2026-05-03` (the observation date),
and **6 of them are counted as late** — the metric knows about deliveries that
have not happened. `kit_late_rate` is 0.127; excluding the look-ahead rows,
0.12496. The denominator `kits_shipped` is fully gated, so numerator and
denominator are censored differently.

**Fix:** introduce `is_mature_late_assessment` (or simply require
`kit_delivered_date <= observation_date`) and gate both measures on it.

### F16 — Fulfilment waste books engaged customers as 100% waste
**Reviewer B · CONFIRMED** · `phase-1:869-871`, `:891`

`never_activated_30d = is_mature_30d and not combined_activated_30d`, and
`combined_activated_30d` requires login within 30 days **and** an on-time kit — so
a customer who logged in and used the app but whose kit missed the 10-day SLA has
their entire COGS + shipping booked as "spent with no return".

Of the 695 accounts in the waste bucket, **283 (40.7%) logged in within 30 days**.
That is ~$3,860 of the $9,493 never-activated waste and ~36% of the blended
`cac_uplift_pct`. The reader is told "self-serve's real CAC is 55% higher because
it buys people who never show up"; two-fifths of that is "OH's carrier is slow".

**Important:** the direction the spec cares about survives — self_serve +55.4% vs
sales_assisted +13.4%, blended +29.4%, all matching Appendix A. This is a
definitional problem, **not** a join problem.

**Fix:** split `waste_reason` into `kit_lost`, `never_logged_in` and
`late_kit_no_activation`. The two halves lead to opposite decisions.

### F17 — Spec §1.8's second falsification test is missing, and the first is unfailable
**Reviewer B · CONFIRMED** · `phase-1:1504-1516`

§1.8 demands two tests: (a) self-selected have no delivery defect, (b)
system-inflicted are **not concentrated in short tenure**. The plan writes only
(a), and (a) cannot fail because the CASE puts `when kit_failed_sla then
'system_inflicted'` *before* the `self_selected` branch — it asserts the code's
own control flow. On this seed it also evaluates over an empty set (F7).

Had (b) been written it would have found `avg(premium_tenure_days)` of 661.7
(system_inflicted) vs 661.3 (ambiguous) vs a base median of 660 — tenure is a
near-constant in this generator and cannot discriminate anything. **That is the
finding the spec asked the test to surface, and the plan discards it.**

**Fix:** write (b) as a real assertion, and add a non-degeneracy test that
`self_selected` is non-empty.

### F18 — `eligible_premium_accounts` publishes 255,000 for a base of 15,000
**Reviewer D · CONFIRMED** · contract seed `phase-3:103`

Same semi-additivity as F5: 15,000 × 17 weeks. The decision table prints
`255000.000` against a threshold of `10000.000`, status `ok`. The threshold
`below 10000` could never fire against a hardcoded generator constant anyway —
the alarm is undecidable by construction.

### F19 — `nullif(current_value, '')` hard-errors the moment F4 is fixed
**Reviewer D · CONFIRMED (reproduced in DuckDB)** · `phase-3:390-393`

`select try_cast(nullif(v,'') as double) from (select 1.5::double as v)` →
`Conversion Error: Could not convert string '' to DOUBLE`. dbt-duckdb infers
`current_value` as DOUBLE as soon as the values are real numbers. The model only
"works" today *because* of F4, which keeps the column VARCHAR.

**Fix:** `try_cast(nullif(cast(current_value as varchar), '') as double)`, or
force the seed column type in `dbt_project.yml`.

### F20 — `avg_breakeven_cycles above 2.0` can never fire
**Reviewer D · CONFIRMED** · contract seed `phase-3:86`

`breakeven_cycles` is `ceil(...)`, so it is an integer: self_serve 1,
sales_assisted 2. Blended `avg_breakeven_cycles ≈ 1.30`, so `> 2.0` is false.
Even at channel grain sales_assisted lands on exactly 2.0 and `>` is strict.
Appendix A itself predicts "sales_assisted 2 nominal" — so the flagship LTV:CAC
substitute has an alarm that by design cannot fire on its own expected value.

**Fix:** `>= 2.0` (or 1.5), evaluated per channel.

### F21 — `avg_days_to_first_login above 7.0` is the inverted alarm §1.4 itself describes
**Reviewer D · CONFIRMED** · contract seed `phase-3:111`

Spec §1.4 states this mean "**improves as the product gets worse**, because the
15% who never log in drop out of it". The contract then puts an `above` threshold
on that exact mean. Actual value 4.92 → `ok`, while 592 accounts (19.7%) never
logged in at all. If onboarding degrades and another 300 accounts never log in,
the mean falls further and the alarm gets **quieter**.

**Fix:** threshold the censored share or a percentile from
`fct_login_timing_distribution`, never the mean.

### F22 — Task 4's "expected triggers" is wrong, and its remedy is threshold-mining
**Reviewer D · CONFIRMED** · `phase-3:437-440`

The plan says *"Expected: at least `activation_rate_30d_vs_benchmark` and
`cac_uplift_pct` show up as triggered."* Actual `activation_rate_30d = 0.71101`;
`/0.70 = 1.0157` → **`ok`**, not triggered. (`cac_uplift_pct` does trigger.)

The accompanying instruction — *"If nothing triggers, the thresholds are too
loose to be useful; revise them before moving on"* — turns a wrong expectation
into pressure to reverse-engineer thresholds from observed data, which destroys
the falsifiability §3.1 exists to create.

### F23 — Appendix A's fulfilment waste double-counts lost kits, and an acceptance criterion tells you to reproduce it
**Reviewer D · CONFIRMED** · spec Appendix A:396

`$12,124 = $11,220 across 819 non-activated + $904 across 66 lost kits`. The
arithmetic is internally clean and the total reconciles with the effective-CAC
gap to within $4. But the two sets are **not disjoint**:
`sum(case when kit_lost and combined_activated_30d then 1 else 0 end)` returns
**0** — no lost-kit account is ever activated, so the lost set sits entirely
inside the non-activated set.

The spec's `$904` line is therefore **wholly double-counted**: waste is
overstated by $904 (7.5%), not by an additional amount. In the live warehouse the
overlap is **74 accounts** (84 lost in total, 74 of them inside the 769 mature
non-activated).

**The Phase 1 plan itself is correct here** — its ordered CASE puts `kit_lost`
first, making the buckets disjoint (695 + 74), and Reviewer B verified the
uniqueness test. The defect is in the spec: Appendix A's decomposition, and
§1.3's acceptance wording ("reconciles with the counts of lost kits **and** of
mature non-activated accounts"), which instructs the implementer to reconcile
against both sets as though they were disjoint.

**Fix:** state the decomposition as disjoint (non-activated *excluding* lost, plus
lost) and add a test asserting no account is counted twice.

---

## MEDIUM

| # | Finding | Loc | Verdict |
|---|---|---|---|
| M1 | `billing_cycle_months` is declared the single source of the recurrence assumption but only `int_billing_cycles` reads it; set it to 3 and the clock is right while margin stays monthly, `breakeven_cycles` triples, build green | phase-1:141, :527-534 | PLAUSIBLE |
| M2 | No completeness test on `fct_subscription_unit_economics` — the pricing join is INNER, so a pricing miss *removes* accounts. `relationships` tests orphans, not coverage; `assert_cost_to_recover_exceeds_cac` is algebraically true for every non-null row | phase-1:552-558 | CONFIRMED |
| M3 | Censoring register covers 5 of ~12 published rates; omits `at_risk_account_rate` (97 accounts, 3.2%, excluded), both task rates, `attach_rate`. Spec §6.3 says *every* rate | phase-1:1276-1294 | CONFIRMED |
| M4 | `activation_rate_30d_vs_benchmark`: the plan's "runs BELOW 1.0" is false (71.1% > 70% benchmark; every fully-mature week 0.70–0.75). The apparent crossing is week 2026-03-30 at 76% maturity. A card saying "activation fell below benchmark" would be reporting censoring — in the phase whose thesis is making censoring visible | phase-1:2011-2024 | CONFIRMED |
| M5 | `share_breakeven_within_window`'s label presents a modelled schedule as observed behaviour — the §1.1 violation | phase-1:774-780 | PLAUSIBLE |
| M6 | All five Phase 1 singular tests are structurally unfailable; legitimate as regression guards, but presented as TDD cycles and as satisfying the falsification requirement | phase-1:190-198, 498-513, 840-850, 1504-1531 | CONFIRMED |
| M7 | Task 1's cycle-ceiling guard is promised in a var comment and never built | phase-1:146-149 | CONFIRMED |
| M8 | `test_skips_do_not_end_the_subscription` is `X or True` — mutation-tested: made a skip terminate the subscription, test still passed | phase-2:238-253 | CONFIRMED |
| M9 | `test_churn_hazard_declines_across_cycles` asserts on a dict literal, never calling the generator. Replaced the hazard with a flat 0.20 — **all 9 tests still passed** | phase-2:167-175 | CONFIRMED |
| M10 | `test_tier_changes_include_both_directions` compares against the *original* tier, so round-trips read as no-change: **109 failures across 200 seeds**. Seed 11 happens to be clean; the plan's own advice ("raise n") makes it strictly worse | phase-2:218-235 | CONFIRMED |
| M11 | Planted-effect recovery conditions on `combined_activated_30d` but the effect is planted on `first_login_date is null` — recovers 1.50 instead of 1.99, a 25% attenuation already present in the passing state, inside a band wide enough to hide it | phase-2:1397-1451 | CONFIRMED |
| M12 | Stated `rebill_rate` expectation 0.72–0.82 is unreachable; actual 0.6776. Invites tuning the generator to hit an arithmetic slip | phase-2:1119 | CONFIRMED |
| M13 | `churned_this_cycle` is NULL (not FALSE) for 72% of rows — `x.canceled_at_cycle = c.cycle_index` on a missed left join | phase-2:840 | CONFIRMED |
| M14 | Four new Phase 2 metrics are semi-additive across cycles with no guard; ungrouped they blend a cumulative survival curve with an incremental hazard | phase-2:1078-1108 | CONFIRMED |
| M15 | `METRICS.md` misdescribes `avg_days_to_first_login`/`avg_days_to_kit_delivery` — the implementation also requires `is_mature_30d` AND `days_to_* <= 30` | METRICS.md:93-101 | CONFIRMED |
| M16 | `zero_digital_access_accounts` gates on a flag derived from an unrelated var; the two 14s agree only coincidentally, and `dbt_project.yml:26-32` says they are different concepts | _semantic_models.yml:126-128 | CONFIRMED |
| M17 | `mf list metrics` returns **62**, not the documented 33 — 29 undocumented proxies including `cumulative_subscriptions`, a semi-additive alias with no grain warning returning 26,740 against 3,000 real subscriptions | _semantic_models.yml | CONFIRMED |
| M18 | `contribution_margin_per_cycle` is numerically identical to `contribution_margin_per_subscription` ($14.27 both) — `fct_weekly_channel_economics.sql:26` already computes per-cycle margin. The contract carries both rows with identical thresholds, so the board shows one number twice under two names | phase-3:105-106 | CONFIRMED |
| M19 | `wow_subscription_growth` can only ever be `no_data` — `mf query` exits 1 without a `metric_time` group-by | phase-3:80 | CONFIRMED |
| M20 | Four channel/state-scoped thresholds evaluated on national aggregates, silencing every one: `cac_by_channel` 15.0 vs blended 12.05 (sales_assisted 24.87); `effective_cac` 20.0 vs ~15.9 (sales_assisted ~31); `kit_lost_rate` 0.05 vs 0.0276 (OH 0.0719); `state_penetration` 0.10 vs 0.20 (PA 0.081, NJ 0.090) | phase-3 seed | CONFIRMED |
| M21 | Un-normalised cumulative totals: `channel_spend` (permanently triggered) and `incremental_mrr` (ok cumulative, permanently triggered weekly). Both meaningless without a stated period | phase-3 seed | CONFIRMED |
| M22 | Appendix A's 14-day censoring figure is an arithmetic slip: 119 and 83 are correct linear interpolations, but 238 = 357×(20/30) — the 14-day window computed as 20 days. Linear would be 167; the real value is 97 | spec Appendix A:399 | CONFIRMED |
| M23 | Appendix A's "CA 44.9%" is CA's share of the *eligible base* (6737/15000), not of margin. Actual margin share CA **50.9%**, top-3 **76.8%**; the stated top-3 of 68.7% matches neither denominator | spec Appendix A:400 | CONFIRMED |
| M24 | Spec §5.2 and Appendix A say the median account has 2 observable cycles; it has **1** (distribution 339/1256/1099/306, so the 1500th account sits in cohort 1) | spec §5.2:303 | CONFIRMED |
| M25 | The Phase 3 renderer omits most cards §3.2 specifies — the entire benchmark strip, new-subs-per-week, saturation, concentration, cycle-exposure chart, corrected per-cycle margin, fulfilment waste, SLA by state, damage split — while the Self-Review claims full coverage. Three Phase 1 CSVs are exported and consumed by nothing | phase-3:626-633 | CONFIRMED |
| M26 | Spec §6.3, §6.6 and §6.7 are ticked in Task 6 Step 5 without being met: one censoring table is not "denominator beside each rate"; Task 4 deliberately queries ungrouped, contradicting "at the grain the dashboard actually uses"; no `git diff` of the CSVs is run | phase-3:1035-1042 | CONFIRMED |

---

## LOW

- **L1** `phase-1:246` expects a decreasing 4-bucket distribution; actual peaks in the middle (339/1256/1099/306), as a logistic signup curve must. A literal implementer could halt on a correct model.
- **L2** `phase-1:1905` expects max `margin_share` 0.40–0.50; actual CA 0.5088.
- **L3** `phase-1:718` expects self_serve CAC $7–12; actual $6.56 (and $7.14 once F1 is fixed — inside the band).
- **L4** `phase-1:465` declares `signup_week (date)`; `date_trunc('week', DATE)` returns TIMESTAMP in DuckDB. Harmless, but it is the same class of trap the plan documents for `INTERVAL`.
- **L5** `phase-1:2029` estimates the test total at 165–175; counting the plan's own YAML it lands nearer 178. A low estimate triggers a false "baseline broke" alarm.
- **L6** Hardcoded business numbers contradict the plan's own global constraint: `premium_tenure_days <= 180` (Task 10), login bands 2/7/14 (Task 9).
- **L7** `phase-2:1514` expects 31 passed; Task 2 Step 1 adds a tenth test, so 32.
- **L8** `phase-2:1477` says "the 10 new metrics"; the plan declares 5 ratio + 2 derived explicitly and 13 more via `create_metric: true`.
- **L9** `fct_subscription_lifecycle` selects `account_state`, `channel`, `premium_tenure_band` but declares no dimensions for them; the group-bys resolve through the `accounts` model instead, so the three columns are dead weight.
- **L10** `kit_on_time_delivery_rate` and `kit_sla_rate` are the same number computed twice (0.8454204971058904 both), documented as answering different questions, and carried as two contract rows under different decision questions.
- **L11** `cac_payback_months` treats one-time kit COGS and shipping as recurring — the assumption spec §1.2(a) exists to fix, but currently undeclared in METRICS.md.
- **L12** The decision table renders rates, counts, dollars and days in one column via `_num(..., 3)` with no unit annotation.
- **L13** `_stat_card` double-escapes band-3/band-4 titles (`_esc` called on the channel, then again on the title).
- **L14** `VOID_CARDS` embeds literal benchmarks ("<5%/month", "3.9% average") — numbers on the page from no CSV, against the plan's own "No invented data" constraint.
- **L15** Void-badge inconsistency: the card reads `PHASE 2.1 + 2.2 + 2.7 → GRR MEASURED · NRR PENDING`, but 2.7 is precisely what makes NRR measurable.
- **L16** `raw_metric_values` gets no `unique`/`not_null` schema test, unlike `raw_published_metrics`.
- **L17** Spec §1.6 says `activation_rate_30d` runs 60.3%–75.2%; actual weekly range is 60.29%–77.27%.
- **L18** The contract seed is 8 rows short of coverage (`weekly_new_subscriptions`, `attach_rate`, the three activation rates, `mature_cohort_size_30d`, `at_risk_accounts`, `cumulative_subscriptions_to_date`). Task 2 handles this procedurally but does not name them.
- **L19** `win_rate` (0.30198 vs threshold 0.30) is correct but knife-edge — 0.002 from flipping.

---

## Verified correct

This is the coverage evidence. It matters as much as the findings.

**22 of 33 live metrics recomputed from the raw seed CSVs and matched to full
precision** (Reviewer A): `digital_activation_rate_7d` 0.6587837837837838,
`kit_sla_rate` 0.8454204971058904, `activation_rate_7d/14d/30d`,
`task_completion_rate`, `task_engagement_rate`, `zero_digital_access_accounts`
592, `zero_task_accounts` 430, `mature_cohort_size_30d` 2661,
`avg_days_to_first_login` 4.916405900759947, `avg_days_to_kit_delivery`,
`win_rate` 899/2977, `conversion_lag_days` 654.157, `at_risk_account_rate`
944/2903, `at_risk_accounts`, `weekly_new_subscriptions` 3000, `incremental_mrr`
83,870.00, `arpa`, `contribution_margin_per_subscription` 14.27, `kit_lost_rate`,
`kit_on_time_delivery_rate`.

**Structural integrity of the existing marts:** no fan-out anywhere (group-bys sum
to 3000/944/2937/2661); `fct_weekly_attach` is a genuine 12×17 spine with a unique
key; the kit taxonomy partitions cleanly (2483 + 373 + 81 = 2937, zero
delivered-and-lost); surrogate primary entities are genuinely unique;
`cost_per_activated_account` nulls numerator and denominator on the same 8
zero-mature channel-weeks; `wow_subscription_growth` refuses an ungrouped query
rather than answering misleadingly — a better failure mode than F5's;
aggregations use `sum(total)/sum(count)` and avoid the average-of-averages trap.

**Phase 1's billing-cycle clock is correct.** No `date_diff` anywhere in the cycle
count — the spine-and-filter construction dodges the documented trap. The `::date`
cast is present and necessary. End-of-month clamping is correct **and
non-sticky** (2026-01-31 +1mo = 2026-02-28, +2mo = 2026-03-31, which is the right
billing behaviour). `cycle_index = 0` is unambiguously the initial purchase, all
3,000 accounts get that row, no due date exceeds the observation date, and the
ceiling of 4 is never reached. The observation date is byte-identical to
`int_activation_funnel`'s.

**Phase 1's effective-CAC and waste join — the part the spec flagged as most
likely broken — is correct.** Pre-aggregated to (channel, week) before the join,
so no fan-out; 34-row count preserved; no orphaned waste row; channel drawn from
the same lineage on both sides, so no misattribution. Direction and magnitude
match Appendix A's key signal: self_serve **+55.4%** (spec ~56%), sales_assisted
**+13.4%** (spec ~15%), blended **+29.4%** (spec ~30.5%). `cac_uplift_pct =
waste/spend` is algebraically identical to `effective_cac/cac − 1` at every grain.

**Also sound in Phase 1:** `breakeven_cycles`' null handling (CASE with no ELSE →
genuinely NULL, never 0 or infinity, exactly as §1.2 requires); per-cycle margins
$9.49/$15.49/$21.49 and weighted $14.27; the login-timing `15-30` band (no
future-login leak; `never` = 15.9% matching `NEVER_LOGS_IN_RATE = 0.15`); every
censoring-register denominator matching its metric's actual gate; state
saturation summing to exactly 3,000 with a complete final week; recoverable
revenue $12,455.52 vs the spec's $12,540; the §1.1 naming constraint respected
throughout.

**Phase 2's generator determinism is correct** — `LIFECYCLE_SEED = SEED + 5 = 47`
is distinct from all five existing streams, the generator instantiates its own
`default_rng`, runs after the others, and only reads their output. No existing
seed CSV moves. Its `_add_months` matches DuckDB's `DATE + INTERVAL n MONTH::date`
for every date in 2026 × 0–4 months, 0 mismatches. Right-censoring on the spine is
correct and correctly motivated: a 10-day-old account gets only a cycle-0 row and
is neither retained nor churned at cycle 1. GRR excludes expansion, NRR adds it,
both read the same `starting_mrr_usd`, and GRR is arithmetically incapable of
exceeding 100%. Cancellation is absorbing and no account is charged after
cancelling.

**Phase 2 handles the circularity trap well.** The planted multiplier is named,
commented as an assumption, mirrored as a dbt var so generator and test read one
value, documented in a METRICS.md assumptions table, and explicitly barred from
the narrative. The recovery test is framed as pipeline validation, not discovery.
No tautology dressed as a finding anywhere. (One undeclared assumption worth
adding to that table: `PER_CYCLE_PAUSE_RATE` makes pause churn-immune, so
retention is biased upward by roughly the paused population — small at 3.5%, but
undeclared.)

**MetricFlow entity qualification is right in all three plans.** Every
`--group-by` uses the entity name, never the semantic-model name —
`account__cycle_exposure_cohort`, `effective_cac_row__channel`,
`saturation_state__state`, `lifecycle_row__cycle_index`,
`mrr_movement_cycle__movement_cycle_index` — confirmed against the shipped export
header `account__risk_driver`. Reviewer C ran all four of Phase 2's lifecycle
`mf query` commands against real data; all succeeded.

**The Phase 3 renderer's number handling is correct** where it isn't structurally
broken: `_pct` is applied only to genuine 0–1 ratios at all six call sites,
`_num`/`_money` are used correctly, no percentage or count is multiplied by 100.
The `status` CASE puts the null branch first, so a missing value can never fall
through to `ok` or `triggered`, and a legitimate `0` is preserved.
`MissingControlFile` raises rather than rendering a placeholder, and the
three-state theme CSS is correctly structured with the `:root` token test
guarding the un-stamped-theme bug.

**19 of the 34 contract thresholds are in the right unit, the right direction and
plausibly placed** — including all five that correctly fire today
(`pct_base_never_rebilled`, `cac_uplift_pct`, `avg_delivery_delay_days`,
`at_risk_account_rate`, `system_inflicted_at_risk_accounts`,
`zero_digital_access_accounts`). Every one of the 34 metric names exists today or
is created by Phase 1; none is orphaned; no Phase 2 dependency leaks in.

**Repo bookkeeping checks out:** 33 metrics in `_metrics.yml`, 11 control CSVs,
7 seeds + 20 models + 96 tests = PASS 123, `pytest` baseline 22 passed, 34
contract rows, and §1.7's vanity audit verified — all 10 named metrics genuinely
appear in no export (23 exported + 10 unexported = 33).

---

## Recommended repair order

**Before anything else — F1.** It is the only defect in shipped code, it is a
five-line fix, and every CAC-derived number in the repo and in Appendix A is
being judged against a corrupted baseline until it lands.

**Then, per plan, in this order:**

*Phase 1:* F2 (nothing else is verifiable until `dbt parse` succeeds) → F6
(one-line fix, wrong headline number) → F7 + F17 together (the same defect from
the model side and the test side) → F16 → M1–M7.

*Phase 2:* F3 (same gate) → F11 + F12 (both corrupt the retention curve's shape)
→ F10 → F13 (the largest design change; it subsumes part of F10) → F14, M8–M12.

*Phase 3:* F4 (nothing renders until the parser works) → F19 (surfaces the moment
F4 is fixed) → F5 + F8 + F9 (the three wrong numbers on the board) → the
threshold repairs F18, F20, F21, M18–M21 → M25 (the missing cards).

**Spec edits:** F23 and M22–M24 are corrections to Appendix A and §5.2. None
changes a conclusion; all four change a number an implementer is told to
reproduce.

---

## Appendix A — §5.2's LTV:CAC table, independently recomputed

Reviewer D reproduced all 16 cells. Survival model: geometric lifetime with
monthly churn `c`, `S(n) = (1−c)ⁿ`, mean lifetime `Σ S(n) = 1/c` counting the
acquisition cycle, undiscounted (§5.1 explicitly discards a discount rate, so
this is the internally consistent choice), tail share after cycle 4 = `(1−c)⁴`.

| Churn | Spec lifetime | Recomputed | Spec LTV | Recomputed | Spec ratio | Recomputed | Spec % after cy.4 | Recomputed |
|---|---|---|---|---|---|---|---|---|
| 3% | 33.3 | 33.333 ✓ | $476 | $476.33 ✓ | 27.5 | 27.53 ✓ | 88.5% | 88.529% ✓ |
| 5% | 20.0 | 20.000 ✓ | $286 | $285.80 ✓ | 16.5 | 16.52 ✓ | 81.5% | 81.451% ✓ |
| 8% | 12.5 | 12.500 ✓ | $179 | $178.62 ✓ | 10.3 | 10.33 ✓ | 71.6% | 71.639% ✓ |
| 15% | 6.7 | 6.667 ✓ | $95 | $95.27 ✓ | 5.5 | 5.51 ✓ | 52.2% | 52.201% ✓ |

**All 16 cells reproduce to the stated precision**, and the prose conclusions that
rest on them — "72%…89% of LTV falls outside the window", "a 5× spread that all
leads to the same decision", "all four clear 3:1" — follow. The most contrarian
decision in the spec is arithmetically sound.

The only correction is to an *input*, not the arithmetic: the median account has
**1** observable cycle, not 2 (M24).

---

## Appendix B — Appendix A magnitudes vs. the warehouse

Appendix A declares itself illustrative, and most drift is harmless. Flagged
below are the entries where the drift would mislead an implementer using them as
tripwires.

| Quantity | Spec | Actual | Note |
|---|---|---|---|
| `pct_base_never_rebilled` | 11.9% (357) | **11.3% (339)** | fine as a tripwire |
| Cycle exposure | 357/1143/1143/357 | **339/1256/1099/306** | the spec's symmetric shape is not what a saturating logistic produces |
| Per-cycle margin | $9.49/$15.49/$21.49, wtd $14.29 | same; wtd **$14.27** | ✓ |
| Nominal CAC | $7.20 / $27.40 / $13.26 | **$7.14 / $26.55 / $12.96** | within 3% *once F1 is fixed*; without the fix the warehouse reads $6.56/$24.87/$12.05 |
| Effective CAC blended | $17.30 | ~$16.5 (F1-corrected) | direction and uplift ratios match |
| Fulfilment waste | $12,124 | overstated **$904 (7.5%)** | **F23 — the lost set sits entirely inside the non-activated set** |
| Censoring register | 357 / 238 / 119 / 83 | **339 / 97 / 63 / 40** | **M22 — the 14-day figure used a 20-day window** |
| Damage split | 448 / 360 / 136 | **448 / 0 / 496** | **F7 — `self_selected` is structurally empty** |
| Recoverable revenue | $12,540 (448 × $27.99) | **$12,455.52** | ✓, and 448 matches the live count exactly |
| Margin concentration | CA 44.9%, top-3 68.7% | **CA 50.9%, top-3 76.8%** | **M23 — 44.9% is CA's share of the eligible base, not of margin** |
| Lost kits | 66 | **84** | |
| Non-activated | 819 | **769** mature / 863 total | |
| Median observable cycles | 2 | **1** | M24 |

---

## Note on reviewer disagreement

Reviewers B and D reported different cycle-exposure distributions —
339/1256/1099/306 versus 339/1193/1189/279. I adjudicated this directly by
running the spine-and-filter construction Phase 1 Task 1 specifies against the
warehouse: the result is **339 / 1256 / 1099 / 306**, matching Reviewer B.
Reviewer D's figures are wrong, most likely from different month arithmetic. Both
distributions sum to 3,000 and both support M24's conclusion that the median is
1 cycle, so no other finding is affected.


---

## Validation pass

The findings above were re-checked against the warehouse independently of the
reviewer who raised each one. Status per critical/high finding:

| Finding | Status | Evidence from the re-check |
|---|---|---|
| F1 spend leak | **Reproduced exactly** | staging $38,876.40 vs mart $36,144.02; per-channel $15,003.64/$13,784.91 and $23,872.76/$22,359.11 |
| F2 / F3 parse failure | **Confirmed structurally** | 7 of 7 semantic models with measures declare `agg_time_dimension`; `accounts` is the sole model without one and has zero measures; `dim_accounts` has no date column. The suggested fix name `accounts_signup_date` matches the established convention (`activation_signup_date`, `kit_signup_date`, `at_risk_signup_date`) |
| F4 parser footer | **Reproduced exactly** | last stdout line is `🖨 Wrote query output to /dev/stdout` |
| F5 attach_rate | **Reproduced exactly** | `attach_rate` 0.104863 · `attach_rate_vs_target` 0.699085 · `eligible_premium_accounts` 255000 |
| F7 self_selected empty | **Reproduced exactly** | 4 accounts at `premium_tenure_days <= 180`; min 56 / median 660 / max 900; band `181-365` holds 136 |
| F9 attach ordering | **Worse than reported** | two consecutive runs returned two different orders — non-deterministic, not merely unsorted |
| F15 kits_late | **Reproduced exactly** | 36 deliveries after the 2026-05-03 cutoff, 6 of them counted late; `kit_late_rate` 0.12700 |
| F16 waste definition | **Reproduced exactly** | bucket 695 (excluding lost), of which 283 logged in within 30 days and 412 never logged in |
| F18 eligible base | **Reproduced exactly** | 255,000 |
| F20 breakeven alarm | **Confirmed by arithmetic** | self_serve ceil(7.14/14.27)=1, sales_assisted ceil(26.55/14.27)=2, blended avg 1.30; `> 2.0` is false either way |
| F21 login-mean alarm | **Reproduced exactly** | mean 4.92 while 592 accounts never logged in |
| F23 waste double-count | **Corrected** | overlap is 74 accounts, not 84; the spec's $904 line is wholly double-counted; the Phase 1 plan's ordered CASE is correct |
| F6, F8, F17, F19, F22 | Not independently re-run | reasoning-based or dependent on Phase 1 models that do not exist yet; the arguments are internally sound |
| F10 – F14 | Not independently re-run | require reconstructing the Phase 2 generator, which Reviewer C did; its evidence (executed SQL, mutation tests, injected violations) is quoted verbatim above |

**Cycle-exposure conflict resolved:** running the spine-and-filter construction
Phase 1 Task 1 specifies gives **339 / 1256 / 1099 / 306**, matching Reviewer B.
Reviewer D's 339/1193/1189/279 is wrong. Both sum to 3,000 and both support M24.
