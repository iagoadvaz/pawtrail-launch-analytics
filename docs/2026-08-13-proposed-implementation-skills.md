# Proposed Implementation Skills

Date: 2026-08-13
Status: Proposal — not yet implemented

## Purpose

A set of Claude Code skills to make implementing
`docs/superpowers/plans/2026-08-12-pawtrail-launch-analytics.md` faster and more
accurate.

These recommendations are derived from the failure classes the plan actually
exhibited across two review passes, not from generic dbt advice. Twelve distinct
defects were found and fixed in commits `4bd1336` (silent-failure bugs) and
`f2c9f18` (methodology and coverage gaps). They cluster into roughly five
repeatable patterns, listed below.

## Guiding principle

**Prefer skills that carry a runnable check over skills that carry a reminder.**

Nearly every defect in the two review passes was caught by *running* something —
a calibration simulation, a measure-vs-metric cross-reference, a YAML/Python
parse sweep. A prose checklist saying "verify your joins" gets skimmed. A script
that prints `cac: 0/18 non-null` does not.

There is a second reason these belong in skills rather than in a document: the
plan is designed to be executed by subagents
(`superpowers:subagent-driven-development`). A subagent implementing Task 13 will
not have the context of the review that found the week-boundary trap. Skills
scoped to trigger on "editing a dbt model" or "writing a semantic model" fire
automatically for whoever is doing the work, which is exactly what is needed to
survive that handoff.

---

## 1. `dbt-silent-failure-review`

**Scope:** project (`.claude/skills/`)
**Trigger:** after writing any dbt model, before commit.

The archetype is the CAC join: a `LEFT JOIN` that matched zero rows, nulled
three columns, and built green because the schema tests only covered columns
that could never be null.

**Encode as a script that:**
- Reports row count before and after every join, and non-null counts for each
  joined-in column. A `LEFT JOIN` that adds no rows but nulls columns is the
  dangerous case, and it is invisible in a normal `dbt build`.
- Asserts the declared grain is genuinely unique.
- Flags any aggregate applied over an already-aggregated column (cumulative
  sums, snapshot counts).
- Flags date joins where the two sides derive their boundary differently
  (e.g. `date_trunc('week', ...)` on one side, a generator-supplied week start
  on the other).
- Suggests a `not_null` test on any derived column that can only be null if a
  join failed.

**Would have caught:** the all-NULL CAC join, the two primary entities declared
on non-unique columns, the missing state × week spine.

---

## 2. `metricflow-semantic-layer`

**Scope:** project (`.claude/skills/`)
**Trigger:** editing `_semantic_models.yml` or `_metrics.yml`.

This area produced four independent failures, which makes it the densest
concentration of defects in the plan.

**Encode:**
- Entities must be *provably* unique, not "looks like a key". Verify with a
  uniqueness test before declaring an entity primary.
- Every semantic model with measures needs an `agg_time_dimension`, or
  `mf validate-configs` rejects it.
- Classify every measure as additive / semi-additive / non-additive, and record
  which groupings are valid. Semi-additive measures are the trap: they sum
  correctly along one dimension and silently mislead along another.
- Ratio metrics need numerator and denominator in the same semantic model, or a
  valid join path between them.
- `export DBT_PROFILES_DIR="$PWD"` before any `mf` command — `mf` has no
  `--profiles-dir` flag and falls back to `~/.dbt/profiles.yml`.
- Do not stop at `mf validate-configs`. Query each metric at **each grain the
  dashboard will actually use**. Validation passes on metrics that return
  nonsense when grouped.

**Would have caught:** `agg: max` returning one state's attach rate labelled as
the national trend, the three semantic models missing time dimensions, the
missing `DBT_PROFILES_DIR`.

---

## 3. `synthetic-data-calibration`

**Scope:** user level (general-purpose)
**Trigger:** writing or tuning a data generator.

This is where "plausible but wrong" originates, and every downstream layer
inherits it. A miscalibrated generator cannot be fixed in the semantic layer.

**Encode:**
- State what a borrowed real distribution *actually measures* before resampling
  it. Olist's `order_estimated_delivery_date` is padded by 10–12 days, so
  `actual - estimated` measures forecast conservatism, not shipping time.
- Print summary statistics and the resulting headline rates before committing
  any parameter value.
