---
name: plan-consistency-sweep
description: Use after editing a long plan or spec document (adding/removing a metric, model, CSV export, or test) — before considering the edit done, since hardcoded counts and cross-references drift out of sync with the content they describe and a stale count fails a later green build for the wrong reason.
---

# Plan Consistency Sweep

## Overview

This project reintroduced the exact defect it had already been reviewed for,
twice: a metric count stated in prose drifted after adding more metrics, and a
"6 CSV files" / "8 CSV files" claim disagreed with itself two lines apart after
adding two more exports. Both were caught by mechanical cross-reference, not by
re-reading the prose.

**Core principle:** a hardcoded count is a bug waiting for the next edit. Prefer
deriving the count at verification time (`grep -c ... | mf list ...`) over
writing a number in prose. Where a number must stay in prose, sweep for drift
every time the surrounding section changes.

## When to Use

After editing any long plan/spec markdown file that declares metrics, models,
tests, or exports — before treating the edit as finished.

## Checklist

Run these against the plan/spec file(s):

1. **Every measure a metric references is declared in some semantic model.**
   ```bash
   grep -oP '(?<=measure: )\w+|(?<=numerator: )\w+|(?<=denominator: )\w+' _metrics.yml | sort -u > /tmp/refs
   grep -oP '(?<=- name: )\w+' _semantic_models.yml | sort -u > /tmp/declared
   comm -23 /tmp/refs /tmp/declared   # anything printed here is unresolved
   ```
2. **Every column referenced downstream exists in its producing model's
   `Produces:` line or `select` list.** Grep the column name in the consuming
   model and in the producing model's final select.
3. **Every exported CSV feeds a documented dashboard view, and every view has a
   matching export.** Diff the `--csv` filenames in the export task against the
   filenames referenced in the dashboard README/task.
4. **Stated counts (`N metrics`, `N tests`, `N CSV files`) match what's actually
   listed.** If a count appears in prose, `grep -c` the thing it's counting and
   compare. If they can drift independently, remove the number from prose and
   describe the set instead ("every metric declared in `_metrics.yml`") rather
   than re-deriving it once more.
5. **All fenced ```yaml and ```python/```sql blocks parse/compile.** A quick
   sweep:
   ```python
   import yaml, re, sys
   text = open(sys.argv[1]).read()
   for i, block in enumerate(re.findall(r'```yaml\n(.*?)```', text, re.S)):
       jinja_stripped = re.sub(r'\{\{.*?\}\}', '0', block)
       yaml.safe_load(jinja_stripped)  # raises on malformed YAML
   ```

## Common Mistakes

| Mistake | Fix |
|---|---|
| Writing "N metrics" in prose, then adding a metric later | Delete the number; describe the set, or derive it at verification time |
| Fixing one instance of a repeated count, missing the other | `grep -n` the number itself across the whole file, not just the section you edited |
| Assuming a script-caught false positive means the check is wrong | Read the actual YAML at that line before dismissing — comment prose containing a keyword can trigger false positives too |

## Where This Applies in This Project

Run after any edit to `docs/superpowers/plans/2026-08-12-pawtrail-launch-analytics.md`
or `docs/superpowers/specs/2026-08-12-pawtrail-launch-analytics-design.md` —
particularly after Task 14/15 edits (semantic models / metrics) and Task 16
(dashboard exports), which is where both drift incidents in this project
actually happened.
