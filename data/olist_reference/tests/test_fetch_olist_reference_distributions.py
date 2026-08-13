import pandas as pd

from data.olist_reference.fetch_olist_reference_distributions import (
    compute_delivery_duration_distribution,
    compute_state_distribution,
    map_to_us_market,
)


def test_delivery_duration_is_purchase_to_delivery_in_days():
    orders = pd.DataFrame(
        {
            "order_id": ["a", "b", "c"],
            "order_purchase_timestamp": [
                "2018-01-01 10:00:00",
                "2018-01-01 10:00:00",
                "2018-01-01 10:00:00",
            ],
            "order_delivered_customer_date": [
                "2018-01-08 10:00:00",  # 7 days in transit
                "2018-01-04 10:00:00",  # 3 days in transit
                None,  # never delivered, must be dropped
            ],
        }
    )

    result = compute_delivery_duration_distribution(orders)

    assert list(result) == [7, 3]


def test_delivery_duration_drops_non_positive_durations():
    """Olist contains a handful of rows where the delivery timestamp precedes
    the purchase timestamp. They are data errors, not same-day deliveries, and
    would pull the rescaled fulfilment distribution toward zero."""
    orders = pd.DataFrame(
        {
            "order_id": ["a", "b"],
            "order_purchase_timestamp": ["2018-01-10 10:00:00", "2018-01-01 10:00:00"],
            "order_delivered_customer_date": ["2018-01-09 10:00:00", "2018-01-06 10:00:00"],
        }
    )

    result = compute_delivery_duration_distribution(orders)

    assert list(result) == [5]


def test_state_distribution_sums_to_one():
    customers = pd.DataFrame({"customer_state": ["SP", "SP", "RJ", "MG"]})

    result = compute_state_distribution(customers)

    assert result["SP"] == 0.5
    assert result["RJ"] == 0.25
    assert result["MG"] == 0.25
    assert abs(result.sum() - 1.0) < 1e-9


def test_map_to_us_market_preserves_shape_and_renormalises():
    source = pd.Series({"SP": 0.5, "RJ": 0.3, "MG": 0.15, "RR": 0.05}, name="share")

    result = map_to_us_market(source, n_states=3)

    # The long tail is dropped and the remainder renormalised to 1.0.
    assert len(result) == 3
    assert abs(result.sum() - 1.0) < 1e-9
    # Labels are US state codes, ranked to match the source concentration order.
    assert list(result.index) == ["CA", "TX", "FL"]
    # Relative ordering (the real, borrowed signal) survives the relabelling.
    assert result["CA"] > result["TX"] > result["FL"]


def test_map_to_us_market_keeps_every_state_above_a_usable_sample_size():
    """The smallest retained region must still be big enough that a per-state
    rate is not pure noise at the project's account volume (see Task 6's
    N_ACCOUNTS). Olist's untruncated tail goes down to ~0.05%, which at 3000
    accounts is one or two rows per state."""
    source = pd.Series(
        {f"S{i}": share for i, share in enumerate([0.42, 0.13, 0.12, 0.05, 0.04, 0.001])},
        name="share",
    )

    result = map_to_us_market(source, n_states=5)

    assert result.min() * 3000 >= 30
