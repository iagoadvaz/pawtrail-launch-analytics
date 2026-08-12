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
- Produces: `compute_delivery_delay_distribution(orders: pd.DataFrame) -> pd.Series` and `compute_state_distribution(customers: pd.DataFrame) -> pd.Series`, and (when run as a script) the committed files `data/olist_reference/reference_delivery_delays.csv` and `data/olist_reference/reference_state_distribution.csv`, consumed by Task 5's `build_seeds.py`.

- [ ] **Step 1: Document how to obtain the real Olist dataset**

Create `data/olist_reference/README.md`:

```markdown
# Olist reference distributions

This project borrows two *statistical distributions* from the real, public
[Olist Brazilian E-Commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
(Kaggle) to make PawTrail's synthetic kit-delivery logistics and geography
realistic. No Olist customer, order, or product identity is reused — only
the empirical shape of delivery delays and state distribution.

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

This writes `reference_delivery_delays.csv` and
`reference_state_distribution.csv` into this directory. Those two small
files are committed to the repo; the raw Olist download itself is not
(see `.gitignore`).
```

- [ ] **Step 2: Write the failing test**

Create `data/olist_reference/tests/test_fetch_olist_reference_distributions.py`:

```python
import pandas as pd

from data.olist_reference.fetch_olist_reference_distributions import (
    compute_delivery_delay_distribution,
    compute_state_distribution,
)


def test_delivery_delay_distribution_computes_actual_minus_estimated():
    orders = pd.DataFrame(
        {
            "order_id": ["a", "b", "c"],
            "order_estimated_delivery_date": [
                "2018-01-10",
                "2018-01-10",
                "2018-01-10",
            ],
            "order_delivered_customer_date": [
                "2018-01-12",  # 2 days late
                "2018-01-08",  # 2 days early
                None,  # not yet delivered, must be dropped
            ],
        }
    )

    result = compute_delivery_delay_distribution(orders)

    assert list(result) == [2, -2]


def test_state_distribution_sums_to_one():
    customers = pd.DataFrame({"customer_state": ["SP", "SP", "RJ", "MG"]})

    result = compute_state_distribution(customers)

    assert result["SP"] == 0.5
    assert result["RJ"] == 0.25
    assert result["MG"] == 0.25
    assert abs(result.sum() - 1.0) < 1e-9
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

These distributions (delivery delay in days, customer state share) are used
downstream only as sampling scaffolds for synthetic PawTrail data. No Olist
customer, order, or product identity is reused.
"""
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).parent / "raw"
OUTPUT_DIR = Path(__file__).parent


def compute_delivery_delay_distribution(orders: pd.DataFrame) -> pd.Series:
    """Return delivery delay in days (actual - estimated) for delivered orders.

    Positive values mean the order arrived late; negative means early.
    """
    delivered = orders.dropna(
        subset=["order_delivered_customer_date", "order_estimated_delivery_date"]
    ).copy()
    delivered["order_delivered_customer_date"] = pd.to_datetime(
        delivered["order_delivered_customer_date"]
    )
    delivered["order_estimated_delivery_date"] = pd.to_datetime(
        delivered["order_estimated_delivery_date"]
    )
    delay_days = (
        delivered["order_delivered_customer_date"]
        - delivered["order_estimated_delivery_date"]
    ).dt.days
    return delay_days.rename("delay_days")


def compute_state_distribution(customers: pd.DataFrame) -> pd.Series:
    """Return the share of customers per state, summing to 1.0."""
    counts = customers["customer_state"].value_counts()
    return (counts / counts.sum()).rename("share")


def main() -> None:
    orders = pd.read_csv(RAW_DIR / "olist_orders_dataset.csv")
    customers = pd.read_csv(RAW_DIR / "olist_customers_dataset.csv")

    delay_days = compute_delivery_delay_distribution(orders)
    delay_days.to_csv(OUTPUT_DIR / "reference_delivery_delays.csv", index=False)

    state_share = compute_state_distribution(customers)
    state_share.to_csv(OUTPUT_DIR / "reference_state_distribution.csv")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest data/olist_reference/tests/test_fetch_olist_reference_distributions.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Download the real dataset and generate the committed reference files**

Follow `data/olist_reference/README.md` (requires a Kaggle account), then:

```bash
python data/olist_reference/fetch_olist_reference_distributions.py
```

Expected: `data/olist_reference/reference_delivery_delays.csv` and `reference_state_distribution.csv` are created.

- [ ] **Step 7: Commit**

```bash
git add data/olist_reference/README.md data/olist_reference/fetch_olist_reference_distributions.py data/olist_reference/tests/test_fetch_olist_reference_distributions.py data/olist_reference/reference_delivery_delays.csv data/olist_reference/reference_state_distribution.csv
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

