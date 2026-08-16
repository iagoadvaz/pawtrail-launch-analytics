"""Orchestrate the full synthetic data generation pipeline and write dbt seeds."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from data.olist_reference.fetch_olist_reference_distributions import (
    OUTPUT_DIR as _OLIST_REFERENCE_OUTPUT_DIR,
)
from generator.generate_activity import generate_digital_engagement, generate_kit_deliveries
from generator.generate_subscription_lifecycle import generate_subscription_lifecycle
from generator.generate_business_data import (
    generate_marketing_spend,
    generate_premium_base,
    generate_pricing,
    generate_sales_pitches,
)
from generator.generate_subscriptions import LAUNCH_DATE, generate_subscriptions

REFERENCE_DIR = _OLIST_REFERENCE_OUTPUT_DIR
SEEDS_DIR = Path(__file__).parent.parent / "pawtrail_dbt" / "seeds"

N_ACCOUNTS = 3000
LAUNCH_DAYS = 120
SEED = 42
PROBLEM_STATE = "OH"
# Calibrated against the 10-day kit SLA: this lands the problem region near
# 56% on-time (among kits that actually get delivered) against an ~88%
# baseline. The mart-layer on-time rate counts lost kits as SLA failures too,
# which lands the problem region around 51% there instead -- both figures are
# correct, just in different frames. A larger penalty (the original 12) pushes
# it to 0%, which reads as a broken generator rather than an operational
# problem.
PROBLEM_DELAY_PENALTY_DAYS = 5
# Kept well above N_ACCOUNTS so the resulting attach rate stays realistic (< 100%).
TOTAL_ELIGIBLE_PREMIUM_ACCOUNTS = 15000

# Independent seeds per generator. Reusing one seed across generators draws from
# the same stream at different offsets, which is fragile: reordering a draw in
# one generator silently changes the values every other generator produces.
SUBSCRIPTION_SEED = SEED
DELIVERY_SEED = SEED + 1
ENGAGEMENT_SEED = SEED + 2
SPEND_SEED = SEED + 3
PITCH_SEED = SEED + 4
LIFECYCLE_SEED = SEED + 5


def _load_reference_distributions() -> tuple[pd.Series, "pd.Series[int]"]:
    state_distribution = pd.read_csv(
        REFERENCE_DIR / "reference_state_distribution.csv", index_col=0
    )["share"]
    duration_days_sample = pd.read_csv(REFERENCE_DIR / "reference_delivery_durations.csv")[
        "duration_days"
    ].to_numpy()
    return state_distribution, duration_days_sample


def build_seeds() -> None:
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)

    state_distribution, duration_days_sample = _load_reference_distributions()

    subscriptions = generate_subscriptions(
        n_accounts=N_ACCOUNTS,
        launch_days=LAUNCH_DAYS,
        seed=SUBSCRIPTION_SEED,
        state_distribution=state_distribution,
    )
    kit_deliveries = generate_kit_deliveries(
        subscriptions,
        duration_days_sample=duration_days_sample,
        problem_state=PROBLEM_STATE,
        problem_delay_penalty_days=PROBLEM_DELAY_PENALTY_DAYS,
        seed=DELIVERY_SEED,
    )
    digital_engagement = generate_digital_engagement(subscriptions, seed=ENGAGEMENT_SEED)
    premium_base = generate_premium_base(state_distribution, TOTAL_ELIGIBLE_PREMIUM_ACCOUNTS)
    pricing = generate_pricing()
    marketing_spend = generate_marketing_spend(LAUNCH_DATE, LAUNCH_DAYS, seed=SPEND_SEED)
    sales_pitches = generate_sales_pitches(subscriptions, seed=PITCH_SEED)

    subscription_events = generate_subscription_lifecycle(
        subscriptions,
        digital_engagement,
        launch_days=LAUNCH_DAYS,
        seed=LIFECYCLE_SEED,
    )

    subscriptions.to_csv(SEEDS_DIR / "raw_subscriptions.csv", index=False)
    kit_deliveries.to_csv(SEEDS_DIR / "raw_kit_deliveries.csv", index=False)
    digital_engagement.to_csv(SEEDS_DIR / "raw_digital_engagement.csv", index=False)
    premium_base.to_csv(SEEDS_DIR / "raw_premium_base.csv", index=False)
    pricing.to_csv(SEEDS_DIR / "raw_pricing.csv", index=False)
    marketing_spend.to_csv(SEEDS_DIR / "raw_marketing_spend.csv", index=False)
    sales_pitches.to_csv(SEEDS_DIR / "raw_sales_pitches.csv", index=False)
    subscription_events.to_csv(SEEDS_DIR / "raw_subscription_events.csv", index=False)


if __name__ == "__main__":
    build_seeds()
