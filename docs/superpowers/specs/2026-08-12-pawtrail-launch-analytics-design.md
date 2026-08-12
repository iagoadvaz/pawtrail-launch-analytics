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
  *only* as a statistical scaffold — its empirical delivery-time distribution
  (estimated vs. actual delivery date) and state-level geographic distribution
  are resampled to generate realistic shipment timing/delay patterns and
  regional spread for PawTrail's kit deliveries. Olist's actual customer,
  order, or product identities are **not** reused as if they were PawTrail
  accounts — only the underlying statistical patterns are borrowed.
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
`dim_accounts` (state, pet tier, channel, Premium tenure before attach).

**Tests**: dbt schema tests (not_null, unique, relationships, accepted_values)
on all mart keys and categorical fields, plus singular tests for sanity bounds
(e.g., all rate metrics between 0 and 1, no negative delivery intervals).

## 6. Metrics catalog (semantic layer)

All metrics below are declared in the dbt Semantic Layer (MetricFlow) and are
the authoritative, single source of truth for every number shown on the
dashboard and in the narrative memo.

**Acquisition / conversion**
- Eligible Premium accounts (addressable universe)
- Cumulative PawTrail subscriptions (total and week-over-week)
- Attach rate (Premium → PawTrail) vs. launch target
- Attach rate by channel (self-serve vs. sales-assisted)
- Attach rate by segment (state, pet tier, Premium tenure before attach)
- Conversion lag (days between becoming Premium and attaching PawTrail)
- Week-over-week growth rate of new subscriptions (adoption curve shape)

**Activation** (the most critical metric in this phase)
- % accounts with app login within 7 days
- % accounts with first kit delivered within promised SLA
- Time from subscription to first digital access
- Time from subscription to first kit delivered
- Time from subscription to first completed care-plan task
- **Combined activation rate** at 7/14/30 days (digital + physical) — the
  phase's North Star metric
- Digital-only activation rate / physical-only activation rate (isolates
  which leg is failing)
- % pet profiles with complete onboarding

**Early engagement** (leading signal, not retention)
- % of first-cycle tasks/content marked complete
- Average app sessions in first 2–4 weeks
- % accounts with at least 1 health/activity log in the first cycle
- Repeat engagement rate within 30 days (2nd, 3rd session — habit-forming
  signal)
- Feature adoption (which app features are used first)

**Physical kit operations** (largest operational risk of the launch)
- First-kit on-time delivery rate (SLA %)
- Delay distribution (days late)
- Lost/damaged kit rate
- Complaint/replacement rate in the first cycle
- Delivery SLA by state/region (surfaces problem geographies)

**Early risk signals** (churn proxies — no churn data exists yet)
- Accounts with zero digital access in 14 days
- Accounts with delayed or missing first kit
- Accounts with zero completed tasks in the first cycle
- Composite at-risk queue, tagged by driver (digital failure vs. physical
  failure vs. onboarding gap)

**Business signals**
- Incremental revenue from attach (aggregate MRR added, even at small N)
- Cancellation-before-first-cycle rate (immediate regret signal, distinct
  from mature churn)
- Support/call-center contact volume and top reasons related to PawTrail

**Acquisition efficiency (CAC and related)**
- Attach CAC: marketing/sales spend allocated to the PawTrail campaign ÷ new
  subscriptions in the period
- CAC by channel (self-serve vs. sales-assisted)
- CAC by segment (state/region)
- Cost per activated account = CAC ÷ activation rate (more meaningful than
  raw CAC in launch phase, since an unactivated subscription is a weak signal)
- Estimated payback period (CAC ÷ monthly contribution margin per
  subscription, where contribution margin = price − kit COGS − shipping)
- ARPA (average revenue per account) for the add-on
- Contribution margin per subscription (basic unit economics)
- Cost per lead/pitch (sales-assisted channel, funnel stage above attach)
- Win rate for the sales-assisted channel (% of pitches that convert)
- Paid vs. organic CAC split (in-app cross-sell should be near-zero CAC;
  separating it from paid-campaign CAC is what should actually drive
  investment decisions)

**Segmentation** (applied across all metrics above)
State/region · pet tier/type · channel · Premium tenure before attach

**North Star for the launch phase**: Combined 30-day activation rate — % of
subscribing accounts with confirmed digital usage **and** an on-time first
kit delivery, within the first 30 days.

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
│   ├── raw_olist/            # subset of the real Olist dataset
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

- dbt schema tests on all mart models (not_null, unique, relationships,
  accepted_values).
- Singular dbt tests for metric sanity bounds (rates within [0, 1], no
  negative time intervals).
- Manual sanity check: the injected "problem" segment (Section 4) must be
  visibly identifiable in the dashboard and called out correctly in
  `NARRATIVE.md`, proving the metrics and dashboard actually surface a
  root-cause signal rather than just displaying numbers.