from generator.generate_subscriptions import generate_subscriptions

REFERENCE_STATES = pd.Series({"SP": 0.6, "RJ": 0.3, "MG": 0.1})


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
    """The first week should have materially fewer signups than the middle
    of the launch window, confirming an S-curve rather than a flat ramp."""
    df = generate_subscriptions(
        n_accounts=2000, launch_days=120, seed=42, state_distribution=REFERENCE_STATES
    )
    days = (df["pawtrail_signup_date"] - df["pawtrail_signup_date"].min()).dt.days

    first_week = ((days >= 0) & (days < 7)).sum()
    middle_week = ((days >= 56) & (days < 63)).sum()

    assert middle_week > first_week
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

LAUNCH_DATE = dt.date(2026, 1, 1)


def _sample_signup_days(n_accounts: int, launch_days: int, rng: np.random.Generator) -> np.ndarray:
    """Sample signup day-offsets following a logistic (S-curve) adoption curve."""
    u = rng.uniform(0.02, 0.98, size=n_accounts)
    logistic_x = np.log(u / (1 - u))  # standard logistic quantile
    scale = launch_days / 12.0
    midpoint = launch_days / 2.0
    days = midpoint + logistic_x * scale
    return np.clip(days, 0, launch_days - 1).astype(int)


def generate_subscriptions(
    n_accounts: int,
    launch_days: int,
    seed: int,
    state_distribution: pd.Series,
) -> pd.DataFrame:
    """Return one row per synthetic PawTrail subscription account."""
    rng = np.random.default_rng(seed)

    signup_days = _sample_signup_days(n_accounts, launch_days, rng)
    states = rng.choice(state_distribution.index, size=n_accounts, p=state_distribution.values)
    channels = rng.choice(CHANNELS, size=n_accounts, p=[0.7, 0.3])
    pet_tiers = rng.choice(PET_TIERS, size=n_accounts, p=[0.4, 0.4, 0.2])
    premium_tenure_days = rng.integers(30, 900, size=n_accounts)

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

Expected: 4 passed.

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
- Consumes: the `subscriptions: pd.DataFrame` produced by Task 3 (`account_id, state, pawtrail_signup_date` columns required), and a `delay_days_sample: np.ndarray` shaped like Task 2's `reference_delivery_delays.csv` values.
- Produces: `generate_kit_deliveries(subscriptions, delay_days_sample, problem_state, problem_delay_penalty_days, seed) -> pd.DataFrame` with columns `account_id, kit_delivered_date, kit_lost, delivery_delay_days`; `generate_digital_engagement(subscriptions, seed) -> pd.DataFrame` with columns `account_id, first_login_date, care_tasks_completed_first_cycle`. Consumed by Task 6's `build_seeds.py`.

- [ ] **Step 1: Write the failing tests**

Create `generator/tests/test_generate_activity.py`:

