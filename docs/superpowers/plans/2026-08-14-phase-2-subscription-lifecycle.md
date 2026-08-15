# Phase 2 — Subscription lifecycle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the generator emit lifecycle events — renewal, cancellation, pause, skip and tier change — so that rebill rate, churn, retention, GRR and NRR stop being unobservable.

**Architecture:** A new generator (`generate_subscription_lifecycle.py`) simulates each account's trajectory cycle by cycle over the billing clock established in Phase 1, emitting an event stream at grain (account, sequence). That stream becomes a seed, a staging model, an intermediate model that reconstructs subscription state at every cycle, and two marts — one for lifecycle and one for MRR movement. Phase 1 models are not rewritten.

**Tech Stack:** Python 3.10–3.13 with a seeded numpy `default_rng`, pandas; dbt-core + dbt-duckdb; MetricFlow; pytest.

**Spec:** `/home/iagoadvaz/projects/pawtrail-launch-analytics/docs/superpowers/specs/2026-08-14-subscription-analytics-gap-scope.md` (§3, items 2.1, 2.2 and 2.7)

## Scope of this plan — read before starting

Spec §3 lists **seven** generator extensions. This plan covers **three**: 2.1 (cancellation, pause, skip), 2.2 (second and third cycle + renewal charge) and 2.7 (tier change).

Those three form **one subsystem**: all describe subscription state over time, they share the same generator surface, and only together do they produce a coherent metric set. Splitting them would produce plans that do not deliver working software on their own — without 2.2 there is no cycle to cancel; without 2.7 NRR is capped at ≤100% by construction, which the spec classifies as worse than absent.

The other four items are independent subsystems and **need their own plans**: 2.3 (payment transactions), 2.4 (returns and reverse logistics), 2.5 (referrals), 2.6 (support contacts). None of them is a prerequisite for this plan's metrics.

## Global Constraints

