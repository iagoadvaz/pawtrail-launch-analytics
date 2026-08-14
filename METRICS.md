# PawTrail Launch Analytics — Metrics Dictionary

This is a human-readable companion to the MetricFlow semantic layer defined in
`pawtrail_dbt/models/marts/_metrics.yml` (33 metrics) and
`pawtrail_dbt/models/marts/_semantic_models.yml` (8 semantic models). Every
metric below is queryable via `mf query --metrics <name>`.

Formulas use `÷` for `numerator / denominator` on `ratio` metrics, cite the
underlying measure for `simple` metrics, and spell out the expression for
`derived` metrics. "Source semantic model" is the semantic model that owns the
measure(s) behind the metric — the dbt model each one is built on is noted in
parentheses on first mention.

The metrics are organized into the five dashboard categories from Task 16
(spec §6's dashboard structure): Launch pulse, Activation, Kit operations,
Acquisition efficiency, Customer Success queue.

---

## 1. Launch pulse

Top-line adoption trend: how many accounts are attaching, how fast, against
what addressable base.

### weekly_new_subscriptions
- **Definition:** The count of new Premium-to-PawTrail subscriptions recorded in a given week.
- **Formula:** `simple` — measure `subscription_count` (count of `account_id`).
- **Source:** `subscriptions` (`fct_subscriptions`)

### eligible_premium_accounts
- **Definition:** The addressable base of existing Premium accounts eligible to attach to PawTrail, summed by state and week.
- **Formula:** `simple` — measure `eligible_premium_accounts` (sum of `eligible_premium_accounts`).
- **Source:** `weekly_attach` (`fct_weekly_attach`)

### attach_rate
- **Definition:** The share of the eligible Premium base that has attached to PawTrail to date.
- **Formula:** `ratio` — `cumulative_subscriptions ÷ eligible_premium_accounts`
- **Source:** `weekly_attach`

### attach_rate_vs_target
- **Definition:** Attach rate expressed as a fraction of the launch target, so 1.0 means the launch is exactly on plan and no separate reference line is needed on the dashboard.
- **Formula:** `derived` — `rate ÷ attach_rate_launch_target` (dbt var), where `rate` aliases the `attach_rate` metric.
- **Source:** `weekly_attach` (via `attach_rate`)

### wow_subscription_growth
- **Definition:** Week-over-week percentage change in new subscriptions — the shape of the adoption curve.
- **Formula:** `derived` — `(current_week − prior_week) ÷ nullif(prior_week, 0)`, where `current_week` and `prior_week` are the `weekly_new_subscriptions` metric evaluated at a one-week offset.
- **Source:** `subscriptions` (via `weekly_new_subscriptions`)

### cumulative_subscriptions_to_date
- **Definition:** Running total of PawTrail subscriptions attached to date.
- **Formula:** `simple` — measure `cumulative_subscriptions`.
- **Source:** `weekly_attach`

---

## 2. Activation

Whether newly attached accounts actually get set up and engaged: digital
login, kit SLA, combined activation, time-to-milestone, and task engagement,
plus early-warning zero-engagement counts.

### digital_activation_rate_7d
- **Definition:** The share of accounts with a full 7-day window that logged into the PawTrail app within 7 days of signup.
- **Formula:** `ratio` — `digitally_activated_accounts ÷ mature_accounts_7d`
- **Source:** `activation_events` (`fct_activation_events`)

### kit_sla_rate
- **Definition:** The share of accounts with a full SLA window whose physical kit was activated within the 10-day delivery SLA.
- **Formula:** `ratio` — `kit_activated_accounts ÷ mature_accounts_sla`
- **Source:** `activation_events`

### activation_rate_7d
- **Definition:** The share of accounts with a full 7-day combined window that activated on both the digital and physical (kit-SLA) legs within 7 days.
- **Formula:** `ratio` — `combined_activated_accounts_7d ÷ mature_accounts_combined_7d`
- **Source:** `activation_events`

### activation_rate_14d
- **Definition:** The share of accounts with a full 14-day combined window that activated on both legs within 14 days.
- **Formula:** `ratio` — `combined_activated_accounts_14d ÷ mature_accounts_combined_14d`
- **Source:** `activation_events`

### activation_rate_30d
- **Definition:** The launch's North Star: the share of accounts with a full 30-day window that activated on both the digital and physical legs within 30 days.
- **Formula:** `ratio` — `combined_activated_accounts_30d ÷ mature_accounts_30d`
- **Source:** `activation_events`

### mature_cohort_size_30d
- **Definition:** Count of accounts that have had the full 30-day window to activate — the denominator base behind the 30-day activation rate, shown alongside it so a reader can see how thin the most recent weeks' cohort is.
- **Formula:** `simple` — measure `mature_accounts_30d`.
- **Source:** `activation_events`

### avg_days_to_first_login
- **Definition:** Average number of days from signup to first digital login, among accounts that ever logged in.
- **Formula:** `simple` — measure `avg_days_to_first_login` (average of `days_to_first_login`; nulls for accounts that never logged in are skipped).
- **Source:** `activation_events`

### avg_days_to_kit_delivery
- **Definition:** Average number of days from signup to first kit delivered, among accounts whose kit arrived.
- **Formula:** `simple` — measure `avg_days_to_kit_delivery` (average of `days_to_kit_delivery`; nulls for undelivered kits are skipped).
- **Source:** `activation_events`

### conversion_lag_days
- **Definition:** Average number of days between an account becoming Premium and attaching to PawTrail.
- **Formula:** `simple` — measure `avg_conversion_lag_days` (average of `conversion_lag_days`).
- **Source:** `subscriptions`

### task_completion_rate
- **Definition:** The share of available first-cycle care-plan tasks that mature accounts actually completed — how much of the care plan got done.
- **Formula:** `ratio` — `tasks_completed ÷ tasks_available`
- **Source:** `activation_events`

### task_engagement_rate
- **Definition:** The share of mature accounts that completed at least one first-cycle care-plan task — how many people started at all, a different question from `task_completion_rate`.
- **Formula:** `ratio` — `task_engaged_accounts ÷ mature_accounts_30d`
- **Source:** `activation_events`

### zero_digital_access_accounts
- **Definition:** Count of mature (14-day combined-window) accounts that had zero digital access in the first 14 days — an early-warning failure count.
- **Formula:** `simple` — measure `zero_digital_access_accounts`.
- **Source:** `activation_events`

### zero_task_accounts
- **Definition:** Count of mature (30-day) accounts that completed zero first-cycle care-plan tasks.
- **Formula:** `simple` — measure `zero_task_accounts`.
- **Source:** `activation_events`

---

## 3. Kit operations

Physical fulfillment performance: on-time delivery, loss, and lateness.

### kit_on_time_delivery_rate
- **Definition:** Share of shipped kits delivered within the 10-day SLA.
- **Formula:** `ratio` — `kits_on_time ÷ kits_shipped`
- **Source:** `kit_deliveries` (`fct_kit_deliveries`)

### kit_lost_rate
- **Definition:** Share of shipped kits that were lost in transit and never arrived.
- **Formula:** `ratio` — `kits_lost ÷ kits_shipped`
- **Source:** `kit_deliveries`

### kit_late_rate
- **Definition:** Share of shipped kits that did arrive, but arrived late (i.e. missed the SLA without being lost).
- **Formula:** `ratio` — `kits_late ÷ kits_shipped`
- **Source:** `kit_deliveries`

### avg_delivery_delay_days
- **Definition:** Average number of days late, counted only among kits that actually arrived late — "when a kit is late, how late," not diluted by the on-time majority.
- **Formula:** `simple` — measure `avg_days_late`.
- **Source:** `kit_deliveries`

---

## 4. Acquisition efficiency

Cost and return per acquired/activated account, by channel, plus sales-assist
performance.

### win_rate
- **Definition:** Share of sales-assisted pitches that converted into a won subscription.
- **Formula:** `ratio` — `pitches_won ÷ pitches_total`
- **Source:** `sales_pitches` (`fct_sales_pitches`)

### cac_by_channel
- **Definition:** Customer acquisition cost per new subscription, by marketing/sales channel.
- **Formula:** `ratio` — `channel_spend_usd ÷ channel_new_subscriptions`
- **Source:** `weekly_channel_economics` (`fct_weekly_channel_economics`)

### cost_per_activated_account
- **Definition:** Acquisition cost per account that went on to actually activate, by channel — a quality-adjusted CAC that punishes channels that acquire accounts cheaply but don't activate them. The denominator is the activation rate observed among the week's *mature* accounts applied to every account the week acquired, not the raw activated-and-mature count: spend is booked for the whole cohort, so dividing it by only the accounts that have finished their 30-day window would put a complete numerator over a partial denominator and overstate cost in the most recent weeks. Null for weeks in which no account is mature yet, where the activation rate cannot be estimated at all.
- **Formula:** `ratio` — `channel_activation_measurable_spend_usd ÷ channel_estimated_activated_subscriptions`
- **Source:** `weekly_channel_economics`

### channel_spend
- **Definition:** Total marketing/sales spend, by channel and week.
- **Formula:** `simple` — measure `channel_spend_usd`.
- **Source:** `weekly_channel_economics`

### incremental_mrr
- **Definition:** Incremental monthly recurring revenue added by newly attached PawTrail subscriptions.
- **Formula:** `simple` — measure `mrr_added_usd`.
- **Source:** `weekly_channel_economics`

### arpa
- **Definition:** Average revenue per newly acquired account.
- **Formula:** `ratio` — `mrr_added_usd ÷ channel_new_subscriptions`
- **Source:** `weekly_channel_economics`

### contribution_margin_per_subscription
- **Definition:** Contribution margin generated per subscription — total margin over total subscriptions, so each week counts in proportion to the subscriptions it actually carried rather than equally.
- **Formula:** `ratio` — `channel_total_contribution_margin_usd ÷ channel_new_subscriptions`
- **Source:** `weekly_channel_economics`

### cac_payback_months
- **Definition:** Estimated number of months to recover customer acquisition cost out of contribution margin — total spend over total monthly contribution margin. Not the average of each week's own payback: the launch's first weeks carry a handful of subscriptions and payback figures in the tens of months, and weighting those equally with weeks carrying a hundred or more reports roughly four times the true figure.
- **Formula:** `ratio` — `channel_spend_usd ÷ channel_total_contribution_margin_usd`
- **Source:** `weekly_channel_economics`

---

## 5. Customer Success queue

Who Customer Success should call: the at-risk account count and rate.

### at_risk_account_rate
- **Definition:** Share of assessable accounts currently flagged at risk for the Customer Success team to intervene on.
- **Formula:** `ratio` — `at_risk_accounts_count ÷ assessable_accounts`
- **Source:** `at_risk_accounts` (`fct_at_risk_accounts`)

### at_risk_accounts
- **Definition:** Count of accounts currently flagged at risk — the size of the Customer Success outreach queue, typically read broken out by `risk_driver`.
- **Formula:** `simple` — measure `at_risk_accounts_count`.
- **Source:** `at_risk_accounts`

---

## Definitions that carry a judgement call

These are the three places where a defensible alternative definition exists
and was rejected for a specific reason — the places an interviewer is most
likely to probe.

**Cohort maturity.** Every activation denominator (`mature_accounts_7d`,
`mature_accounts_sla`, `mature_accounts_30d`, `mature_accounts_combined_7d`,
`mature_accounts_combined_14d`) counts only accounts that have had the *full*
activation window, not every account that has signed up so far. The
alternative — count everyone regardless of how recently they signed up — was
rejected because it reports recent signups as activation failures before they
have even had the chance to activate, which understates activation precisely
in the newest weeks: exactly the weeks a launch dashboard is read for.

**On-time vs. delivered.** Combined activation (`activation_rate_7d/14d/30d`)
and `kit_sla_rate` require the kit to hit the 10-day delivery SLA, not merely
to arrive at some point within 30 days. A kit that shows up on day 25 counts
as "delivered" but not as "on time," and the activation North Star is built
on the stricter, SLA-based definition rather than the looser "arrived
eventually" one.

**Semi-additivity of attach rate.** `cumulative_subscriptions` and
`eligible_premium_accounts` (both on `weekly_attach`) sum correctly across
regions within a single week, but not across weeks — summing across weeks
would double-count cumulative subscriptions and multiply the eligible base by
the number of weeks included. `attach_rate` is therefore valid grouped by
week, or by week and region together, but must never be grouped by region
alone.

---

## Future extensions

Every metric computable from the existing generator output is already
implemented above. The list below is the catalog of metrics from spec §6 that
are **not** implemented, each with the specific source data it would need —
this is exactly the set blocked on new synthetic data, not a generic "out of
scope."

| Not implemented | Blocked on |
|---|---|
| App sessions in first 2–4 weeks, repeat engagement rate, feature adoption | Session-level event stream; the generator emits a first-login date and a task count, not sessions |
| % accounts with at least 1 health/activity log in the first cycle | A health/activity log event. This is a different app surface from care-plan tasks, so `task_engagement_rate` is **not** a stand-in for it and must not be labelled as one |
| Attach rate by channel, by pet tier, and by Premium tenure band | An eligible Premium base attributed to those dimensions. `fct_premium_base` is per state only, and channel does not exist for accounts that never attached — see the segmentation note in spec §6 |
| Time to first completed care-plan task | A first-task timestamp; `care_tasks_completed_first_cycle` is a count with no date |
| % pet profiles with complete onboarding | An onboarding-completeness field on the account |
| Cancellation-before-first-cycle rate | Cancellation events; the launch window carries no churn signal by design |
| Support/call-center contact volume and top reasons | A support-contact stream with reason codes |
| Complaint/replacement rate in the first cycle | Complaint and replacement events |
| Cost per lead/pitch | Lead-stage events above the pitch; only pitch outcomes exist |
| Paid vs. organic CAC split | Spend-source tagging on `raw_marketing_spend` |
| CAC by state/region | Spend allocated by state; spend is generated per week × channel only |

Note that the first two rows are the ones an interviewer is most likely to
probe, because engagement depth is the natural follow-up to an activation
story. The honest answer is that measuring it needs event-level data the
launch simulation does not produce, not that it was judged unimportant.
