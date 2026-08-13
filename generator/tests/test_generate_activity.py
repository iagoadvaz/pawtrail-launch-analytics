import datetime as dt

import numpy as np
import pandas as pd

from generator.generate_activity import (
    TARGET_MEDIAN_FULFILLMENT_DAYS,
    generate_digital_engagement,
    generate_kit_deliveries,
)


def _sample_subscriptions(states):
    return pd.DataFrame(
        {
            "account_id": [f"acct_{i}" for i in range(len(states))],
            "state": states,
            "pawtrail_signup_date": [dt.date(2026, 1, 5)] * len(states),
        }
    )


# A stand-in for the real Olist duration distribution: right-skewed, all positive.
DURATION_SAMPLE = np.array([3, 4, 5, 6, 7, 8, 10, 12, 15, 22, 35])


def test_problem_state_has_longer_average_delivery_duration():
    states = ["CA"] * 500 + ["OH"] * 500
    subs = _sample_subscriptions(states)

    result = generate_kit_deliveries(
        subs, duration_days_sample=DURATION_SAMPLE, problem_state="OH",
        problem_delay_penalty_days=10, seed=1,
    )

    avg_ca = result.loc[subs["state"] == "CA", "delivery_duration_days"].mean()
    avg_oh = result.loc[subs["state"] == "OH", "delivery_duration_days"].mean()

    assert avg_oh > avg_ca + 5


def test_durations_are_rescaled_to_the_fulfilment_target():
    """The empirical Olist median (~10-12 days) describes marketplace shipping,
    not subscription-kit fulfilment. It is rescaled so the SLA threshold in
    Task 8 sits at a plausible point on the distribution rather than passing
    or failing essentially everyone."""
    states = ["CA"] * 2000
    subs = _sample_subscriptions(states)

    result = generate_kit_deliveries(
        subs, duration_days_sample=DURATION_SAMPLE, problem_state="OH",
        problem_delay_penalty_days=10, seed=4,
    )

    median_duration = result["delivery_duration_days"].median()
    assert abs(median_duration - TARGET_MEDIAN_FULFILLMENT_DAYS) <= 2


def test_kit_delivered_date_is_always_after_signup():
    states = ["CA"] * 300
    subs = _sample_subscriptions(states)

    result = generate_kit_deliveries(
        subs, duration_days_sample=DURATION_SAMPLE, problem_state="OH",
        problem_delay_penalty_days=10, seed=2,
    )

    delivered = result.dropna(subset=["kit_delivered_date"])
    merged = delivered.merge(subs, on="account_id")
    # Strictly after: a kit cannot be fulfilled and delivered the same day the
    # account signed up. The old delay-vs-estimate model piled a large share of
    # accounts onto exactly day zero.
    assert (merged["kit_delivered_date"] > merged["pawtrail_signup_date"]).all()
    assert (result["delivery_duration_days"] >= 1).all()


def test_digital_engagement_zero_tasks_when_no_login():
    states = ["CA"] * 1000
    subs = _sample_subscriptions(states)

    result = generate_digital_engagement(subs, seed=3)

    never_logged_in = result[result["first_login_date"].isna()]
    assert (never_logged_in["care_tasks_completed_first_cycle"] == 0).all()
    assert len(never_logged_in) > 0  # sanity: the no-login probability actually fires
