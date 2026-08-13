"""Generate synthetic PawTrail subscription accounts for the launch window.

All identifiers and dates are fabricated. Only the *shape* of the state
distribution (imported from the real Olist reference, see
data/olist_reference/) is meaningful — account identities are not real.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

PET_TIERS = ["small", "medium", "large"]
CHANNELS = ["self_serve", "sales_assisted"]

# Per-state attach propensity multipliers are spread across this range, so attach
# rate varies by geography instead of being constant by construction. The 3x
# spread between the weakest and strongest region is what makes the spec's
# "attach rate by segment" views carry a discoverable signal.
STATE_ATTACH_PROPENSITY_RANGE = (0.6, 1.8)

MIN_PREMIUM_TENURE_DAYS = 30
MAX_PREMIUM_TENURE_DAYS = 900
# Tenure falls by this many days for each day later in the launch window, giving
# early adopters materially longer Premium histories.
TENURE_DECAY_DAYS_PER_DAY = 4.0
TENURE_NOISE_DAYS = 150.0

# Anchored to a Monday so that date_trunc('week', ...) in dbt lands on exactly
# the same boundary as the weekly marketing-spend buckets. A mid-week launch
# date silently breaks the spend join in fct_weekly_channel_economics: DuckDB
# truncates weeks to Monday, so Thursday-anchored spend weeks never match.
LAUNCH_DATE = dt.date(2026, 1, 5)


def _sample_signup_days(n_accounts: int, launch_days: int, rng: np.random.Generator) -> np.ndarray:
    """Sample signup day-offsets following a logistic (S-curve) adoption curve.

    The scale is chosen so the sampled range actually spans the launch window.
    With u clipped to (0.02, 0.98) the logistic quantile tops out at ~+/-3.89, so
    a scale of launch_days/8 puts the extremes at roughly day 2 and day 118 of a
    120-day window. A tighter scale (e.g. launch_days/12) collapses the range to
    days 21-98, leaving the first and last three weeks of the "launch window"
    with zero signups.
    """
    u = rng.uniform(0.02, 0.98, size=n_accounts)
    logistic_x = np.log(u / (1 - u))  # standard logistic quantile
    scale = launch_days / 8.0
    midpoint = launch_days / 2.0
    days = midpoint + logistic_x * scale
    return np.clip(days, 0, launch_days - 1).astype(int)


def _subscriber_state_distribution(
    state_distribution: pd.Series, rng: np.random.Generator
) -> pd.Series:
    """Tilt the eligible-base state shares by a per-state attach propensity.

    Sampling subscriber states straight from the eligible-base distribution makes
    attach rate identical in every state by construction, which silently empties
    every 'attach rate by segment' view in the spec. Drawing a propensity
    multiplier per state means attach rate becomes something the dashboard can
    actually discover.
    """
    # The spread is deterministic (linspace across the range) and only the
    # assignment of propensity to state is seeded. Drawing each multiplier
    # independently from a uniform would leave the observed spread to chance —
    # with a handful of states it lands below 1.5x roughly a third of the time,
    # which would make the accompanying test flaky rather than meaningful.
    propensity = rng.permutation(
        np.linspace(*STATE_ATTACH_PROPENSITY_RANGE, num=len(state_distribution))
    )
    tilted = state_distribution.to_numpy() * propensity
    return pd.Series(tilted / tilted.sum(), index=state_distribution.index)


def generate_subscriptions(
    n_accounts: int,
    launch_days: int,
    seed: int,
    state_distribution: pd.Series,
) -> pd.DataFrame:
    """Return one row per synthetic PawTrail subscription account."""
    rng = np.random.default_rng(seed)

    signup_days = _sample_signup_days(n_accounts, launch_days, rng)
    subscriber_states = _subscriber_state_distribution(state_distribution, rng)
    states = rng.choice(
        subscriber_states.index, size=n_accounts, p=subscriber_states.to_numpy()
    )
    channels = rng.choice(CHANNELS, size=n_accounts, p=[0.7, 0.3])
    pet_tiers = rng.choice(PET_TIERS, size=n_accounts, p=[0.4, 0.4, 0.2])

    # Long-tenured Premium accounts adopt an add-on earlier than accounts that
    # only just upgraded, so tenure decays across the launch window rather than
    # being independent of it. Without this, tenure segments are indistinguishable.
    tenure_trend = MAX_PREMIUM_TENURE_DAYS - signup_days * TENURE_DECAY_DAYS_PER_DAY
    premium_tenure_days = np.clip(
        tenure_trend + rng.normal(0, TENURE_NOISE_DAYS, size=n_accounts),
        MIN_PREMIUM_TENURE_DAYS,
        MAX_PREMIUM_TENURE_DAYS,
    ).astype(int)

    signup_dates = [LAUNCH_DATE + dt.timedelta(days=int(d)) for d in signup_days]

    return pd.DataFrame(
        {
            "account_id": [f"acct_{i:05d}" for i in range(n_accounts)],
            "state": states,
            "pet_tier": pet_tiers,
            "channel": channels,
            "premium_tenure_days": premium_tenure_days,
            "pawtrail_signup_date": signup_dates,
        }
    )
