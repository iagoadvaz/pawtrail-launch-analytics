import csv
from pathlib import Path

import pytest

from dashboard.build_dashboard import (
    REQUIRED_CONTROL_FILES,
    MissingControlFile,
    build_dashboard,
)


def _write(path: Path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


@pytest.fixture
def control_dir(tmp_path):
    d = tmp_path / "control"
    d.mkdir()
    _write(d / "control_attach_rate.csv",
           ["weekly_attach_row__signup_week__week", "attach_rate", "attach_rate_vs_target"],
           [["2026-01-05", "0.004", "0.027"], ["2026-05-04", "0.199", "1.327"]])
    # Both files carry what `mf query` actually emits at their own grain. The
    # earlier fixture put a plausible 0.119 into the cohort file, a value that
    # export cannot produce -- so the assertion below passed on fabricated data
    # while the real page rendered 100.0%. A fixture that models an impossible
    # CSV tests nothing but itself.
    _write(d / "control_cycle_exposure.csv",
           ["account__cycle_exposure_cohort", "assessable_base_accounts"],
           [["0", "339"], ["1", "1256"], ["2", "1099"], ["3+", "306"]])
    _write(d / "control_base_never_rebilled.csv",
           ["pct_base_never_rebilled", "renewal_unexposed_accounts", "assessable_base_accounts"],
           [["0.113", "339", "3000"]])
    _write(d / "control_breakeven_by_channel.csv",
           ["account__channel", "avg_breakeven_cycles", "share_breakeven_cycle_exposed"],
           [["self_serve", "1.0", "0.98"], ["sales_assisted", "2.4", "0.61"]])
    _write(d / "control_effective_cac.csv",
           ["effective_cac_row__channel", "effective_cac", "cac_uplift_pct"],
           [["self_serve", "11.24", "0.561"], ["sales_assisted", "31.44", "0.147"]])
    _write(d / "control_censoring_register.csv",
           ["metric_name", "denominator_accounts", "excluded_accounts", "excluded_share"],
           [["activation_rate_30d", "2643", "357", "0.119"]])
    _write(d / "control_decision_contract.csv",
           ["metric_name", "decision_question", "current_value", "threshold_value",
            "threshold_direction", "status", "action", "owner"],
           [["cac_uplift_pct", "efficient", "0.305", "0.25", "above", "triggered",
             "Review the kit shipping eligibility criteria", "Growth + Ops"]])
    for name in REQUIRED_CONTROL_FILES:
        if not (d / name).exists():
            _write(d / name, ["placeholder_col"], [["0"]])
    return d


def test_raises_when_a_required_control_file_is_missing(tmp_path, control_dir):
    (control_dir / "control_attach_rate.csv").unlink()

    with pytest.raises(MissingControlFile) as excinfo:
        build_dashboard(control_dir, tmp_path / "out.html")

    assert "control_attach_rate.csv" in str(excinfo.value)


def test_emits_no_placeholder_tokens(tmp_path, control_dir):
    """A dashboard that renders 'TODO' or 'NaN' is worse than one that fails:
    the wrong number gets through review, the exception does not."""
    html = build_dashboard(control_dir, tmp_path / "out.html")

    for token in ("TODO", "TBD", "NaN", "None", "{}", "undefined"):
        assert token not in html, token


def test_renders_real_numbers_from_the_csvs(tmp_path, control_dir):
    html = build_dashboard(control_dir, tmp_path / "out.html")

    assert "19.9" in html      # final attach rate
    assert "11.3" in html      # pct_base_never_rebilled, ungrouped


def test_declares_the_four_decision_bands(tmp_path, control_dir):
    html = build_dashboard(control_dir, tmp_path / "out.html")

    for band in ("Are we growing", "Do customers stay",
                 "Are customers valuable", "Are we acquiring efficiently"):
        assert band in html


def test_void_cards_declare_what_unblocks_them(tmp_path, control_dir):
    """The void convention: every non-measurable card says what it is blocked on
    and which phase unblocks it. Without that the void reads as carelessness."""
    html = build_dashboard(control_dir, tmp_path / "out.html")

    assert "PHASE 2" in html
    assert "Blocked on" in html


def test_defines_every_color_outside_theme_blocks(tmp_path, control_dir):
    """A colour whose only definition lives inside @media or [data-theme] does
    not apply in the un-stamped state -- the classic unreadable-page bug."""
    html = build_dashboard(control_dir, tmp_path / "out.html")

    root_block = html.split(":root{")[1].split("}")[0]
    for token in ("--ink", "--surface", "--plane", "--s1", "--s2"):
        assert token in root_block, token


def test_writes_the_file(tmp_path, control_dir):
    out = tmp_path / "out.html"

    build_dashboard(control_dir, out)

    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<title>")
