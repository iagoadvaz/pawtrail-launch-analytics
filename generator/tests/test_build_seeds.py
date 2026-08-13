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
