import pandas as pd

from generator.generate_subscriptions import LAUNCH_DATE, generate_subscriptions

REFERENCE_STATES = pd.Series({"CA": 0.6, "TX": 0.3, "FL": 0.1})


def test_generates_requested_number_of_accounts():
    df = generate_subscriptions(
        n_accounts=500, launch_days=120, seed=42, state_distribution=REFERENCE_STATES
    )

    assert len(df) == 500
    assert df["account_id"].is_unique


def test_signup_dates_fall_within_launch_window():
    df = generate_subscriptions(
        n_accounts=500, launch_days=120, seed=42, state_distribution=REFERENCE_STATES
    )

    min_date = df["pawtrail_signup_date"].min()
    max_date = df["pawtrail_signup_date"].max()

    assert (max_date - min_date).days <= 120


def test_same_seed_is_deterministic():
    df1 = generate_subscriptions(200, 120, seed=7, state_distribution=REFERENCE_STATES)
    df2 = generate_subscriptions(200, 120, seed=7, state_distribution=REFERENCE_STATES)

    pd.testing.assert_frame_equal(df1, df2)


def test_adoption_curve_is_not_uniform():
    """The first week should have materially fewer signups than the middle of
    the launch window, confirming an S-curve rather than a flat ramp.

    Weeks are measured from the launch date, not from the first observed signup,
    so this also catches a curve whose sampled range never reaches the start of
    the window: comparing week 1 against week 9 would pass trivially if week 1
    were structurally empty.
    """
    df = generate_subscriptions(
        n_accounts=2000, launch_days=120, seed=42, state_distribution=REFERENCE_STATES
    )
    # pd.to_datetime is required: the generator emits datetime.date objects, so
    # the raw column is object dtype and the .dt accessor would raise.
    days = (pd.to_datetime(df["pawtrail_signup_date"]) - pd.Timestamp(LAUNCH_DATE)).dt.days

    first_week = ((days >= 0) & (days < 7)).sum()
    middle_week = ((days >= 56) & (days < 63)).sum()
    last_week = ((days >= 113) & (days < 120)).sum()

    # The curve must actually start and finish inside the declared window.
    assert first_week > 0
    assert last_week > 0
    # ...and be S-shaped, not a flat ramp.
    assert middle_week > 3 * first_week


def test_attach_propensity_varies_by_state():
    """Subscriber state share must diverge from the eligible-base state share,
    otherwise attach rate is identical in every state by construction and every
    'attach rate by segment' chart in the spec is flat noise."""
    df = generate_subscriptions(
        n_accounts=4000, launch_days=120, seed=42, state_distribution=REFERENCE_STATES
    )

    subscriber_share = df["state"].value_counts(normalize=True)
    # Attach rate by state is proportional to subscriber share / base share.
    relative_attach = subscriber_share / REFERENCE_STATES

    assert relative_attach.max() / relative_attach.min() > 1.5


def test_longer_premium_tenure_adopts_earlier():
    """Premium tenure must correlate negatively with signup day, so 'attach rate
    by Premium tenure' and 'conversion lag' carry a real signal rather than
    reproducing the same flat rate in every bucket."""
    df = generate_subscriptions(
        n_accounts=4000, launch_days=120, seed=42, state_distribution=REFERENCE_STATES
    )
    days = (pd.to_datetime(df["pawtrail_signup_date"]) - pd.Timestamp(LAUNCH_DATE)).dt.days

    assert days.corr(df["premium_tenure_days"]) < -0.2
