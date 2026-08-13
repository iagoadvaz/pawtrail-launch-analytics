# PawTrail Launch Analytics — Design Spec

Date: 2026-08-12
Status: Approved (ready for implementation planning)

## 1. Purpose and background

This is a portfolio case study built to demonstrate direct subscription/ecommerce
analytics skills — SQL, dbt, semantic layer design, and BI dashboarding — for
Senior Data Analyst roles focused on Post-Sales / subscription / ecommerce
domains.

The entire project — code, comments, commit messages, README, narrative memo,
metrics dictionary, and any other artifact in this repository — **must be
written in English**, with no exceptions.

The product, company, and all data in this repository are **entirely
fictional**. No real company, dataset, or confidential information is used.
One real, public dataset (Olist Brazilian E-Commerce) is blended in purely as
a statistical scaffold for delivery-logistics realism, as detailed in
Section 4.

## 2. Scope

Simulate the **launch window (day 0–120)** of a fictional subscription add-on
product: **PawTrail**, a monthly offering bundled on top of an existing pet-care
platform's Premium plan, combining:

- A **physical component**: a monthly kit (treats, toys, enrichment items)
  shipped to the pet owner's home.
- A **digital component**: an app module for logging pet health/activity and
  completing "care plan" tasks.

This structure intentionally mirrors a real interview case (subscription
add-on with a physical + digital dual-activation risk, launch-phase framing,
no long-term retention history yet) without referencing any real company or
product.

**Out of scope** (deliberately, and documented as a reasoning point in the
narrative memo):
- 12-month cohort churn, NRR, LTV, LTV:CAC — not statistically reliable this
  early; would be speculative.
- Rule of 40, Magic Number, Quick Ratio — mature-stage SaaS metrics requiring
  months/quarters of retention and expansion data.
- Orchestration tooling (Airflow/Dagster), CI/CD pipelines, multi-user auth.
- Sigma — mentioned as a known tool in the target job description, but not
  implemented (no accessible free tier); Tableau Public is used instead as
  the closest available equivalent for the BI deliverable.

## 3. Architecture

```
Olist (real CSV: delivery timing, state distribution)  ─┐
                                                          ├─→ DuckDB (raw) ─→ dbt (staging → intermediate → marts) ─→ MetricFlow (semantic layer) ─→ Tableau Public
Synthetic generator (Python, seeded: subscriptions,     ─┘
signups, digital engagement, pet tiers)
```

- **Warehouse/engine**: DuckDB (local, zero-cost, no cloud account required to
  reproduce the project).
- **Transformation**: dbt (dbt-core + dbt-duckdb adapter).
- **Semantic layer**: dbt Semantic Layer / MetricFlow, run locally via the
  `mf query` CLI (no dbt Cloud dependency). Metrics are declared once and
  queried consistently — directly addressing the "legacy refactor / semantic
  layer" scenario raised in the source interview.
- **BI / dashboard**: Tableau Public (free, produces a public shareable link;
  matches one of the two BI tools named in the target job description).

## 4. Data strategy (hybrid: real + synthetic)

- **Real data (Olist Brazilian E-Commerce, public Kaggle dataset)**: used
  *only* as a statistical scaffold — its empirical **purchase-to-delivery
  duration** distribution and its regional concentration curve are resampled to
  generate realistic shipment timing and regional spread for PawTrail's kit
  deliveries. Olist's actual customer, order, or product identities are **not**
  reused as if they were PawTrail accounts — only the underlying statistical
  patterns are borrowed. Two transformations are applied and documented in
  `data/olist_reference/README.md`:
  - Duration, **not** estimated-vs-actual delta. Olist's estimated delivery
    dates are padded by roughly 10–12 days, so the delta measures forecast
    conservatism rather than how long a shipment took. Durations are then
    rescaled to a subscription-kit fulfilment range, preserving the right-skewed
    shape at a plausible absolute level.
  - The regional concentration curve is mapped onto US state codes by rank, and
    truncated to the top 12 regions. PawTrail prices in USD, so Brazilian state
    codes would be internally inconsistent in every chart; and Olist's
    untruncated tail reaches ~0.05% share, which at this project's volume is one
    or two accounts per region — enough for a meaningless rate to outrank the
    deliberately injected problem on a sorted chart. Only the shape is borrowed;
    no claim is made about any real US market.
