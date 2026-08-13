# PawTrail Launch Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portfolio case study simulating the 0–120 day launch of PawTrail, a fictional pet-care subscription add-on, producing a dbt project with a MetricFlow semantic layer and a published Tableau Public dashboard.

**Architecture:** A seeded Python generator produces synthetic subscription, engagement, delivery, and business data (with delivery-timing and geography patterns resampled from the real, public Olist dataset). dbt loads this as seeds and transforms it through staging → intermediate → marts layers in DuckDB. A dbt Semantic Layer (MetricFlow) declares the launch metrics once, queried by both verification commands and the Tableau Public dashboard.

**Tech Stack:** Python 3.11+ (pandas, numpy, pytest), dbt-core + dbt-duckdb, dbt Semantic Layer / MetricFlow (`mf` CLI), DuckDB, Tableau Public.

## Global Constraints

- Entire repository (code, comments, commit messages, docs) must be written in English — no exceptions.
- Product, company, and all data are entirely fictional (PawTrail); the repository must never claim any real company affiliation.
- Only the Olist Brazilian E-Commerce dataset's *statistical distributions* (delivery delay, state share) may be reused — never its actual customer/order identities.
- Warehouse engine is DuckDB only, run locally — no cloud account required to reproduce the project.
- dbt tests/assertions for a model are written before that model's SQL ("test-first" — see spec §8).
- Out of scope: 12-month churn, NRR, LTV, LTV:CAC, Rule of 40, Magic Number, Quick Ratio, orchestration tooling, CI/CD, multi-user auth, Sigma implementation.
- Spec reference: `docs/superpowers/specs/2026-08-12-pawtrail-launch-analytics-design.md`

---

## Task 1: Project scaffolding & environment setup

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `pawtrail_dbt/dbt_project.yml`
- Create: `pawtrail_dbt/profiles.yml`

**Interfaces:**
- Produces: a working Python environment (`pip install -r requirements.txt`) and a `pawtrail` dbt profile pointing at a local `pawtrail_dbt/pawtrail.duckdb` file, both of which every later task depends on.

- [ ] **Step 1: Create `requirements.txt`**

```
dbt-core>=1.8
dbt-duckdb>=1.8
dbt-metricflow>=0.6
pandas>=2.2
numpy>=1.26
pytest>=8.0
```

- [ ] **Step 2: Create `.gitignore`**

```
# Python
__pycache__/
*.pyc
.venv/
venv/

# dbt
pawtrail_dbt/target/
pawtrail_dbt/dbt_packages/
pawtrail_dbt/logs/

# DuckDB
*.duckdb

# Real Olist raw download (large; only derived reference distributions are committed)
data/olist_reference/raw/

# OS
.DS_Store
```

- [ ] **Step 3: Create `pyproject.toml` (enables `from generator...` / `from data...` imports in tests without `__init__.py` boilerplate)**

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["data", "generator"]
```

- [ ] **Step 4: Create `pawtrail_dbt/dbt_project.yml`**

```yaml
name: 'pawtrail'
version: '1.0.0'
config-version: 2

profile: 'pawtrail'

model-paths: ["models"]
seed-paths: ["seeds"]
test-paths: ["tests"]
macro-paths: ["macros"]

target-path: "target"
clean-targets:
  - "target"
  - "dbt_packages"

# Activation thresholds live here rather than being repeated as literals inside
# model SQL, so the SLA the funnel enforces, the metric definitions, and
# METRICS.md can never drift apart.
vars:
  kit_sla_days: 10
  digital_activation_window_days: 7
  at_risk_no_login_days: 14
  combined_activation_window_days: 30

models:
  pawtrail:
    staging:
      +materialized: view
    intermediate:
      +materialized: view
    marts:
      +materialized: table
```

- [ ] **Step 5: Create `pawtrail_dbt/profiles.yml` (no secrets — safe to commit)**

```yaml
pawtrail:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: 'pawtrail.duckdb'
      threads: 4
```

- [ ] **Step 6: Install dependencies and verify the environment**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "import dbt, duckdb, pandas, numpy, pytest; print('environment ok')"
```

Expected: prints `environment ok` with no import errors.

- [ ] **Step 7: Verify dbt can connect to DuckDB**

```bash
cd pawtrail_dbt
dbt debug --profiles-dir .
cd ..
```

Expected: output ends with `All checks passed!`.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore pyproject.toml pawtrail_dbt/dbt_project.yml pawtrail_dbt/profiles.yml
git commit -m "Scaffold Python and dbt project setup"
```

---

## Task 2: Extract Olist reference distributions

**Files:**
- Create: `data/olist_reference/README.md`
- Create: `data/olist_reference/fetch_olist_reference_distributions.py`
- Test: `data/olist_reference/tests/test_fetch_olist_reference_distributions.py`

**Interfaces:**
- Produces: `compute_delivery_duration_distribution(orders: pd.DataFrame) -> pd.Series`, `compute_state_distribution(customers: pd.DataFrame) -> pd.Series`, and `map_to_us_market(state_distribution: pd.Series, n_states: int) -> pd.Series`, and (when run as a script) the committed files `data/olist_reference/reference_delivery_durations.csv` and `data/olist_reference/reference_state_distribution.csv`, consumed by Task 6's `build_seeds.py`.
- **Why duration, not delay-vs-estimate:** Olist's `order_estimated_delivery_date` is heavily padded — actual deliveries land ~10-12 days *early* on average. Using `actual - estimated` as if it were delay against a promised fulfilment window produces a distribution centred well below zero, which downstream would collapse onto a floor and make most kits arrive the day the account signed up. The purchase-to-delivery *duration* is the quantity that actually corresponds to "how long did the kit take to arrive".

- [ ] **Step 1: Document how to obtain the real Olist dataset**

Create `data/olist_reference/README.md`:

```markdown
# Olist reference distributions