- **Prerequisite:** Phase 1 must be merged. This plan consumes `int_billing_cycles` and `dim_accounts.cycles_elapsed`.
- **Branch:** a new worktree from the Phase 1 branch.
- **Determinism:** every generator takes an explicit `seed` and uses `np.random.default_rng(seed)`. Independent seeds per generator — reusing one seed across generators means reordering a draw in one silently changes the values every other one produces. Follow `SUBSCRIPTION_SEED = SEED`, `DELIVERY_SEED = SEED + 1`, … in `build_seeds.py`.
- **Monday-aligned weeks:** any date column that will be aggregated by week must match DuckDB's `date_trunc('week', ...)`. The generator already anchors `LAUNCH_DATE = 2026-01-05` (a Monday) for that reason.
- **A planted effect is declared, never "discovered":** this plan deliberately plants a relationship between non-activation and churn. Spec §5.1 forbids planting an effect and presenting its discovery as a finding. The required mitigation: the constant is named, commented as a generator assumption, and there is a test that verifies the analysis **recovers** the planted value — which validates the pipeline instead of feigning discovery. No narrative text may present this relationship as a result.
- **Mandatory skills:** `synthetic-data-calibration` before fixing any generator parameter; `statistical-test-assertions` in every test that asserts over drawn data; `cohort-metric-definition` before any windowed-rate SQL; `dbt-silent-failure-review` on the new joins; `metricflow-semantic-layer` on the new metrics.
- **Baseline to preserve:** the Phase 1 baseline (recorded in that plan's Task 12, Step 4). Regenerating seeds changes downstream numbers — Task 2 handles that explicitly.

---

## File Structure

**New**
- `generator/generate_subscription_lifecycle.py` — the trajectory simulator.
- `generator/tests/test_generate_subscription_lifecycle.py` — generator tests.
- `pawtrail_dbt/seeds/raw_subscription_events.csv` — event stream.
- `pawtrail_dbt/models/staging/stg_subscription_events.sql`
- `pawtrail_dbt/models/intermediate/int_subscription_state.sql` — state per account × cycle.
- `pawtrail_dbt/models/marts/fct_subscription_lifecycle.sql` — grain account × cycle.
- `pawtrail_dbt/models/marts/fct_mrr_movement.sql` — grain cycle; new/expansion/contraction/churned.
- `pawtrail_dbt/tests/assert_no_events_after_cancellation.sql`
- `pawtrail_dbt/tests/assert_mrr_movement_reconciles.sql`
- `pawtrail_dbt/tests/assert_planted_churn_multiplier_is_recovered.sql`

**Modified**
- `generator/build_seeds.py`, `pawtrail_dbt/dbt_project.yml`, the staging/intermediate/marts YAMLs, `_semantic_models.yml`, `_metrics.yml`, `METRICS.md`, `dashboard/README.md`.

---

### Task 1: The subscription trajectory simulator

**Files:**
- Create: `generator/generate_subscription_lifecycle.py`
- Create: `generator/tests/test_generate_subscription_lifecycle.py`

**Interfaces:**
- Consumes: the `subscriptions` DataFrame from `generate_subscriptions` (columns `account_id`, `pet_tier`, `pawtrail_signup_date`), and the `digital_engagement` DataFrame from `generate_digital_engagement` (column `first_login_date`).
- Produces: `generate_subscription_lifecycle(subscriptions, digital_engagement, launch_days, seed) -> pd.DataFrame` with columns `account_id`, `event_seq` (int, 1-based), `event_type` (str), `event_date` (date), `cycle_index` (int), `reason_code` (str or empty), `new_pet_tier` (str or empty). Task 2 calls this function; Task 3 models the CSV.

**INVOKE FIRST:** the `synthetic-data-calibration` skill — this task fixes nine distribution parameters, and a miscalibrated generator produces plausible-looking data that every downstream layer inherits as ground truth.

- [ ] **Step 1: Create the worktree**

```bash
cd /home/iagoadvaz/projects/pawtrail-launch-analytics
git worktree add .claude/worktrees/phase-2-lifecycle -b phase-2-subscription-lifecycle phase-1-computable-metrics
cd .claude/worktrees/phase-2-lifecycle
ln -s /home/iagoadvaz/projects/pawtrail-launch-analytics/.claude/worktrees/implement-pawtrail-launch/.venv .venv
.venv/bin/pytest -q 2>&1 | tail -3
```

Expected: 22 passed. If not, stop — the Phase 1 baseline is not intact.

- [ ] **Step 2: Write the failing tests**

Create `generator/tests/test_generate_subscription_lifecycle.py`:

```python
import datetime as dt

import pandas as pd

from generator.generate_subscription_lifecycle import (
    DAY_ZERO_CANCEL_RATE,
    NON_ACTIVATED_CHURN_MULTIPLIER,
    PER_CYCLE_CHURN_HAZARD,
    generate_subscription_lifecycle,
)


def _subscriptions(n=600, launch=dt.date(2026, 1, 5)):
    return pd.DataFrame(
        {
            "account_id": [f"A{i:05d}" for i in range(n)],
            "pet_tier": ["small", "medium", "large"] * (n // 3),
            # Spread across the window so accounts exist with 0 to 3 elapsed
            # cycles, as in the real generator.
            "pawtrail_signup_date": [launch + dt.timedelta(days=(i * 97) % 110) for i in range(n)],
        }
    )


def _engagement(subs, logged_in_share=0.85):
    cutoff = int(len(subs) * logged_in_share)
    return pd.DataFrame(
        {
            "account_id": subs["account_id"],
            "first_login_date": [
                subs["pawtrail_signup_date"].iloc[i] + dt.timedelta(days=3)
                if i < cutoff
                else pd.NaT
                for i in range(len(subs))
            ],
        }
    )


def test_is_deterministic_for_a_given_seed():
    subs = _subscriptions()
    eng = _engagement(subs)

    a = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=7)
    b = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=7)

    pd.testing.assert_frame_equal(a, b)


def test_no_event_precedes_signup():
    subs = _subscriptions()
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=7)

    merged = events.merge(subs[["account_id", "pawtrail_signup_date"]], on="account_id")
    assert (merged["event_date"] >= merged["pawtrail_signup_date"]).all()


def test_no_event_follows_a_cancellation():
    """Cancellation is absorbing. An event after it would mean an account being
    charged after it left, which is the most expensive mistake this generator
    can make -- and one no schema test would catch."""
    subs = _subscriptions()
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=7)

    for account_id, group in events.groupby("account_id"):
        ordered = group.sort_values("event_seq")
        types = list(ordered["event_type"])
        if "canceled" in types:
            assert types.index("canceled") == len(types) - 1, account_id


def test_every_account_has_an_activation_event():
    subs = _subscriptions()
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=7)

    first = events.sort_values("event_seq").groupby("account_id").first()
    assert (first["event_type"] == "activated").all()
    assert len(first) == len(subs)


def test_churn_hazard_declines_across_cycles():
    """Subscription retention is not memoryless: the hazard declines and
    survivors get stickier. If this premise breaks, the simulated curve becomes a
    pure exponential and the cohort analysis loses the only interesting shape it
    could show.

    Asserts on GENERATED OUTPUT, not on the constant. Reading
    PER_CYCLE_CHURN_HAZARD and checking it declines tests a dict literal: a
    generator that ignored the constant entirely (hazard hardcoded to 0.20)
    passed that version of this test, and so did the eight others."""
    subs = _subscriptions(n=3000)
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=11)

    # Recover the hazard per cycle with the AT-RISK denominator: accounts alive
    # entering the cycle, not every account that has a row at it.
    observed = {}
    for cycle in (1, 2):
        alive = {
            a for a, g in events.groupby("account_id")
            if not ((g["event_type"] == "canceled") & (g["cycle_index"] < cycle)).any()
            and (g["cycle_index"] >= cycle).any()
        }
        churned = {
            a for a, g in events.groupby("account_id")
            if ((g["event_type"] == "canceled") & (g["cycle_index"] == cycle)).any()
        }
        observed[cycle] = len(churned & alive) / len(alive)

    # Cycle 2's hazard must be materially below cycle 1's. The gap in the planted
    # parameters is ~0.23 -> ~0.11, so a 25% relative margin is far outside
    # sampling noise at n=3000 and still fails loudly on a flat hazard.
    assert observed[2] < observed[1] * 0.75, observed


def test_non_activated_accounts_churn_more():
    """The planted effect. This test is NOT a discovery -- it verifies the
    generator's documented parameter reaches the data intact. See the global
    constraint on planted effects."""
    subs = _subscriptions(n=3000)
    eng = _engagement(subs, logged_in_share=0.5)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=11)

    canceled = set(events.loc[events["event_type"] == "canceled", "account_id"])
    logged_in = set(eng.loc[eng["first_login_date"].notna(), "account_id"])
    never = set(subs["account_id"]) - logged_in

    rate_logged = len(canceled & logged_in) / len(logged_in)
    rate_never = len(canceled & never) / len(never)

    # A deliberately loose band: with ~1500 accounts per arm the standard error
    # of the difference in proportions is around 1.5 points, so a tight
    # assertion on the multiplier would fail on legitimate re-seeds. What must
    # hold is the DIRECTION and the order of magnitude.
    assert rate_never > rate_logged
    assert 1.3 < (rate_never / rate_logged) < NON_ACTIVATED_CHURN_MULTIPLIER * 1.4


def test_day_zero_cancellations_exist_and_are_a_minority():
    subs = _subscriptions(n=3000)
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=11)

    merged = events.merge(subs[["account_id", "pawtrail_signup_date"]], on="account_id")
    day_zero = merged[
        (merged["event_type"] == "canceled")
        & (merged["event_date"] == merged["pawtrail_signup_date"])
    ]
    share = len(day_zero) / len(subs)

    assert 0 < share < DAY_ZERO_CANCEL_RATE * 2


def test_tier_changes_include_both_directions():
    """Without upgrades, expansion MRR is zero and NRR is capped at 100% by
    construction -- which the spec classifies as worse than absent."""
    subs = _subscriptions(n=3000)
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=11)

    order = {"small": 0, "medium": 1, "large": 2}
    original = dict(zip(subs["account_id"], subs["pet_tier"]))

    # Direction is measured against the tier IN FORCE before the event, replayed
    # in event_seq order -- not against the account's original tier. Comparing
    # to the original makes a round trip (small -> medium -> small) read as
    # "no change" and trips the != 0 assertion: that version failed on 109 of
    # 200 seeds. Seed 11 happens to be clean, which is why it looked fine, and
    # the obvious remedy of raising `n` makes it strictly worse because round
    # trips scale with n.
    directions = []
    in_force = dict(original)
    for _, row in events.sort_values(["account_id", "event_seq"]).iterrows():
        if row["event_type"] != "tier_changed":
            continue
        acct = row["account_id"]
        directions.append(order[row["new_pet_tier"]] - order[in_force[acct]])
        in_force[acct] = row["new_pet_tier"]

    assert any(d > 0 for d in directions), "no upgrade generated"
    assert any(d < 0 for d in directions), "no downgrade generated"
    assert all(d != 0 for d in directions), "tier_changed with no actual tier change"


def test_skips_do_not_end_the_subscription():
    """Skip is the replenishment model's named metric (Crystallize). A skip that
    ends the subscription would be a cancellation under another name."""
    subs = _subscriptions(n=1500)
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=11)

    skipped = events[events["event_type"] == "skipped"]
    assert len(skipped) > 0

    for account_id, group in events.groupby("account_id"):
        ordered = group.sort_values("event_seq")
        types = list(ordered["event_type"])
        if "skipped" in types and "canceled" not in types:
            # `len(types) > 1` would be a tautology -- `activated` is always
            # first, so it is true whenever a skip exists at all, making the
            # whole assertion `X or True`. Mutating the generator so a skip
            # BREAKS out of the cycle loop still passed that version.
            #
            # Assert the property directly: the cycle after a skip must carry
            # its own event whenever that cycle is inside the observed window.
            skip_cycles = set(ordered.loc[ordered["event_type"] == "skipped", "cycle_index"])
            present_cycles = set(ordered["cycle_index"])
            last_cycle = max(present_cycles)
            for c in skip_cycles:
                if c < last_cycle:
                    assert c + 1 in present_cycles, (account_id, c, present_cycles)
```

- [ ] **Step 3: Run to verify they fail**

```bash
.venv/bin/pytest generator/tests/test_generate_subscription_lifecycle.py -q 2>&1 | tail -5
```

Expected: a collection error — `ModuleNotFoundError: No module named 'generator.generate_subscription_lifecycle'`.

- [ ] **Step 4: Write the generator**

Create `generator/generate_subscription_lifecycle.py`:

```python
"""Simulate each subscription's trajectory cycle by cycle.

WHAT THIS EMITS: one row per lifecycle event, at grain (account_id, event_seq).
Event types are `activated` (always first), `renewed`, `skipped`, `paused`,
`resumed`, `tier_changed` and `canceled` (always last, absorbing).

READ THIS BEFORE TUNING ANY CONSTANT: every number below is a modelling
assumption, not an observation. They are named and commented so the write-up can
cite them as assumptions. In particular NON_ACTIVATED_CHURN_MULTIPLIER plants a
relationship between non-activation and churn -- the analysis must never present
recovering it as a finding. The accompanying test asserts the planted value is
recovered, which validates the pipeline rather than pretending to discover
anything.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

PET_TIER_ORDER = ["small", "medium", "large"]

# Cancellation hazard per cycle, among accounts that reach that cycle alive.
# DECLINING on purpose: subscription retention is not memoryless -- early churn
# is high and survivors get stickier. A constant rate would produce a pure
# exponential, exactly the shape the spec (§5.2) argues is not inferable from
# three points; simulating the wrong shape would make the cohort analysis
# misleading.
#
# Cycle 4 lands at 6%, in the neighbourhood of the <5%/month benchmark
# Crystallize cites for consumer goods -- close enough for the dashboard to have
# a real contrast against the target, far enough not to look calibrated to pass.
PER_CYCLE_CHURN_HAZARD = {1: 0.20, 2: 0.11, 3: 0.075, 4: 0.06}

# Accounts that cancel on the same day they subscribe. A named sticky.io metric
# (#7). Kept low: a launch with a double-digit day-0 cancel rate would signal a
# checkout problem, which is not the story this dataset tells.
DAY_ZERO_CANCEL_RATE = 0.018

# How much more likely an account that never logged in is to cancel, relative to
# one that did. PLANTED EFFECT -- see the module header.
NON_ACTIVATED_CHURN_MULTIPLIER = 2.0

# Skip: skipping ONE shipment while keeping the subscription. This is the metric
# Crystallize names for the replenishment model, and it has no SaaS equivalent --
# which makes it the most specific signal in this dataset.
PER_CYCLE_SKIP_RATE = 0.08

# Pause: suspending indefinitely, with resumption likely. Distinct from
# cancellation because Shopify asks for both tracked as separate volume.
PER_CYCLE_PAUSE_RATE = 0.035
PAUSE_RESUME_PROBABILITY = 0.55

# Tier change. The upgrade arm is what gives NRR the ability to exceed 100%;
# without it the indicator is capped by construction.
PER_CYCLE_UPGRADE_RATE = 0.022
PER_CYCLE_DOWNGRADE_RATE = 0.011


def _add_months(date: dt.date, months: int) -> dt.date:
    """Month arithmetic that clamps end-of-month deterministically.

    Mirrors DuckDB's `DATE + INTERVAL n MONTH` (2026-01-31 + 1 month =
    2026-02-28), so the Python-side cycle clock and int_billing_cycles.sql agree
    on every due date. They must: the mart joins events to cycles by date.
    """
    month_index = date.month - 1 + months
    year = date.year + month_index // 12
    month = month_index % 12 + 1
    last_day_of_month = [
        31,
        29 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 28,
        31, 30, 31, 30, 31, 31, 30, 31, 30, 31,
    ][month - 1]
    return dt.date(year, month, min(date.day, last_day_of_month))


def generate_subscription_lifecycle(
    subscriptions: pd.DataFrame,
    digital_engagement: pd.DataFrame,
    launch_days: int,
    seed: int,
) -> pd.DataFrame:
    """Return one row per lifecycle event for every account."""
    rng = np.random.default_rng(seed)

    logged_in = set(
        digital_engagement.loc[
            digital_engagement["first_login_date"].notna(), "account_id"
        ]
    )

    observation_date = subscriptions["pawtrail_signup_date"].max()

    records: list[dict] = []

    for row in subscriptions.itertuples(index=False):
        account_id = row.account_id
        signup_date = row.pawtrail_signup_date
        current_tier = row.pet_tier
        activated = account_id in logged_in

        seq = 1
        records.append(
            {
                "account_id": account_id,
                "event_seq": seq,
                "event_type": "activated",
                "event_date": signup_date,
                "cycle_index": 0,
                "reason_code": "",
                "new_pet_tier": "",
            }
        )

        # Day-zero cancellation: decided before any cycle, because an account
        # that leaves the same day never faces a renewal at all.
        if rng.random() < DAY_ZERO_CANCEL_RATE:
            seq += 1
            records.append(
                {
                    "account_id": account_id,
                    "event_seq": seq,
                    "event_type": "canceled",
                    "event_date": signup_date,
                    "cycle_index": 0,
                    "reason_code": "day_zero",
                    "new_pet_tier": "",
                }
            )
            continue

        paused = False
        for cycle_index in sorted(PER_CYCLE_CHURN_HAZARD):
            due_date = _add_months(signup_date, cycle_index)
            # Only cycles that actually came due inside the observed window.
            # Emitting past that would invent future behaviour.
            if due_date > observation_date:
                break

            if paused:
                if rng.random() < PAUSE_RESUME_PROBABILITY:
                    paused = False
                    seq += 1
                    records.append(
                        {
                            "account_id": account_id,
                            "event_seq": seq,
                            "event_type": "resumed",
                            "event_date": due_date,
                            "cycle_index": cycle_index,
                            "reason_code": "",
                            "new_pet_tier": "",
                        }
                    )
                else:
                    continue

            hazard = PER_CYCLE_CHURN_HAZARD[cycle_index]
            if not activated:
                hazard = min(hazard * NON_ACTIVATED_CHURN_MULTIPLIER, 0.95)

            draw = rng.random()
            if draw < hazard:
                seq += 1
                records.append(
                    {
                        "account_id": account_id,
                        "event_seq": seq,
                        "event_type": "canceled",
                        "event_date": due_date,
                        "cycle_index": cycle_index,
                        "reason_code": "never_activated" if not activated else "voluntary",
                        "new_pet_tier": "",
                    }
                )
                break

            if rng.random() < PER_CYCLE_PAUSE_RATE:
                paused = True
                seq += 1
                records.append(
                    {
                        "account_id": account_id,
                        "event_seq": seq,
                        "event_type": "paused",
                        "event_date": due_date,
                        "cycle_index": cycle_index,
                        "reason_code": "",
                        "new_pet_tier": "",
                    }
                )
                continue

            if rng.random() < PER_CYCLE_SKIP_RATE:
                seq += 1
                records.append(
                    {
                        "account_id": account_id,
                        "event_seq": seq,
                        "event_type": "skipped",
                        "event_date": due_date,
                        "cycle_index": cycle_index,
                        "reason_code": "",
                        "new_pet_tier": "",
                    }
                )
                continue

            tier_draw = rng.random()
            tier_position = PET_TIER_ORDER.index(current_tier)
            if tier_draw < PER_CYCLE_UPGRADE_RATE and tier_position < 2:
                current_tier = PET_TIER_ORDER[tier_position + 1]
                seq += 1
                records.append(
                    {
                        "account_id": account_id,
                        "event_seq": seq,
                        "event_type": "tier_changed",
                        "event_date": due_date,
                        "cycle_index": cycle_index,
                        "reason_code": "upgrade",
                        "new_pet_tier": current_tier,
                    }
                )
            elif (
                tier_draw < PER_CYCLE_UPGRADE_RATE + PER_CYCLE_DOWNGRADE_RATE
                and tier_position > 0
            ):
                current_tier = PET_TIER_ORDER[tier_position - 1]
                seq += 1
                records.append(
                    {
                        "account_id": account_id,
                        "event_seq": seq,
                        "event_type": "tier_changed",
                        "event_date": due_date,
                        "cycle_index": cycle_index,
                        "reason_code": "downgrade",
                        "new_pet_tier": current_tier,
                    }
                )

            seq += 1
            records.append(
                {
                    "account_id": account_id,
                    "event_seq": seq,
                    "event_type": "renewed",
                    "event_date": due_date,
                    "cycle_index": cycle_index,
                    "reason_code": "",
                    "new_pet_tier": "",
                }
            )

    return pd.DataFrame.from_records(
        records,
        columns=[
            "account_id",
            "event_seq",
            "event_type",
            "event_date",
            "cycle_index",
            "reason_code",
            "new_pet_tier",
        ],
    )
```

- [ ] **Step 5: Run the tests and verify they pass**

```bash
.venv/bin/pytest generator/tests/test_generate_subscription_lifecycle.py -q 2>&1 | tail -5
```

Expected: 9 passed.

If `test_no_event_follows_a_cancellation` fails, the `break` after cancellation is gone. If `test_tier_changes_include_both_directions` fails for lack of a downgrade, the sample may be too small — raise `n` in the test before touching the rates.

- [ ] **Step 6: Commit**

```bash
git add generator/generate_subscription_lifecycle.py generator/tests/test_generate_subscription_lifecycle.py
git commit -m "feat: simulate subscription lifecycle events cycle by cycle"
```

---

### Task 2: Wire into the seed build and re-anchor the baseline

**Files:**
- Modify: `generator/build_seeds.py`
- Modify: `generator/tests/test_build_seeds.py`
- Create: `pawtrail_dbt/seeds/raw_subscription_events.csv` (generated)

**Interfaces:**
- Consumes: `generate_subscription_lifecycle` (Task 1).
- Produces: the seed `raw_subscription_events.csv`. Task 3 models it.

- [ ] **Step 1: Extend the orchestrator test**

In `generator/tests/test_build_seeds.py`, add `raw_subscription_events.csv` to the existing written-files test, and add:

```python
def test_lifecycle_events_reference_only_known_accounts(tmp_path, monkeypatch):
    """An event for a non-existent account would pass pytest and only break at
    dbt's relationships test, much later. Catching it here is cheaper."""
    import pandas as pd

    from generator import build_seeds as bs

    monkeypatch.setattr(bs, "SEEDS_DIR", tmp_path)
    bs.build_seeds()

    subs = pd.read_csv(tmp_path / "raw_subscriptions.csv")
    events = pd.read_csv(tmp_path / "raw_subscription_events.csv")

    assert set(events["account_id"]) <= set(subs["account_id"])
    assert events.groupby("account_id")["event_seq"].apply(
        lambda s: list(s) == sorted(s)
    ).all()
```

- [ ] **Step 2: Run to verify it fails**

```bash
.venv/bin/pytest generator/tests/test_build_seeds.py -q 2>&1 | tail -5
```

Expected: FAIL — `raw_subscription_events.csv` is not written.

- [ ] **Step 3: Wire into the orchestrator**

In `generator/build_seeds.py`:

1. Add to the imports block:

```python
from generator.generate_subscription_lifecycle import generate_subscription_lifecycle
```

2. Add after the line `PITCH_SEED = SEED + 4`:

```python
LIFECYCLE_SEED = SEED + 5
```

3. Inside `build_seeds()`, after the line that creates `sales_pitches`:

```python
    subscription_events = generate_subscription_lifecycle(
        subscriptions,
        digital_engagement,
        launch_days=LAUNCH_DAYS,
        seed=LIFECYCLE_SEED,
    )
```

4. After the last `.to_csv(...)` line:

```python
    subscription_events.to_csv(SEEDS_DIR / "raw_subscription_events.csv", index=False)
```

- [ ] **Step 4: Run the tests and regenerate the seeds**

```bash
.venv/bin/pytest -q 2>&1 | tail -3
.venv/bin/python -m generator.build_seeds
wc -l pawtrail_dbt/seeds/raw_subscription_events.csv
```

Expected: all tests pass; the CSV has between 6,000 and 12,000 rows (3,000 accounts × 2–4 events).

- [ ] **Step 5: Confirm the pre-existing seeds did NOT change**

This is the critical step. The new generator consumes an independent seed, so no other seed may have changed — if any did, a draw was reordered and every Phase 1 number moves without explanation.

```bash
git status --short pawtrail_dbt/seeds/
```

Expected: **only** `?? pawtrail_dbt/seeds/raw_subscription_events.csv`. If any existing `raw_*.csv` shows as modified, **stop and report** — the RNG consumption order changed.

- [ ] **Step 6: Confirm dbt is still green**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build 2>&1 | tail -4
```

Expected: the same total as Phase 1, `ERROR=0`. The new seed is not declared yet, so nothing changes.

- [ ] **Step 7: Commit**

```bash
git add generator/build_seeds.py generator/tests/test_build_seeds.py pawtrail_dbt/seeds/raw_subscription_events.csv
git commit -m "feat: wire lifecycle events into the seed build"
```

---

### Task 3: Staging and subscription state per cycle

**Files:**
- Create: `pawtrail_dbt/models/staging/stg_subscription_events.sql`
- Create: `pawtrail_dbt/models/intermediate/int_subscription_state.sql`
- Create: `pawtrail_dbt/tests/assert_no_events_after_cancellation.sql`
- Modify: `pawtrail_dbt/models/staging/_staging__models.yml`, `pawtrail_dbt/models/intermediate/_intermediate__models.yml`

**Interfaces:**
- Consumes: seed `raw_subscription_events`, model `int_billing_cycles` (Phase 1).
- Produces: `int_subscription_state`, grain account × cycle, columns `subscription_state_key`, `account_id`, `cycle_index`, `renewal_due_date`, `state` (`'active'`, `'skipped'`, `'paused'`, `'canceled'`), `is_retained` (boolean), `pet_tier_at_cycle` (varchar), `churned_this_cycle` (boolean, null-safe), `at_risk_this_cycle` (boolean).

**INVOKE FIRST:** `cohort-metric-definition` and `dbt-silent-failure-review`.

- [ ] **Step 1: Write the failing test**

Create `pawtrail_dbt/tests/assert_no_events_after_cancellation.sql`:

```sql
-- Fails if any BILLABLE EVENT is recorded at or after an account's
-- cancellation. Charging an account after it left is the most expensive
-- mistake this generator can make.
--
-- THE ASSERTION RUNS AGAINST THE EVENT STREAM, NOT THE DERIVED STATE. An
-- earlier version of this test compared int_subscription_state.state against a
-- cancellation cycle derived from the same expression the state column itself
-- is built from -- so it compared a value against itself and could not fail.
-- Injecting 20 post-cancellation `renewed` events into the stream left it
-- returning zero rows. Anything downstream of int_subscription_state is
-- disqualified as the subject of this test for that reason.
with canceled as (
    select
        account_id,
        min(cycle_index) as canceled_at_cycle,
        min(event_seq)   as canceled_at_seq
    from {{ ref('stg_subscription_events') }}
    where event_type = 'canceled'
    group by 1
)

select e.account_id, e.cycle_index, e.event_seq, e.event_type, c.canceled_at_cycle
from {{ ref('stg_subscription_events') }} e
join canceled c on e.account_id = c.account_id
where e.event_seq > c.canceled_at_seq
  and e.event_type in ('renewed', 'tier_changed', 'skipped', 'resumed', 'paused')
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt test --select assert_no_events_after_cancellation 2>&1 | tail -6
```

Expected: FAIL at compilation — the models do not exist.

- [ ] **Step 3: Declare the seed and write the staging model**

Create `pawtrail_dbt/models/staging/stg_subscription_events.sql`:

```sql
select
    account_id,
    cast(event_seq as integer) as event_seq,
    event_type,
    cast(event_date as date) as event_date,
    cast(cycle_index as integer) as cycle_index,
    nullif(reason_code, '') as reason_code,
    nullif(new_pet_tier, '') as new_pet_tier
from {{ ref('raw_subscription_events') }}
```

In `pawtrail_dbt/models/staging/_staging__models.yml`, append:

```yaml
  - name: stg_subscription_events
    columns:
      - name: account_id
        tests:
          - not_null
          - relationships:
              arguments:
                to: ref('stg_subscriptions')
                field: account_id
      - name: event_type
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['activated', 'renewed', 'skipped', 'paused', 'resumed', 'tier_changed', 'canceled']
      - name: event_date
        tests:
          - not_null
```

- [ ] **Step 4: Write the state model**

Create `pawtrail_dbt/models/intermediate/int_subscription_state.sql`:

```sql
-- Subscription state at every cycle that actually came due.
--
-- THE SPINE COMES FROM int_billing_cycles, NOT FROM THE EVENTS. This is
-- deliberate: an account that canceled at cycle 1 emits no events at cycles 2
-- and 3, and deriving the grain from the events would make those accounts simply
-- vanish from the denominator -- which is exactly how a retention rate starts
-- rising while the business shrinks. The spine guarantees that those who left
-- stay counted.
with cycles as (
    select account_id, cycle_index, renewal_due_date
    from {{ ref('int_billing_cycles') }}
),

events as (
    select * from {{ ref('stg_subscription_events') }}
),

-- Which cycle the account canceled at, if it canceled.
cancellation as (
    select account_id, min(cycle_index) as canceled_at_cycle
    from events
    where event_type = 'canceled'
    group by 1
),

-- The state-defining event for the cycle. An account can have both a
-- tier_changed and a renewed in the same cycle; the state event is the one with
-- the highest event_seq among those that define state.
cycle_event as (
    select
        account_id,
        cycle_index,
        event_type,
        row_number() over (
            partition by account_id, cycle_index order by event_seq desc
        ) as recency
    from events
    where event_type in ('renewed', 'skipped', 'paused', 'canceled', 'activated')
),

-- The tier in force at the cycle: the last tier_changed up to here, or the
-- original tier.
tier_at_cycle as (
    select
        c.account_id,
        c.cycle_index,
        coalesce(
            (
                select e.new_pet_tier
                from events e
                where e.account_id = c.account_id
                  and e.event_type = 'tier_changed'
                  and e.cycle_index <= c.cycle_index
                order by e.event_seq desc
                limit 1
            ),
            s.pet_tier
        ) as pet_tier_at_cycle
    from cycles c
    join {{ ref('stg_subscriptions') }} s on c.account_id = s.account_id
)

-- Pause carried forward: an account is paused at cycle n if its most recent
-- pause/resume event at or before cycle n was a 'paused'. This is what makes a
-- still-paused cycle -- which emits no event -- resolve to 'paused' rather than
-- falling through to 'active'.
paused_state as (
    select
        c.account_id,
        c.cycle_index,
        coalesce(
            (
                select ev.event_type = 'paused'
                from {{ ref('stg_subscription_events') }} ev
                where ev.account_id = c.account_id
                  and ev.cycle_index <= c.cycle_index
                  and ev.event_type in ('paused', 'resumed')
                order by ev.cycle_index desc, ev.event_seq desc
                limit 1
            ),
            false
        ) as is_paused
    from cycles c
)

select
    c.account_id || '_' || cast(c.cycle_index as varchar) as subscription_state_key,
    c.account_id,
    c.cycle_index,
    c.renewal_due_date,
    case
        when x.canceled_at_cycle is not null and c.cycle_index >= x.canceled_at_cycle
            then 'canceled'
        when e.event_type = 'skipped' then 'skipped'
        when e.event_type = 'paused' then 'paused'
        -- A STILL-PAUSED cycle emits no event at all: when the resume draw
        -- fails, the generator `continue`s without writing a record. Reading
        -- pause from a single event therefore loses it, and the `else` branch
        -- below silently reports the account as active -- and bills it. In the
        -- generated data that is 21 rows and $629.79 of phantom MRR, and it
        -- understates paused volume by 17%, which is precisely the number
        -- Shopify asks for.
        --
        -- So pause is carried FORWARD from the last pause/resume event rather
        -- than read from this cycle's event.
        when p.is_paused then 'paused'
        else 'active'
    end as state,
    -- Retained = still paying. A skipped or paused account is still a subscriber
    -- but does NOT generate revenue that cycle -- which is why is_retained is
    -- narrower than "not canceled", and why the two readings must exist
    -- separately.
    (x.canceled_at_cycle is null or c.cycle_index < x.canceled_at_cycle)
        as is_retained,
    -- coalesce, because `x.canceled_at_cycle = c.cycle_index` is NULL (not
    -- false) for every account that never cancelled -- 72% of rows. The column
    -- is declared boolean and its sibling is_retained is null-safe; leaving
    -- this one three-valued means any future `where not churned_this_cycle`
    -- silently drops those rows.
    coalesce(x.canceled_at_cycle = c.cycle_index, false) as churned_this_cycle,
    -- Alive ENTERING this cycle, and therefore able to churn during it. This is
    -- the denominator a hazard rate needs: an account that cancelled at cycle 1
    -- is carried forward as 'canceled' at cycles 2 and 3, and counting it in
    -- those denominators understates the hazard by 24% at cycle 2 and 31% at
    -- cycle 3 -- and steepens the apparent decline, which is the one shape
    -- spec section 5.2(b) says matters.
    (x.canceled_at_cycle is null or c.cycle_index <= x.canceled_at_cycle)
        as at_risk_this_cycle,
    t.pet_tier_at_cycle
from cycles c
left join cancellation x on c.account_id = x.account_id
left join cycle_event e
    on c.account_id = e.account_id
   and c.cycle_index = e.cycle_index
   and e.recency = 1
left join paused_state p
    on c.account_id = p.account_id and c.cycle_index = p.cycle_index
left join tier_at_cycle t
    on c.account_id = t.account_id
   and c.cycle_index = t.cycle_index
```

- [ ] **Step 5: Add the schema tests**

In `pawtrail_dbt/models/intermediate/_intermediate__models.yml`:

```yaml
  - name: int_subscription_state
    columns:
      - name: subscription_state_key
        tests:
          - unique
          - not_null
      - name: state
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['active', 'skipped', 'paused', 'canceled']
      - name: is_retained
        tests:
          - not_null
      - name: churned_this_cycle
        tests:
          - not_null
      - name: at_risk_this_cycle
        tests:
          - not_null
      - name: pet_tier_at_cycle
        tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['small', 'medium', 'large']
```

- [ ] **Step 6: Run and verify the row count**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select stg_subscription_events+ 2>&1 | tail -10
../.venv/bin/python -c "
import duckdb
c = duckdb.connect('pawtrail.duckdb', read_only=True)
print('int_billing_cycles:', c.sql('select count(*) from main.int_billing_cycles').fetchone())
print('int_subscription_state:', c.sql('select count(*) from main.int_subscription_state').fetchone())
print('by state:', c.sql('select state, count(*) from main.int_subscription_state group by 1 order by 2 desc').fetchall())
"
```

Expected: the two counts **identical** — the spine defines the grain and no join may fan out. If `int_subscription_state` has more rows, the `recency = 1` filter failed.

- [ ] **Step 7: Commit**

```bash
git add pawtrail_dbt/models/staging/stg_subscription_events.sql \
        pawtrail_dbt/models/staging/_staging__models.yml \
        pawtrail_dbt/models/intermediate/int_subscription_state.sql \
        pawtrail_dbt/models/intermediate/_intermediate__models.yml \
        pawtrail_dbt/tests/assert_no_events_after_cancellation.sql
git commit -m "feat: reconstruct subscription state per billing cycle from the event stream"
```

---

### Task 4: Lifecycle mart and rebill, churn and retention metrics

**Files:**
- Create: `pawtrail_dbt/models/marts/fct_subscription_lifecycle.sql`
- Modify: `pawtrail_dbt/models/marts/_marts__core.yml`, `_semantic_models.yml`, `_metrics.yml`
- Modify: `pawtrail_dbt/models/intermediate/int_billing_cycles.sql` (header comment only)

**Interfaces:**
- Consumes: `int_subscription_state` (Task 3), `dim_accounts`, `dim_pricing`.
- Produces: mart at grain account × cycle; metrics `rebill_rate`, `monthly_churn_rate`, `retention_rate`, `skip_rate`, `pause_rate`.

**INVOKE FIRST:** `cohort-metric-definition` and `metricflow-semantic-layer`.

> **Naming note.** Phase 1 forbids the name `rebill_rate` because no charge existed in the data. **This phase lifts that prohibition** — after Task 1 a real `renewed` event exists, so `rebill_rate` now names a measurement. When implementing, update the header comment in `int_billing_cycles.sql` to record that the constraint was lifted and why.

- [ ] **Step 1: Write the mart**

Create `pawtrail_dbt/models/marts/fct_subscription_lifecycle.sql`:

```sql
-- Grain account x cycle, enriched with the segmentation dimensions. This is the
-- table behind rebill rate, churn, retention, skip and pause.
with state as (
    select * from {{ ref('int_subscription_state') }}
),

accounts as (
    select account_id, state as account_state, channel, premium_tenure_band
    from {{ ref('dim_accounts') }}
),

pricing as (
    select pet_tier, monthly_price_usd from {{ ref('dim_pricing') }}
)

select
    s.subscription_state_key,
    s.account_id,
    s.cycle_index,
    s.renewal_due_date,
    s.state,
    s.is_retained,
    s.churned_this_cycle,
    s.pet_tier_at_cycle,
    a.account_state,
    a.channel,
    a.premium_tenure_band,
    -- Revenue recognised in the cycle. Skip and pause keep the subscription but
    -- do not bill, so cycle MRR is zero for them -- and that difference between
    -- "retained" and "billing" is exactly what the replenishment model makes
    -- material and a SaaS model would not have.
    case when s.state = 'active' then p.monthly_price_usd else 0 end as cycle_mrr_usd,
    -- Denominator of the cycle-1 rebill rate: accounts that reached the end of
    -- cycle 0 alive and whose cycle 1 has come due. Restricting here rather than
    -- in the metric stops a dimensional cut from accidentally changing the
    -- denominator.
    (s.cycle_index = 1) as is_cycle_one,
    (s.cycle_index = 1 and s.state = 'active') as rebilled_at_cycle_one
from state s
join accounts a on s.account_id = a.account_id
join pricing p on s.pet_tier_at_cycle = p.pet_tier
```

- [ ] **Step 2: Add the schema tests**

In `pawtrail_dbt/models/marts/_marts__core.yml`:

```yaml
  - name: fct_subscription_lifecycle
    columns:
      - name: subscription_state_key
        tests:
          - unique
          - not_null
      - name: account_id
        tests:
          - not_null
          - relationships:
              arguments:
                to: ref('dim_accounts')
                field: account_id
      - name: cycle_mrr_usd
        tests:
          - not_null
      - name: state
        tests:
          - accepted_values:
              arguments:
                values: ['active', 'skipped', 'paused', 'canceled']
```

- [ ] **Step 3: Declare the semantic model**

In `_semantic_models.yml`:

```yaml
  - name: subscription_lifecycle
    model: ref('fct_subscription_lifecycle')
    defaults:
      agg_time_dimension: cycle_due_date
    entities:
      - name: lifecycle_row
        type: primary
        expr: subscription_state_key
      - name: account
        type: foreign
        expr: account_id
    dimensions:
      - name: cycle_due_date
        type: time
        expr: renewal_due_date
        type_params:
          time_granularity: day
      - name: cycle_index
        type: categorical
      - name: subscription_state
        type: categorical
        expr: state
    measures:
      - name: cycle_one_accounts
        agg: sum
        expr: case when is_cycle_one then 1 else 0 end
        create_metric: true
      - name: cycle_one_rebilled_accounts
        agg: sum
        expr: case when rebilled_at_cycle_one then 1 else 0 end
        create_metric: true
      - name: retained_accounts
        agg: sum
        expr: case when is_retained then 1 else 0 end
        create_metric: true
      - name: churned_accounts
        agg: sum
        expr: case when churned_this_cycle then 1 else 0 end
        create_metric: true
      - name: at_risk_accounts_this_cycle
        agg: sum
        expr: case when at_risk_this_cycle then 1 else 0 end
        create_metric: true
      - name: cycle_rows
        agg: count
        expr: subscription_state_key
        create_metric: true
      - name: skipped_cycles
        agg: sum
        expr: case when state = 'skipped' then 1 else 0 end
        create_metric: true
      - name: paused_cycles
        agg: sum
        expr: case when state = 'paused' then 1 else 0 end
        create_metric: true
      - name: cycle_mrr_usd
        agg: sum
        expr: cycle_mrr_usd
        create_metric: true
```

- [ ] **Step 4: Declare the metrics**

In `_metrics.yml`:

```yaml
  # The most-cited subscription metric across the four references (sticky.io #6):
  # what share of accounts that reached cycle 1 actually renewed. Different from
  # retention: a paused or skipped account is still a subscriber but did NOT
  # rebill, and the replenishment model makes that difference material.
  - name: rebill_rate
    type: ratio
    label: "Rebill Rate (cycle 0 to cycle 1)"
    type_params:
      numerator: cycle_one_rebilled_accounts
      denominator: cycle_one_accounts

  - name: retention_rate
    type: ratio
    # CUMULATIVE SURVIVAL at cycle n, NOT the complement of monthly_churn_rate.
    # The two share a name-shape and answer different questions; reading this as
    # 1 - churn is wrong. ONLY MEANINGFUL GROUPED BY
    # lifecycle_row__cycle_index -- see the same note on weekly_attach.
    label: "Cumulative Survival at Cycle (share still subscribed)"
    type_params:
      numerator: retained_accounts
      denominator: cycle_rows

  # HAZARD, not share-of-everyone. The denominator is accounts ALIVE ENTERING
  # the cycle, never every row of the spine: an account that cancelled at cycle
  # 1 is carried forward as 'canceled' and had no opportunity to churn at cycle
  # 2. Using cycle_rows understates the hazard by 24% at cycle 2 and 31% at
  # cycle 3, and -- because the dead-account share grows monotonically -- makes
  # the curve look like it declines faster than it does.
  #
  # ONLY MEANINGFUL GROUPED BY lifecycle_row__cycle_index. Queried ungrouped it
  # blends hazards across cycles and means nothing.
  - name: monthly_churn_rate
    type: ratio
    label: "Churn Hazard per Billing Cycle (denominator = alive entering cycle)"
    type_params:
      numerator: churned_accounts
      denominator: at_risk_accounts_this_cycle

  # Skip is the metric Crystallize names for the replenishment model and which
  # does not exist in SaaS. Tracked as both volume AND rate because Shopify asks
  # explicitly for the volume, not only the rate.
  - name: skip_rate
    type: ratio
    label: "Skip Rate per Cycle"
    type_params:
      numerator: skipped_cycles
      denominator: cycle_rows

  - name: pause_rate
    type: ratio
    label: "Pause Rate per Cycle"
    type_params:
      numerator: paused_cycles
      denominator: cycle_rows
```

- [ ] **Step 5: Run and check against the planted parameters**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select fct_subscription_lifecycle 2>&1 | tail -6
../.venv/bin/dbt parse && ../.venv/bin/mf validate-configs 2>&1 | tail -4
../.venv/bin/mf query --metrics rebill_rate
../.venv/bin/mf query --metrics monthly_churn_rate,retention_rate,skip_rate,pause_rate --group-by lifecycle_row__cycle_index --order lifecycle_row__cycle_index
```

Expected: `rebill_rate` **0.63–0.72** (measured 0.6776).

The derivation matters, because an earlier draft of this plan said 0.72–0.82 and
that band is unreachable: it omitted the non-activation multiplier and the
day-zero cancels. With 15.8% of accounts never logging in, the effective cycle-1
hazard is `0.842 × 0.20 + 0.158 × 0.40 = 0.232`, so
`(1 − 0.018) × (1 − 0.232) × (1 − 0.035) × (1 − 0.08) ≈ 0.67`.

**Do not tune `PER_CYCLE_CHURN_HAZARD` or `PER_CYCLE_SKIP_RATE` to hit a band.**
If the measured value sits outside 0.63–0.72, re-derive the band before touching
the generator.

`monthly_churn_rate` should recover the planted hazards **at the at-risk
denominator**: ~0.23 at cycle 1, **~0.11 at cycle 2, ~0.075 at cycle 3**. Check
against those values, not merely "it declines" — with the wrong (`cycle_rows`)
denominator the number declines *faster* than the truth, so a decline test passes
precisely on the bug it is meant to catch. `skip_rate` near 0.08.

**If cycle 2 does not land near 0.11, stop and report** — the denominator is
probably counting already-cancelled accounts.

- [ ] **Step 6: Commit**

```bash
git add pawtrail_dbt/models/marts/fct_subscription_lifecycle.sql \
        pawtrail_dbt/models/marts/_marts__core.yml \
        pawtrail_dbt/models/marts/_semantic_models.yml \
        pawtrail_dbt/models/marts/_metrics.yml \
        pawtrail_dbt/models/intermediate/int_billing_cycles.sql
git commit -m "feat: add rebill rate, churn, retention, skip and pause metrics"
```

---

### Task 5: MRR movement, GRR and NRR

**Files:**
- Create: `pawtrail_dbt/models/marts/fct_mrr_movement.sql`
- Create: `pawtrail_dbt/tests/assert_mrr_movement_reconciles.sql`
- Modify: `pawtrail_dbt/models/marts/_marts__business.yml`, `_semantic_models.yml`, `_metrics.yml`

**Interfaces:**
- Consumes: `fct_subscription_lifecycle` (Task 4).
- Produces: mart at grain cycle, columns `cycle_index`, `cycle_due_week`, `starting_mrr_usd`, `new_mrr_usd`, `expansion_mrr_usd`, `reactivation_mrr_usd`, `contraction_mrr_usd`, `churned_mrr_usd`, `ending_mrr_usd`; metrics `gross_revenue_retention`, `net_revenue_retention`.

- [ ] **Step 1: Write the reconciliation test first**

Create `pawtrail_dbt/tests/assert_mrr_movement_reconciles.sql`:

```sql
-- Fails if the movement bridge does not close: starting MRR + new + expansion -
-- contraction - churned must equal ending MRR exactly.
--
-- This is the model's only real guard. A decomposition that does not reconcile
-- produces an NRR that looks plausible and is wrong, and no schema test would
-- catch it.
select
    cycle_index,
    starting_mrr_usd,
    new_mrr_usd,
    expansion_mrr_usd,
    reactivation_mrr_usd,
    contraction_mrr_usd,
    churned_mrr_usd,
    ending_mrr_usd
from {{ ref('fct_mrr_movement') }}
where abs(
    (starting_mrr_usd + new_mrr_usd + expansion_mrr_usd + reactivation_mrr_usd
     - contraction_mrr_usd - churned_mrr_usd)
    - ending_mrr_usd
) > 0.01
```

**This test is the one that catches the reactivation gap.** Without the
`reactivation_mrr_usd` term it fires at cycles 2 and 3 with gaps of -$2,629.07
and -$479.83 — which is correct behaviour from the test and a missing bucket in
the model, not the reverse. Do not widen the tolerance to silence it.

- [ ] **Step 2: Run to verify it fails**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt test --select assert_mrr_movement_reconciles 2>&1 | tail -6
```

Expected: FAIL at compilation.

- [ ] **Step 3: Write the model**

Create `pawtrail_dbt/models/marts/fct_mrr_movement.sql`:

```sql
-- The MRR movement decomposition: new, expansion, contraction, churned,
-- reactivation.
--
-- REACTIVATION IS NOT OPTIONAL. A row whose previous cycle billed $0 (skipped or
-- paused) and which bills again this cycle belongs to no other bucket:
-- `expansion` requires previous_cycle_mrr > 0 and `new` requires it to be null.
-- Omitting it leaves the bridge unreconciled by -$2,629.07 at cycle 2 and
-- -$479.83 at cycle 3 -- 65 return-from-skip plus 28 return-from-pause rows.
-- With PER_CYCLE_SKIP_RATE = 0.08 this is guaranteed at scale, not a tail case.
--
-- The `state <> 'canceled'` guard is load-bearing: previous_cycle_mrr = 0 also
-- matches post-cancellation rows, which must stay in `churned`.
--
-- WHY THE EXPANSION ARM MATTERS SO MUCH: without upgrade events, expansion MRR
-- is always zero and NRR is capped at 100% by construction. An indicator
-- structurally incapable of exceeding 100% is misleading, not incomplete --
-- worse than absent. That is why spec item 2.7 (tier change) is a prerequisite
-- for this model rather than an extra.
with lifecycle as (
    select
        account_id,
        cycle_index,
        cycle_mrr_usd,
        state
    from {{ ref('fct_subscription_lifecycle') }}
),

-- The account's MRR at the previous cycle, so the change can be classified.
with_previous as (
    select
        account_id,
        cycle_index,
        cycle_mrr_usd,
        state,
        lag(cycle_mrr_usd) over (
            partition by account_id order by cycle_index
        ) as previous_cycle_mrr_usd
    from lifecycle
),

classified as (
    select
        cycle_index,
        -- New: the account's first appearance (no previous cycle) with revenue.
        sum(case
            when previous_cycle_mrr_usd is null and cycle_mrr_usd > 0
            then cycle_mrr_usd else 0
        end) as new_mrr_usd,
        -- Expansion: moved up a tier and is still billing.
        sum(case
            when previous_cycle_mrr_usd is not null
                 and cycle_mrr_usd > previous_cycle_mrr_usd
                 and previous_cycle_mrr_usd > 0
            then cycle_mrr_usd - previous_cycle_mrr_usd else 0
        end) as expansion_mrr_usd,
        -- Contraction: moved down a tier, OR stopped billing without canceling
        -- (skip, pause). Counting a skip as contraction is the right read for
        -- replenishment: the revenue vanished this cycle and the account is
        -- still alive.
        sum(case
            when previous_cycle_mrr_usd is not null
                 and cycle_mrr_usd < previous_cycle_mrr_usd
                 and state <> 'canceled'
            then previous_cycle_mrr_usd - cycle_mrr_usd else 0
        end) as contraction_mrr_usd,
        -- Reactivation: billed $0 last cycle (skipped or paused) and is
        -- billing again now. Without this bucket the bridge does not
        -- reconcile -- see the model header.
        sum(case
            when previous_cycle_mrr_usd = 0
                 and cycle_mrr_usd > 0
                 and state <> 'canceled'
            then cycle_mrr_usd else 0
        end) as reactivation_mrr_usd,
        -- Churned: canceled, and the previous cycle's revenue is gone for good.
        sum(case
            when state = 'canceled' and coalesce(previous_cycle_mrr_usd, 0) > 0
            then previous_cycle_mrr_usd else 0
        end) as churned_mrr_usd,
        sum(coalesce(previous_cycle_mrr_usd, 0)) as starting_mrr_usd,
        sum(cycle_mrr_usd) as ending_mrr_usd
    from with_previous
    group by 1
)

select
    cycle_index,
    starting_mrr_usd,
    new_mrr_usd,
    expansion_mrr_usd,
    reactivation_mrr_usd,
    contraction_mrr_usd,
    churned_mrr_usd,
    ending_mrr_usd
from classified
```

**The contraction definition is a known limitation, and it must be labelled.**
Contraction here is *cash not billed this cycle*, not *subscription value lost*,
so a one-cycle skip books the full price as contraction and the return books
reactivation. That is internally consistent and it reconciles — but it means GRR
and NRR read 0.68–0.80 and are **not comparable to any published NRR benchmark**,
because a transient skip is being scored as a downgrade.

Expansion is $340 at cycle 1 against $6,387.79 of contraction, of which ~$4,795
is skip and pause that mostly returns. No parameterisation of a 2.2% upgrade rate
on a ~$10 tier delta offsets a 20%+ churn hazard, so **item 2.7 removes the
structural cap on NRR without making the number benchmark-comparable.** Say that
plainly in METRICS.md rather than implying the upgrade arm resolved it.

The stronger fix, if this becomes worth the rework: define contraction and churn
on subscription value at the tier in force, and publish skipped/paused revenue as
its own "deferred billings" line. That is the replenishment-specific signal, and
it is more useful named than smuggled inside contraction.

- [ ] **Step 4: Add the schema tests and declare the metrics**

In `_marts__business.yml`:

```yaml
  - name: fct_mrr_movement
    columns:
      - name: cycle_index
        tests:
          - unique
          - not_null
      - name: starting_mrr_usd
        tests:
          - not_null
      - name: ending_mrr_usd
        tests:
          - not_null
```

In `_semantic_models.yml`:

```yaml
  - name: mrr_movement
    model: ref('fct_mrr_movement')
    entities:
      - name: mrr_movement_cycle
        type: primary
        expr: cycle_index
    dimensions:
      - name: movement_cycle_index
        type: categorical
        expr: cycle_index
      # REQUIRED. MetricFlow demands an agg_time_dimension for every measure,
      # and this model has five. Without it `dbt parse` fails with
      # "Aggregation time dimension for measure starting_mrr_usd is not set!" --
      # a parse error, which gates dbt build and stops every Phase 1 test
      # running too. Every other semantic model in this project that carries
      # measures declares one.
      #
      # fct_mrr_movement is aggregated to cycle_index alone, which spans ~120
      # distinct due dates, so the mart must also be regrained to
      # (cycle_index, cycle_due_week) and carry that column. Regraining is the
      # better fix regardless: it is what lets the movement bridge be read as a
      # time series rather than as four opaque buckets.
      - name: cycle_due_week
        type: time
        expr: cycle_due_week
        type_params:
          time_granularity: week
    defaults:
      agg_time_dimension: cycle_due_week
    measures:
      - name: starting_mrr_usd
        agg: sum
        expr: starting_mrr_usd
        create_metric: true
      - name: ending_mrr_usd
        agg: sum
        expr: ending_mrr_usd
        create_metric: true
      - name: expansion_mrr_usd
        agg: sum
        expr: expansion_mrr_usd
        create_metric: true
      - name: reactivation_mrr_usd
        agg: sum
        expr: reactivation_mrr_usd
        create_metric: true
      - name: contraction_mrr_usd
        agg: sum
        expr: contraction_mrr_usd
        create_metric: true
      - name: churned_mrr_usd
        agg: sum
        expr: churned_mrr_usd
        create_metric: true
```

In `_metrics.yml`:

```yaml
  # GRR: how much of the starting revenue survives, IGNORING expansion. Capped
  # at 100% by definition.
  - name: gross_revenue_retention
    type: derived
    label: "Gross Revenue Retention"
    type_params:
      expr: (starting - churned - contraction) / nullif(starting, 0)
      metrics:
        - name: starting_mrr_usd
          alias: starting
        - name: churned_mrr_usd
          alias: churned
        - name: contraction_mrr_usd
          alias: contraction

  # NRR: the same, INCLUDING expansion and reactivation -- which is why it can
  # exceed 100%, and why it is only honest once spec item 2.7 (tier change)
  # exists. See the header of fct_mrr_movement.sql.
  #
  # READ THE LABEL. Item 2.7 removes the STRUCTURAL cap (expansion is no longer
  # identically zero) but not the NUMERICAL one: contraction is defined as cash
  # not billed, so transient skips are scored as downgrades and NRR runs
  # 0.69-0.80. It is a launch-cohort reading over at most 4 cycles, not a figure
  # to compare against a published benchmark.
  - name: net_revenue_retention
    type: derived
    label: "Net Revenue Retention (launch cohort, <=4 cycles, not benchmark-comparable)"
    type_params:
      expr: (starting + expansion + reactivation - churned - contraction) / nullif(starting, 0)
      metrics:
        - name: starting_mrr_usd
          alias: starting
        - name: expansion_mrr_usd
          alias: expansion
        - name: reactivation_mrr_usd
          alias: reactivation
        - name: churned_mrr_usd
          alias: churned
        - name: contraction_mrr_usd
          alias: contraction
```

- [ ] **Step 5: Run and verify NRR can exceed 100%**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build --select fct_mrr_movement+ 2>&1 | tail -8
../.venv/bin/dbt parse && ../.venv/bin/mf validate-configs 2>&1 | tail -4
../.venv/bin/mf query --metrics gross_revenue_retention,net_revenue_retention,expansion_mrr_usd --group-by mrr_movement_cycle__movement_cycle_index --order mrr_movement_cycle__movement_cycle_index
```

Expected: `assert_mrr_movement_reconciles` passes. `expansion_mrr_usd` **greater than zero** in at least one cycle — if it is zero everywhere, the upgrade arm did not reach the data and NRR is capped, which is exactly the failure the spec warns about. `net_revenue_retention` greater than `gross_revenue_retention` in every cycle with expansion.

- [ ] **Step 6: Commit**

```bash
git add pawtrail_dbt/models/marts/fct_mrr_movement.sql \
        pawtrail_dbt/models/marts/_marts__business.yml \
        pawtrail_dbt/models/marts/_semantic_models.yml \
        pawtrail_dbt/models/marts/_metrics.yml \
        pawtrail_dbt/tests/assert_mrr_movement_reconciles.sql
git commit -m "feat: decompose MRR movement and expose GRR and NRR"
```

---

### Task 6: Planted-effect recovery and exports

**Files:**
- Create: `pawtrail_dbt/tests/assert_planted_churn_multiplier_is_recovered.sql`
- Create: 5 CSVs in `dashboard/`
- Modify: `METRICS.md`, `dashboard/README.md`, `pawtrail_dbt/dbt_project.yml`

- [ ] **Step 1: Add the planted-effect var**

In `pawtrail_dbt/dbt_project.yml`, inside `vars:`:

```yaml
  # Mirrors NON_ACTIVATED_CHURN_MULTIPLIER in
  # generator/generate_subscription_lifecycle.py. It exists so the recovery test
  # reads the value from one source -- a silent drift between generator and test
  # would make the test pass while validating the wrong number.
  planted_non_activated_churn_multiplier: 2.0
```

- [ ] **Step 2: Write the recovery test**

Create `pawtrail_dbt/tests/assert_planted_churn_multiplier_is_recovered.sql`:

```sql
-- Fails if the pipeline does NOT recover, within a loose band, the relationship
-- between non-activation and churn that the generator plants.
--
-- READ CAREFULLY: this test does not exist to "discover" that non-activation
-- causes churn -- that relationship was planted on purpose and is documented in
-- generate_subscription_lifecycle.py. It exists to verify that the models, joins
-- and aggregations between the generator and the metric preserve the
-- relationship. If the multiplier arrives distorted, some join is dropping or
-- duplicating rows -- exactly the kind of error that produces a green build and
-- wrong numbers.
--
-- No narrative text may present this result as a finding.
with by_activation as (
    select
        f.combined_activated_30d,
        count(*) as accounts,
        sum(case when l.ever_churned then 1 else 0 end) as churned
    from {{ ref('int_activation_funnel') }} f
    join (
        select account_id, max(case when churned_this_cycle then 1 else 0 end) = 1
            as ever_churned
        from {{ ref('fct_subscription_lifecycle') }}
        group by 1
    ) l on f.account_id = l.account_id
    where f.is_mature_30d
    group by 1
),

rates as (
    select
        max(case when combined_activated_30d then churned * 1.0 / nullif(accounts, 0) end)
            as rate_activated,
        max(case when not combined_activated_30d then churned * 1.0 / nullif(accounts, 0) end)
            as rate_not_activated
    from by_activation
)

select
    rate_activated,
    rate_not_activated,
    rate_not_activated / nullif(rate_activated, 0) as observed_multiplier
from rates
-- A deliberately loose band. The planted multiplier acts on the per-cycle
-- hazard, while what is observed here is "canceled at any point" -- the two
-- quantities are related but not equal, and compounding across 2 to 4 cycles
-- compresses the ratio. A tight band would fail on legitimate re-seeds.
where rate_activated is null
   or rate_not_activated is null
   or rate_not_activated <= rate_activated
   or rate_not_activated / nullif(rate_activated, 0)
        > {{ var('planted_non_activated_churn_multiplier') }} * 1.6
```

- [ ] **Step 3: Run the full build**

```bash
cd pawtrail_dbt && ../.venv/bin/dbt build 2>&1 | tail -6
```

Expected: `ERROR=0`. Record the new total.

- [ ] **Step 4: Generate the CSVs**

```bash
cd pawtrail_dbt
../.venv/bin/mf query --metrics rebill_rate,retention_rate,monthly_churn_rate --group-by lifecycle_row__cycle_index --order lifecycle_row__cycle_index --csv ../dashboard/control_lifecycle_by_cycle.csv
../.venv/bin/mf query --metrics skip_rate,pause_rate,skipped_cycles,paused_cycles --group-by lifecycle_row__cycle_index --order lifecycle_row__cycle_index --csv ../dashboard/control_skip_and_pause.csv
../.venv/bin/mf query --metrics gross_revenue_retention,net_revenue_retention,expansion_mrr_usd,churned_mrr_usd,contraction_mrr_usd --group-by mrr_movement_cycle__movement_cycle_index --order mrr_movement_cycle__movement_cycle_index --csv ../dashboard/control_mrr_movement.csv
../.venv/bin/mf query --metrics monthly_churn_rate --group-by account__channel,lifecycle_row__cycle_index --order account__channel --csv ../dashboard/control_churn_by_channel.csv
../.venv/bin/mf query --metrics rebill_rate --group-by account__state --order rebill_rate --csv ../dashboard/control_rebill_by_state.csv
ls -1 ../dashboard/control_*.csv | wc -l
```

Expected: `23` (18 from Phase 1 plus 5).

- [ ] **Step 5: Document in METRICS.md**

Add the 10 new metrics to the dictionary in the existing format. Add a generator-assumptions section:

```markdown
## Generator assumptions behind the lifecycle metrics

Every churn, retention and rebill number on this dashboard is produced by a
**simulation whose parameters are stated below**, not by observed customer
behaviour. They are listed so any reader can see exactly which shape was assumed
and which was measured.

| Parameter | Value | Why this value |
|---|---|---|
| `PER_CYCLE_CHURN_HAZARD` | 20% / 11% / 7.5% / 6% | Declining hazard — subscription retention is not memoryless; survivors get stickier. A constant rate would produce a pure exponential, the one shape the spec argues is not inferable from three points |
| `DAY_ZERO_CANCEL_RATE` | 1.8% | Kept low: a double-digit day-0 cancel rate would signal a checkout problem, not the story this dataset tells |
| `NON_ACTIVATED_CHURN_MULTIPLIER` | 2.0 | **Planted relationship.** Accounts that never logged in churn twice as fast. This is an assumption, never a finding — see below |
| `PER_CYCLE_SKIP_RATE` | 8% | Skip is the replenishment-model metric Crystallize names; it has no SaaS equivalent |
| `PER_CYCLE_PAUSE_RATE` | 3.5% | Tracked separately from cancellation because Shopify asks for pauses as volume, not folded into churn |
| `PER_CYCLE_UPGRADE_RATE` | 2.2% | Without an upgrade arm, expansion MRR is structurally zero and NRR is capped at 100% by construction |
| `PER_CYCLE_DOWNGRADE_RATE` | 1.1% | Half the upgrade rate |

**On the planted churn relationship.** `NON_ACTIVATED_CHURN_MULTIPLIER` makes
non-activated accounts churn faster. The dbt test
`assert_planted_churn_multiplier_is_recovered` checks the pipeline recovers it.
That test validates the **joins and aggregations**, not the hypothesis: the
relationship was put there deliberately. No narrative in this project may present
"non-activation predicts churn" as a discovery. Recovering a planted effect
demonstrates the analysis works; it demonstrates nothing about pet owners.
```

- [ ] **Step 6: Final verification**

```bash
cd /home/iagoadvaz/projects/pawtrail-launch-analytics/.claude/worktrees/phase-2-lifecycle
.venv/bin/pytest -q 2>&1 | tail -3
cd pawtrail_dbt && ../.venv/bin/dbt build 2>&1 | tail -4
```

Expected: pytest with 31 passed (22 plus 9 new); `dbt build` with `ERROR=0`.

- [ ] **Step 7: Commit**

```bash
git add pawtrail_dbt/ dashboard/ METRICS.md
git commit -m "feat: verify planted churn effect is recovered, export lifecycle CSVs

Documents every generator parameter as a declared assumption. The planted
effect may never be presented as a finding."
```

---

## Self-Review

**Spec coverage (§3, in-scope items):**

| Item | Task |
|---|---|
| 2.1 Cancellation, pause, skip with date and reason | 1, 3, 4 |
| 2.1 Day-0 cancellation | 1 (`DAY_ZERO_CANCEL_RATE`), 4 |
| 2.2 Second and third cycle + renewal charge | 1, 3, 4 |
| 2.2 Rebill rate, GRR, ARR, MRR movement | 4, 5 |
| 2.7 Tier change → expansion MRR, NRR | 1, 5 |
| §3 "NRR requires 2.7" | 5, with an explicit check that expansion > 0 |
| §5.1 planted effect declared, never discovered | Global Constraints, Task 1 header, Task 6 Steps 2 and 5 |

**Out of scope for this plan, needing their own plans:** 2.3 payments, 2.4 returns, 2.5 referrals, 2.6 support.

**Type consistency:** `generate_subscription_lifecycle` returns the 7 columns `stg_subscription_events` reads (Task 3 Step 3). `int_subscription_state` produces `subscription_state_key`, `is_retained`, `churned_this_cycle`, `pet_tier_at_cycle` — all consumed by name in `fct_subscription_lifecycle` (Task 4) and in `assert_planted_churn_multiplier_is_recovered` (Task 6). `fct_mrr_movement` consumes `cycle_mrr_usd` and `state`, both produced in Task 4.