- **Synthetic data (generated, seeded Python script)**: everything specific to
  the subscription mechanic — signup dates following an S-curve adoption
  curve over ~120 days, plan/pet tier, channel (self-serve vs. sales-assisted),
  digital engagement events, kit delivery linkage, and task completions.
- A deliberate "problem" is injected into the synthetic generation (e.g., one
  state or channel with a materially worse kit delivery SLA), so the dashboard
  and narrative have a genuine root cause to investigate — mirroring the
  interview question "what would you do if activation were low?".

## 5. Data model (dbt)

**Staging**: `stg_subscriptions`, `stg_digital_engagement`, `stg_kit_deliveries`
— typing and cleaning only.

**Intermediate**: activation funnel joins — subscribed → digital access within
7 days → kit delivered within SLA → first care-plan task completed.

**Marts**: `fct_subscriptions`, `fct_activation_events`, `fct_kit_deliveries`,
`fct_at_risk_accounts` (the Customer Success work queue, tagged by failure
driver), `dim_accounts` (state, pet tier, channel, Premium tenure before
attach).

**Tests**: dbt schema tests (not_null, unique, relationships, accepted_values)
on all mart keys and categorical fields, plus singular tests for sanity bounds
(e.g., all rate metrics between 0 and 1, no negative delivery intervals).

## 6. Metrics catalog (semantic layer)

Every metric below that is computable from this version's generated data is
declared in the dbt Semantic Layer (MetricFlow), and the semantic layer is the
authoritative, single source of truth for every number shown on the dashboard
and in the narrative memo. No number is computed in Tableau or written by hand
into the memo.

A subset of the catalog is **deferred**, marked `[deferred]` below. Each one is
blocked on a synthetic data stream this version does not generate — session
events, cancellations, support contacts, lead-stage events, or spend tagged by
source and region — not on analytical difficulty. `METRICS.md` lists each
deferred metric against the specific source data it would need. This split is
deliberate and is itself part of what the case study demonstrates: shipping a
coherent, fully-sourced metric layer beats declaring a larger catalog that
cannot be computed.

**Acquisition / conversion**
- Eligible Premium accounts (addressable universe)
- Cumulative PawTrail subscriptions (total and week-over-week)
- Attach rate (Premium → PawTrail) vs. launch target
- Attach rate by state/region
- [deferred] Attach rate by channel (self-serve vs. sales-assisted)
- [deferred] Attach rate by pet tier and by Premium tenure before attach
- Conversion lag (days between becoming Premium and attaching PawTrail)
- Week-over-week growth rate of new subscriptions (adoption curve shape)

**Activation** (the most critical metric in this phase)
- % accounts with app login within 7 days
- % accounts with first kit delivered within promised SLA
- Time from subscription to first digital access
- Time from subscription to first kit delivered
- [deferred] Time from subscription to first completed care-plan task
- **Combined activation rate** at 7/14/30 days (digital + physical) — the
  phase's North Star metric
- Digital-only activation rate / physical-only activation rate (isolates
  which leg is failing)
- [deferred] % pet profiles with complete onboarding

**Early engagement** (leading signal, not retention)
- % of first-cycle tasks/content marked complete
- [deferred] Average app sessions in first 2–4 weeks
- [deferred] % accounts with at least 1 health/activity log in the first cycle
  — health/activity logging is a distinct app surface from care-plan tasks
  (§2), and the generator emits only task completions, so the implemented
  task-engagement rate is not a substitute for it
- [deferred] Repeat engagement rate within 30 days (2nd, 3rd session — habit-forming
  signal)
- [deferred] Feature adoption (which app features are used first)

**Physical kit operations** (largest operational risk of the launch)
- First-kit on-time delivery rate (SLA %)
- Delay distribution (days late)
- Lost/damaged kit rate
- [deferred] Complaint/replacement rate in the first cycle
- Delivery SLA by state/region (surfaces problem geographies)

