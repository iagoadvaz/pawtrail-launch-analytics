# PawTrail — Scope: closing the gaps against subscription-analytics references

> **What this document is.** A **scope specification**, not an implementation
> plan. It is the input to the `superpowers:writing-plans` skill, which produces
> the actual execution plan. It describes *what must be true at the end*, with
> acceptance criteria, and deliberately avoids prescribing steps.
>
> **The phases are independently selectable.** When feeding this to the skill,
> choose the slice: Phase 1 is coherent and shippable on its own; Phase 2 is
> optional and its sub-items can be taken individually; Phase 3 applies to any
> slice.

---

## 1. Context and diagnosis

PawTrail Launch Analytics (branch `worktree-implement-pawtrail-launch`) is a
portfolio case study for a Senior Data Analyst role: it simulates days 0–120 of
the launch of a monthly subscription add-on — a physical pet-care kit plus a
care-tracking app — sold on top of an existing Premium plan. It currently ships
7 seeds → 20 dbt models → 33 MetricFlow metrics → 11 CSVs. The Tableau workbook
was never published.

Compared against four industry references, the diagnosis is singular:

> **The project measures acquisition and onboarding very well, and does not
> measure the subscription.**
> All four sources agree that the core of subscription analytics is what happens
> at the **second charge**. PawTrail has none: no renewal, no cancellation, no
> pause or skip, no payment, no second kit.

The direct consequence: `incremental_mrr`, `arpa` and `cac_payback_months` are
forecasts presented as measurements — payback "in months" is arithmetically
undefined without evidence that month-2 revenue exists.

**A falsifiable claim already in the repository.** `METRICS.md:265` states *"Every
metric computable from the existing generator output is already implemented
above."* This is false: at least 12 relevant metrics are computable from the
current seeds and do not exist. Fixing that is the highest return per unit of
effort in the entire scope, and it is all of Phase 1.

### How the sources were weighted

| Source | Weight | What it uniquely contributes |
|---|---|---|
| Shopify — *Subscription analytics* | **highest** | The three jobs of analytics (retain / find revenue drivers / forecast revenue); CLV:CAC as the paramount relationship; cancellations **and pauses** as volume; first-four-week referrals as a leading predictor; the demand that quantitative metrics be blended with qualitative signal |
| Crystallize — *Mastering Subscription Analytics* | high | Names PawTrail's business model explicitly — *replenishment → renewal, **skip**, inventory*; numeric benchmarks; organise by decision, not by list; the vanity-metric test |
| Sticky.io — *Top 20* | medium | The payment and billing block (rebill, approval, dunning, refunds, fraud) — 8 of the 20 |
| Synthesis Systems | supporting | The e-commerce vs. subscription-commerce framing; expansion revenue |

No metric entered this scope because it appeared on a list. Each entered because
it changes a decision.

---

## 2. Phase 1 — Computable from the current seeds

**Nothing here touches the generator.** This is the minimum coherent slice, and
it is what makes `METRICS.md:265` true again.

### 1.1 Billing-cycle clock

**Requirement.** A derived notion of renewal schedule and cycle index per
account, obtained from `pawtrail_signup_date` alone: the due date of cycle *n*,
how many cycles have already come due as of the observation date, and a
partition of the base into "has faced at least one renewal" and "has not".
Available as a segmentation axis for the existing metrics.

**Non-negotiable naming constraint.** Nothing may be called `rebill_rate`,
`renewal_revenue` or `retained_mrr`. The artefact measures **exposure** to
renewal — the opportunity to charge — never the charge itself. Naming it wrong
makes the dashboard present modelled scheduling as observed behaviour, which is
the gravest failure available in this project.

**Acceptance.** `pct_base_never_rebilled` published as a number; no account
carries a cycle whose due date exceeds the observation date; the observation
date is the same one already used in `int_activation_funnel`, not a second
definition.

**Why it matters.** It converts "churn is out of scope because we only have 120
days" from a prose caveat into a computed fact. Measuring the limits of your own
data is the strongest seniority signal a synthetic case study can give.

