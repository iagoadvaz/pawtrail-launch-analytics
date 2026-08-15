"""Grain tests for the attach-rate metrics.

`fct_weekly_attach` is a (state, week) spine carrying two snapshot columns:
`eligible_premium_accounts`, constant per state, and `cumulative_subscriptions`,
a running total. Both are semi-additive -- they sum across states within a week,
never across weeks. A measure declared `agg: sum` over either one answers any
query spanning more than one week by adding up seventeen weekly snapshots of a
base that never changed, and MetricFlow returns that number without complaint.

The consequence is not a rounding error. It inverts the launch verdict: the
ungrouped `attach_rate_vs_target` reads 0.699 -- 30% below the launch target --
on a launch that finished 33% above it.
"""

import pytest

TOTAL_SUBSCRIPTIONS = 3000
ELIGIBLE_PREMIUM_BASE = 15000
LAUNCH_STATES = 12
LAUNCH_TARGET = 0.15


def test_eligible_base_is_not_multiplied_by_the_number_of_weeks(mf_query):
    """The addressable universe is 15,000 accounts however the query is sliced.

    It is a generator constant, so any answer other than 15,000 is arithmetic
    the semantic layer invented -- 255,000 is 15,000 seen seventeen times.
    """
    rows = mf_query(["eligible_premium_accounts"])

    assert len(rows) == 1
    assert float(rows[0]["eligible_premium_accounts"]) == ELIGIBLE_PREMIUM_BASE


def test_ungrouped_attach_rate_is_the_launch_to_date_rate(mf_query):
    """Asked with no grouping, attach_rate must answer for the launch to date.

    3,000 of 15,000 eligible Premium accounts attached, so the rate is 0.20 and
    the launch finished at 1.33x its 15% target.
    """
    rows = mf_query(["attach_rate", "attach_rate_vs_target"])

    assert len(rows) == 1
    expected_rate = TOTAL_SUBSCRIPTIONS / ELIGIBLE_PREMIUM_BASE
    assert float(rows[0]["attach_rate"]) == pytest.approx(expected_rate, abs=1e-6)
    assert float(rows[0]["attach_rate_vs_target"]) == pytest.approx(
        expected_rate / LAUNCH_TARGET, abs=1e-6
    )


def test_state_grain_components_reconcile_with_the_national_totals(mf_query):
    """Split by state alone, the parts must still add up to the whole.

    This is the grouping the model's own comment used to forbid ("never query
    it grouped by state alone"), which is the tell that the measures were
    aggregating wrongly rather than that the question was invalid: "how did each
    state do over the launch" is exactly what a regional rollout asks.
    """
    rows = mf_query(
        ["cumulative_subscriptions", "eligible_premium_accounts"],
        group_by=["weekly_attach_row__state"],
    )

    assert len(rows) == LAUNCH_STATES
    assert sum(float(r["cumulative_subscriptions"]) for r in rows) == TOTAL_SUBSCRIPTIONS
    assert (
        sum(float(r["eligible_premium_accounts"]) for r in rows)
        == ELIGIBLE_PREMIUM_BASE
    )


def test_weekly_series_still_reports_each_week_on_its_own_snapshot(mf_query):
    """Regression guard on the fix above, not a defect of its own.

    Grouped by week the metric is already correct, because each row's snapshot
    is read on its own. Whatever makes the roll-ups above right must leave this
    series alone -- it is the launch-pulse chart, and it is the one reading of
    attach rate that has always been trustworthy.
    """
    rows = mf_query(
        ["attach_rate", "attach_rate_vs_target"],
        group_by=["weekly_attach_row__signup_week"],
    )

    assert len(rows) == 17
    rates = [float(r["attach_rate"]) for r in rows]
    assert rates == sorted(rates), "cumulative attach rate must never decrease"
    assert rates[-1] == pytest.approx(TOTAL_SUBSCRIPTIONS / ELIGIBLE_PREMIUM_BASE, abs=1e-6)
    assert float(rows[-1]["attach_rate_vs_target"]) == pytest.approx(
        TOTAL_SUBSCRIPTIONS / ELIGIBLE_PREMIUM_BASE / LAUNCH_TARGET, abs=1e-6
    )
