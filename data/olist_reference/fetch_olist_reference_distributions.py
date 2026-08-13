"""Derive empirical reference distributions from the real Olist dataset.

These distributions (delivery duration in days, regional concentration) are used
downstream only as sampling scaffolds for synthetic PawTrail data. No Olist
customer, order, or product identity is reused.
"""
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).parent / "raw"
OUTPUT_DIR = Path(__file__).parent

# US state codes ordered by population, used to relabel Olist's regional
# concentration curve onto a US market. Rank i of the source distribution maps
# to rank i here, so the *shape* is preserved and only the label changes.
US_STATES_BY_RANK = [
    "CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI", "NJ", "VA",
    "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
]


def compute_delivery_duration_distribution(orders: pd.DataFrame) -> pd.Series:
    """Return purchase-to-delivery duration in whole days for delivered orders.

    This is deliberately *not* `actual - estimated`. Olist's estimated delivery
    dates are padded by roughly 10-12 days, so the estimate delta describes
    forecast conservatism rather than how long a shipment actually took.
    """
    delivered = orders.dropna(
        subset=["order_delivered_customer_date", "order_purchase_timestamp"]
    ).copy()
    delivered["order_delivered_customer_date"] = pd.to_datetime(
        delivered["order_delivered_customer_date"]
    )
    delivered["order_purchase_timestamp"] = pd.to_datetime(
        delivered["order_purchase_timestamp"]
    )
    duration_days = (
        delivered["order_delivered_customer_date"]
        - delivered["order_purchase_timestamp"]
    ).dt.days
    # A small number of Olist rows have a delivery timestamp before the purchase
    # timestamp. Those are data errors, not instant deliveries.
    duration_days = duration_days[duration_days > 0]
    return duration_days.reset_index(drop=True).rename("duration_days")


def compute_state_distribution(customers: pd.DataFrame) -> pd.Series:
    """Return the share of customers per state, summing to 1.0."""
    counts = customers["customer_state"].value_counts()
    return (counts / counts.sum()).rename("share")


def map_to_us_market(state_distribution: pd.Series, n_states: int) -> pd.Series:
    """Relabel the top `n_states` regions onto US state codes, renormalised.

    Two problems are solved at once. First, PawTrail prices in USD, so Brazilian
    state codes would be internally inconsistent in every chart. Second, Olist's
    untruncated tail reaches ~0.05% share, which at this project's account volume
    is one or two accounts per state — enough to let a meaningless 0%-or-100%
    rate outrank the deliberately injected problem region on any sorted chart.

    Only the concentration curve is borrowed. No claim is made about the real
    geographic distribution of any US market.
    """
    if n_states > len(US_STATES_BY_RANK):
        raise ValueError(
            f"n_states={n_states} exceeds the {len(US_STATES_BY_RANK)} available labels"
        )

    top = state_distribution.sort_values(ascending=False).head(n_states)
    renormalised = top / top.sum()
    renormalised.index = US_STATES_BY_RANK[:n_states]
    renormalised.index.name = "state"
    return renormalised.rename("share")


def main() -> None:
    orders = pd.read_csv(RAW_DIR / "olist_orders_dataset.csv")
    customers = pd.read_csv(RAW_DIR / "olist_customers_dataset.csv")

    duration_days = compute_delivery_duration_distribution(orders)
    duration_days.to_csv(OUTPUT_DIR / "reference_delivery_durations.csv", index=False)

    state_share = map_to_us_market(compute_state_distribution(customers), n_states=12)
    state_share.to_csv(OUTPUT_DIR / "reference_state_distribution.csv")


if __name__ == "__main__":
    main()