```python
import datetime as dt

import numpy as np
import pandas as pd

from generator.generate_activity import (
    generate_digital_engagement,
    generate_kit_deliveries,
)


def _sample_subscriptions(states):
    return pd.DataFrame(
        {
            "account_id": [f"acct_{i}" for i in range(len(states))],
            "state": states,
            "pawtrail_signup_date": [dt.date(2026, 1, 1)] * len(states),
        }
    )


def test_problem_state_has_higher_average_delay():
    states = ["SP"] * 500 + ["RJ"] * 500
    subs = _sample_subscriptions(states)
    delay_sample = np.zeros(1000)  # isolate the penalty effect from baseline noise

    result = generate_kit_deliveries(
        subs, delay_days_sample=delay_sample, problem_state="RJ",
        problem_delay_penalty_days=10, seed=1,
    )

    avg_delay_sp = result.loc[subs["state"] == "SP", "delivery_delay_days"].mean()
    avg_delay_rj = result.loc[subs["state"] == "RJ", "delivery_delay_days"].mean()

    assert avg_delay_rj > avg_delay_sp + 5


def test_kit_delivered_date_never_before_signup():
    states = ["SP"] * 300
    subs = _sample_subscriptions(states)
    delay_sample = np.array([-30, -10, -3, -1, 0, 1, 3, 5, 90])  # wide, realistic-looking range

    result = generate_kit_deliveries(
        subs, delay_days_sample=delay_sample, problem_state="RJ",
        problem_delay_penalty_days=10, seed=2,
    )

    delivered = result.dropna(subset=["kit_delivered_date"])
    merged = delivered.merge(subs, on="account_id")
    assert (merged["kit_delivered_date"] >= merged["pawtrail_signup_date"]).all()


def test_digital_engagement_zero_tasks_when_no_login():
    states = ["SP"] * 1000
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

Delivery delays are sampled from the real Olist empirical delay distribution
to keep the logistics noise realistic. One state is deliberately made worse
than the rest so the launch dashboard has a genuine root cause to surface.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

BASE_FULFILLMENT_DAYS = 5


def generate_kit_deliveries(
    subscriptions: pd.DataFrame,
    delay_days_sample: np.ndarray,
    problem_state: str,
    problem_delay_penalty_days: int,
    seed: int,
) -> pd.DataFrame:
    """Return one row per account describing its first-kit delivery outcome."""
    rng = np.random.default_rng(seed)
    n = len(subscriptions)

    sampled_delays = rng.choice(delay_days_sample, size=n, replace=True)
    penalty = np.where(subscriptions["state"].values == problem_state, problem_delay_penalty_days, 0)
    # Floor total delay so kit_delivered_date can never land before signup.
    total_delay = np.maximum(sampled_delays + penalty, -BASE_FULFILLMENT_DAYS)

    lost_mask = rng.uniform(size=n) < np.where(
        subscriptions["state"].values == problem_state, 0.08, 0.02
    )

    delivered_dates = [
        None if lost else signup + dt.timedelta(days=BASE_FULFILLMENT_DAYS + int(delay))
        for signup, delay, lost in zip(subscriptions["pawtrail_signup_date"], total_delay, lost_mask)
    ]

    return pd.DataFrame(
        {
            "account_id": subscriptions["account_id"],
            "kit_delivered_date": delivered_dates,
            "kit_lost": lost_mask,
            "delivery_delay_days": total_delay,
        }
    )


def generate_digital_engagement(subscriptions: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Return one row per account describing its first-cycle digital activity."""
    rng = np.random.default_rng(seed)
    n = len(subscriptions)

    never_logs_in = rng.uniform(size=n) < 0.15
    days_to_first_login = rng.integers(0, 21, size=n)
    tasks_completed = np.where(never_logs_in, 0, rng.integers(0, 5, size=n))

    first_login_date = [
        None if skip else signup + dt.timedelta(days=int(d))
        for signup, d, skip in zip(subscriptions["pawtrail_signup_date"], days_to_first_login, never_logs_in)
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

Expected: 3 passed.

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
- Consumes: `LAUNCH_DATE` from Task 3's `generator.generate_subscriptions`; a `subscriptions: pd.DataFrame` with a `channel` column for `generate_sales_pitches`.
- Produces: `generate_premium_base(state_distribution, total_eligible) -> pd.DataFrame` (`state, eligible_premium_accounts`); `generate_pricing() -> pd.DataFrame` (`pet_tier, monthly_price_usd, kit_cogs_usd, shipping_cost_usd`); `generate_marketing_spend(launch_date, launch_days, seed) -> pd.DataFrame` (`week_start_date, channel, spend_usd`); `generate_sales_pitches(subscriptions, seed) -> pd.DataFrame` (`pitch_id, won`). Consumed by Task 6's `build_seeds.py`.

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
    state_distribution = pd.Series({"SP": 0.6, "RJ": 0.4})

    result = generate_premium_base(state_distribution, total_eligible=1000)

    by_state = result.set_index("state")["eligible_premium_accounts"]
    assert by_state["SP"] == 600
    assert by_state["RJ"] == 400


def test_pricing_has_one_row_per_tier_with_positive_margin():
    result = generate_pricing()

    assert len(result) == 3
    margin = result["monthly_price_usd"] - result["kit_cogs_usd"] - result["shipping_cost_usd"]
    assert (margin > 0).all()


def test_marketing_spend_covers_full_launch_window():
    result = generate_marketing_spend(launch_date=dt.date(2026, 1, 1), launch_days=120, seed=1)

    assert result["week_start_date"].min() == dt.date(2026, 1, 1)
    assert (result["week_start_date"].max() - dt.date(2026, 1, 1)).days <= 120
    assert set(result["channel"]) == {"self_serve", "sales_assisted"}
    assert (result["spend_usd"] > 0).all()


def test_sales_pitches_win_count_matches_sales_assisted_subscriptions():
    subscriptions = pd.DataFrame(
        {
            "account_id": [f"a{i}" for i in range(10)],
            "channel": ["sales_assisted"] * 4 + ["self_serve"] * 6,
        }
    )

    result = generate_sales_pitches(subscriptions, seed=5)

    assert result["won"].sum() == 4
    assert len(result) > 4  # some pitches must have been lost
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
    """Return weekly marketing spend by channel, ramping over the launch."""
    rng = np.random.default_rng(seed)
    n_weeks = launch_days // 7 + 1
    weeks = np.arange(n_weeks)
    week_start_dates = [launch_date + dt.timedelta(days=int(w * 7)) for w in weeks]

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
    """Return one row per sales-assisted pitch, won or lost.

    The number of pitches is derived from the number of sales-assisted
    subscriptions divided by an assumed win rate, so the generated data is
    internally consistent with the subscriptions already created.
    """
    rng = np.random.default_rng(seed)
    assumed_win_rate = 0.35
    n_won = (subscriptions["channel"] == "sales_assisted").sum()
    n_total_pitches = int(round(n_won / assumed_win_rate))
    n_lost = n_total_pitches - n_won

    pitch_ids = [f"pitch_{i:05d}" for i in range(n_total_pitches)]
    won_flags = np.array([True] * n_won + [False] * n_lost)
    rng.shuffle(won_flags)

    return pd.DataFrame({"pitch_id": pitch_ids, "won": won_flags})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest generator/tests/test_generate_business_data.py -v
```