**Early risk signals** (churn proxies — no churn data exists yet)
- Accounts with zero digital access in 14 days
- Accounts with delayed or missing first kit
- Accounts with zero completed tasks in the first cycle
- Composite at-risk queue, tagged by driver (digital failure vs. physical
  failure vs. onboarding gap)

**Business signals**
- Incremental revenue from attach (aggregate MRR added, even at small N)
- [deferred] Cancellation-before-first-cycle rate (immediate regret signal, distinct
  from mature churn)
- [deferred] Support/call-center contact volume and top reasons related to PawTrail

**Acquisition efficiency (CAC and related)**
- Attach CAC: marketing/sales spend allocated to the PawTrail campaign ÷ new
  subscriptions in the period
- CAC by channel (self-serve vs. sales-assisted)
- [deferred] CAC by segment (state/region)
- Cost per activated account = CAC ÷ activation rate (more meaningful than
  raw CAC in launch phase, since an unactivated subscription is a weak signal)
- Estimated payback period (CAC ÷ monthly contribution margin per
  subscription, where contribution margin = price − kit COGS − shipping)
- ARPA (average revenue per account) for the add-on
- Contribution margin per subscription (basic unit economics)
- [deferred] Cost per lead/pitch (sales-assisted channel, funnel stage above attach)
- Win rate for the sales-assisted channel (% of pitches that convert)
- [deferred] Paid vs. organic CAC split (in-app cross-sell should be near-zero CAC;
  separating it from paid-campaign CAC is what should actually drive
  investment decisions)

**Segmentation**
State/region · pet tier/type · channel · Premium tenure before attach — all four
available on the activation, engagement, kit-operations and risk metrics via
`dim_accounts`.

One exception, and it is a definitional one rather than a gap in the model:
**attach rate can only be segmented by state**. Its denominator is the eligible
Premium base, which is known per state and is not attributable to a channel, pet
tier, or tenure band — an account's channel is a property of how it *attached*,
so it does not exist for the accounts that never did. Segmenting attach rate by
a dimension that only exists post-conversion would divide a channel-specific
numerator by a whole-population denominator and read as a far lower rate than
reality. Splitting the base by channel would require attributing the
addressable universe to channels in the generator; until then those cuts are
marked `[deferred]` above. Attach rate is also semi-additive: it may be grouped
by week, or by week and state, but never by state alone.

**North Star for the launch phase**: Combined 30-day activation rate — % of
subscribing accounts with confirmed digital usage **and** an on-time first
kit delivery, within the first 30 days.

Two definitional constraints on this metric, both load-bearing:

- **"On-time" means the kit hit the delivery SLA**, not merely that it arrived
  inside the 30-day window. Almost every kit arrives within 30 days, so the
  looser reading would let a region with a severe delivery problem still score
  as fully activated — collapsing the metric's ability to surface the very
  failure it exists to detect.
- **The denominator is the mature cohort only** — accounts that have had the
  full 30 days. Accounts that signed up recently have not failed to activate;
  they have not yet had the chance. Counting them as failures biases the metric
  downward hardest in the most recent weeks, which are exactly the weeks a
  launch dashboard is read for. The same treatment applies to the 7-day digital
  and kit-SLA rates against their own windows.

**Explicitly excluded, with rationale documented in the narrative memo**:
LTV:CAC, Rule of 40, Magic Number, Quick Ratio, 12-month churn, NRR — all
require months/quarters of retention and expansion data not yet available.
Citing this exclusion explicitly is itself part of the interview-answer
pattern this case is built to demonstrate.

## 7. Deliverables and repository structure

New repository at `~/projects/pawtrail-launch-analytics`, English-only
throughout:

```
pawtrail-launch-analytics/
├── data/
│   ├── olist_reference/      # derived Olist distributions + fetch script
│   └── generator/            # seeded Python script for synthetic data
├── pawtrail_dbt/             # dbt project: staging, intermediate, marts,
│                              # MetricFlow semantic models + metrics
├── dashboard/                # Tableau Public workbook + published link
├── docs/
│   └── superpowers/specs/    # this design doc and future plan docs
├── README.md                 # context, fiction/data disclaimers,
│                              # architecture, how to run
├── NARRATIVE.md              # 1-page memo: is the launch healthy, based on
│                              # which signals, and what to recommend next
└── METRICS.md                # metrics dictionary (semantic layer, human-
                               # readable mirror of the MetricFlow definitions)
```

