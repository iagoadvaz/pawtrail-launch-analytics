"""Generate synthetic marketing spend, sales pipeline, pricing, and the
addressable Premium account base — the inputs needed for CAC, attach-rate,
and unit-economics metrics."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

PET_TIERS = ["small", "medium", "large"]

# Per-state sales win propensity. Spread deterministically across this range and
# only the state assignment is seeded, so the overall win rate emerges from the
# generated pipeline instead of being a constant handed to the generator.
WIN_PROPENSITY_RANGE = (0.22, 0.48)


def generate_premium_base(state_distribution: pd.Series, total_eligible: int) -> pd.DataFrame:
    """Return the addressable Premium account count per state (the attach-rate denominator)."""
    counts = (state_distribution * total_eligible).round().astype(int)
    return pd.DataFrame({"state": counts.index, "eligible_premium_accounts": counts.values})


def generate_pricing() -> pd.DataFrame:
    """Return monthly price and kit COGS per pet tier."""
    return pd.DataFrame(
        {
            "pet_tier": PET_TIERS,
            "monthly_price_usd": [19.99, 29.99, 39.99],
            "kit_cogs_usd": [7.0, 10.0, 13.0],
            "shipping_cost_usd": [3.5, 4.5, 5.5],
        }
    )


def generate_marketing_spend(launch_date: dt.date, launch_days: int, seed: int) -> pd.DataFrame:
    """Return weekly marketing spend by channel, ramping over the launch.

    Week starts are snapped back to the Monday of the launch week so they sit on
    the same boundary DuckDB's date_trunc('week', ...) produces downstream. Without
    this, the CAC join in fct_weekly_channel_economics matches zero rows.
    """
    rng = np.random.default_rng(seed)
    n_weeks = launch_days // 7 + 1
    weeks = np.arange(n_weeks)
    first_week_start = launch_date - dt.timedelta(days=launch_date.weekday())
    week_start_dates = [first_week_start + dt.timedelta(days=int(w * 7)) for w in weeks]

    paid_spend = np.clip(500 + weeks * 40 + rng.normal(0, 50, size=n_weeks), 100, None)
    sales_spend = np.clip(1200 + weeks * 20 + rng.normal(0, 80, size=n_weeks), 300, None)

    return pd.DataFrame(
        {
            "week_start_date": list(week_start_dates) * 2,
            "channel": ["self_serve"] * n_weeks + ["sales_assisted"] * n_weeks,
            "spend_usd": np.concatenate([paid_spend, sales_spend]).round(2),
        }
    )


def generate_sales_pitches(subscriptions: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Return one row per sales-assisted pitch, won or lost, tagged by state.

    Every won pitch corresponds to a sales-assisted subscription that actually
    exists, so the pipeline stays internally consistent. The number of *lost*
    pitches is drawn per state from a varying win propensity, which means the
    reported win rate is an emergent property of the generated pipeline and
    varies by region.

    The earlier approach — dividing the won count by a fixed `assumed_win_rate`
    — made the headline win rate exactly the constant the generator was handed,
    so the dashboard would have displayed an assumption as if it were a finding.
    """
    rng = np.random.default_rng(seed)
    won = subscriptions[subscriptions["channel"] == "sales_assisted"]

    states = sorted(subscriptions["state"].unique())
    propensity = dict(
        zip(states, rng.permutation(np.linspace(*WIN_PROPENSITY_RANGE, num=len(states))))
    )

    rows = []
    for state, pitch_date in zip(won["state"], won["pawtrail_signup_date"]):
        rows.append({"state": state, "pitch_date": pitch_date, "won": True})
        # Losses before this win: geometric in the state's win propensity, so
        # wins / total converges on that propensity rather than on a constant.
        # They are dated to the won pitch they preceded, which is enough for the
        # semantic layer to have an aggregation time dimension.
        for _ in range(int(rng.geometric(propensity[state])) - 1):
            rows.append({"state": state, "pitch_date": pitch_date, "won": False})

    pitches = pd.DataFrame(rows)
    pitches.insert(0, "pitch_id", [f"pitch_{i:05d}" for i in range(len(pitches))])
    return pitches
