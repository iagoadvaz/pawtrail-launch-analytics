import datetime as dt

import pandas as pd

from generator.generate_subscription_lifecycle import (
    DAY_ZERO_CANCEL_RATE,
    _add_months,
    NON_ACTIVATED_CHURN_MULTIPLIER,
    PER_CYCLE_CHURN_HAZARD,
    generate_subscription_lifecycle,
)


def _subscriptions(n=600, launch=dt.date(2026, 1, 5)):
    return pd.DataFrame(
        {
            "account_id": [f"A{i:05d}" for i in range(n)],
            "pet_tier": ["small", "medium", "large"] * (n // 3),
            # Spread across the window so accounts exist with 0 to 3 elapsed
            # cycles, as in the real generator.
            "pawtrail_signup_date": [launch + dt.timedelta(days=(i * 97) % 110) for i in range(n)],
        }
    )


def _engagement(subs, logged_in_share=0.85):
    cutoff = int(len(subs) * logged_in_share)
    return pd.DataFrame(
        {
            "account_id": subs["account_id"],
            "first_login_date": [
                subs["pawtrail_signup_date"].iloc[i] + dt.timedelta(days=3)
                if i < cutoff
                else pd.NaT
                for i in range(len(subs))
            ],
        }
    )


def test_is_deterministic_for_a_given_seed():
    subs = _subscriptions()
    eng = _engagement(subs)

    a = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=7)
    b = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=7)

    pd.testing.assert_frame_equal(a, b)


def test_no_event_precedes_signup():
    subs = _subscriptions()
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=7)

    merged = events.merge(subs[["account_id", "pawtrail_signup_date"]], on="account_id")
    assert (merged["event_date"] >= merged["pawtrail_signup_date"]).all()


def test_no_event_follows_a_cancellation():
    """Cancellation is absorbing. An event after it would mean an account being
    charged after it left, which is the most expensive mistake this generator
    can make -- and one no schema test would catch."""
    subs = _subscriptions()
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=7)

    for account_id, group in events.groupby("account_id"):
        ordered = group.sort_values("event_seq")
        types = list(ordered["event_type"])
        if "canceled" in types:
            assert types.index("canceled") == len(types) - 1, account_id


def test_every_account_has_an_activation_event():
    subs = _subscriptions()
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=7)

    first = events.sort_values("event_seq").groupby("account_id").first()
    assert (first["event_type"] == "activated").all()
    assert len(first) == len(subs)


def test_churn_hazard_declines_across_cycles():
    """Subscription retention is not memoryless: the hazard declines and
    survivors get stickier. If this premise breaks, the simulated curve becomes a
    pure exponential and the cohort analysis loses the only interesting shape it
    could show.

    Asserts on GENERATED OUTPUT, not on the constant. Reading
    PER_CYCLE_CHURN_HAZARD and checking it declines tests a dict literal: a
    generator that ignored the constant entirely (hazard hardcoded to 0.20)
    passed that version of this test, and so did the eight others."""
    subs = _subscriptions(n=3000)
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=11)

    # Recover the hazard per cycle with the AT-RISK denominator: accounts alive
    # entering the cycle, not every account that has a row at it.
    observed = {}
    for cycle in (1, 2):
        alive = {
            a for a, g in events.groupby("account_id")
            if not ((g["event_type"] == "canceled") & (g["cycle_index"] < cycle)).any()
            and (g["cycle_index"] >= cycle).any()
        }
        churned = {
            a for a, g in events.groupby("account_id")
            if ((g["event_type"] == "canceled") & (g["cycle_index"] == cycle)).any()
        }
        observed[cycle] = len(churned & alive) / len(alive)

    # Cycle 2's hazard must be materially below cycle 1's. The gap in the planted
    # parameters is ~0.23 -> ~0.11, so a 25% relative margin is far outside
    # sampling noise at n=3000 and still fails loudly on a flat hazard.
    assert observed[2] < observed[1] * 0.75, observed


def test_non_activated_accounts_churn_more():
    """The planted effect. This test is NOT a discovery -- it verifies the
    generator's documented parameter reaches the data intact. See the global
    constraint on planted effects."""
    subs = _subscriptions(n=3000)
    eng = _engagement(subs, logged_in_share=0.5)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=11)

    canceled = set(events.loc[events["event_type"] == "canceled", "account_id"])
    logged_in = set(eng.loc[eng["first_login_date"].notna(), "account_id"])
    never = set(subs["account_id"]) - logged_in

    rate_logged = len(canceled & logged_in) / len(logged_in)
    rate_never = len(canceled & never) / len(never)

    # A deliberately loose band: with ~1500 accounts per arm the standard error
    # of the difference in proportions is around 1.5 points, so a tight
    # assertion on the multiplier would fail on legitimate re-seeds. What must
    # hold is the DIRECTION and the order of magnitude.
    assert rate_never > rate_logged
    assert 1.3 < (rate_never / rate_logged) < NON_ACTIVATED_CHURN_MULTIPLIER * 1.4