## 8. Validation approach

- **Test-first modeling**: for each dbt model, the expected schema tests and
  singular-test assertions (e.g., "combined activation rate must be within
  [0, 1]", "every subscription must resolve to exactly one account") are
  written and defined *before* the model's SQL is implemented, not
  afterward. This is treated as an explicit engineering practice for the
  project, not an afterthought — it plays the same role a TDD red/green
  cycle plays in application code, adapted to declarative data
  transformations.
- dbt schema tests on all mart models (not_null, unique, relationships,
  accepted_values).
- Singular dbt tests for metric sanity bounds (rates within [0, 1], no
  negative time intervals).
- Manual sanity check: the injected "problem" segment (Section 4) must be
  visibly identifiable in the dashboard and called out correctly in
  `NARRATIVE.md`, proving the metrics and dashboard actually surface a
  root-cause signal rather than just displaying numbers.

## 9. References

External sources used to validate the metrics catalog (Section 6) against
real-world industry practice. None of these describe PawTrail or any real
company in this repository — they ground the metric *definitions and
benchmarks* only.

- **Attach rate** — standard formula is subscriptions-with-add-on ÷ total
  active subscriptions (or Add-on ARR ÷ Core ARR). Typical benchmarks: 10–30%
  for optional add-ons, 40%+ for top performers.
  [Product Attach Rates for SaaS Companies (Ordway Labs)](https://ordwaylabs.com/blog/product-attach-rates-saas-companies/),
  [Attach Rate for Add-ons Playbook (Umbrex)](https://umbrex.com/resources/company-analysis/product-management/attach-rate-for-add-ons/)

- **Activation rate** — confirmed as the leading indicator of retention;
  activation windows of 7 days (consumer) or 14–30 days (B2B) are standard.
  Healthy benchmark: 25–35% of signups; below 20% signals severe onboarding
  friction. Validates the 7/14/30-day activation windows and the choice of
  activation as the launch-phase North Star.
  [Activation metrics: how to find, measure, and improve yours (Appcues)](https://www.appcues.com/blog/product-activation-metric),
  [Activation Rate: How to Define, Measure, and Improve It (ProdPad)](https://www.prodpad.com/glossary/activation-rate/)

- **CAC payback and cross-sell spend** — formula: CAC ÷ (net new MRR ×
  gross margin), healthy range 5–12 months. Upsell/cross-sell spend is
  explicitly *not* part of traditional CAC and should be tracked separately
  — this directly supports the paid-vs-organic CAC split in Section 6.
  [CAC Payback Period: How to Calculate and Reduce It (Userpilot)](https://userpilot.com/blog/cac-payback/),
  [CAC Payback Period (Chargebee)](https://www.chargebee.com/resources/glossaries/cac-payback-period/)

- **Physical fulfillment SLA and churn** — subscription box operators
  target ≥98% on-time delivery; below 95% signals a structural problem.
  28% of subscription box cancellations are driven by poor delivery
  experience, and nearly half of all cancellations happen within the first
  90 days. Supports treating kit delivery SLA as the top operational risk
  and the 0–120 day launch window framing.
  [Subscription Box Fulfillment (Swell)](https://www.swell.is/content/subscription-box-fulfillment),
  [Subscription Shipping Delays: Fix Shipping Churn Fast (Blustream)](https://blustream.ai/blog/subscription-shipping-delays-fix-shipping-churn-fast)

- **Why LTV:CAC, NRR, and churn are excluded at launch** — NRR is only
  considered reliable after 12–18 months of consistent customer data; LTV is
  speculative pre-scale because ICP, pricing, and retention are still
  unfixed; chasing churn too early is a documented early-stage mistake.
  Supports the explicit out-of-scope decisions in Sections 2 and 6.
  [LTV:CAC is a misleading metric to measure performance — here's what to
  track instead (Stage 2 Capital)](https://www.stage2.capital/blog/ltvcac-is-a-misleading-metric-to-measure-performance-heres-what-to-track-instead)
