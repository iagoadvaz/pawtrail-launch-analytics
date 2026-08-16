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