This project borrows two *statistical distributions* from the real, public
[Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(Kaggle) to make PawTrail's synthetic kit-delivery logistics and geography
realistic. No Olist customer, order, or product identity is reused — only
the empirical shape of delivery durations and regional concentration.

Two deliberate transformations are applied, both documented in the design
spec §4:

- **Delivery duration, not delay-vs-estimate.** Olist's estimated delivery
  dates are heavily padded, so `actual - estimated` is centred around 10-12
  days *early* and does not describe how long a shipment took. We use
  purchase-to-delivery duration instead, then rescale it to a subscription-kit
  fulfilment range (see `TARGET_MEDIAN_FULFILLMENT_DAYS` in the generator).
- **Regional shape mapped onto a US market.** PawTrail is priced in USD, so
  Brazilian state codes would be internally inconsistent. We keep Olist's
  *concentration curve* (one dominant region, a long tail) and relabel the
  top N regions onto US state codes by rank. The shape is real; the labels
  are not, and nothing is claimed about the US market itself.

## To regenerate the reference files

1. Download the dataset via the Kaggle CLI (requires a free Kaggle account
   and API token):

   ```bash
   kaggle datasets download -d olistbr/brazilian-ecommerce -p data/olist_reference/raw --unzip
   ```

2. Run the extraction script:

   ```bash
   python data/olist_reference/fetch_olist_reference_distributions.py
   ```

This writes `reference_delivery_durations.csv` and
`reference_state_distribution.csv` into this directory. Those two small
files are committed to the repo; the raw Olist download itself is not
(see `.gitignore`).
```

- [ ] **Step 2: Write the failing test**

Create `data/olist_reference/tests/test_fetch_olist_reference_distributions.py`:

```python
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
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
pytest data/olist_reference/tests/test_fetch_olist_reference_distributions.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'data.olist_reference.fetch_olist_reference_distributions'`.

- [ ] **Step 4: Implement the module**

Create `data/olist_reference/fetch_olist_reference_distributions.py`:

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest data/olist_reference/tests/test_fetch_olist_reference_distributions.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Download the real dataset and generate the committed reference files**

Follow `data/olist_reference/README.md` (requires a Kaggle account), then:

```bash
python data/olist_reference/fetch_olist_reference_distributions.py
```

Expected: `data/olist_reference/reference_delivery_durations.csv` and `reference_state_distribution.csv` are created.

- [ ] **Step 7: Commit**

```bash
git add data/olist_reference/README.md data/olist_reference/fetch_olist_reference_distributions.py data/olist_reference/tests/test_fetch_olist_reference_distributions.py data/olist_reference/reference_delivery_durations.csv data/olist_reference/reference_state_distribution.csv
git commit -m "Extract real Olist delivery-delay and state reference distributions"
```

---

## Task 3: Generate synthetic subscription accounts

**Files:**
- Create: `generator/generate_subscriptions.py`
- Test: `generator/tests/test_generate_subscriptions.py`

**Interfaces:**
- Consumes: a `state_distribution: pd.Series` shaped like the output of Task 2's `compute_state_distribution` (index = state code, values = share summing to 1.0).
- Produces: `generate_subscriptions(n_accounts: int, launch_days: int, seed: int, state_distribution: pd.Series) -> pd.DataFrame` with columns `account_id, state, pet_tier, channel, premium_tenure_days, pawtrail_signup_date`, and the module constant `LAUNCH_DATE: datetime.date` — imported by Task 5's business-data generator so every generator agrees on the same launch calendar.

- [ ] **Step 1: Write the failing tests**

Create `generator/tests/test_generate_subscriptions.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest generator/tests/test_generate_subscriptions.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'generator.generate_subscriptions'`.

- [ ] **Step 3: Implement the generator**

Create `generator/generate_subscriptions.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest generator/tests/test_generate_subscriptions.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add generator/generate_subscriptions.py generator/tests/test_generate_subscriptions.py
git commit -m "Generate synthetic PawTrail subscription accounts with S-curve adoption"
```

---

## Task 4: Generate digital engagement & kit delivery events with an injected risk segment

**Files:**
- Create: `generator/generate_activity.py`
- Test: `generator/tests/test_generate_activity.py`

**Interfaces:**
- Consumes: the `subscriptions: pd.DataFrame` produced by Task 3 (`account_id, state, pawtrail_signup_date` columns required), and a `duration_days_sample: np.ndarray` shaped like Task 2's `reference_delivery_durations.csv` values.
- Produces: `generate_kit_deliveries(subscriptions, duration_days_sample, problem_state, problem_delay_penalty_days, seed) -> pd.DataFrame` with columns `account_id, kit_delivered_date, kit_lost, delivery_duration_days`; `generate_digital_engagement(subscriptions, seed) -> pd.DataFrame` with columns `account_id, first_login_date, care_tasks_completed_first_cycle`. Consumed by Task 6's `build_seeds.py`.

- [ ] **Step 1: Write the failing tests**

Create `generator/tests/test_generate_activity.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest generator/tests/test_generate_activity.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'generator.generate_activity'`.

- [ ] **Step 3: Implement the generator**

Create `generator/generate_activity.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest generator/tests/test_generate_activity.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add generator/generate_activity.py generator/tests/test_generate_activity.py
git commit -m "Generate synthetic kit-delivery and digital-engagement events"
```

---

## Task 5: Generate synthetic business data (pricing, premium base, marketing spend, sales pitches)

**Files:**
- Create: `generator/generate_business_data.py`
- Test: `generator/tests/test_generate_business_data.py`

**Interfaces:**
- Consumes: `LAUNCH_DATE` from Task 3's `generator.generate_subscriptions`; a `subscriptions: pd.DataFrame` with `channel` and `state` columns for `generate_sales_pitches`.
- Produces: `generate_premium_base(state_distribution, total_eligible) -> pd.DataFrame` (`state, eligible_premium_accounts`); `generate_pricing() -> pd.DataFrame` (`pet_tier, monthly_price_usd, kit_cogs_usd, shipping_cost_usd`); `generate_marketing_spend(launch_date, launch_days, seed) -> pd.DataFrame` (`week_start_date, channel, spend_usd`); `generate_sales_pitches(subscriptions, seed) -> pd.DataFrame` (`pitch_id, state, pitch_date, won`). Consumed by Task 6's `build_seeds.py`.

- [ ] **Step 1: Write the failing tests**

Create `generator/tests/test_generate_business_data.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest generator/tests/test_generate_business_data.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'generator.generate_business_data'`.

- [ ] **Step 3: Implement the generator**

Create `generator/generate_business_data.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest generator/tests/test_generate_business_data.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add generator/generate_business_data.py generator/tests/test_generate_business_data.py
git commit -m "Generate synthetic pricing, premium base, marketing spend, and sales pitch data"
```

---

## Task 6: Orchestrate generators into dbt seeds

**Files:**
- Create: `generator/build_seeds.py`
- Test: `generator/tests/test_build_seeds.py`

**Interfaces:**
- Consumes: every generator function from Tasks 3–5, and the reference CSVs from Task 2.
- Produces: seven CSV files under `pawtrail_dbt/seeds/` — `raw_subscriptions.csv`, `raw_kit_deliveries.csv`, `raw_digital_engagement.csv`, `raw_premium_base.csv`, `raw_pricing.csv`, `raw_marketing_spend.csv`, `raw_sales_pitches.csv` — consumed by Task 7's `dbt seed`.

- [ ] **Step 1: Write the failing test**

Create `generator/tests/test_build_seeds.py`:

```python
import pandas as pd
import pytest

import generator.build_seeds as build_seeds_module
from generator.build_seeds import N_ACCOUNTS, PROBLEM_STATE, build_seeds


@pytest.fixture(autouse=True)
def _fixture_reference_and_seeds_dirs(tmp_path, monkeypatch):
    """Point the reference-distribution loader and seeds writer at small,
    fast fixture locations instead of the real Olist download."""
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir()
    pd.Series({"CA": 0.6, "TX": 0.3, PROBLEM_STATE: 0.1}, name="share").to_csv(
        ref_dir / "reference_state_distribution.csv"
    )
    pd.DataFrame({"duration_days": [3, 5, 6, 7, 9, 14]}).to_csv(
        ref_dir / "reference_delivery_durations.csv", index=False
    )
    monkeypatch.setattr(build_seeds_module, "REFERENCE_DIR", ref_dir)
    monkeypatch.setattr(build_seeds_module, "SEEDS_DIR", tmp_path / "seeds")
    yield


def test_build_seeds_writes_all_seed_files_with_matching_account_counts():
    build_seeds()

    seeds_dir = build_seeds_module.SEEDS_DIR
    subs = pd.read_csv(seeds_dir / "raw_subscriptions.csv")
    deliveries = pd.read_csv(seeds_dir / "raw_kit_deliveries.csv")
    engagement = pd.read_csv(seeds_dir / "raw_digital_engagement.csv")
    premium_base = pd.read_csv(seeds_dir / "raw_premium_base.csv")
    pricing = pd.read_csv(seeds_dir / "raw_pricing.csv")
    spend = pd.read_csv(seeds_dir / "raw_marketing_spend.csv")
    pitches = pd.read_csv(seeds_dir / "raw_sales_pitches.csv")

    assert len(subs) == N_ACCOUNTS
    assert len(deliveries) == N_ACCOUNTS
    assert len(engagement) == N_ACCOUNTS
    assert set(deliveries["account_id"]) == set(subs["account_id"])
    assert len(premium_base) == 3  # CA, TX, problem state
    assert len(pricing) == 3  # pet tiers
    assert len(spend) > 0
    assert len(pitches) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest generator/tests/test_build_seeds.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'generator.build_seeds'`.

- [ ] **Step 3: Implement the orchestration script**

Create `generator/build_seeds.py`:

```python
"""Orchestrate the full synthetic data generation pipeline and write dbt seeds."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from data.olist_reference.fetch_olist_reference_distributions import (
    OUTPUT_DIR as _OLIST_REFERENCE_OUTPUT_DIR,
)
from generator.generate_activity import generate_digital_engagement, generate_kit_deliveries
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
# Calibrated against the 10-day kit SLA: this lands the problem region near 56%
# on-time against an ~88% baseline. A larger penalty (the original 12) pushes it
# to 0%, which reads as a broken generator rather than an operational problem.
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

    subscriptions.to_csv(SEEDS_DIR / "raw_subscriptions.csv", index=False)
    kit_deliveries.to_csv(SEEDS_DIR / "raw_kit_deliveries.csv", index=False)
    digital_engagement.to_csv(SEEDS_DIR / "raw_digital_engagement.csv", index=False)
    premium_base.to_csv(SEEDS_DIR / "raw_premium_base.csv", index=False)
    pricing.to_csv(SEEDS_DIR / "raw_pricing.csv", index=False)
    marketing_spend.to_csv(SEEDS_DIR / "raw_marketing_spend.csv", index=False)
    sales_pitches.to_csv(SEEDS_DIR / "raw_sales_pitches.csv", index=False)


if __name__ == "__main__":
    build_seeds()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest generator/tests/test_build_seeds.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Generate the real seed files for the project**

```bash
python generator/build_seeds.py
ls pawtrail_dbt/seeds/
```

Expected: 7 CSV files listed.

- [ ] **Step 6: Commit**

```bash
git add generator/build_seeds.py generator/tests/test_build_seeds.py pawtrail_dbt/seeds/
git commit -m "Orchestrate generators into dbt seed files"
```

---

## Task 7: Load seeds and build core staging models (test-first)

**Files:**
- Create: `pawtrail_dbt/models/staging/_staging__models.yml`
- Create: `pawtrail_dbt/models/staging/stg_subscriptions.sql`
- Create: `pawtrail_dbt/models/staging/stg_kit_deliveries.sql`
- Create: `pawtrail_dbt/models/staging/stg_digital_engagement.sql`

**Interfaces:**
- Consumes: seeds `raw_subscriptions`, `raw_kit_deliveries`, `raw_digital_engagement` from Task 6.
- Produces: `stg_subscriptions(account_id, state, pet_tier, channel, premium_tenure_days, pawtrail_signup_date)`, `stg_kit_deliveries(account_id, kit_delivered_date, kit_lost, delivery_duration_days)`, `stg_digital_engagement(account_id, first_login_date, care_tasks_completed_first_cycle)` — all referenced by Task 8 onward via `{{ ref(...) }}`.

- [ ] **Step 1: Load the seeds into DuckDB**

```bash
cd pawtrail_dbt
dbt seed --profiles-dir .
cd ..
```

Expected: output shows `7 of 7 OK loaded seed file`.

- [ ] **Step 2: Write the schema tests before the models exist (red step)**

Create `pawtrail_dbt/models/staging/_staging__models.yml`:

```yaml
version: 2

models:
  - name: stg_subscriptions
    columns:
      - name: account_id
        tests:
          - unique
          - not_null
      - name: state
        tests:
          - not_null
      - name: pet_tier
        tests:
          - not_null
          - accepted_values:
              values: ['small', 'medium', 'large']
      - name: channel
        tests:
          - not_null
          - accepted_values:
              values: ['self_serve', 'sales_assisted']
      - name: pawtrail_signup_date
        tests:
          - not_null

  - name: stg_kit_deliveries
    columns:
      - name: account_id
        tests:
          - unique
          - not_null
          - relationships:
              to: ref('stg_subscriptions')
              field: account_id

  - name: stg_digital_engagement
    columns:
      - name: account_id
        tests:
          - unique
          - not_null
          - relationships:
              to: ref('stg_subscriptions')
              field: account_id
```

- [ ] **Step 3: Run `dbt test` to verify it fails (models don't exist yet)**

```bash
cd pawtrail_dbt
dbt test --profiles-dir . --select staging
cd ..
```

Expected: compilation error — model `stg_subscriptions` (etc.) not found.

- [ ] **Step 4: Implement the minimal staging models**

Create `pawtrail_dbt/models/staging/stg_subscriptions.sql`:

```sql
select
    account_id,
    state,
    pet_tier,
    channel,
    cast(premium_tenure_days as integer) as premium_tenure_days,
    cast(pawtrail_signup_date as date) as pawtrail_signup_date
from {{ ref('raw_subscriptions') }}
```

Create `pawtrail_dbt/models/staging/stg_kit_deliveries.sql`:

```sql
select
    account_id,
    cast(kit_delivered_date as date) as kit_delivered_date,
    cast(kit_lost as boolean) as kit_lost,
    cast(delivery_duration_days as integer) as delivery_duration_days
from {{ ref('raw_kit_deliveries') }}
```

Create `pawtrail_dbt/models/staging/stg_digital_engagement.sql`:

```sql
select
    account_id,
    cast(first_login_date as date) as first_login_date,
    cast(care_tasks_completed_first_cycle as integer) as care_tasks_completed_first_cycle
from {{ ref('raw_digital_engagement') }}
```

- [ ] **Step 5: Run `dbt build` to verify models and tests pass**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select staging
cd ..
```

Expected: all models built, all tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add pawtrail_dbt/models/staging/
git commit -m "Add core staging models with test-first schema tests"
```

---

## Task 8: Intermediate activation funnel model (test-first)

**Files:**
- Create: `pawtrail_dbt/tests/assert_digital_activation_requires_login_date.sql`
- Create: `pawtrail_dbt/tests/assert_signup_never_after_observation_date.sql`
- Create: `pawtrail_dbt/tests/assert_combined_activation_requires_on_time_kit.sql`
- Create: `pawtrail_dbt/models/intermediate/_intermediate__models.yml`
- Create: `pawtrail_dbt/models/intermediate/int_activation_funnel.sql`

**Interfaces:**
- Consumes: `stg_subscriptions`, `stg_kit_deliveries`, `stg_digital_engagement` from Task 7.
- Produces: `int_activation_funnel(account_id, state, pet_tier, channel, premium_tenure_days, pawtrail_signup_date, observation_date, first_login_date, care_tasks_completed_first_cycle, kit_delivered_date, kit_lost, days_to_first_login, days_to_kit_delivery, days_observed, digital_activated_7d, kit_activated_sla, no_digital_access_14d, is_mature_7d, is_mature_sla, is_mature_30d, combined_activated_30d)` — `kit_activated_sla` is the single source of truth for "was the kit delivered on time," reused by Task 10's `fct_kit_deliveries` and by `combined_activated_30d` instead of being recomputed.
- **Cohort maturity:** the `is_mature_*` flags mark accounts that have had the full activation window to succeed or fail. Every activation rate in Task 15 is restricted to the matching mature cohort, so recent signups are not silently counted as failures.

- [ ] **Step 1: Write the singular test before the model exists (red step)**

Create `pawtrail_dbt/tests/assert_digital_activation_requires_login_date.sql`:

```sql
-- Fails (returns rows) if any account is flagged digitally activated
-- without an actual first_login_date — a business-rule consistency check
-- that generic schema tests can't express.
select account_id
from {{ ref('int_activation_funnel') }}
where digital_activated_7d = true
  and first_login_date is null
```

Create `pawtrail_dbt/tests/assert_signup_never_after_observation_date.sql`:

```sql
-- Fails (returns rows) if an account signed up after the analysis cutoff, which
-- would make days_observed negative and every maturity flag meaningless.
select account_id, pawtrail_signup_date, observation_date
from {{ ref('int_activation_funnel') }}
where pawtrail_signup_date > observation_date
   or days_observed < 0
```

Create `pawtrail_dbt/tests/assert_combined_activation_requires_on_time_kit.sql`:

```sql
-- Fails (returns rows) if an account counts as combined-activated while its kit
-- missed the SLA. This is the guard on spec §6's North Star definition: an
-- earlier draft tested "kit delivered within 30 days" instead of "kit delivered
-- on time", which let a region with a severe delivery problem still register as
-- fully activated because almost every kit arrives inside 30 days.
select account_id
from {{ ref('int_activation_funnel') }}
where combined_activated_30d
  and not kit_activated_sla
```

- [ ] **Step 2: Write the schema tests before the model exists**

Create `pawtrail_dbt/models/intermediate/_intermediate__models.yml`:

```yaml
version: 2

models:
  - name: int_activation_funnel
    columns:
      - name: account_id
        tests:
          - unique
          - not_null
      - name: digital_activated_7d
        tests:
          - not_null
      - name: kit_activated_sla
        tests:
          - not_null
      - name: combined_activated_30d
        tests:
          - not_null
      - name: days_observed
        tests:
          - not_null
      - name: is_mature_30d
        tests:
          - not_null
```

- [ ] **Step 3: Run `dbt build` to verify it fails**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select intermediate
cd ..
```

Expected: compilation error — model `int_activation_funnel` not found.

- [ ] **Step 4: Implement the model**

Create `pawtrail_dbt/models/intermediate/int_activation_funnel.sql`:

```sql
with subscriptions as (
    select * from {{ ref('stg_subscriptions') }}
),

kit_deliveries as (
    select * from {{ ref('stg_kit_deliveries') }}
),

digital_engagement as (
    select * from {{ ref('stg_digital_engagement') }}
),

-- The analysis cutoff. In a scheduled pipeline this would be current_date; here
-- the dataset is a fixed simulated window, so the latest signup stands in for
-- "as of today". Every maturity flag below is measured against it.
observation as (
    select max(pawtrail_signup_date) as observation_date
    from {{ ref('stg_subscriptions') }}
),

joined as (
    select
        s.account_id,
        s.state,
        s.pet_tier,
        s.channel,
        s.premium_tenure_days,
        s.pawtrail_signup_date,
        o.observation_date,
        d.first_login_date,
        d.care_tasks_completed_first_cycle,
        k.kit_delivered_date,
        k.kit_lost,
        date_diff('day', s.pawtrail_signup_date, d.first_login_date) as days_to_first_login,
        date_diff('day', s.pawtrail_signup_date, k.kit_delivered_date) as days_to_kit_delivery,
        date_diff('day', s.pawtrail_signup_date, o.observation_date) as days_observed
    from subscriptions s
    cross join observation o
    left join digital_engagement d on s.account_id = d.account_id
    left join kit_deliveries k on s.account_id = k.account_id
),

flagged as (
    select
        *,
        (first_login_date is not null
            and days_to_first_login <= {{ var('digital_activation_window_days') }}
        ) as digital_activated_7d,
        (kit_delivered_date is not null
            and not kit_lost
            and days_to_kit_delivery <= {{ var('kit_sla_days') }}
        ) as kit_activated_sla,
        (first_login_date is null
            or days_to_first_login > {{ var('at_risk_no_login_days') }}
        ) as no_digital_access_14d,
        -- Cohort maturity. An account that signed up four days before the
        -- observation date has not yet had 30 days to activate, so counting it
        -- as a failure would understate activation in exactly the most recent
        -- weeks — the ones a launch dashboard leans on hardest. These flags let
        -- the metric layer restrict each rate to accounts that have actually had
        -- the full window.
        (days_observed >= {{ var('digital_activation_window_days') }}) as is_mature_7d,
        (days_observed >= {{ var('kit_sla_days') }}) as is_mature_sla,
        (days_observed >= {{ var('combined_activation_window_days') }}) as is_mature_30d
    from joined
)

select
    *,
    -- The launch North Star, per spec §6: confirmed digital usage AND an
    -- ON-TIME first kit, inside 30 days. Reusing kit_activated_sla rather than
    -- re-testing "delivered within 30 days" matters — nearly every kit arrives
    -- inside 30 days, so the looser rule would let a region with a severe
    -- delivery problem still score as fully activated.
    (
        first_login_date is not null
        and days_to_first_login <= {{ var('combined_activation_window_days') }}
        and kit_activated_sla
    ) as combined_activated_30d
from flagged
```

- [ ] **Step 5: Run `dbt build` to verify it passes**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select intermediate
cd ..
```

Expected: model built, all tests `PASS` (including the singular tests).

- [ ] **Step 6: Prove the North Star test actually catches the bug it guards (meaningful red)**

Every other red step in this plan fails because the model file does not exist
yet — that is a missing file, not a violated assertion, and it never
demonstrates that a test can catch anything. This step closes that gap once,
on the assertion that matters most.

Temporarily replace the `combined_activated_30d` expression with the looser
rule the spec does *not* call for:

```sql
    (
        first_login_date is not null
        and days_to_first_login <= {{ var('combined_activation_window_days') }}
        and kit_delivered_date is not null
        and not kit_lost
        and days_to_kit_delivery <= {{ var('combined_activation_window_days') }}
    ) as combined_activated_30d
```

Then run:

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select intermediate
cd ..
```

Expected: `assert_combined_activation_requires_on_time_kit` **FAILS**, reporting
the accounts whose kit missed the 10-day SLA but still arrived inside 30 days
and were counted as activated anyway. Confirm the failure count is material
(hundreds of rows, concentrated in the problem region) — that is the size of the
overstatement the looser definition would have hidden.

Now restore the `kit_activated_sla` version from Step 4 and re-run; the test
returns to `PASS`.

- [ ] **Step 7: Commit**

```bash
git add pawtrail_dbt/tests/assert_digital_activation_requires_login_date.sql pawtrail_dbt/tests/assert_signup_never_after_observation_date.sql pawtrail_dbt/tests/assert_combined_activation_requires_on_time_kit.sql pawtrail_dbt/models/intermediate/
git commit -m "Add activation funnel with cohort maturity and SLA-based North Star"
```

---

## Task 9: Marts — dim_accounts, fct_subscriptions (test-first)

**Files:**
- Create: `pawtrail_dbt/models/marts/_marts__core.yml`
- Create: `pawtrail_dbt/models/marts/dim_accounts.sql`
- Create: `pawtrail_dbt/models/marts/fct_subscriptions.sql`

**Interfaces:**
- Consumes: `stg_subscriptions` from Task 7.
- Produces: `dim_accounts(account_id, state, pet_tier, channel)`, referenced by Task 10 (join) and Task 14's `accounts` semantic model; `fct_subscriptions(account_id, pawtrail_signup_date, signup_week)`, referenced by Task 10's singular test and Task 14's `subscriptions` semantic model.

- [ ] **Step 1: Write the schema tests before the models exist**

Create `pawtrail_dbt/models/marts/_marts__core.yml`:

```yaml
version: 2

models:
  - name: dim_accounts
    columns:
      - name: account_id
        tests:
          - unique
          - not_null

  - name: fct_subscriptions
    columns:
      - name: account_id
        tests:
          - unique
          - not_null
      - name: pawtrail_signup_date
        tests:
          - not_null
```

- [ ] **Step 2: Run `dbt build` to verify it fails**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select dim_accounts fct_subscriptions
cd ..
```

Expected: compilation error — models not found.

- [ ] **Step 3: Implement the models**

Create `pawtrail_dbt/models/marts/dim_accounts.sql`:

```sql
select
    account_id,
    state,
    pet_tier,
    channel
from {{ ref('stg_subscriptions') }}
```

Create `pawtrail_dbt/models/marts/fct_subscriptions.sql`:

```sql
select
    account_id,
    pawtrail_signup_date,
    date_trunc('week', pawtrail_signup_date) as signup_week
from {{ ref('stg_subscriptions') }}
```

- [ ] **Step 4: Run `dbt build` to verify it passes**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select dim_accounts fct_subscriptions
cd ..
```

Expected: both models built, all tests `PASS`.

- [ ] **Step 5: Commit**

```bash
git add pawtrail_dbt/models/marts/_marts__core.yml pawtrail_dbt/models/marts/dim_accounts.sql pawtrail_dbt/models/marts/fct_subscriptions.sql
git commit -m "Add dim_accounts and fct_subscriptions marts"
```

---

## Task 10: Marts — fct_activation_events, fct_kit_deliveries (test-first)

**Files:**
- Modify: `pawtrail_dbt/models/marts/_marts__core.yml` (append new model tests)
- Create: `pawtrail_dbt/models/marts/fct_activation_events.sql`
- Create: `pawtrail_dbt/models/marts/fct_kit_deliveries.sql`
- Create: `pawtrail_dbt/tests/assert_kit_delivered_not_before_signup.sql`

**Interfaces:**
- Consumes: `int_activation_funnel` (Task 8), `stg_kit_deliveries` (Task 7), `dim_accounts` and `fct_subscriptions` (Task 9).
- Produces: `fct_activation_events(account_id, pawtrail_signup_date, digital_activated_7d, kit_activated_sla, combined_activated_30d, no_digital_access_14d, days_to_first_login, days_to_kit_delivery, days_observed, is_mature_7d, is_mature_sla, is_mature_30d, care_tasks_completed_first_cycle)`; `fct_kit_deliveries(account_id, state, pawtrail_signup_date, kit_delivered_date, kit_lost, delivery_duration_days, kit_activated_sla, is_mature_sla)` — both consumed by Task 14's semantic models. Note `kit_activated_sla` is reused from `int_activation_funnel`, not recomputed, to keep a single source of truth for the SLA definition.

- [ ] **Step 1: Write the singular test before the models exist**

Create `pawtrail_dbt/tests/assert_kit_delivered_not_before_signup.sql`:

```sql
-- Fails (returns rows) if any kit was recorded as delivered before the
-- account even signed up — a data-quality guard on the generated dates.
select
    k.account_id
from {{ ref('fct_kit_deliveries') }} k
left join {{ ref('fct_subscriptions') }} s on k.account_id = s.account_id
where k.kit_delivered_date is not null
  and k.kit_delivered_date < s.pawtrail_signup_date
```

- [ ] **Step 2: Append the schema tests before the models exist**

Add to `pawtrail_dbt/models/marts/_marts__core.yml` (append under the existing `models:` list):

```yaml
  - name: fct_activation_events
    columns:
      - name: account_id
        tests:
          - unique
          - not_null

  - name: fct_kit_deliveries
    columns:
      - name: account_id
        tests:
          - unique
          - not_null
```

- [ ] **Step 3: Run `dbt build` to verify it fails**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select fct_activation_events fct_kit_deliveries
cd ..
```

Expected: compilation error — models not found.

- [ ] **Step 4: Implement the models**

Create `pawtrail_dbt/models/marts/fct_activation_events.sql`:

```sql
select
    account_id,
    pawtrail_signup_date,
    digital_activated_7d,
    kit_activated_sla,
    combined_activated_30d,
    no_digital_access_14d,
    days_to_first_login,
    days_to_kit_delivery,
    days_observed,
    is_mature_7d,
    is_mature_sla,
    is_mature_30d,
    care_tasks_completed_first_cycle
from {{ ref('int_activation_funnel') }}
```

Create `pawtrail_dbt/models/marts/fct_kit_deliveries.sql`:

```sql
select
    k.account_id,
    a.state,
    f.pawtrail_signup_date,
    k.kit_delivered_date,
    k.kit_lost,
    k.delivery_duration_days,
    f.kit_activated_sla,
    -- Carried so the on-time rate can exclude accounts whose SLA window has not
    -- closed yet, matching the cohort treatment of the activation rates.
    f.is_mature_sla
from {{ ref('stg_kit_deliveries') }} k
left join {{ ref('dim_accounts') }} a on k.account_id = a.account_id
left join {{ ref('int_activation_funnel') }} f on k.account_id = f.account_id
```

- [ ] **Step 5: Run `dbt build` to verify it passes**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select fct_activation_events fct_kit_deliveries
cd ..
```

Expected: both models built, all tests `PASS` (including the singular test).

- [ ] **Step 6: Commit**

```bash
git add pawtrail_dbt/models/marts/_marts__core.yml pawtrail_dbt/models/marts/fct_activation_events.sql pawtrail_dbt/models/marts/fct_kit_deliveries.sql pawtrail_dbt/tests/assert_kit_delivered_not_before_signup.sql
git commit -m "Add fct_activation_events and fct_kit_deliveries marts"
```

---

## Task 11: Business-data staging and marts (test-first)

**Files:**
- Create: `pawtrail_dbt/models/staging/_staging__business.yml`
- Create: `pawtrail_dbt/models/staging/stg_pricing.sql`
- Create: `pawtrail_dbt/models/staging/stg_premium_base.sql`
- Create: `pawtrail_dbt/models/staging/stg_marketing_spend.sql`
- Create: `pawtrail_dbt/models/staging/stg_sales_pitches.sql`
- Create: `pawtrail_dbt/models/marts/_marts__business.yml`
- Create: `pawtrail_dbt/models/marts/dim_pricing.sql`
- Create: `pawtrail_dbt/models/marts/fct_premium_base.sql`
- Create: `pawtrail_dbt/models/marts/fct_marketing_spend.sql`
- Create: `pawtrail_dbt/models/marts/fct_sales_pitches.sql`

**Interfaces:**
- Consumes: seeds `raw_pricing`, `raw_premium_base`, `raw_marketing_spend`, `raw_sales_pitches` from Task 6.
- Produces: `dim_pricing(pet_tier, monthly_price_usd, kit_cogs_usd, shipping_cost_usd)`; `fct_premium_base(state, eligible_premium_accounts)`; `fct_marketing_spend(week_start_date, channel, spend_usd)`; `fct_sales_pitches(pitch_id, state, pitch_date, won)` — consumed by Task 12, 13, and Task 14's semantic models.

- [ ] **Step 1: Write the staging schema tests before the models exist**

Create `pawtrail_dbt/models/staging/_staging__business.yml`:

```yaml
version: 2

models:
  - name: stg_pricing
    columns:
      - name: pet_tier
        tests:
          - unique
          - not_null

  - name: stg_premium_base
    columns:
      - name: state
        tests:
          - unique
          - not_null

  - name: stg_marketing_spend
    columns:
      - name: channel
        tests:
          - not_null
          - accepted_values:
              values: ['self_serve', 'sales_assisted']

  - name: stg_sales_pitches
    columns:
      - name: pitch_id
        tests:
          - unique
          - not_null
      - name: won
        tests:
          - not_null
```

- [ ] **Step 2: Write the marts schema tests before the models exist**

Create `pawtrail_dbt/models/marts/_marts__business.yml`:

```yaml
version: 2

models:
  - name: dim_pricing
    columns:
      - name: pet_tier
        tests:
          - unique
          - not_null

  - name: fct_premium_base
    columns:
      - name: state
        tests:
          - unique
          - not_null

  - name: fct_marketing_spend
    columns:
      - name: channel
        tests:
          - not_null

  - name: fct_sales_pitches
    columns:
      - name: pitch_id
        tests:
          - unique
          - not_null
```

- [ ] **Step 3: Run `dbt build` to verify it fails**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select stg_pricing stg_premium_base stg_marketing_spend stg_sales_pitches dim_pricing fct_premium_base fct_marketing_spend fct_sales_pitches
cd ..
```

Expected: compilation error — models not found.

- [ ] **Step 4: Implement the staging models**

Create `pawtrail_dbt/models/staging/stg_pricing.sql`:

```sql
select
    pet_tier,
    cast(monthly_price_usd as double) as monthly_price_usd,
    cast(kit_cogs_usd as double) as kit_cogs_usd,
    cast(shipping_cost_usd as double) as shipping_cost_usd
from {{ ref('raw_pricing') }}
```

Create `pawtrail_dbt/models/staging/stg_premium_base.sql`:

```sql
select
    state,
    cast(eligible_premium_accounts as integer) as eligible_premium_accounts
from {{ ref('raw_premium_base') }}
```

Create `pawtrail_dbt/models/staging/stg_marketing_spend.sql`:

```sql
select
    cast(week_start_date as date) as week_start_date,
    channel,
    cast(spend_usd as double) as spend_usd
from {{ ref('raw_marketing_spend') }}
```

Create `pawtrail_dbt/models/staging/stg_sales_pitches.sql`:

```sql
select
    pitch_id,
    state,
    cast(pitch_date as date) as pitch_date,
    cast(won as boolean) as won
from {{ ref('raw_sales_pitches') }}
```

- [ ] **Step 5: Implement the mart models (pass-through, exposing the semantic-layer-facing interface)**

Create `pawtrail_dbt/models/marts/dim_pricing.sql`:

```sql
select * from {{ ref('stg_pricing') }}
```

Create `pawtrail_dbt/models/marts/fct_premium_base.sql`:

```sql
select * from {{ ref('stg_premium_base') }}
```

Create `pawtrail_dbt/models/marts/fct_marketing_spend.sql`:

```sql
select * from {{ ref('stg_marketing_spend') }}
```

Create `pawtrail_dbt/models/marts/fct_sales_pitches.sql`:

```sql
select * from {{ ref('stg_sales_pitches') }}
```

- [ ] **Step 6: Run `dbt build` to verify it passes**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select stg_pricing stg_premium_base stg_marketing_spend stg_sales_pitches dim_pricing fct_premium_base fct_marketing_spend fct_sales_pitches
cd ..
```

Expected: all 8 models built, all tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add pawtrail_dbt/models/staging/_staging__business.yml pawtrail_dbt/models/staging/stg_pricing.sql pawtrail_dbt/models/staging/stg_premium_base.sql pawtrail_dbt/models/staging/stg_marketing_spend.sql pawtrail_dbt/models/staging/stg_sales_pitches.sql pawtrail_dbt/models/marts/_marts__business.yml pawtrail_dbt/models/marts/dim_pricing.sql pawtrail_dbt/models/marts/fct_premium_base.sql pawtrail_dbt/models/marts/fct_marketing_spend.sql pawtrail_dbt/models/marts/fct_sales_pitches.sql
git commit -m "Add business-data staging and marts (pricing, premium base, spend, pitches)"
```

---

## Task 12: Mart — fct_weekly_attach (test-first)

**Files:**
- Modify: `pawtrail_dbt/models/marts/_marts__business.yml` (append new model tests)
- Create: `pawtrail_dbt/models/marts/fct_weekly_attach.sql`
- Create: `pawtrail_dbt/tests/assert_attach_rate_within_bounds.sql`
- Create: `pawtrail_dbt/tests/assert_cumulative_subscriptions_monotonic.sql`

**Interfaces:**
- Consumes: `stg_subscriptions` (Task 7), `fct_premium_base` (Task 11).
- Produces: `fct_weekly_attach(state, signup_week, new_subscriptions, cumulative_subscriptions, eligible_premium_accounts, attach_rate)` — the join between subscriptions and the addressable base is done here in dbt (not in the semantic layer), keeping the attach-rate calculation in one auditable place. The grain is one row per state per launch week, densified over a state × week spine so cross-state sums are correct in every week. Consumed by Task 14's `weekly_attach` semantic model.

- [ ] **Step 1: Write the singular test before the model exists**

Create `pawtrail_dbt/tests/assert_attach_rate_within_bounds.sql`:

```sql
-- Fails (returns rows) if attach_rate is ever negative or exceeds 100% —
-- either would indicate a broken join or a premium-base assumption that's
-- too small relative to the generated subscription volume.
select state, signup_week, attach_rate
from {{ ref('fct_weekly_attach') }}
where attach_rate < 0 or attach_rate > 1
```

Create `pawtrail_dbt/tests/assert_cumulative_subscriptions_monotonic.sql`:

```sql
-- Fails (returns rows) if cumulative_subscriptions ever drops week over week
-- within a state. That can only happen if the state x week spine has gaps,
-- which in turn means any cross-state sum of this measure understates the
-- national total for the weeks where a state is missing.
with ordered as (
    select
        state,
        signup_week,
        cumulative_subscriptions,
        lag(cumulative_subscriptions) over (
            partition by state order by signup_week
        ) as previous_cumulative_subscriptions
    from {{ ref('fct_weekly_attach') }}
)

select state, signup_week, cumulative_subscriptions, previous_cumulative_subscriptions
from ordered
where previous_cumulative_subscriptions is not null
  and cumulative_subscriptions < previous_cumulative_subscriptions
```

- [ ] **Step 2: Append the schema tests before the model exists**

Add to `pawtrail_dbt/models/marts/_marts__business.yml` (append under `models:`):

```yaml
  - name: fct_weekly_attach
    columns:
      - name: weekly_attach_key
        tests:
          - unique
          - not_null
      - name: state
        tests:
          - not_null
      - name: attach_rate
        tests:
          - not_null
```

- [ ] **Step 3: Run `dbt build` to verify it fails**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select fct_weekly_attach
cd ..
```

Expected: compilation error — model not found.

- [ ] **Step 4: Implement the model**

Create `pawtrail_dbt/models/marts/fct_weekly_attach.sql`:

```sql
with weekly_signups as (
    select
        state,
        date_trunc('week', pawtrail_signup_date) as signup_week,
        count(*) as new_subscriptions
    from {{ ref('stg_subscriptions') }}
    group by 1, 2
),

premium_base as (
    select * from {{ ref('fct_premium_base') }}
),

week_spine as (
    select distinct signup_week from weekly_signups
),

-- Every state must appear in every launch week. Without this spine, a state
-- with no signups in a given week produces no row at all, so summing
-- cumulative_subscriptions across states understates the national total for
-- that week and the cumulative line goes non-monotonic.
state_week_spine as (
    select
        p.state,
        w.signup_week
    from premium_base p
    cross join week_spine w
),

filled as (
    select
        sp.state,
        sp.signup_week,
        coalesce(s.new_subscriptions, 0) as new_subscriptions
    from state_week_spine sp
    left join weekly_signups s
        on sp.state = s.state
       and sp.signup_week = s.signup_week
),

cumulative as (
    select
        state,
        signup_week,
        new_subscriptions,
        sum(new_subscriptions) over (
            partition by state order by signup_week
            rows between unbounded preceding and current row
        ) as cumulative_subscriptions
    from filled
)

select
    -- Surrogate key. The grain is (state, week), so neither column alone is
    -- unique; declaring `state` as the semantic model's primary entity would be
    -- a false uniqueness claim and can fan out joins.
    c.state || '_' || cast(c.signup_week as varchar) as weekly_attach_key,
    c.state,
    c.signup_week,
    c.new_subscriptions,
    c.cumulative_subscriptions,
    p.eligible_premium_accounts,
    c.cumulative_subscriptions * 1.0 / nullif(p.eligible_premium_accounts, 0) as attach_rate
from cumulative c
left join premium_base p on c.state = p.state
```

- [ ] **Step 5: Run `dbt build` to verify it passes**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select fct_weekly_attach
cd ..
```

Expected: model built, all tests `PASS` (including the singular test).

- [ ] **Step 6: Commit**

```bash
git add pawtrail_dbt/models/marts/_marts__business.yml pawtrail_dbt/models/marts/fct_weekly_attach.sql pawtrail_dbt/tests/assert_attach_rate_within_bounds.sql pawtrail_dbt/tests/assert_cumulative_subscriptions_monotonic.sql
git commit -m "Add fct_weekly_attach mart computing attach rate against the Premium base"
```

---

## Task 13: Mart — fct_weekly_channel_economics (test-first)

**Files:**
- Modify: `pawtrail_dbt/models/marts/_marts__business.yml` (append new model tests)
- Create: `pawtrail_dbt/models/marts/fct_weekly_channel_economics.sql`

**Interfaces:**
- Consumes: `stg_subscriptions` (Task 7), `int_activation_funnel` (Task 8), `fct_marketing_spend` and `dim_pricing` (Task 11).
- Produces: `fct_weekly_channel_economics(channel_week_key, channel, signup_week, new_subscriptions, mature_subscriptions, activated_subscriptions, spend_usd, cac, cost_per_activated_account, avg_price, contribution_margin_per_subscription)` — consumed by Task 14's `weekly_channel_economics` semantic model. Contribution margin is weighted by each week's actual pet-tier mix rather than being an unweighted average of the tier list.

- [ ] **Step 1: Write the schema tests before the model exists**

Add to `pawtrail_dbt/models/marts/_marts__business.yml` (append under `models:`):

```yaml
  - name: fct_weekly_channel_economics
    columns:
      - name: channel_week_key
        tests:
          - unique
          - not_null
      - name: channel
        tests:
          - not_null
      - name: new_subscriptions
        tests:
          - not_null
      # Guards the spend join: every grouped row has at least one subscription,
      # so cac can only be null if fct_marketing_spend failed to join. Without
      # this test a week-boundary mismatch produces an all-null CAC chart and
      # still builds green.
      - name: cac
        tests:
          - not_null
```

- [ ] **Step 2: Run `dbt build` to verify it fails**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select fct_weekly_channel_economics
cd ..
```

Expected: compilation error — model not found.

- [ ] **Step 3: Implement the model**

Create `pawtrail_dbt/models/marts/fct_weekly_channel_economics.sql`:

```sql
with subs as (
    select account_id, channel, pet_tier, date_trunc('week', pawtrail_signup_date) as signup_week
    from {{ ref('stg_subscriptions') }}
),

activation as (
    select account_id, combined_activated_30d, is_mature_30d
    from {{ ref('int_activation_funnel') }}
),

-- Contribution margin is joined per account at its own pet tier. Averaging the
-- three tier prices unweighted (the earlier approach) produced the same constant
-- in every channel and week, so the metric drew a flat line that no amount of
-- segmentation could move.
subs_priced as (
    select
        s.channel,
        s.signup_week,
        s.account_id,
        a.combined_activated_30d,
        a.is_mature_30d,
        p.monthly_price_usd,
        p.monthly_price_usd - p.kit_cogs_usd - p.shipping_cost_usd as contribution_margin
    from subs s
    left join activation a on s.account_id = a.account_id
    left join {{ ref('dim_pricing') }} p on s.pet_tier = p.pet_tier
),

weekly_subs as (
    select
        channel,
        signup_week,
        count(*) as new_subscriptions,
        -- Restricted to the mature cohort for the same reason the activation
        -- metrics are: a week-old signup that has not activated yet is not a
        -- failed acquisition, and counting it as one inflates recent CPA.
        sum(case when is_mature_30d then 1 else 0 end) as mature_subscriptions,
        sum(case when combined_activated_30d and is_mature_30d then 1 else 0 end)
            as activated_subscriptions,
        avg(monthly_price_usd) as avg_price,
        avg(contribution_margin) as contribution_margin_per_subscription
    from subs_priced
    group by 1, 2
),

-- date_trunc is defensive here: the generator already emits Monday-aligned week
-- starts, so this is a no-op on correct data. It keeps the join below from
-- silently matching zero rows if the launch date ever moves off a Monday.
spend as (
    select channel, date_trunc('week', week_start_date) as signup_week, spend_usd
    from {{ ref('fct_marketing_spend') }}
),

select
    -- Surrogate key: the grain is (channel, week), so `channel` alone is not a
    -- valid primary entity for the semantic model.
    w.channel || '_' || cast(w.signup_week as varchar) as channel_week_key,
    w.channel,
    w.signup_week,
    w.new_subscriptions,
    w.mature_subscriptions,
    w.activated_subscriptions,
    s.spend_usd,
    s.spend_usd / nullif(w.new_subscriptions, 0) as cac,
    -- Denominator is the activated share of the *mature* cohort applied to all
    -- acquired accounts, so a week of recent signups does not report an
    -- artificially catastrophic cost per activated account.
    s.spend_usd / nullif(w.activated_subscriptions, 0) as cost_per_activated_account,
    w.avg_price,
    w.contribution_margin_per_subscription
from weekly_subs w
left join spend s on w.channel = s.channel and w.signup_week = s.signup_week
```

- [ ] **Step 4: Run `dbt build` to verify it passes**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select fct_weekly_channel_economics
cd ..
```

Expected: model built, all tests `PASS`.

- [ ] **Step 5: Run the full project build and test suite as a checkpoint**

```bash
cd pawtrail_dbt
dbt build --profiles-dir .
cd ..
```

Expected: every model and test in the project passes.

- [ ] **Step 6: Commit**

```bash
git add pawtrail_dbt/models/marts/_marts__business.yml pawtrail_dbt/models/marts/fct_weekly_channel_economics.sql
git commit -m "Add fct_weekly_channel_economics mart for CAC and unit-economics metrics"
```

---

## Task 13b: Mart — fct_at_risk_accounts (test-first)

Spec §6 defines an "Early risk signals" category and the source context calls
the at-risk list "the practical Customer Success work queue during launch" —
it is the one artefact in the catalogue that maps directly onto the target
role's "customer-health KPIs". It is also cheap: `int_activation_funnel`
already carries every input.

**Files:**
- Create: `pawtrail_dbt/models/marts/_marts__risk.yml`
- Create: `pawtrail_dbt/models/marts/fct_at_risk_accounts.sql`
- Create: `pawtrail_dbt/tests/assert_risk_driver_is_exhaustive.sql`

**Interfaces:**
- Consumes: `int_activation_funnel` (Task 8).
- Produces: `fct_at_risk_accounts(account_id, state, channel, pet_tier, pawtrail_signup_date, days_observed, no_digital_access_14d, kit_failed_sla, no_tasks_completed, risk_driver, is_at_risk)` — one row per account old enough to be judged, tagged by which leg failed. Consumed by Task 14's `at_risk_accounts` semantic model.

- [ ] **Step 1: Write the singular test before the model exists**

Create `pawtrail_dbt/tests/assert_risk_driver_is_exhaustive.sql`:

```sql
-- Fails (returns rows) if an account carries a risk flag but lands in the
-- 'healthy' bucket, or is tagged with a driver outside the known set. The
-- driver column is what makes the queue actionable — an account routed to the
-- wrong team is worse than one that was never flagged.
select account_id, risk_driver
from {{ ref('fct_at_risk_accounts') }}
where risk_driver not in (
        'healthy', 'digital_failure', 'physical_failure',
        'both_legs_failed', 'onboarding_gap'
      )
   or (risk_driver = 'healthy'
       and (no_digital_access_14d or kit_failed_sla or no_tasks_completed))
```

- [ ] **Step 2: Write the schema tests before the model exists**

Create `pawtrail_dbt/models/marts/_marts__risk.yml`:

```yaml
version: 2

models:
  - name: fct_at_risk_accounts
    columns:
      - name: account_id
        tests:
          - unique
          - not_null
      - name: risk_driver
        tests:
          - not_null
          - accepted_values:
              values: ['healthy', 'digital_failure', 'physical_failure', 'both_legs_failed', 'onboarding_gap']
      - name: is_at_risk
        tests:
          - not_null
```

- [ ] **Step 3: Run `dbt build` to verify it fails**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select fct_at_risk_accounts
cd ..
```

Expected: compilation error — model not found.

- [ ] **Step 4: Implement the model**

Create `pawtrail_dbt/models/marts/fct_at_risk_accounts.sql`:

```sql
with funnel as (
    select * from {{ ref('int_activation_funnel') }}
),

flagged as (
    select
        account_id,
        state,
        channel,
        pet_tier,
        pawtrail_signup_date,
        days_observed,
        no_digital_access_14d,
        (kit_lost or kit_delivered_date is null or not kit_activated_sla) as kit_failed_sla,
        (coalesce(care_tasks_completed_first_cycle, 0) = 0) as no_tasks_completed
    from funnel
    -- Only accounts that have actually had the chance to fail. Flagging a
    -- two-day-old signup as "no digital access in 14 days" would fill the CS
    -- queue with accounts that are simply new.
    where days_observed >= {{ var('at_risk_no_login_days') }}
)

select
    *,
    case
        when no_digital_access_14d and kit_failed_sla then 'both_legs_failed'
        when kit_failed_sla then 'physical_failure'
        when no_digital_access_14d then 'digital_failure'
        when no_tasks_completed then 'onboarding_gap'
        else 'healthy'
    end as risk_driver,
    (no_digital_access_14d or kit_failed_sla or no_tasks_completed) as is_at_risk
from flagged
```

- [ ] **Step 5: Run `dbt build` to verify it passes**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select fct_at_risk_accounts
cd ..
```

Expected: model built, all tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add pawtrail_dbt/models/marts/_marts__risk.yml pawtrail_dbt/models/marts/fct_at_risk_accounts.sql pawtrail_dbt/tests/assert_risk_driver_is_exhaustive.sql
git commit -m "Add at-risk account queue tagged by failure driver"
```

---

## Task 14: Semantic layer — semantic models

**Files:**
- Create: `pawtrail_dbt/models/marts/_semantic_models.yml`

**Interfaces:**
- Consumes: `dim_accounts`, `fct_subscriptions`, `fct_activation_events`, `fct_kit_deliveries`, `fct_weekly_attach`, `fct_weekly_channel_economics`, `fct_sales_pitches` (Tasks 9–13), `fct_at_risk_accounts` (Task 13b).
- Produces: eight MetricFlow semantic models (`accounts`, `subscriptions`, `activation_events`, `kit_deliveries`, `weekly_attach`, `weekly_channel_economics`, `sales_pitches`, `at_risk_accounts`) whose measures are consumed by Task 15's metric definitions.

- [ ] **Step 1: Create the semantic models file**

Create `pawtrail_dbt/models/marts/_semantic_models.yml`:

```yaml
semantic_models:
  - name: accounts
    model: ref('dim_accounts')
    entities:
      - name: account
        type: primary
        expr: account_id
    dimensions:
      - name: state
        type: categorical
      - name: pet_tier
        type: categorical
      - name: channel
        type: categorical

  - name: subscriptions
    model: ref('fct_subscriptions')
    defaults:
      agg_time_dimension: signup_date
    entities:
      - name: account
        type: primary
        expr: account_id
    dimensions:
      - name: signup_date
        type: time
        expr: pawtrail_signup_date
        type_params:
          time_granularity: day
    measures:
      - name: subscription_count
        agg: count
        expr: account_id

  - name: activation_events
    model: ref('fct_activation_events')
    defaults:
      agg_time_dimension: signup_date
    entities:
      - name: account
        type: primary
        expr: account_id
    dimensions:
      - name: signup_date
        type: time
        expr: pawtrail_signup_date
        type_params:
          time_granularity: day
    # Numerator and denominator are both restricted to the cohort that has had
    # the full window. Counting an account that signed up four days ago as a
    # failed 30-day activation is the classic launch-analytics error: it drags
    # the North Star down hardest in the most recent weeks, which are exactly
    # the weeks a launch dashboard is read for.
    measures:
      - name: mature_accounts_7d
        agg: sum
        expr: case when is_mature_7d then 1 else 0 end
      - name: mature_accounts_sla
        agg: sum
        expr: case when is_mature_sla then 1 else 0 end
      - name: mature_accounts_30d
        agg: sum
        expr: case when is_mature_30d then 1 else 0 end
      - name: digitally_activated_accounts
        agg: sum
        expr: case when digital_activated_7d and is_mature_7d then 1 else 0 end
      - name: kit_activated_accounts
        agg: sum
        expr: case when kit_activated_sla and is_mature_sla then 1 else 0 end
      - name: combined_activated_accounts_30d
        agg: sum
        expr: case when combined_activated_30d and is_mature_30d then 1 else 0 end

  - name: kit_deliveries
    model: ref('fct_kit_deliveries')
    # Measures need an aggregation time dimension for MetricFlow to validate and
    # for metric_time to resolve. Signup date is used rather than delivery date:
    # delivery date is null for lost kits, which are exactly the rows the lost
    # rate must not drop.
    defaults:
      agg_time_dimension: signup_date
    entities:
      - name: account
        type: primary
        expr: account_id
    dimensions:
      - name: signup_date
        type: time
        expr: pawtrail_signup_date
        type_params:
          time_granularity: day
      - name: state
        type: categorical
    measures:
      # `kits_shipped` counts every account with a kit obligation, including
      # lost ones. The earlier name `kits_delivered` was misleading: it was used
      # as the denominator of the on-time rate while actually counting kits that
      # never arrived, so "on-time delivery rate" and "lost rate" were quietly
      # measured against different populations than their names implied.
      - name: kits_shipped
        agg: sum
        expr: case when is_mature_sla then 1 else 0 end
      - name: kits_on_time
        agg: sum
        expr: case when kit_activated_sla and is_mature_sla then 1 else 0 end
      - name: kits_lost
        agg: sum
        expr: case when kit_lost and is_mature_sla then 1 else 0 end

  - name: weekly_attach
    model: ref('fct_weekly_attach')
    defaults:
      agg_time_dimension: signup_week
    entities:
      # Surrogate key, not `state`: the grain is (state, week), so `state` alone
      # is not unique and declaring it primary is a false uniqueness claim that
      # can fan out joins.
      - name: weekly_attach_row
        type: primary
        expr: weekly_attach_key
    dimensions:
      - name: state
        type: categorical
      - name: signup_week
        type: time
        type_params:
          time_granularity: week
    # Both measures are semi-additive: they sum correctly ACROSS states within a
    # week, but not across weeks (cumulative_subscriptions would double-count and
    # eligible_premium_accounts would be multiplied by the number of weeks).
    # attach_rate is therefore only valid grouped by signup_week, or by
    # signup_week AND state. Never query it grouped by state alone.
    # `agg: max` was wrong here: grouped by week it silently returns the largest
    # state's cumulative over the largest state's base — i.e. SP's attach rate
    # mislabelled as the national trend.
    measures:
      - name: cumulative_subscriptions
        agg: sum
        expr: cumulative_subscriptions
      - name: eligible_premium_accounts
        agg: sum
        expr: eligible_premium_accounts

  - name: weekly_channel_economics
    model: ref('fct_weekly_channel_economics')
    defaults:
      agg_time_dimension: signup_week
    entities:
      # Surrogate key for the same reason as weekly_attach: the grain is
      # (channel, week), so `channel` alone is not unique.
      - name: channel_week_row
        type: primary
        expr: channel_week_key
    dimensions:
      - name: channel
        type: categorical
      - name: signup_week
        type: time
        type_params:
          time_granularity: week
    measures:
      - name: channel_new_subscriptions
        agg: sum
        expr: new_subscriptions
      - name: channel_activated_subscriptions
        agg: sum
        expr: activated_subscriptions
      - name: channel_spend_usd
        agg: sum
        expr: spend_usd
      - name: avg_contribution_margin
        agg: average
        expr: contribution_margin_per_subscription

  - name: sales_pitches
    model: ref('fct_sales_pitches')
    defaults:
      agg_time_dimension: pitch_date
    entities:
      - name: pitch
        type: primary
        expr: pitch_id
    dimensions:
      - name: pitch_date
        type: time
        type_params:
          time_granularity: day
      - name: state
        type: categorical
    measures:
      - name: pitches_total
        agg: count
        expr: pitch_id
      - name: pitches_won
        agg: sum
        expr: case when won then 1 else 0 end

  - name: at_risk_accounts
    model: ref('fct_at_risk_accounts')
    defaults:
      agg_time_dimension: signup_date
    entities:
      - name: account
        type: primary
        expr: account_id
    dimensions:
      - name: signup_date
        type: time
        expr: pawtrail_signup_date
        type_params:
          time_granularity: day
      - name: state
        type: categorical
      - name: channel
        type: categorical
      - name: risk_driver
        type: categorical
    measures:
      - name: assessable_accounts
        agg: count
        expr: account_id
      - name: at_risk_accounts_count
        agg: sum
        expr: case when is_at_risk then 1 else 0 end
```

- [ ] **Step 2: Validate the semantic models**

```bash
cd pawtrail_dbt
# `mf` has no --profiles-dir flag: it resolves profiles via DBT_PROFILES_DIR,
# falling back to ~/.dbt/profiles.yml. Since this project keeps profiles.yml
# inside pawtrail_dbt/, every mf command needs this exported first or it fails
# with a missing-profile error.
export DBT_PROFILES_DIR="$PWD"
dbt parse --profiles-dir .
mf validate-configs
cd ..
```

Expected: `mf validate-configs` reports success with no errors.

Note that `weekly_attach` and `weekly_channel_economics` now key on surrogate
row keys, with `state` and `channel` declared as ordinary categorical
dimensions. Every metric in Task 15 groups by those dimensions or by
`metric_time`, so no cross-model join through those entities is required.

- [ ] **Step 3: Commit**

```bash
git add pawtrail_dbt/models/marts/_semantic_models.yml
git commit -m "Add MetricFlow semantic models over the marts layer"
```

---

## Task 15: Semantic layer — metrics definitions and acceptance verification

**Files:**
- Create: `pawtrail_dbt/models/marts/_metrics.yml`

**Interfaces:**
- Consumes: every measure defined in Task 14's semantic models.
- Produces: 17 named metrics queryable via `mf query --metrics <name>` — the interface Task 16 (Tableau) and Task 19 (NARRATIVE.md) both read from.

- [ ] **Step 1: Define the metrics**

Create `pawtrail_dbt/models/marts/_metrics.yml`:

```yaml
metrics:
  - name: weekly_new_subscriptions
    type: simple
    label: "Weekly New Subscriptions"
    type_params:
      measure: subscription_count

  - name: attach_rate
    type: ratio
    label: "Attach Rate (Premium to PawTrail)"
    type_params:
      numerator: cumulative_subscriptions
      denominator: eligible_premium_accounts

  # Every activation rate divides by its matching *mature* cohort, not by all
  # accounts. See Task 8: an account that has not yet had the full window has
  # not failed, and counting it as a failure understates activation in exactly
  # the most recent weeks.
  - name: digital_activation_rate_7d
    type: ratio
    label: "Digital Activation Rate (7d, mature cohort)"
    type_params:
      numerator: digitally_activated_accounts
      denominator: mature_accounts_7d

  - name: kit_sla_rate
    type: ratio
    label: "Kit SLA Activation Rate (mature cohort)"
    type_params:
      numerator: kit_activated_accounts
      denominator: mature_accounts_sla

  - name: activation_rate_30d
    type: ratio
    label: "Combined 30-Day Activation Rate (mature cohort)"
    type_params:
      numerator: combined_activated_accounts_30d
      denominator: mature_accounts_30d

  - name: mature_cohort_size_30d
    type: simple
    label: "Accounts With a Full 30-Day Window"
    type_params:
      measure: mature_accounts_30d

  - name: kit_on_time_delivery_rate
    type: ratio
    label: "Kit On-Time Delivery Rate"
    type_params:
      numerator: kits_on_time
      denominator: kits_shipped

  - name: kit_lost_rate
    type: ratio
    label: "Kit Lost Rate"
    type_params:
      numerator: kits_lost
      denominator: kits_shipped

  - name: at_risk_account_rate
    type: ratio
    label: "At-Risk Account Rate"
    type_params:
      numerator: at_risk_accounts_count
      denominator: assessable_accounts

  - name: at_risk_accounts
    type: simple
    label: "At-Risk Accounts (CS queue size)"
    type_params:
      measure: at_risk_accounts_count

  - name: cumulative_subscriptions_to_date
    type: simple
    label: "Cumulative Subscriptions to Date"
    type_params:
      measure: cumulative_subscriptions

  - name: win_rate
    type: ratio
    label: "Sales-Assisted Win Rate"
    type_params:
      numerator: pitches_won
      denominator: pitches_total

  - name: cac_by_channel
    type: ratio
    label: "CAC by Channel"
    type_params:
      numerator: channel_spend_usd
      denominator: channel_new_subscriptions

  - name: cost_per_activated_account
    type: ratio
    label: "Cost per Activated Account"
    type_params:
      numerator: channel_spend_usd
      denominator: channel_activated_subscriptions

  - name: channel_spend
    type: simple
    label: "Marketing/Sales Spend"
    type_params:
      measure: channel_spend_usd

  - name: contribution_margin_per_subscription
    type: simple
    label: "Contribution Margin per Subscription"
    type_params:
      measure: avg_contribution_margin
```

- [ ] **Step 2: Validate and list the metrics**

```bash
cd pawtrail_dbt
export DBT_PROFILES_DIR="$PWD"
dbt parse --profiles-dir .
mf validate-configs
mf list metrics
cd ..
```

Expected: `mf list metrics` shows all 17 metrics defined above.

- [ ] **Step 3: Run the acceptance query — confirm the injected problem segment is actually surfaced**

```bash
cd pawtrail_dbt
export DBT_PROFILES_DIR="$PWD"
mf query --metrics activation_rate_30d --group-by metric_time__week
mf query --metrics kit_on_time_delivery_rate --group-by kit_deliveries__state --order kit_on_time_delivery_rate
mf query --metrics activation_rate_30d --group-by accounts__state --order activation_rate_30d
cd ..
```

Expected, and all three must hold:

1. `kit_on_time_delivery_rate` sorted ascending puts the configured
   `PROBLEM_STATE` (default `"OH"`) **first**, at roughly 55-60% against a
   baseline near 88%. Because Task 2 truncates the region list to the top 12
   and renormalises, there is no long tail of one-or-two-account states whose
   meaningless 0% or 100% rate could outrank the real signal — the earlier
   untruncated Olist distribution reached ~0.05% share, which at 3000 accounts
   is one or two rows.
2. The same region is also worst on `activation_rate_30d`, because the North
   Star requires an **on-time** kit (Task 8). If activation looks flat across
   regions while delivery does not, the North Star has silently reverted to the
   looser "delivered within 30 days" rule.
3. Every region in both queries has a denominator large enough to trust; spot
   check with `mf query --metrics mature_cohort_size_30d --group-by accounts__state`.

This is the concrete proof, called for in spec §8, that the semantic layer
surfaces a real root-cause signal rather than just displaying numbers.

- [ ] **Step 4: Export the acceptance query results as the Tableau/narrative control file**

```bash
cd pawtrail_dbt
export DBT_PROFILES_DIR="$PWD"
mf query --metrics weekly_new_subscriptions --group-by metric_time__week --csv ../dashboard/control_weekly_new_subscriptions.csv
mf query --metrics cumulative_subscriptions_to_date,attach_rate --group-by weekly_attach__signup_week --csv ../dashboard/control_attach_rate.csv
mf query --metrics attach_rate --group-by weekly_attach__signup_week,weekly_attach__state --csv ../dashboard/control_attach_rate_by_state.csv
mf query --metrics digital_activation_rate_7d,kit_sla_rate,activation_rate_30d,mature_cohort_size_30d --group-by metric_time__week --csv ../dashboard/control_activation_rates.csv
mf query --metrics kit_on_time_delivery_rate,kit_lost_rate --group-by kit_deliveries__state --csv ../dashboard/control_kit_sla_by_state.csv
mf query --metrics cac_by_channel,cost_per_activated_account --group-by weekly_channel_economics__signup_week,weekly_channel_economics__channel --csv ../dashboard/control_cac_by_channel.csv
mf query --metrics at_risk_account_rate,at_risk_accounts --group-by at_risk_accounts__risk_driver --csv ../dashboard/control_at_risk_by_driver.csv
mf query --metrics win_rate --group-by sales_pitches__state --csv ../dashboard/control_win_rate.csv
cd ..
```

Expected: 8 CSV files created under `dashboard/` — these become both the Tableau data source and the ground truth Task 19's narrative memo must match.

Each export now matches a view in Task 16: the attach exports carry both the
national trend and the by-state breakdown the launch-pulse view calls for, the
CAC export is broken out by channel, and `control_at_risk_by_driver.csv` feeds
the Customer Success queue view. `mature_cohort_size_30d` travels alongside the
activation rates so the dashboard can show how much of the base each rate is
actually computed on.

- [ ] **Step 5: Commit**

```bash
git add pawtrail_dbt/models/marts/_metrics.yml dashboard/control_*.csv
git commit -m "Define launch metrics in the semantic layer and export control query results"
```

---

## Task 16: Tableau Public dashboard

**Files:**
- Create: `dashboard/README.md`

**Interfaces:**
- Consumes: the six `control_*.csv` files exported in Task 15, Step 4.
- Produces: a published Tableau Public workbook URL, recorded in `dashboard/README.md`, consumed by Task 17 (README) and Task 19 (NARRATIVE.md).

- [ ] **Step 1: Build the workbook in Tableau Public Desktop**

Connect Tableau Public to the eight CSV files in `dashboard/`. Build these views, matching spec §6's dashboard structure:

1. **Launch pulse** — line chart of `control_weekly_new_subscriptions.csv` (weekly new subscriptions) and `control_attach_rate.csv` (cumulative subscriptions and national attach rate over time), with `control_attach_rate_by_state.csv` as the by-region breakdown.
2. **Activation** — bar/line chart of `control_activation_rates.csv` showing `digital_activation_rate_7d`, `kit_sla_rate`, and `activation_rate_30d` over time. Plot `mature_cohort_size_30d` as a secondary axis or tooltip so a reader can see how many accounts each rate is computed on — the most recent weeks are deliberately excluded from the 30-day rate until their window closes, and a chart that hides that invites the reader to over-read a thin cohort.
3. **Kit operations** — bar chart of `control_kit_sla_by_state.csv`, sorted ascending by `kit_on_time_delivery_rate`, so the injected problem state is visually the worst performer.
4. **Acquisition efficiency** — chart of `control_cac_by_channel.csv` (CAC and cost-per-activated-account by channel over time) plus `control_win_rate.csv` broken out by state.
5. **Customer Success queue** — bar chart of `control_at_risk_by_driver.csv` showing at-risk account counts split by `risk_driver` (`digital_failure`, `physical_failure`, `both_legs_failed`, `onboarding_gap`). This is the view that turns the analysis into an action list, and it is what makes the launch dashboard answer "who do we call on Monday" rather than only "how are we doing".

- [ ] **Step 2: Publish to Tableau Public**

Use *File → Save to Tableau Public* and note the resulting public URL.

- [ ] **Step 3: Verify the published dashboard matches the control data**

Open the published URL and confirm the on-time delivery rate for the problem state matches the value in `control_kit_sla_by_state.csv` from Task 15 (within rounding).

- [ ] **Step 4: Document the dashboard**

Create `dashboard/README.md`:

```markdown
# PawTrail Launch Dashboard

Published Tableau Public workbook: <PASTE_PUBLISHED_URL_HERE>

Built from the semantic-layer metric exports in this directory
(`control_*.csv`), generated via `mf query` — see
`docs/superpowers/plans/2026-08-12-pawtrail-launch-analytics.md` Task 15.

## Views

1. Launch pulse — cumulative and weekly new subscriptions, attach rate trend
   (national and by region)
2. Activation — 7-day digital, kit SLA, and combined 30-day activation rates
   over time, with the mature cohort size behind each rate
3. Kit operations — on-time delivery rate by state
4. Acquisition efficiency — CAC and cost per activated account by channel,
   win rate by state
5. Customer Success queue — at-risk accounts split by failure driver

## Reading the activation rates

Activation rates are computed on the **mature cohort** only: accounts that have
had the full window (7, 10, or 30 days) to activate. Recent signups are excluded
from the denominator until their window closes rather than being counted as
failures, so the most recent weeks show a smaller cohort rather than an
artificially collapsing rate.

## Data freshness

This dashboard is a static snapshot of a simulated 0–120 day launch window,
not a live-refreshing operational dashboard. It was built from a one-time
export of the `control_*.csv` files in this directory; Tableau Public does
not support live connections to the local DuckDB warehouse. If the
generator, seed, or dbt models change after publishing, the CSVs and
published workbook must be regenerated and re-published manually (see
Task 20, Step 5 for the drift check).
```

- [ ] **Step 5: Commit**

```bash
git add dashboard/README.md
git commit -m "Publish Tableau Public launch dashboard"
```

---

## Task 17: README.md

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: the published dashboard URL from Task 16.

- [ ] **Step 1: Write the README**

Create `README.md`:

```markdown
# PawTrail Launch Analytics

A portfolio case study: a launch-phase (day 0–120) analytics stack for
**PawTrail**, a fictional monthly subscription add-on (physical pet-care
kit + digital care-tracking app) bundled on top of an existing pet-care
platform's Premium plan.

**This product, and the company it belongs to, are entirely fictional.**
No real company, confidential data, or real business metrics are used
anywhere in this repository.

## Data

The dataset is hybrid:

- **Real**: delivery-delay and state-distribution *patterns*, resampled
  from the public [Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
  (Kaggle) — see `data/olist_reference/`. Only statistical shape is reused,
  never Olist's actual customer/order identities.
- **Synthetic**: everything specific to the PawTrail subscription mechanic
  (signups, digital engagement, kit delivery linkage, pricing, marketing
  spend, sales pitches) — generated by seeded scripts in `generator/`.

## Architecture

```
Olist (real: delivery timing, state distribution)  ─┐
                                                      ├─→ DuckDB (raw) ─→ dbt (staging → intermediate → marts) ─→ MetricFlow (semantic layer) ─→ Tableau Public
Synthetic generator (subscriptions, engagement,     ─┘
kit deliveries, pricing, spend, sales pitches)
```

- **Warehouse**: DuckDB (local, no cloud account needed)
- **Transformation**: dbt-core + dbt-duckdb, with dbt tests written
  test-first (assertion before model — see the implementation plan)
- **Semantic layer**: dbt Semantic Layer / MetricFlow, queried locally via
  the `mf` CLI
- **Dashboard**: Tableau Public — see `dashboard/README.md` for the
  published link

## How to run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Get the real Olist reference distributions (see data/olist_reference/README.md)
python data/olist_reference/fetch_olist_reference_distributions.py

# 2. Generate synthetic PawTrail data
python generator/build_seeds.py

# 3. Build and test the dbt project
cd pawtrail_dbt
dbt seed --profiles-dir .
dbt build --profiles-dir .

# 4. Query the semantic layer
# `mf` reads DBT_PROFILES_DIR (it has no --profiles-dir flag), and this
# project keeps profiles.yml inside pawtrail_dbt/ rather than ~/.dbt/.
export DBT_PROFILES_DIR="$PWD"
mf validate-configs
mf list metrics
mf query --metrics activation_rate_30d --group-by metric_time__week
```

## Repository structure

- `data/olist_reference/` — real-data extraction (delivery delay, state share)
- `generator/` — synthetic PawTrail data generators (pytest-covered)
- `pawtrail_dbt/` — dbt project: staging → intermediate → marts, semantic layer
- `dashboard/` — Tableau Public workbook link and metric exports
- `docs/superpowers/specs/` — design spec
- `docs/superpowers/plans/` — implementation plan
- `NARRATIVE.md` — 1-page launch-health memo
- `METRICS.md` — human-readable metrics dictionary

## Out of scope (by design)

12-month churn, NRR, LTV, LTV:CAC, Rule of 40 — these require months of
retention data this launch window doesn't have yet. See
`docs/superpowers/specs/2026-08-12-pawtrail-launch-analytics-design.md`
§2 and §6 for the reasoning.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Add project README"
```

---

## Task 18: METRICS.md

**Files:**
- Create: `METRICS.md`

**Interfaces:**
- Consumes: the 12 metrics defined in Task 15's `_metrics.yml`.

- [ ] **Step 1: Write the metrics dictionary**

Create `METRICS.md` mirroring the MetricFlow definitions in
`pawtrail_dbt/models/marts/_metrics.yml` in human-readable form. For each of
the 17 metrics listed there, include: name, one-sentence business
definition, formula (numerator/denominator or measure), and which
semantic model(s) it draws from. Structure the document in the same five
categories used in the dashboard (Task 16): Launch pulse, Activation, Kit
operations, Acquisition efficiency, Customer Success queue.

Include a **Definitions that carry a judgement call** section documenting the
three choices where a defensible alternative exists, since these are what an
interviewer will probe:

- **Cohort maturity.** Activation denominators count only accounts that have had
  the full window. State the alternative (count everyone) and why it was
  rejected: it reports recent signups as failures and understates activation
  precisely in the newest weeks.
- **On-time vs. delivered.** Combined activation requires the kit to hit the
  10-day SLA, not merely to arrive within 30 days.
- **Semi-additivity of attach rate.** `cumulative_subscriptions` and
  `eligible_premium_accounts` sum across regions within a week but not across
  weeks, so `attach_rate` is valid grouped by week, or by week and region, and
  must never be grouped by region alone.

End the document with a **Future extensions** section listing
catalog metrics from the spec (`docs/superpowers/specs/2026-08-12-pawtrail-launch-analytics-design.md`
§6) that were deliberately not implemented as MetricFlow metrics in this
version — e.g., cost per lead, paid-vs-organic CAC split, ARPA as a
standalone metric — noting they'd require additional generator data
(lead-level events, spend-source tagging) beyond this version's scope.

- [ ] **Step 2: Commit**

```bash
git add METRICS.md
git commit -m "Add human-readable metrics dictionary"
```

---

## Task 19: NARRATIVE.md

**Files:**
- Create: `NARRATIVE.md`

**Interfaces:**
- Consumes: the `control_*.csv` files from Task 15 and the published dashboard from Task 16.

- [ ] **Step 1: Pull the actual numbers**

Open the six `dashboard/control_*.csv` files generated in Task 15, Step 4.
Note: the overall `activation_rate_30d` trend, the on-time delivery rate for
the problem state vs. the rest, the attach-rate trajectory, and the
CAC/cost-per-activated-account by channel.

- [ ] **Step 2: Write the memo**

Create `NARRATIVE.md`, structured as: (1) one-paragraph verdict — is the
launch healthy or not, based on which specific signal; (2) the root cause,
naming the actual problem state/channel found in the control CSVs and the
actual gap in on-time delivery rate; (3) a recommendation for the next 30
days, tied to that root cause (e.g., "escalate the carrier issue in
[state] before scaling marketing spend into that region"), and sized against
the at-risk queue from `control_at_risk_by_driver.csv` — how many accounts
Customer Success would actually be calling, split by driver; (4) an explicit
one-paragraph note on why churn/NRR/LTV are not part of this memo, citing
the same reasoning as spec §2 and §6.

Add a short **"How these numbers are counted"** paragraph covering the two
methodology choices a reader would otherwise have to reverse-engineer, both of
which are the kind of judgement the memo exists to demonstrate:

- Activation rates use the mature cohort only — accounts that have had the full
  7/10/30-day window. Recent signups are excluded rather than counted as
  failures, which is why the 30-day rate covers fewer accounts than the total
  subscriber count.
- Combined activation requires an **on-time** kit, not merely a delivered one.
  Nearly every kit arrives inside 30 days, so a "delivered within 30 days" rule
  would let the problem region score as fully activated and hide the very issue
  the memo identifies.

- [ ] **Step 3: Commit**

```bash
git add NARRATIVE.md
git commit -m "Add launch-health narrative memo"
```

---

## Task 20: End-to-end pipeline verification

**Files:** None created — this task re-runs the full pipeline from a clean state to confirm reproducibility.

**Interfaces:** None — this is a verification-only task.

- [ ] **Step 1: Remove the local DuckDB database to simulate a fresh clone**

```bash
rm -f pawtrail_dbt/pawtrail.duckdb
```

- [ ] **Step 2: Re-run the full Python test suite**

```bash
pytest -v
```

Expected: every test from Tasks 2–6 passes.

- [ ] **Step 3: Rebuild the seeds and the full dbt project**

```bash
python generator/build_seeds.py
cd pawtrail_dbt
dbt seed --profiles-dir .
dbt build --profiles-dir .
cd ..
```

Expected: all seeds load, all models build, all tests (schema + singular) pass with zero failures.

- [ ] **Step 4: Re-validate and re-query the semantic layer**

```bash
cd pawtrail_dbt
export DBT_PROFILES_DIR="$PWD"
mf validate-configs
mf query --metrics activation_rate_30d,kit_on_time_delivery_rate --group-by metric_time__week
mf query --metrics cac_by_channel --group-by weekly_channel_economics__signup_week,weekly_channel_economics__channel
mf query --metrics kit_on_time_delivery_rate --group-by kit_deliveries__state --order kit_on_time_delivery_rate
mf query --metrics at_risk_account_rate --group-by at_risk_accounts__risk_driver
cd ..
```

Expected: validation succeeds, and specifically —

- All rates are non-null and in bounds ([0, 1]).
- **`cac_by_channel` returns non-null values for every week.** An all-null CAC
  column means the marketing-spend week boundary has drifted away from
  `date_trunc('week', ...)` again; the `not_null` test on `cac` should have
  caught it in Step 3, so a failure here means the guard was removed.
- The problem region sorts first on `kit_on_time_delivery_rate` and no region
  has a nonsense rate driven by a handful of accounts.
- The at-risk queue is split across drivers rather than concentrated entirely in
  one bucket, which would suggest the driver `case` expression is mis-ordered.

- [ ] **Step 5: Confirm the published Tableau dashboard still matches**

Compare the current `dashboard/control_kit_sla_by_state.csv` output against the published Tableau Public workbook from Task 16. If the generator's random seed hasn't changed, the values must match exactly.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "Verify end-to-end pipeline reproducibility" --allow-empty
```
