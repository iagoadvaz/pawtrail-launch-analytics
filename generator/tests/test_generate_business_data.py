import datetime as dt

import pandas as pd

from generator.generate_business_data import (
    generate_marketing_spend,
    generate_premium_base,
    generate_pricing,
    generate_sales_pitches,
)


def test_premium_base_scales_with_state_distribution():
    state_distribution = pd.Series({"CA": 0.6, "TX": 0.4})

    result = generate_premium_base(state_distribution, total_eligible=1000)

    by_state = result.set_index("state")["eligible_premium_accounts"]
    assert by_state["CA"] == 600
    assert by_state["TX"] == 400


def test_pricing_has_one_row_per_tier_with_positive_margin():
    result = generate_pricing()

    assert len(result) == 3
    margin = result["monthly_price_usd"] - result["kit_cogs_usd"] - result["shipping_cost_usd"]
    assert (margin > 0).all()


def test_marketing_spend_covers_full_launch_window():
    result = generate_marketing_spend(launch_date=dt.date(2026, 1, 5), launch_days=120, seed=1)

    assert result["week_start_date"].min() == dt.date(2026, 1, 5)
    assert (result["week_start_date"].max() - dt.date(2026, 1, 5)).days <= 120
    assert set(result["channel"]) == {"self_serve", "sales_assisted"}
    assert (result["spend_usd"] > 0).all()


def test_marketing_spend_weeks_are_monday_aligned():
    """Spend weeks must start on the same weekday boundary DuckDB's
    date_trunc('week', ...) produces (Monday), or the CAC join in
    fct_weekly_channel_economics matches zero rows and every CAC comes out
    NULL without any test failing."""
    result = generate_marketing_spend(launch_date=dt.date(2026, 1, 5), launch_days=120, seed=1)

    assert all(d.weekday() == 0 for d in result["week_start_date"])


def test_sales_pitches_win_count_matches_sales_assisted_subscriptions():
    subscriptions = pd.DataFrame(
        {
            "account_id": [f"a{i}" for i in range(10)],
            "state": ["CA"] * 5 + ["TX"] * 5,
            "pawtrail_signup_date": [dt.date(2026, 1, 5)] * 10,
            "channel": ["sales_assisted"] * 4 + ["self_serve"] * 6,
        }
    )

    result = generate_sales_pitches(subscriptions, seed=5)

    assert result["won"].sum() == 4
    assert len(result) > 4  # some pitches must have been lost
    assert result["pitch_id"].is_unique


def test_win_rate_is_emergent_not_a_fixed_constant():
    """Win rate must vary by state rather than reproducing a single assumed
    value. A hard-coded win rate turns the dashboard's headline stat tile into
    a restatement of a generator assumption."""
    subscriptions = pd.DataFrame(
        {
            "account_id": [f"a{i}" for i in range(3000)],
            "state": ["CA", "TX", "FL"] * 1000,
            "pawtrail_signup_date": [dt.date(2026, 1, 5)] * 3000,
            "channel": ["sales_assisted"] * 3000,
        }
    )

    result = generate_sales_pitches(subscriptions, seed=5)
    win_rate_by_state = result.groupby("state")["won"].mean()

    assert win_rate_by_state.max() - win_rate_by_state.min() > 0.05
