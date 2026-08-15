# PR #1 — Plan-Conformance Review

**Target:** `worktree-implement-pawtrail-launch` → `master` (PR #1)
**Plan:** `docs/superpowers/plans/2026-08-12-pawtrail-launch-analytics.md`, **as it exists on the PR branch** (4,224 lines at `7d0b1b4`), not master's 4,027-line copy.
**Scope:** all non-`*.csv` files in `git diff master...worktree-implement-pawtrail-launch`.
**Date:** 2026-08-14

---

## Verdict

**CONFORMS, with one material omission and three documentation/definition deviations.**

The implementation is an unusually faithful execution of the plan. Every generator
module, every staging model, every intermediate/mart model, every singular test, and
both semantic-layer YAML files were compared block-by-block against the PR branch's
plan text:

| Artifact class | Result |
|---|---|
| `generator/*.py` + tests (5 modules, 4 test files) | byte-identical to plan, except two *comment-only* edits in `generate_activity.py` and `build_seeds.py` that correct a calibration figure |
| `data/olist_reference/*` | byte-identical |
| `pawtrail_dbt/models/**/*.sql` (20 models) | byte-identical, except two files (see D1, and a plan **syntax error** the PR correctly fixed) |
| `pawtrail_dbt/tests/*.sql` (9 singular tests) | all 9 present, byte-identical |
| `_semantic_models.yml` (8 semantic models) | byte-identical to the plan block |
| `_metrics.yml` (33 metrics) | byte-identical to the plan block |
| Schema YAML (5 files) | superset of plan — every plan test present, plus the relationships tests the plan deferred to later tasks; all diffs are the dbt-1.11 `arguments:` nesting requirement |
| `dbt_project.yml` vars | all 7 vars, all values identical to plan |
| `dashboard/control_*.csv` | all 10 exports present, all non-empty, all reproducible |
| `METRICS.md` | all 33 metrics documented, count claim ("33 metrics") accurate |
| `README.md`, `NARRATIVE.md` | conform to plan structure |

**Verification run during this review:**

- `pytest` → **22 passed**
- `dbt build --profiles-dir .` → **PASS=123, ERROR=0** (7 seeds, 20 models, 96 tests)
- Rebuilt DuckDB reproduces the committed `control_*.csv` files exactly (`git status` clean
  after a full rebuild) — Task 20's reproducibility claim holds.

The PR also **modifies the plan itself (+260/−63)**, and every one of those edits is a
correction discovered during implementation and honestly back-ported (MetricFlow
entity-qualified group-by names, `create_metric: true`, the time-spine model, `python -m`
invocation, the corrected acceptance-criteria figures). This is not goalpost-moving.
The one exception is F1 below, where the plan was *not* updated to record a deferral.

Nothing about `mf query --group-by` identifiers is stale: the PR's plan and the PR's
export commands both use `account__state`, `channel_week_row__signup_week`,
`weekly_attach_row__state`, and `pitch__state`, and all ten exports return rows.

---

## Findings

### F1 — Task 16's deliverables are not shipped; the plan was not updated to say so
**Severity: HIGH (conformance)** · `dashboard/README.md:3`, `README.md:38`

The plan's stated **Goal** names three deliverables: a dbt project, a MetricFlow semantic
layer, **and "a published Tableau Public dashboard."** Task 16's Files list creates
`dashboard/pawtrail_launch.twbx`; Steps 1–3 build and publish the workbook; Task 20 Step 5
diffs the published workbook against `control_kit_sla_by_state.csv`.

None of that exists. There is no `.twbx` in the branch, no published URL, and Task 20
Step 5 cannot have been executed.

`dashboard/README.md` and `README.md` disclose this honestly ("Pending", "not yet
published"), which is the right call. What makes it a conformance finding rather than a
documented scope cut is that **the PR modified the plan in nine other places to record
in-flight deviations, but left Tasks 16/17/19/20 asserting a published dashboard.** The
plan and the shipped repo now disagree about a top-line deliverable, and a reader
executing the plan from scratch would look for a workbook that was never made.

---

### F2 — `cost_per_activated_account` keeps the naive denominator; the plan's own comment specified the corrected one
**Severity: MEDIUM** · `pawtrail_dbt/models/marts/fct_weekly_channel_economics.sql:69`

This is the only substantive SQL deviation in the PR, and it goes the *wrong* way.

The plan (Task 13, Step 3) ships SQL that divides the full week's spend by
`activated_subscriptions` — a count restricted to accounts that are **both activated and
30-day mature** — while its adjacent comment specifies a different, correct computation:

> "Denominator is the activated share of the *mature* cohort applied to all acquired
> accounts, so a week of recent signups does not report an artificially catastrophic cost
> per activated account."

The plan's SQL and the plan's comment disagree. The PR resolved that conflict by keeping
the buggy SQL and **rewriting the comment** to declare the artifact intentional
("treat the most recent 1-2 weeks as still settling"). That is a deviation from the
plan's stated intent, not an inherited plan defect.

**Measured impact on the shipped data (`pawtrail.duckdb`, `main` schema):**

- `cost_per_activated_account` is **NULL for 8 of 34 channel-week rows** — every row from
  `2026-04-06` onward, i.e. the 4 most recent of 17 weeks, in both channels. Those weeks
  have `mature_subscriptions = 0` while spend is fully counted, so `nullif` blanks them.
- The newest *partially* mature week, `2026-03-30` (136 of 180 signups mature), is
  inflated:

  | channel | shipped CPA | maturity-corrected | overstatement |
  |---|---|---|---|
  | `self_serve` | $16.60 | $13.07 | +27% |
  | `sales_assisted` | $55.55 | $37.73 | +47% |

The same defect propagates into the `cost_per_activated_account` **metric**
(`_metrics.yml`, `channel_spend_usd ÷ channel_activated_subscriptions`) and therefore into
`dashboard/control_cac_by_channel.csv`, which is the data source for the plan's Task 16
"Acquisition efficiency" view.

Note that `mature_subscriptions` — the exact input the plan's comment calls for — **is
already computed** in this model and listed in the plan's Interfaces line, but is exposed
to no semantic-model measure and used in no denominator anywhere in the project. The fix
is `spend_usd / nullif(new_subscriptions * (activated_subscriptions * 1.0 /
nullif(mature_subscriptions, 0)), 0)`.

---

### F3 — NARRATIVE.md reads the F2 artifact as a stable business result
**Severity: MEDIUM** · `NARRATIVE.md:36`

> "in the latest mature cohort, cost per activated account was $16.60 for self-serve versus
> $55.55 for sales-assisted (3.3x), **consistent with every prior week**."

The two dollar figures are correctly transcribed from `control_cac_by_channel.csv`, but the
"consistent with every prior week" claim is contradicted by the same file. The immediately
prior week (`2026-03-23`) reads **$7.11 / $27.10**. The levels roughly double week over
week, entirely because of the maturity artifact in F2 — not because acquisition
efficiency changed. Across all fully-mature weeks the self-serve/sales-assisted ratio
ranges from 2.7x to 17.0x, so "3.3x, consistent with every prior week" is not supported by
the shipped numbers either.

The memo then uses that reading to conclude "channel spend discipline is working and should
continue unchanged" — a recommendation resting on a censoring artifact.

(The rest of NARRATIVE.md was checked number-by-number against the control CSVs and the
warehouse and is accurate: 51.4% OH on-time vs. an 86.2% eleven-state mean, the 34.8-point
gap, NJ as next-worst at 82.6%, 944 at-risk accounts split 496/352/96, the 69.1–75.2%
eight-week activation band dropping to 60.3%, OH's 23.3% week-of-March-30 attach rate,
136 mature accounts in that cohort, and four weeks with no 30-day rate. All verified.)

---

### F4 — The launch attach-rate target is declared, justified by a promise, and then used nowhere a reader sees it
**Severity: MEDIUM** · `pawtrail_dbt/dbt_project.yml:43`

The var carries an explicit rationale for its own existence:

> "It lives here, not in a Tableau constant, so the target on the chart and the target
> quoted in NARRATIVE.md cannot disagree."

Neither consumer exists. `NARRATIVE.md` never mentions the 15% target or the word
"target" at all. No `control_*.csv` export carries `attach_rate_vs_target`, and no view in
`dashboard/README.md` references it. The metric is declared in `_metrics.yml:24` and
documented in `METRICS.md:40`, and it works — `mf query --metrics attach_rate_vs_target
--group-by weekly_attach_row__signup_week` returns a clean series ending at **1.33x**.

So spec §6's "Attach rate ... vs. launch target" is implemented in the semantic layer but
delivered to no reader, and the launch's single clearest piece of good news (attach
finished 33% above plan) is absent from the memo whose job is to state the verdict.

---

### F5 — `at_risk_account_rate` is tautological at the only grain the project queries it
**Severity: LOW (plan defect inherited by implementation)** · `dashboard/control_at_risk_by_driver.csv`

Plan Task 15 Step 4 and Task 20 Step 4 both query
`at_risk_account_rate --group-by account__risk_driver`. Because `risk_driver` *is* the
at-risk classification, the ratio is 1.0 for every non-healthy driver and 0.0 for
`healthy`, by construction. The shipped CSV shows exactly that:

```
digital_failure,1.0,496
physical_failure,1.0,352
healthy,0.0,0
both_legs_failed,1.0,96
```

The rate column carries zero information at this grain; only the count does. Task 20 Step
4's acceptance criterion ("the at-risk queue is split across drivers rather than
concentrated entirely in one bucket") is only meaningful against `at_risk_accounts`. The
rate is informative grouped by `metric_time__week` or `account__state`, neither of which
the plan exports. The implementation matches the plan exactly here — the defect is in the
plan's choice of group-by.

---

### F6 — Time-to-milestone measures carry no maturity gate, and the generator emits events past the declared cutoff
**Severity: LOW** · `pawtrail_dbt/models/marts/_semantic_models.yml:3175`

`int_activation_funnel.sql:16-19` defines `observation_date = max(pawtrail_signup_date)`
(2026-05-03) as the analysis cutoff — "in a scheduled pipeline this would be
`current_date`". But the generator applies no such cutoff: **36 `kit_delivered_date` values
and 25 `first_login_date` values fall after 2026-05-03.**

Every other measure in `_semantic_models.yml` is maturity-gated, but
`avg_days_to_first_login` and `avg_days_to_kit_delivery` are not. The final weeks of
`control_time_to_milestone.csv` are therefore computed partly on events the declared cutoff
says have not happened yet.

The volume is small (~1.2% of kits, ~0.8% of logins) and the direction is benign — the
figures are *unbiased*, whereas a real pipeline would be optimistically biased by seeing
only the fast movers. But it is the one place the project's otherwise rigorous
cohort-maturity discipline is not applied, and it is inconsistent with the "as of today"
framing the funnel model asserts and `assert_signup_never_after_observation_date.sql`
enforces in the other direction.

---

### F7 — `onboarding_gap` is enumerated as a live CS-queue category but is empty
**Severity: LOW (documented, but the docs still list it)** · `dashboard/README.md:20`

`fct_at_risk_accounts.sql:25-37` pre-emptively and correctly explains why this bucket is
expected to be rare-to-empty, and instructs future readers not to "fix" it. Confirmed:
**0 of 2,903 rows.** Not a bug.

The residual issue is downstream: plan Task 16 view 5 and the shipped `dashboard/README.md`
both enumerate `onboarding_gap` alongside the three drivers that do populate, so the CS-queue
view will render 3 of the 4 categories it advertises. A one-clause note in
`dashboard/README.md` ("`onboarding_gap` is a defined driver that this seed produces no
instances of") would close the gap between the model's own reasoning and the reader's.

---

### F8 — Two documents enumerate the maturity windows as "7/10/30", omitting the 14-day combined window
**Severity: LOW (plan text inherited)** · `NARRATIVE.md:58`, `dashboard/README.md:23`

Both say activation rates use "the full 7/10/30-day window". The project also ships
`activation_rate_14d`, backed by `is_mature_combined_14d = days_observed >= greatest(14, 10)`
— a fourth window, documented correctly in `METRICS.md:78` and exported in
`control_activation_rates.csv`. The plan's own Task 19 and Task 16 Step 4 text says
"7/10/30", so this is inherited, but the enumeration is incomplete against what shipped.

---

## Items excluded as already triaged

Confirmed present, not re-derived: average-of-ratios in `avg_cac_payback_months` /
`avg_contribution_margin` (`_semantic_models.yml:3339,3330`); the zero-task maturity-window
mismatch between `fct_at_risk_accounts.sql:20` (14d) and the `zero_task_accounts` measure
(30d); `zero_digital_access_accounts` coupling its 14-day flag to
`is_mature_combined_14d`; and `assert_risk_driver_is_exhaustive.sql` not asserting
driver-to-flag correspondence in the forward direction. All four are inherited verbatim
from the plan's own `_semantic_models.yml` / test blocks.