Expected: 4 passed.

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
    pd.Series({"SP": 0.6, "RJ": 0.3, PROBLEM_STATE: 0.1}, name="share").to_csv(
        ref_dir / "reference_state_distribution.csv"
    )
    pd.DataFrame({"delay_days": [-2, -1, 0, 1, 2, 3]}).to_csv(
        ref_dir / "reference_delivery_delays.csv", index=False
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
    assert len(premium_base) == 3  # SP, RJ, problem state
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
PROBLEM_STATE = "BA"
PROBLEM_DELAY_PENALTY_DAYS = 12
# Kept well above N_ACCOUNTS so the resulting attach rate stays realistic (< 100%).
TOTAL_ELIGIBLE_PREMIUM_ACCOUNTS = 15000


def _load_reference_distributions() -> tuple[pd.Series, "pd.Series[int]"]:
    state_distribution = pd.read_csv(
        REFERENCE_DIR / "reference_state_distribution.csv", index_col=0
    )["share"]
    delay_days_sample = pd.read_csv(REFERENCE_DIR / "reference_delivery_delays.csv")[
        "delay_days"
    ].to_numpy()
    return state_distribution, delay_days_sample


def build_seeds() -> None:
    SEEDS_DIR.mkdir(parents=True, exist_ok=True)

    state_distribution, delay_days_sample = _load_reference_distributions()

    subscriptions = generate_subscriptions(
        n_accounts=N_ACCOUNTS,
        launch_days=LAUNCH_DAYS,
        seed=SEED,
        state_distribution=state_distribution,
    )
    kit_deliveries = generate_kit_deliveries(
        subscriptions,
        delay_days_sample=delay_days_sample,
        problem_state=PROBLEM_STATE,
        problem_delay_penalty_days=PROBLEM_DELAY_PENALTY_DAYS,
        seed=SEED,
    )
    digital_engagement = generate_digital_engagement(subscriptions, seed=SEED)
    premium_base = generate_premium_base(state_distribution, TOTAL_ELIGIBLE_PREMIUM_ACCOUNTS)
    pricing = generate_pricing()
    marketing_spend = generate_marketing_spend(LAUNCH_DATE, LAUNCH_DAYS, seed=SEED)
    sales_pitches = generate_sales_pitches(subscriptions, seed=SEED)

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
- Produces: `stg_subscriptions(account_id, state, pet_tier, channel, premium_tenure_days, pawtrail_signup_date)`, `stg_kit_deliveries(account_id, kit_delivered_date, kit_lost, delivery_delay_days)`, `stg_digital_engagement(account_id, first_login_date, care_tasks_completed_first_cycle)` — all referenced by Task 8 onward via `{{ ref(...) }}`.

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
    cast(delivery_delay_days as integer) as delivery_delay_days
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
- Create: `pawtrail_dbt/models/intermediate/_intermediate__models.yml`
- Create: `pawtrail_dbt/models/intermediate/int_activation_funnel.sql`

**Interfaces:**
- Consumes: `stg_subscriptions`, `stg_kit_deliveries`, `stg_digital_engagement` from Task 7.
- Produces: `int_activation_funnel(account_id, state, pet_tier, channel, pawtrail_signup_date, first_login_date, care_tasks_completed_first_cycle, kit_delivered_date, kit_lost, days_to_first_login, days_to_kit_delivery, digital_activated_7d, kit_activated_sla, combined_activated_30d)` — `kit_activated_sla` is the single source of truth for "was the kit delivered on time," reused by Task 10's `fct_kit_deliveries` instead of being recomputed.

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

joined as (
    select
        s.account_id,
        s.state,
        s.pet_tier,
        s.channel,
        s.pawtrail_signup_date,
        d.first_login_date,
        d.care_tasks_completed_first_cycle,
        k.kit_delivered_date,
        k.kit_lost,
        date_diff('day', s.pawtrail_signup_date, d.first_login_date) as days_to_first_login,
        date_diff('day', s.pawtrail_signup_date, k.kit_delivered_date) as days_to_kit_delivery
    from subscriptions s
    left join digital_engagement d on s.account_id = d.account_id
    left join kit_deliveries k on s.account_id = k.account_id
)

select
    *,
    (first_login_date is not null and days_to_first_login <= 7) as digital_activated_7d,
    (kit_delivered_date is not null and not kit_lost and days_to_kit_delivery <= 10) as kit_activated_sla,
    (
        first_login_date is not null and days_to_first_login <= 30
        and kit_delivered_date is not null and not kit_lost and days_to_kit_delivery <= 30
    ) as combined_activated_30d
from joined
```

- [ ] **Step 5: Run `dbt build` to verify it passes**

```bash
cd pawtrail_dbt
dbt build --profiles-dir . --select intermediate
cd ..
```

Expected: model built, all tests `PASS` (including the singular test).

- [ ] **Step 6: Commit**

```bash
git add pawtrail_dbt/tests/assert_digital_activation_requires_login_date.sql pawtrail_dbt/models/intermediate/
git commit -m "Add activation funnel intermediate model with test-first business-rule test"
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
- Produces: `fct_activation_events(account_id, pawtrail_signup_date, digital_activated_7d, kit_activated_sla, combined_activated_30d, days_to_first_login, days_to_kit_delivery, care_tasks_completed_first_cycle)`; `fct_kit_deliveries(account_id, state, kit_delivered_date, kit_lost, delivery_delay_days, kit_activated_sla)` — both consumed by Task 14's semantic models. Note `kit_activated_sla` is reused from `int_activation_funnel`, not recomputed, to keep a single source of truth for the SLA definition.

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
    days_to_first_login,
    days_to_kit_delivery,
    care_tasks_completed_first_cycle
from {{ ref('int_activation_funnel') }}
```

Create `pawtrail_dbt/models/marts/fct_kit_deliveries.sql`:

```sql
select
    k.account_id,
    a.state,
    k.kit_delivered_date,
    k.kit_lost,
    k.delivery_delay_days,
    f.kit_activated_sla
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
- Produces: `dim_pricing(pet_tier, monthly_price_usd, kit_cogs_usd, shipping_cost_usd)`; `fct_premium_base(state, eligible_premium_accounts)`; `fct_marketing_spend(week_start_date, channel, spend_usd)`; `fct_sales_pitches(pitch_id, won)` — consumed by Task 12, 13, and Task 14's semantic models.

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

**Interfaces:**
- Consumes: `stg_subscriptions` (Task 7), `fct_premium_base` (Task 11).
- Produces: `fct_weekly_attach(state, signup_week, cumulative_subscriptions, eligible_premium_accounts, attach_rate)` — the join between subscriptions and the addressable base is done here in dbt (not in the semantic layer), keeping the attach-rate calculation in one auditable place. Consumed by Task 14's `weekly_attach` semantic model.

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

- [ ] **Step 2: Append the schema tests before the model exists**

Add to `pawtrail_dbt/models/marts/_marts__business.yml` (append under `models:`):

```yaml
  - name: fct_weekly_attach
    columns:
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

cumulative as (
    select
        state,
        signup_week,
        sum(new_subscriptions) over (
            partition by state order by signup_week
            rows between unbounded preceding and current row
        ) as cumulative_subscriptions
    from weekly_signups
),

premium_base as (
    select * from {{ ref('fct_premium_base') }}
)

select
    c.state,
    c.signup_week,
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
git add pawtrail_dbt/models/marts/_marts__business.yml pawtrail_dbt/models/marts/fct_weekly_attach.sql pawtrail_dbt/tests/assert_attach_rate_within_bounds.sql
git commit -m "Add fct_weekly_attach mart computing attach rate against the Premium base"
```

---

## Task 13: Mart — fct_weekly_channel_economics (test-first)

**Files:**
- Modify: `pawtrail_dbt/models/marts/_marts__business.yml` (append new model tests)
- Create: `pawtrail_dbt/models/marts/fct_weekly_channel_economics.sql`

**Interfaces:**
- Consumes: `stg_subscriptions` (Task 7), `int_activation_funnel` (Task 8), `fct_marketing_spend` and `dim_pricing` (Task 11).
- Produces: `fct_weekly_channel_economics(channel, signup_week, new_subscriptions, activated_subscriptions, spend_usd, cac, cost_per_activated_account, avg_price, contribution_margin_per_subscription)` — consumed by Task 14's `weekly_channel_economics` semantic model.

- [ ] **Step 1: Write the schema tests before the model exists**

Add to `pawtrail_dbt/models/marts/_marts__business.yml` (append under `models:`):

```yaml
  - name: fct_weekly_channel_economics
    columns:
      - name: channel
        tests:
          - not_null
      - name: new_subscriptions
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
    select account_id, combined_activated_30d
    from {{ ref('int_activation_funnel') }}
),

subs_with_activation as (
    select s.channel, s.signup_week, s.account_id, a.combined_activated_30d
    from subs s
    left join activation a on s.account_id = a.account_id
),

weekly_subs as (
    select
        channel,
        signup_week,
        count(*) as new_subscriptions,
        sum(case when combined_activated_30d then 1 else 0 end) as activated_subscriptions
    from subs_with_activation
    group by 1, 2
),

spend as (
    select channel, week_start_date as signup_week, spend_usd
    from {{ ref('fct_marketing_spend') }}
),

pricing_avg as (
    select
        avg(monthly_price_usd) as avg_price,
        avg(kit_cogs_usd + shipping_cost_usd) as avg_variable_cost
    from {{ ref('dim_pricing') }}
)

select
    w.channel,
    w.signup_week,
    w.new_subscriptions,
    w.activated_subscriptions,
    s.spend_usd,
    s.spend_usd / nullif(w.new_subscriptions, 0) as cac,
    s.spend_usd / nullif(w.activated_subscriptions, 0) as cost_per_activated_account,
    p.avg_price,
    p.avg_price - p.avg_variable_cost as contribution_margin_per_subscription
from weekly_subs w
left join spend s on w.channel = s.channel and w.signup_week = s.signup_week
cross join pricing_avg p
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

## Task 14: Semantic layer — semantic models

**Files:**
- Create: `pawtrail_dbt/models/marts/_semantic_models.yml`

**Interfaces:**
- Consumes: `dim_accounts`, `fct_subscriptions`, `fct_activation_events`, `fct_kit_deliveries`, `fct_weekly_attach`, `fct_weekly_channel_economics`, `fct_sales_pitches` (Tasks 9–13).
- Produces: five MetricFlow semantic models (`accounts`, `subscriptions`, `activation_events`, `kit_deliveries`, `weekly_attach`, `weekly_channel_economics`, `sales_pitches`) whose measures are consumed by Task 15's metric definitions.

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
    measures:
      - name: activation_event_count
        agg: count
        expr: account_id
      - name: digitally_activated_accounts
        agg: sum
        expr: case when digital_activated_7d then 1 else 0 end
      - name: kit_activated_accounts
        agg: sum
        expr: case when kit_activated_sla then 1 else 0 end
      - name: combined_activated_accounts_30d
        agg: sum
        expr: case when combined_activated_30d then 1 else 0 end

  - name: kit_deliveries
    model: ref('fct_kit_deliveries')
    entities:
      - name: account
        type: primary
        expr: account_id
    dimensions:
      - name: state
        type: categorical
    measures:
      - name: kits_delivered
        agg: count
        expr: account_id
      - name: kits_on_time
        agg: sum
        expr: case when kit_activated_sla then 1 else 0 end
      - name: kits_lost
        agg: sum
        expr: case when kit_lost then 1 else 0 end

  - name: weekly_attach
    model: ref('fct_weekly_attach')
    defaults:
      agg_time_dimension: signup_week
    entities:
      - name: state
        type: primary
        expr: state
    dimensions:
      - name: signup_week
        type: time
        type_params:
          time_granularity: week
    measures:
      - name: cumulative_subscriptions
        agg: max
        expr: cumulative_subscriptions
      - name: eligible_premium_accounts
        agg: max
        expr: eligible_premium_accounts

  - name: weekly_channel_economics
    model: ref('fct_weekly_channel_economics')
    defaults:
      agg_time_dimension: signup_week
    entities:
      - name: channel
        type: primary
        expr: channel
    dimensions:
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
    entities:
      - name: pitch
        type: primary
        expr: pitch_id
    measures:
      - name: pitches_total
        agg: count
        expr: pitch_id
      - name: pitches_won
        agg: sum
        expr: case when won then 1 else 0 end
```

- [ ] **Step 2: Validate the semantic models**

```bash
cd pawtrail_dbt
dbt parse --profiles-dir .
mf validate-configs
cd ..
```

Expected: `mf validate-configs` reports success with no errors. If it reports a join-path error on `weekly_attach` or `weekly_channel_economics`, this means those measures cannot be grouped by dimensions from other semantic models via their non-`account` primary entities — in that case, only group/query them by their own `state`/`channel` dimension (already sufficient for every metric in Task 15) rather than trying to join them to `accounts`.

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
- Produces: 12 named metrics queryable via `mf query --metrics <name>` — the interface Task 16 (Tableau) and Task 19 (NARRATIVE.md) both read from.

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

  - name: digital_activation_rate_7d
    type: ratio
    label: "Digital Activation Rate (7d)"
    type_params:
      numerator: digitally_activated_accounts
      denominator: activation_event_count

  - name: kit_sla_rate
    type: ratio
    label: "Kit SLA Activation Rate"
    type_params:
      numerator: kit_activated_accounts
      denominator: activation_event_count

  - name: activation_rate_30d
    type: ratio
    label: "Combined 30-Day Activation Rate"
    type_params:
      numerator: combined_activated_accounts_30d
      denominator: activation_event_count

  - name: kit_on_time_delivery_rate
    type: ratio
    label: "Kit On-Time Delivery Rate"
    type_params:
      numerator: kits_on_time
      denominator: kits_delivered

  - name: kit_lost_rate
    type: ratio
    label: "Kit Lost Rate"
    type_params:
      numerator: kits_lost
      denominator: kits_delivered

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
dbt parse --profiles-dir .
mf validate-configs
mf list metrics
cd ..
```

Expected: `mf list metrics` shows all 12 metrics defined above.

- [ ] **Step 3: Run the acceptance query — confirm the injected problem segment is actually surfaced**

```bash
cd pawtrail_dbt
mf query --metrics activation_rate_30d --group-by metric_time__week
mf query --metrics kit_on_time_delivery_rate --group-by kit_deliveries__state
cd ..
```

Expected: the second query shows the problem state configured in `generator/build_seeds.py` (`PROBLEM_STATE`, default `"BA"`) with a materially lower on-time delivery rate than other states — this is the concrete proof, called for in spec §8, that the semantic layer surfaces a real root-cause signal rather than just displaying numbers.

- [ ] **Step 4: Export the acceptance query results as the Tableau/narrative control file**

```bash
cd pawtrail_dbt
mf query --metrics weekly_new_subscriptions --group-by metric_time__week --csv ../dashboard/control_weekly_new_subscriptions.csv
mf query --metrics attach_rate --group-by weekly_attach__signup_week --csv ../dashboard/control_attach_rate.csv
mf query --metrics digital_activation_rate_7d,kit_sla_rate,activation_rate_30d --group-by metric_time__week --csv ../dashboard/control_activation_rates.csv
mf query --metrics kit_on_time_delivery_rate,kit_lost_rate --group-by kit_deliveries__state --csv ../dashboard/control_kit_sla_by_state.csv
mf query --metrics cac_by_channel,cost_per_activated_account --group-by weekly_channel_economics__signup_week --csv ../dashboard/control_cac_by_channel.csv
mf query --metrics win_rate --csv ../dashboard/control_win_rate.csv
cd ..
```

Expected: 6 CSV files created under `dashboard/` — these become both the Tableau data source and the ground truth Task 19's narrative memo must match.

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

Connect Tableau Public to the six CSV files in `dashboard/`. Build these views, matching spec §6's dashboard structure:

1. **Launch pulse** — line chart of `control_weekly_new_subscriptions.csv` (cumulative + weekly new subscriptions) and `control_attach_rate.csv` (attach rate trend by state).
2. **Activation** — bar/line chart of `control_activation_rates.csv` showing `digital_activation_rate_7d`, `kit_sla_rate`, and `activation_rate_30d` over time.
3. **Kit operations** — bar chart of `control_kit_sla_by_state.csv`, sorted ascending by `kit_on_time_delivery_rate`, so the injected problem state is visually the worst performer.
4. **Acquisition efficiency** — chart of `control_cac_by_channel.csv` (CAC and cost-per-activated-account by channel over time) plus the single `control_win_rate.csv` value as a stat tile.

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
2. Activation — 7/14/30-day activation rates over time
3. Kit operations — on-time delivery rate by state
4. Acquisition efficiency — CAC and cost per activated account by channel
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
the 12 metrics listed there, include: name, one-sentence business
definition, formula (numerator/denominator or measure), and which
semantic model(s) it draws from. Structure the document in the same four
categories used in the dashboard (Task 16): Launch pulse, Activation, Kit
operations, Acquisition efficiency.

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
[state] before scaling marketing spend into that region"); (4) an explicit
one-paragraph note on why churn/NRR/LTV are not part of this memo, citing
the same reasoning as spec §2 and §6.

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
mf validate-configs
mf query --metrics activation_rate_30d,kit_on_time_delivery_rate --group-by metric_time__week
cd ..
```

Expected: validation succeeds; the query returns non-null, in-bounds ([0, 1]) rates.

- [ ] **Step 5: Confirm the published Tableau dashboard still matches**

Compare the current `dashboard/control_kit_sla_by_state.csv` output against the published Tableau Public workbook from Task 16. If the generator's random seed hasn't changed, the values must match exactly.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "Verify end-to-end pipeline reproducibility" --allow-empty
```
