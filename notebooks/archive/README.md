# Archived notebooks

These are the original exploratory notebooks, kept as the project's history.
**They are not part of the pipeline and are not expected to run.**

Outputs have been stripped with `nbstripout` — the code is byte-identical to
what was there before, but 17 MB of embedded plot images and cell output is
gone. The largest, `02_baseline_eda.ipynb`, went from 13 MB to 16 KB. That
output was making every notebook save produce a six-figure-line diff, which is
why they sat uncommitted through eight phases of work.

## What replaced them

| Notebook | Superseded by |
|---|---|
| `01_initial_preprocessing.ipynb` | [`transform/models/staging/`](../../transform/models/staging/) — cleaning as tested dbt models |
| `03_feature_eng_preprocessing.ipynb` | [`transform/models/intermediate/`](../../transform/models/intermediate/) and [`ml/features.py`](../../ml/features.py) |
| `02_baseline_eda.ipynb`, `04_water_main_heatmap.ipynb` | [`analysis/`](../../analysis/) — queries and figures as importable, testable code |
| `05_baseline_model.ipynb` | [`ml/`](../../ml/) — walk-forward evaluation, ranker, scoring |
| `experiments/fetch_data.ipynb`, `geojson_extract_test.ipynb` | [`extract/`](../../extract/) — paginated extraction with geometry |

## Why they were replaced rather than tidied

The analysis in these notebooks rests on a join that does not hold. Breaks were
matched to mains on `ROADSEGMENTID`, which carries up to 45 distinct mains per
segment — a many-to-many join that expanded 2,766 break records into 10,761 rows
with mostly-wrong pipe attributions. The modelling notebook then predicted
`failure_rate` from a feature set containing `num_breaks`, the quantity
`failure_rate` is derived from.

Conclusions drawn here are unreliable for those reasons, not because notebooks
are the wrong tool. See [`docs/project-plan.md`](../../docs/project-plan.md) §2
for the full diagnostic.

## If you want to run one anyway

They reference `notebooks/config.py` (API keys, gitignored) and CSV paths under
`data/` that no longer exist — the pipeline reads partitioned parquet now. Expect
to fix paths before anything executes.

To keep outputs out of git when editing notebooks in this repo:

```bash
make nbstripout
```