- Check for degeneracy: clipping or flooring pile-ups, structurally empty
  periods, rates saturated at 0% or 100%.
- Verify every signal the analysis is meant to discover is present **at the
  intended magnitude** — not merely present.
- Use independent seeds per generator. Sharing one seed draws from the same
  stream at different offsets, so reordering a draw in one generator silently
  changes every other generator's output.
- If a chart segments by a dimension, that dimension must carry real variance.
  Sampling subscribers from the same distribution as the eligible base makes
  attach rate constant by construction and empties every segmentation view.

**Would have caught:** the Olist estimate-vs-actual misuse, the problem region
calibrated to 0% on-time, the adoption curve leaving the first and last three
weeks empty, the flat segment cuts.

---

## 4. `cohort-metric-definition`

**Scope:** user level (general-purpose)
**Trigger:** defining any rate or ratio over a time-windowed event.

The highest-stakes skill for this project's actual purpose, since these are the
two defects an interviewer would probe first.

**Encode:**
- **Right-censoring.** Does every member of the denominator have the full
  observation window? An account that signed up four days ago has not failed to
  activate in 30 days; it has not yet had the chance. Counting it as a failure
  biases the metric downward hardest in the most recent periods — exactly the
  ones a launch dashboard is read for.
- Do numerator and denominator describe the same population?
- Does the implemented predicate match the spec's *wording*? "On-time delivery"
  is not "delivered within 30 days", and the gap between them is where the
  metric quietly stops detecting the problem it exists to detect.
- Does the resulting value sit in a plausible published benchmark range? A
  result far outside the cited benchmark is a calibration bug until proven
  otherwise.
- Document semi-additivity: which groupings are valid, and which silently lie.

**Would have caught:** the cohort maturity gap, and the North Star drifting from
"on-time kit" to "kit within 30 days".

---

## 5. `statistical-test-assertions`

**Scope:** user level (general-purpose)
**Trigger:** writing a test that asserts on random or generated data.

Small in scope, but it caused two separate problems.

**Encode:**
- Compute the pass probability before fixing a threshold. A seeded test that
  passes 66% of the time across seeds is a coin flip, not a test.
- Never assert a comparison where one side can be structurally zero. The
  original adoption-curve test compared week 1 against week 9 and passed only
  because week 1 was structurally empty — the exact bug it should have caught.
- Assert the non-degenerate precondition explicitly (`assert first_week > 0`)
  alongside the relationship under test.
- Prefer a deterministic invariant over a statistical one where the choice
  exists. Spreading values with `linspace` and seeding only the assignment gives
  a guaranteed spread; independent uniform draws leave it to chance.

**Would have caught:** the adoption-curve test passing on an empty week 1, and
the flaky attach-propensity threshold.

---

## 6. `plan-consistency-sweep` (optional)

**Scope:** project (`.claude/skills/`)
**Trigger:** after editing a long plan or spec document.

Pure mechanics, cheap to run, easy to forget. This is the sweep that was run
manually before the second commit.

**Encode as a script that checks:**
- Every measure referenced by a metric is declared in a semantic model.
- Every column referenced downstream exists in its producing model.
- Every exported CSV feeds a documented dashboard view, and every view has a
  matching export.
- Stated test counts (`Expected: N passed`) match the number of tests listed.
- All YAML blocks parse and all Python blocks compile.

---

## What to skip

General dbt style, naming conventions, and SQL formatting. Those are lint
concerns. Mixing them into the skills above dilutes the signal at the moment it
matters most.

---

## Summary

| # | Skill | Scope | Primary defect class |
|---|-------|-------|----------------------|
| 1 | `dbt-silent-failure-review` | project | Joins that fail green |
| 2 | `metricflow-semantic-layer` | project | Entity/measure/metric correctness |
| 3 | `synthetic-data-calibration` | user | Plausible-but-wrong source data |
| 4 | `cohort-metric-definition` | user | Censoring and definition drift |
| 5 | `statistical-test-assertions` | user | Tests that cannot fail |
| 6 | `plan-consistency-sweep` | project | Cross-reference drift |

Suggested build order: 1 and 2 first, since they cover the defects that ship
silently and produce wrong numbers behind a green build.

When implementing these, use `superpowers:writing-skills` for the file format
and verification workflow.
