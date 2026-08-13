"""Generate synthetic kit-delivery and digital-engagement events.

Delivery durations are resampled from the real Olist empirical purchase-to-
delivery distribution, then rescaled to a subscription-kit fulfilment range, so
the right-skewed shape of real logistics is preserved at a plausible absolute
level. One state is deliberately made worse than the rest so the launch
dashboard has a genuine root cause to surface.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

# Olist's median purchase-to-delivery is ~10-12 days, which describes a
# marketplace shipping a one-off order, not a subscription box operator
# fulfilling a recurring kit. The empirical *shape* (long right tail, occasional
# very slow deliveries) is what we want; the level is rescaled to this target so
# the SLA threshold in Task 8 sits at a meaningful point on the distribution.
# Calibrated against the 10-day SLA so the baseline lands near 88% on-time and
# the injected problem region near 56% — a clear, investigable gap where both
# ends remain plausible. (A larger penalty drives the problem region to a 0%
# on-time rate, which is not a root cause an analyst would find credible.)
TARGET_MEDIAN_FULFILLMENT_DAYS = 5.0

LOST_RATE_BASELINE = 0.02
LOST_RATE_PROBLEM_STATE = 0.08

NEVER_LOGS_IN_RATE = 0.15
FIRST_LOGIN_MEAN_DAYS = 5.0
MAX_FIRST_LOGIN_DAYS = 30
FIRST_CYCLE_TASK_COUNT = 8


def generate_kit_deliveries(
    subscriptions: pd.DataFrame,
    duration_days_sample: np.ndarray,
    problem_state: str,
    problem_delay_penalty_days: int,
    seed: int,
) -> pd.DataFrame:
    """Return one row per account describing its first-kit delivery outcome."""
    rng = np.random.default_rng(seed)
    n = len(subscriptions)
    is_problem_state = subscriptions["state"].values == problem_state

    sampled = rng.choice(duration_days_sample, size=n, replace=True)
    rescale = TARGET_MEDIAN_FULFILLMENT_DAYS / np.median(duration_days_sample)
    penalty = np.where(is_problem_state, problem_delay_penalty_days, 0)
    # At least one day: a kit is picked, packed, and shipped before it arrives.
    duration_days = np.maximum(
        np.round(sampled * rescale + penalty), 1
    ).astype(int)

    lost_mask = rng.uniform(size=n) < np.where(
        is_problem_state, LOST_RATE_PROBLEM_STATE, LOST_RATE_BASELINE
    )

    delivered_dates = [
        None if lost else signup + dt.timedelta(days=int(duration))
        for signup, duration, lost in zip(
            subscriptions["pawtrail_signup_date"], duration_days, lost_mask
        )
    ]

    return pd.DataFrame(
        {
            "account_id": subscriptions["account_id"],
            "kit_delivered_date": delivered_dates,
            "kit_lost": lost_mask,
            "delivery_duration_days": duration_days,
        }
    )


def generate_digital_engagement(subscriptions: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Return one row per account describing its first-cycle digital activity."""
    rng = np.random.default_rng(seed)
    n = len(subscriptions)

    never_logs_in = rng.uniform(size=n) < NEVER_LOGS_IN_RATE

    # Right-skewed, not uniform: accounts that engage at all tend to do so within
    # the first few days. A uniform 0-20 day draw would put only a third of
    # logins inside the 7-day window purely as an artefact of the sampler, making
    # the 7-day digital activation rate a property of the generator rather than
    # something the funnel can meaningfully report.
    days_to_first_login = np.minimum(
        np.round(rng.exponential(FIRST_LOGIN_MEAN_DAYS, size=n)),
        MAX_FIRST_LOGIN_DAYS,
    ).astype(int)

    # Accounts that come back quickly complete more of the first-cycle tasks, so
    # task completion carries a signal instead of being uniform noise.
    task_rate = np.clip(1.0 - days_to_first_login / MAX_FIRST_LOGIN_DAYS, 0.05, 1.0)
    tasks_completed = np.where(
        never_logs_in, 0, rng.binomial(FIRST_CYCLE_TASK_COUNT, task_rate)
    )

    first_login_date = [
        None if skip else signup + dt.timedelta(days=int(d))
        for signup, d, skip in zip(
            subscriptions["pawtrail_signup_date"], days_to_first_login, never_logs_in
        )
    ]

    return pd.DataFrame(
        {
            "account_id": subscriptions["account_id"],
            "first_login_date": first_login_date,
            "care_tasks_completed_first_cycle": tasks_completed,
        }
    )