### 1.2 The breakeven-cycle bridge

**Requirement.** Two conjoined corrections.

*(a) The box recurs.* Contribution margin is currently computed **once**,
assuming a single shipment. In a physical-kit subscription, COGS and shipping
are incurred every cycle. A per-cycle margin must exist, under a **name distinct**
from the first-cycle metric, so that nobody confuses the two.

*(b) The threshold.* `breakeven_cycles` = allocated CAC ÷ per-cycle margin,
rounded up; null — not zero, not infinity — when the per-cycle margin is ≤ 0.
Accompanied by the total cost to recover (CAC plus COGS and shipping accumulated
up to breakeven) and a marker for whether breakeven falls inside the horizon the
120-day window actually observed.

**Acceptance.** A prior check that price − COGS − shipping > 0 across all three
tiers; total cost to recover always exceeds bare CAC (if it does not, the join
dropped pricing or delivery rows — the *green build, wrong numbers* failure mode
dbt produces); the recurrence assumption read from a single declared source,
never hardcoded.

**Why it matters.** It delivers what Shopify calls the paramount relationship
(CLV:CAC) **with no retention data at all**, converting "LTV is out of scope"
from an omission into a stated threshold. See §5.2 for why this is the correct
substitute and not a consolation prize.

### 1.3 Fully loaded cost and effective CAC

**Requirement.** Account for the COGS and shipping spent on accounts that never
activated and on lost kits — today that cost appears nowhere. Expose an effective
CAC that carries this waste, and the percentage difference against nominal CAC.

**Acceptance.** The waste reconciles with the counts of lost kits and of mature
non-activated accounts **taken as disjoint sets**; the difference is reported per
channel, not only in aggregate.

**The two sets overlap completely and must be made disjoint before summing.** No
lost-kit account is ever activated, so every lost kit is also a non-activated
account: adding the two counts double-counts the overlap (74 accounts in the
current seeds). Attribute each account to exactly one waste reason, `kit_lost`
taking precedence, and add a test asserting no account appears twice.

**Why it matters.** The 8% lost-kit problem in OH stops being a rate and becomes
dollars — and it reveals that the seemingly cheap channel is the one that suffers
most.

### 1.4 A censoring register, and distributions instead of means

**Requirement.** (a) Publish, per metric, how many accounts are excluded for
immaturity and what share of the cohort that is. (b) Replace the mean reading of
time-to-first-login with a distribution that accounts for the censored tail
separately.

**Acceptance.** Every rate card on the dashboard shows its denominator and its
exclusion beside the number.

**Why it matters.** Maturity gating exists in the code and is invisible in the
output: the reader compares incomparable denominators without knowing it. And the
mean time-to-first-login **improves as the product gets worse**, because the 15%
who never log in drop out of it.

### 1.5 Cross-cuts the seeds already allow

Four readings that require zero new data and do not exist today:

- **Quality-adjusted CAC** — cross channel against risk/activation. Bad accounts
  are cheap accounts; today you can drive blended CAC down by buying exactly the
  people who never log in.
- **Saturation curve** — penetration against remaining eligible base per state, to
  separate deceleration from demand exhaustion from deceleration from execution
  failure. This is the classic launch-window misdiagnosis.
- **Portfolio concentration** — how much of the margin depends on one state, one
  channel, one tier.
- **MRR and CAC on the same timeline** — today they are adjacent tiles;
  Crystallize treats divergence between the two curves as one of the three most
  common mistakes.

### 1.6 Benchmark reference lines

**Requirement.** Crystallize's targets present on the dashboard: activation >70%,
MRR +5–15%/month, LTV:CAC ~3:1 (substituted — see §5.2), churn <5%/month declared
as a target that cannot be measured.

**Why it matters.** `activation_rate_30d` sits at **71.1%** over the mature
cohort — just above the 70% benchmark — and nobody marks it today. Only
`attach_rate` has a target.