def test_day_zero_cancellations_exist_and_are_a_minority():
    subs = _subscriptions(n=3000)
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=11)

    merged = events.merge(subs[["account_id", "pawtrail_signup_date"]], on="account_id")
    day_zero = merged[
        (merged["event_type"] == "canceled")
        & (merged["event_date"] == merged["pawtrail_signup_date"])
    ]
    share = len(day_zero) / len(subs)

    assert 0 < share < DAY_ZERO_CANCEL_RATE * 2


def test_tier_changes_include_both_directions():
    """Without upgrades, expansion MRR is zero and NRR is capped at 100% by
    construction -- which the spec classifies as worse than absent."""
    subs = _subscriptions(n=3000)
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=11)

    order = {"small": 0, "medium": 1, "large": 2}
    original = dict(zip(subs["account_id"], subs["pet_tier"]))

    # Direction is measured against the tier IN FORCE before the event, replayed
    # in event_seq order -- not against the account's original tier. Comparing
    # to the original makes a round trip (small -> medium -> small) read as
    # "no change" and trips the != 0 assertion: that version failed on 109 of
    # 200 seeds. Seed 11 happens to be clean, which is why it looked fine, and
    # the obvious remedy of raising `n` makes it strictly worse because round
    # trips scale with n.
    directions = []
    in_force = dict(original)
    for _, row in events.sort_values(["account_id", "event_seq"]).iterrows():
        if row["event_type"] != "tier_changed":
            continue
        acct = row["account_id"]
        directions.append(order[row["new_pet_tier"]] - order[in_force[acct]])
        in_force[acct] = row["new_pet_tier"]

    assert any(d > 0 for d in directions), "no upgrade generated"
    assert any(d < 0 for d in directions), "no downgrade generated"
    assert all(d != 0 for d in directions), "tier_changed with no actual tier change"


def test_skips_do_not_end_the_subscription():
    """Skip is the replenishment model's named metric (Crystallize). A skip that
    ends the subscription would be a cancellation under another name."""
    subs = _subscriptions(n=1500)
    eng = _engagement(subs)

    events = generate_subscription_lifecycle(subs, eng, launch_days=120, seed=11)

    skipped = events[events["event_type"] == "skipped"]
    assert len(skipped) > 0

    # The last cycle each account could have faced, derived from the observed
    # window ALONE. This is the load-bearing part of the test and it took two
    # attempts to get right.
    #
    # `len(types) > 1` was the first version: a tautology, since `activated` is
    # always first, so the assertion was `X or True`. The second version
    # compared each skip against `max(present_cycles)` -- the account's own last
    # event -- and was still unfailable, for a subtler reason: if a skip ends
    # the subscription then the skip IS the last event, so `c < last_cycle` is
    # false and the assertion never runs. It read the boundary off the very data
    # the mutation truncates, which is the same self-comparison that makes
    # assert_no_events_after_cancellation unfailable in Task 3.
    #
    # Mutating the generator so a skip BREAKS out of the cycle loop passed both
    # earlier versions and fails this one.
    observation_date = subs["pawtrail_signup_date"].max()
    signup = dict(zip(subs["account_id"], subs["pawtrail_signup_date"]))

    def _last_due_cycle(account_id):
        due = [
            c for c in sorted(PER_CYCLE_CHURN_HAZARD)
            if _add_months(signup[account_id], c) <= observation_date
        ]
        return max(due) if due else 0

    checked = 0
    for account_id, group in events.groupby("account_id"):
        ordered = group.sort_values("event_seq")
        types = list(ordered["event_type"])
        if "skipped" not in types or "canceled" in types:
            continue
        skip_cycles = set(ordered.loc[ordered["event_type"] == "skipped", "cycle_index"])
        present_cycles = set(ordered["cycle_index"])
        last_due = _last_due_cycle(account_id)
        for c in skip_cycles:
            if c < last_due:
                checked += 1
                assert c + 1 in present_cycles, (account_id, c, present_cycles, last_due)

    # A guard on the guard: if no skip is followed by a due cycle, the loop
    # above asserts nothing and the test is vacuous however it is written.
    assert checked > 0, "no skip had a subsequent due cycle to check"
