# Card-by-card explainers

Eight Excalidraw scenes. `00-overview.excalidraw` maps the pipeline and the
seven tabs; the other seven are one file per Tableau dashboard, matching the
tabs in `workbook_mock.html`.

Open them at [excalidraw.com](https://excalidraw.com) (File → Open) or with the
VS Code Excalidraw extension. They are plain JSON and diff in review.

| File | Tab | Cards |
|---|---|---|
| `00-overview.excalidraw` | — | pipeline, seven tabs, three load-bearing conventions |
| `01-launch-pulse.excalidraw` | 1 Launch Pulse | 5 |
| `02-activation.excalidraw` | 2 Activation | 4 |
| `03-kit-operations.excalidraw` | 3 Kit Operations | 4 |
| `04-acquisition-efficiency.excalidraw` | 4 Acquisition Efficiency | 5 |
| `05-retention-lifecycle.excalidraw` | 5 Retention & Lifecycle | 5 |
| `06-cs-queue.excalidraw` | 6 CS Queue | 4 |
| `07-decision-contract.excalidraw` | 7 Decision Contract | 3 |

Every card on the mock has a panel. Each panel carries the source CSV, the real
current figures, and three sections:

- **How it is computed** — the formula as declared in `_metrics.yml`, including
  the denominator, which is where most of these metrics can go wrong.
- **Why it matters** — the decision the number informs.
- **What goes wrong** — how the metric misreads if computed the obvious way
  instead. These are not hypotheticals: each one is a defect this project
  shipped and fixed, with the before/after figures. The attach snapshots that
  summed to 0.1049, the activation tile that reported censoring as performance,
  the skip rate understated by 41% by counting cycle 0, the $2,732 of spend
  dropped by weeks that acquired nobody, the seven thresholds silenced by an
  alphabetical reduction.

That third section is the reason these files exist. The formulas are already in
`METRICS.md`; what is not written down anywhere else is which plausible-looking
version of each metric is wrong, and by how much.

## Regenerating

```bash
python3 dashboard/diagrams/build_diagrams.py
```

The scenes are generated, not hand-drawn. Card content is data, so adding a card
means adding a dict rather than moving boxes. Element ids are seeded and the
`updated` timestamp is pinned, so **re-running must produce no diff** — the same
drift check `build_dashboard.py` carries. A second run that changes a file means
someone edited a scene by hand and the generator no longer describes it.