**The apparent downward crossing is a censoring artefact, not a decline.** Every
fully-mature week runs 0.70–0.75; the weekly range only reaches 60.3% in the week
of 2026-03-30, which is 76% mature, and the final four weeks have no mature
accounts at all. A benchmark card must suppress or hatch weeks below full
maturity, or it will report censoring as a performance drop — in the phase whose
whole thesis is making censoring visible.

### 1.7 Vanity-metric audit

**Requirement.** Each of the **10 declared metrics that never reach a CSV or a
dashboard** receives an explicit decision: it earns a row in the decision-contract
table (§4 below) or it leaves the semantic layer.

They are: `wow_subscription_growth`, `eligible_premium_accounts`, `channel_spend`,
`contribution_margin_per_subscription`, `task_completion_rate`,
`task_engagement_rate`, `zero_digital_access_accounts`, `zero_task_accounts`,
`avg_delivery_delay_days`, `kit_late_rate`.

**The criterion, from Crystallize.** *If the number does not help you decide the
next step, it belongs in a campaign report, not the core KPI set.*

### 1.8 The risk queue: healthy pruning vs. operational damage

**Requirement.** Replace the flat risk-driver enum with a classification into
self-selected damage (never logged in, short tenure, badly matched tier, no
delivery defect — **do not remediate**), system-inflicted damage (lost kit, late
delivery, no digital access — **do remediate**) and ambiguous, ordered by
recoverable revenue.

**Acceptance.** Falsification tests: accounts classified as self-selected have no
delivery defect, and those classified as system-inflicted are not concentrated in
short tenure. Without those tests, the classification may simply be re-encoding
the same self-selection it claims to separate.

**Why it matters.** The 944 at-risk accounts are an unworkable list today.

---

## 3. Phase 2 — Generator extensions (optional, independent sub-items)

Ordered by combined weight across the sources. Each row is a new event in the
generator plus the models and metrics it unlocks.

