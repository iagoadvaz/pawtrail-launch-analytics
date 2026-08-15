"""Consistency tests between the semantic layer and METRICS.md.

This project has reintroduced count drift twice: a metric total stated in prose
went stale after more metrics were added, and a "6 CSV files" claim disagreed
with itself two lines apart. Both were caught by mechanical cross-reference
rather than by re-reading, and both were caught late. A hardcoded count is a
bug waiting for the next edit, so the counts that must stay true are asserted
here instead of being re-checked by hand.

These are guards, not a red-green cycle: they pass on the documentation as it
stands. What they buy is that the *next* edit cannot quietly break it.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
METRICS_MD = REPO_ROOT / "METRICS.md"
METRICS_YML = REPO_ROOT / "pawtrail_dbt/models/marts/_metrics.yml"
SEMANTIC_MODELS_YML = REPO_ROOT / "pawtrail_dbt/models/marts/_semantic_models.yml"


def declared_metrics():
    """Metric names in _metrics.yml — the curated set."""
    return {m["name"] for m in yaml.safe_load(METRICS_YML.read_text())["metrics"]}


def measure_proxies():
    """Measures exposed as queryable names by `create_metric: true`."""
    models = yaml.safe_load(SEMANTIC_MODELS_YML.read_text())["semantic_models"]
    return {
        measure["name"]
        for model in models
        for measure in model.get("measures", [])
        if measure.get("create_metric")
    }


def documented_metrics():
    """Names carrying a `### <name>` section in METRICS.md."""
    return set(re.findall(r"^### (\S+)$", METRICS_MD.read_text(), re.M))


def test_every_declared_metric_has_a_documented_definition():
    """A metric with no entry here is a number with no stated definition.

    That is the failure this dictionary exists to prevent: the semantic layer
    will happily serve a metric nobody has written down the meaning of.
    """
    missing = declared_metrics() - documented_metrics()

    assert not missing, f"declared in _metrics.yml but not documented: {sorted(missing)}"


def test_no_documented_metric_has_been_removed_from_the_semantic_layer():
    """The opposite drift: an entry outliving the metric it describes."""
    orphaned = documented_metrics() - declared_metrics()

    assert not orphaned, f"documented but no longer declared: {sorted(orphaned)}"


def test_the_stated_metric_count_matches_the_declarations():
    """The one count in prose, checked against what it counts."""
    stated = re.search(r"`pawtrail_dbt/models/marts/_metrics\.yml` \((\d+) metrics\)",
                       METRICS_MD.read_text())

    assert stated, "METRICS.md no longer states a metric count in the expected form"
    assert int(stated.group(1)) == len(declared_metrics())


def test_the_measure_proxy_count_is_disclosed():
    """`mf list metrics` returns more names than this file documents.

    The gap is legitimate — measures carrying `create_metric: true` — but it is
    only legitimate while it is disclosed, because a reader who queries an
    undocumented name gets a number with no definition governing it. The
    disclosed figure has to track the declarations, so a new proxy cannot
    appear silently.
    """
    text = METRICS_MD.read_text()
    stated = re.search(r"`mf list metrics` returns (\d+) names", text)

    assert stated, "METRICS.md no longer discloses the `mf list metrics` total"
    # Proxies sharing a name with a declared metric resolve to one name, so the
    # total is a union rather than a sum.
    assert int(stated.group(1)) == len(declared_metrics() | measure_proxies())
