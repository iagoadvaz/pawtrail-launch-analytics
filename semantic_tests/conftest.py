"""Shared machinery for querying the semantic layer from pytest.

These tests exercise MetricFlow, not the warehouse. `dbt build` cannot see the
defects they cover: every one of these metrics is computed from a table whose
own rows are correct, and the error is introduced by how the semantic layer
aggregates them. `mf validate-configs` cannot see them either -- it proves the
YAML is well-formed and every reference resolves, not that a metric returns a
sane number at the grain a dashboard asks for. The only way to observe that is
to run the query.

They require a built warehouse (`dbt build`), so they are slower than the
generator tests by roughly two seconds per query. That is the price of covering
the layer the CSV exports and the memo are actually read from.
"""

import csv
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = REPO_ROOT / "pawtrail_dbt"
MF = REPO_ROOT / ".venv" / "bin" / "mf"


@pytest.fixture(scope="session")
def parsed_manifest():
    """Rebuild `target/semantic_manifest.json` before any query runs.

    `mf` reads the semantic manifest dbt wrote, not the YAML on disk. Editing
    `_semantic_models.yml` and running `mf query` without re-parsing therefore
    answers from the previous version of the file — silently, with no staleness
    warning. That makes an un-parsed run of these tests worse than no tests:
    they would report on YAML that is no longer what the project contains, in
    either direction.
    """
    result = subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "dbt"), "parse", "--profiles-dir", "."],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"dbt parse failed:\n{result.stdout}{result.stderr}"


@pytest.fixture(scope="session")
def mf_query(tmp_path_factory, parsed_manifest):
    """Run `mf query` and return its rows as a list of dicts.

    Reads the result from `--csv`, never from stdout: MetricFlow prints a
    progress spinner and a "Wrote query output" banner around the table, so the
    last line of stdout is a banner rather than a number and parsing it yields
    a silent NULL for every row.
    """
    tmp_path = tmp_path_factory.mktemp("mf")
    counter = {"n": 0}

    def run(metrics, group_by=None):
        counter["n"] += 1
        out = tmp_path / f"query_{counter['n']}.csv"
        cmd = [str(MF), "query", "--metrics", ",".join(metrics), "--csv", str(out)]
        if group_by:
            # --order as well as --group-by: MetricFlow does not guarantee row
            # order otherwise, and these tests assert on the last row.
            cmd += ["--group-by", ",".join(group_by), "--order", ",".join(group_by)]
        result = subprocess.run(
            cmd,
            cwd=PROJECT_DIR,
            env={**os.environ, "DBT_PROFILES_DIR": str(PROJECT_DIR)},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"mf query failed: {' '.join(cmd)}\n{result.stderr or result.stdout}"
        )
        with out.open() as handle:
            return list(csv.DictReader(handle))

    return run