| # | What to generate | Unlocks | Source |
|---|---|---|---|
| 2.1 | Cancellation, **pause** and **skip**, with date and reason | Day-0 cancellation; cancellations and pauses **as volume**; skip rate; churn; retention | Shopify + Crystallize (*skip* is a named metric of the replenishment model, which is exactly PawTrail) |
| 2.2 | Second and third kit + renewal charge | **Rebill rate (cycle 0→1)**; GRR; ARR; MRR movement | Sticky.io #6 + all |
| 2.3 | Payment transactions: approved, declined, retried, refunded | Approval rate; natural attempt ratio; recovered revenue (dunning); refunded revenue | Sticky.io (8 of 20) |
| 2.4 | Returns, refused deliveries, address failures — a class distinct from "lost kit" | Return rate; shipped % | Sticky.io + Shopify (GMV net of shipping) |
| 2.5 | Referrals in the first four weeks | Referral rate | Shopify — **the leading predictor of retention** |
| 2.6 | Support contacts with reason codes | Volume and top reasons; churn root cause | Shopify + Crystallize (mistake #2) |
| 2.7 | **`pet_tier` change** (upgrade/downgrade) | Expansion MRR; NRR; upsell/cross-sell | Crystallize + Synthesis Systems |

### What Phase 2 does **not** solve

Two points that generating events alone does not resolve, and which must appear
in the implementation plan as constraints:

- **NRR requires item 2.7.** Items 2.1–2.3 produce contraction and churn, never
  expansion — none of them moves an account between tiers. Without 2.7, NRR is
  capped at ≤100% by construction: a number structurally incapable of exceeding
  100% is misleading, not incomplete. Worse than absent.
- **LTV and LTV:CAC do not become measurements in any slice.** Full justification
  in §5.2.

---

## 4. Phase 3 — Decision layer and delivery

Applies to any slice of the preceding phases.

### 3.1 A decision contract per metric
Every metric gets a threshold that triggers an action, the action itself, and an
owner. The attach rate's 15% target generalised to all of them. Crystallize calls
for automated alerts on MRR drops, payment failures and LTV changes.
**Why.** 33 correct metrics with no stated consequence are indistinguishable from
a data dictionary. Without thresholds there is no falsifiability — the project can
never be shown to have been right or wrong about anything.

### 3.2 Reorganise the dashboard by decision, not by data domain
The five current categories are by domain (*Launch pulse / Activation / Kit ops /
Acquisition efficiency / CS queue*). Crystallize proposes four questions: **are we
growing? do customers stay? are customers valuable? are we acquiring
efficiently?**

| Band | Cards |
|---|---|
| Benchmark strip | attach vs. target · activation vs. 70% · LTV:CAC substituted by `breakeven_cycles` · churn declared unobservable |
| **1 — Are we growing?** | cumulative attach with target line · new subscriptions per week · saturation curve · portfolio concentration |
| **2 — Do customers stay?** | cycle exposure + `pct_base_never_rebilled` (the only card with data) · 5 void cards |
| **3 — Are customers valuable?** | `breakeven_cycles` by channel · corrected per-cycle margin · activation against benchmark · censoring register |
| **4 — Acquiring efficiently?** | nominal vs. effective CAC · fulfillment waste · SLA by state · damage split |
| Decision layer | threshold / action / owner / status table |

**The second question is precisely the one the project cannot answer.**
Reorganising makes the gap visible instead of hidden behind a convenient
taxonomy — and that is the thesis of the redesign, not a side effect.

**The void convention — a design decision, not an aesthetic one.** Unmeasurable
cards are rendered hatched and declare three things: what they are blocked on, why
the metric carries weight (citing the source), and a **phase badge** naming what
unblocks them and in what status they arrive (`PHASE 2.2 → MEASURED`;
`PHASE 2.1 + 2.2 → GRR MEASURED · NRR PENDING`). The header carries a stamp of the
state depicted, so the void reads as neither permanent nor careless.

### 3.3 Label revenue recognition
MRR and contribution margin come from a price list, not from a payment event.
They are modelled entitlements. This is a disclosure line in the dictionary and on
the dashboard, not more SQL.

### 3.4 Ship the visual deliverable
`dashboard/README.md:3` says "Pending"; the conformance review flags F1 (HIGH) for
the workbook that was never delivered. The case study's final deliverable does not
exist.

---

## 5. Constraints and non-goals

### 5.1 Discarded as over-engineering or circular

- **Pricing the cancellation option, a forward curve with a discount rate, hurdle
  rate / cost of capital.** Excessive financialisation for a portfolio piece; and
  the forward curve requires precisely the retention assumption declared
  unavailable — it is circular.
- **A versioned metric-definition registry.** Git already does this for dbt SQL.
- **A query-refusal layer** (blocking slices that are too thin). Over-engineering
  for 3,000 rows.
- **Injecting a "late kit reduces engagement" effect into the generator and then
  discovering it.** A tautology dressed as a discovery. The current generator
  defines engagement as a function of time-to-first-login alone; lateness does not
  affect tasks. The honest path is the **rigorously executed null result**: a
  comparison stratified by login-timing band × signup week, a cell-size audit, and
  the stated conclusion — *the OH problem is a delivery-cost story, not a retention
  story*. If the effect scenario is generated, it must sit behind a flag, as a
  separate and labelled scenario.

### 5.2 Why LTV:CAC does not become a measurement — and why `breakeven_cycles` replaces it

This is the justification for the scope's most counter-intuitive decision, given
that all four sources rank LTV:CAC at the top.

**(a) The number is dominated by the unobserved tail.** LTV = per-cycle margin ×
expected lifetime, and lifetime is an integral of the survival curve. Across 120
days you observe at most 4 cycles, and only for the oldest accounts; the median
account has **1**. Using the $14.29 per-cycle margin and the $17.30 loaded CAC
(the measured values are $14.27 and ~$16.5 — the table below was recomputed and
verified correct, and neither substitution changes any conclusion):

| Steady-state monthly churn | Mean lifetime | LTV | LTV:CAC | **% of LTV after cycle 4** |
|---|---|---|---|---|
| 3% | 33.3 cycles | $476 | 27.5:1 | **88.5%** |
| 5% | 20.0 | $286 | 16.5:1 | **81.5%** |
| 8% | 12.5 | $179 | 10.3:1 | **71.6%** |
| 15% | 6.7 | $95 | 5.5:1 | **52.2%** |

Even in the most pessimistic scenario, 72% of LTV occurs outside the window; in
the optimistic one, 89%. The number would be 80–90% assumption. And all four
scenarios clear the 3:1 benchmark comfortably — the metric does not discriminate,
the data admit a 5× spread, and every one of them leads to the same decision. It
adds false precision, not information.

**(b) The shape of the curve cannot be inferred from 3 points.** Subscription
retention is not memoryless: the hazard declines and survivors get stickier.
Whether the curve is exponential, Weibull or power-law changes LTV by multiples,
and that shape reveals itself in the middle of the curve — the early points are
precisely the region where every family looks alike. Add that the window is a
**launch**: early adopters are the most engaged segment of the base (the generator
models this — tenure decays with signup day), so these cohorts' retention does not
generalise.

**(c) It is a ratio of a measurement to a projection.** CAC is an observed fact.
LTV is extrapolation. The ratio is a projection, and a single number hides which
half is soft — the same problem as §3.3.

**Necessary precision:** LTV **does become a number** — it can be published with a
stated assumption and a sensitivity band, and that is legitimate analysis. What it
does not become is a **measurement**.

**The substitute.** `breakeven_cycles` = CAC ÷ per-cycle margin. Both inputs are
observed facts; zero survival assumptions. It answers the same decision question —
*is this acquisition sane?* — with a falsifiable statement: *"this account must
survive N cycles"*. And it builds an honest ladder:

1. **Phase 1:** how many cycles the account must survive → *measured*
2. **Phase 2:** what share actually reached cycle N → *measured* (a retention
   checkpoint, not a lifetime)
3. **Never:** what happens at cycle 30 → requires the tail

---

## 6. Global acceptance criteria

1. `METRICS.md:265` stops being false — either because the computable metrics were
   implemented, or because the sentence was corrected with the list of what is
   missing and why.
2. No new artefact names as observed anything that is modelled (§1.1, §3.3).
3. Every published rate shows its denominator and its immaturity exclusion.
4. Every dashboard metric has a row in the decision contract, or has left the
   semantic layer.
5. `dbt build` green at every increment — current baseline PASS=123 (7 seeds,
   20 models, 96 tests, 0 errors); `pytest` baseline 22 passed.
6. `mf validate-configs` passing is **not** sufficient acceptance: every new metric
   needs an `mf query` at **the grain the dashboard actually uses**.
7. CSVs regenerated with a diff against the current ones — every number change
   explainable by a declared definition change.

### Local skills to invoke during execution

`cohort-metric-definition` (before any windowed-rate SQL), `dbt-silent-failure-review`
(new joins), `metricflow-semantic-layer` (new metrics), `plan-consistency-sweep`
(hardcoded counts in METRICS.md).

### Reference files

Under `/home/iagoadvaz/projects/pawtrail-launch-analytics/.claude/worktrees/implement-pawtrail-launch/`:
`pawtrail_dbt/models/intermediate/int_activation_funnel.sql` (the single source of
activation logic and of the observation date) · `pawtrail_dbt/models/marts/fct_weekly_channel_economics.sql`
(allocated CAC) · `pawtrail_dbt/models/marts/fct_at_risk_accounts.sql` ·
`_metrics.yml` and `_semantic_models.yml` · `dbt_project.yml` (the established
pattern of centralising thresholds as vars) · `METRICS.md` · `generator/` (Phase 2
only).

---

## Appendix A — Expected magnitudes

These are **measured** values, queried from the built warehouse on 2026-08-14,
not hand-derived estimates. They exist to catch order-of-magnitude errors when
the real models run. The hand-derived figures this appendix originally carried
were corrected against the warehouse after the metric-correctness review
(`docs/superpowers/reviews/2026-08-14-metric-correctness-review.md`); the
"originally stated" column is kept so an implementer reading an older branch can
see which numbers moved and why.

| New metric | Expected | Originally stated | Derivation |
|---|---|---|---|
| `pct_base_never_rebilled` | **11.3% (339 of 3,000)** | 11.9% (357) | accounts whose first renewal has not come due |
| Cycle exposure | **339 / 1,256 / 1,099 / 306** | 357 / 1,143 / 1,143 / 357 | `max(cycle_index)` per account off the billing spine. The original symmetric shape is not what a saturating logistic produces — the distribution peaks in the middle |
| Per-cycle margin | $9.49 / $15.49 / $21.49; weighted **$14.27** | weighted $14.29 | pricing × actual tier mix 39.8/40.7/19.5 |
| `breakeven_cycles` | self_serve **1**; sales_assisted **2** | unchanged | `ceil(CAC ÷ per-cycle margin)` |
| Median observable horizon | **1 cycle** | ~2 cycles | 339 + 1,256 > 1,500, so the median account sits in cohort 1 |
| Nominal CAC | self_serve **$7.14** · sales_assisted **$26.55** · blended **$12.96** | $7.20 · $27.40 · $13.26 | spend ÷ new subscriptions. **Requires the F1 fix** — the mart currently drops 7% of spend, which reads as $6.56 / $24.87 / $12.05 |
| Effective CAC | ~$11.1 (+55.4%) · ~$30.1 (+13.4%) · blended ~**$16.5 (+29.4%)** | $11.24 (+56%) · $31.44 (+15%) · $17.30 (+30.5%) | (spend + waste) ÷ new subscriptions. Uplift ratios were confirmed correct |
| Fulfillment waste | **$10,635.50** — 695 never-activated **excluding** lost kits, plus 84 lost kits, disjoint | $12,124 as $11,220 + $904 | average (COGS + shipping) of $13.70. **The original decomposition double-counted:** no lost-kit account is ever activated, so the lost set sits entirely inside the non-activated set |
| Damage split | system-inflicted 448 · **self-selected and ambiguous pending recalibration** | 448 · 360 · 136 | the 180-day tenure cut yields **4 accounts base-wide**, so `self_selected` comes out empty — the threshold must be recalibrated against the observed distribution before this row means anything |
| Recoverable revenue | **$12,455.52** (system-inflicted only) | $12,540 | 448 × $27.96 measured ARPA |
| Censoring register | 30d: **339 (11.3%)** · 14d: **97 (3.2%)** · SLA: **63 (2.1%)** · 7d: **40 (1.3%)** | 357 · 238 · 119 · 83 | accounts below the window. **The original 14-day figure used a 20-day window** (357 × 20/30); the others were linear interpolations of an already-wrong base |
| Margin concentration | **CA 50.9%; top 3 76.8%** | CA 44.9%; top 3 68.7% | share of contribution margin. **The original 44.9% was CA's share of the eligible Premium base** (6,737/15,000), a different quantity |

**The most important signal in this appendix:** self-serve's effective CAC rises
55.4% while sales-assisted's rises 13.4%. If the implementation produces the
inverse pattern, the waste join is probably attributing kits to the wrong channel —
self-serve has low CAC and high volume, so it absorbs more waste per acquired
account. This signal was verified correct against the warehouse.

**Do not treat a mismatch against the "originally stated" column as a defect.**
Those figures are superseded.

---

## Appendix B — Visual mock

The target state at the end of Phase 1, with the four-band structure, the void
treatment and the phase badges:
**https://claude.ai/code/artifact/b0d1627f-ca02-438d-bde1-56a00554c292**

Visual constraints to inherit: categorical palette and ordinal ramp validated in
light and dark (lightness band, chroma floor, CVD separation, normal-vision floor,
contrast); at most two series per chart; a single-hue ramp for ordinal scales;
status colours reserved and always paired with an icon and a label; every
visualisation with a table equivalent.

The mock's numbers are illustrative and must not be copied into any code artefact.
