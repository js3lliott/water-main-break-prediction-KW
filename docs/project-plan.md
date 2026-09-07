# KW Water Main Break Risk — Analytics Engineering Project Plan

**Status:** proposed, not yet executed
**Author:** Jordan Samek
**Last updated:** 2026-09-06

---

## 1. What this project actually is

**One sentence:** A weekly-refreshed pipe-level risk model for Kitchener's 929 km / 15,903-segment water distribution network, delivered as a ranked inspection list and a risk map, with the whole transformation layer built and tested like a production analytics stack.

**The question the model answers:** *For each pipe segment in the network, what is the probability it breaks in the next 12 months?* — and, downstream, *if the city can only inspect/renew N km of pipe next year, which N km?*

That second question is the product. A probability nobody can act on is a notebook; a ranked list with a stated hit rate is a deliverable.

### Who it's for (as a portfolio artifact)

Two audiences, and the project has to serve both:

- **A hiring manager for an analytics engineering role** — they will look at the repo, not the app. They want to see a modelled warehouse with tests, a documented DAG, incremental logic, snapshots, CI, and a clean separation between transformation and analysis.
- **A hypothetical asset-management lead at the City of Kitchener** — they will look at the app, not the repo. They want a map, a list, and an honest statement of how often the list is right.

---

## 2. Honest assessment of where the project is today

I reviewed the existing repo before writing this. The domain instinct is right and the data profile in `data/water_main_breaks_data_profile.md` is genuinely good work. The pipeline underneath it has four structural problems that no amount of model tuning will fix.

### 2.1 The join is wrong

`src/data/fetch_data.py` joins breaks to mains on `ROADSEGMENTID`:

```sql
FROM breaks LEFT JOIN mains ON breaks.ROADSEGMENTID = mains.ROADSEGMENTID
```

A road segment contains up to **45 distinct water mains**. This is a many-to-many join. It turns 2,766 break records into **10,761 rows** in `data/raw/water_data.csv` — every break gets duplicated once per pipe on its street, and most of those pipe attributions are wrong.

**The correct key already exists.** `Water_Main_Breaks.ASSETID` → `Water_Mains.WATMAINID`:

- `WATMAINID` is unique across all 15,903 inventory rows (verified)
- **84.6%** of break records match an inventory pipe on this key (verified)
- The 15.4% that don't match are almost certainly pipes that were replaced after breaking and no longer exist in the current inventory — that is a *finding to document*, not a defect to hide

### 2.2 There are no negative examples

Every row in the current modelling dataset is a pipe that broke. The model has never seen a pipe that didn't break. Its stated limitation in the README ("doesn't predict if a water main could break if it's never broken before") is not a limitation of the data — the full inventory is sitting in `Water_Mains.csv` and has been the whole time.

**Only 1,198 of 15,903 pipes (7.5%) have ever had a recorded break.** The other 92.5% are the signal.

### 2.3 The target leaks into itself

`data/processed/model_data.csv` predicts `failure_rate` from a feature set that includes `num_breaks`. `failure_rate` is derived from `num_breaks`. The model is being asked to predict a number from its own numerator. The reported R² is meaningless.

Additionally, `train.py` uses `train_test_split(random_state=42)` — a random split on what is fundamentally time-series data. A pipe's 2015 break can land in train while its 2014 break lands in test.

### 2.4 The repo has committed merge conflicts

`src/features/process_data.py` and `src/models/train.py` both contain unresolved `<<<<<<< HEAD` markers in committed code. Neither file imports successfully. `train.py` also runs a 256-fit nested loop with no early stopping and logs `pipeline.score()` (R²) as a metric named `"score"`.

Other cleanup: `data/` and `mlruns/` are partly committed, `st_app.py` uses `st.cache` (removed from Streamlit in 2024), `requirements.txt` is a 250-line unpinned `pip freeze` including `sklearn==0.0` (the deprecated stub package), and the same Dockerfile commit message appears five times in a row in the history.

### 2.5 The data snapshot is stale

Latest break in the local CSV: **2023-01-09**. That's ~3.5 years of missing incidents. The ArcGIS feature server is live and the extractor in `fetch_data.py` — which is actually the strongest existing code, it correctly handles the 1,000-record pagination limit — already knows how to pull it.

### 2.6 Summary

| | Today | Target |
|---|---|---|
| Grain | 1 row per break incident | 1 row per pipe-segment per year |
| Rows | 2,766 (10,761 after bad join) | ~380,000 pipe-years |
| Negatives | none | ~99.4% of rows |
| Join key | `ROADSEGMENTID` (1:45 fanout) | `ASSETID` → `WATMAINID` (1:1) |
| Target | `failure_rate` (leaky) | `broke_in_year` (binary) + count |
| Validation | random split | temporal holdout |
| Metric | R² | precision@k, PR-AUC, calibration |
| Transform layer | notebooks + broken scripts | dbt models with tests |
| Freshness | Jan 2023 | weekly |

---

## 3. The reframe: a pipe-year panel

This is the single most important decision in the project.

**Grain:** one row per `(watmainid, calendar_year)`, for every year from `max(1997, install_year)` through the current year.

- ~15,903 pipes × ~24 mean eligible years ≈ **~380k rows** (exact count comes out of the build)
- Truncate history at **1997** — the profile correctly found only 10 break records before 1997, so earlier years would be encoded as "no break" when they're really "no record"
- A pipe only enters the panel the year *after* it's installed

**Targets available at this grain:**

| Target | Type | Model family |
|---|---|---|
| `broke_in_year` | binary | gradient-boosted classifier |
| `n_breaks_in_year` | count | Poisson / negative binomial with `log(length_km)` offset |
| `years_to_next_break` | duration + censoring | Cox PH, Weibull AFT, Andersen–Gill recurrent events |

**Base rate:** ~100 breaks/year ÷ 15,903 pipes ≈ **0.63% of pipe-years are positive**. This is a severe class imbalance and it is the honest shape of the problem. Any accuracy figure above 99% is the model predicting "no break" every time.

### Exposure matters

A 300 m main is not the same risk as a 12 m main. The industry unit is **breaks per 100 km per year**. Every rate model gets a `log(length_km)` offset; every classifier gets `length_m` as a feature; every evaluation is reported per-km as well as per-segment.

### Feature discipline: as-of-year-start only

Every feature for pipe *p* in year *t* must be computable on January 1 of year *t*. Concretely:

- `age_years` = t − install_year
- `prior_breaks` = count of breaks on p strictly before t
- `years_since_last_break` (null if never)
- `breaks_within_200m_prior_3y` — spatial neighbourhood pressure, needs geometry
- Static attributes: `material`, `diameter_mm`, `length_m`, `pressure_zone`, `criticality`, `lined`, `is_undersized`, `is_shallow`, `is_bridge_main`, `ownership`
- Weather for year *t* is a judgment call — see §6

**Two leakage traps specific to this dataset:**

1. **`CONDITION_SCORE`** (0% null, range −1 to 10) is almost certainly a derived/consultant-assigned score, and we do not know its vintage. If it was assigned *after* observed breaks, it encodes the answer. **Action:** train one model with it and one without; if the gap is large, exclude it and say why. This goes in the write-up.
2. **`ASSET_EXISTS = 'N'`** — the profile already caught this: those rows have a *median install year of 2008* vs 1963 for `'Y'`. That inversion is the signature of post-break replacement. It is an outcome, not a predictor. Exclude it from features; use it as evidence for the survivorship-bias section.

### The survivorship bias — name it, don't bury it

A cast iron pipe that broke in 2009 and was replaced with PVC now appears in the inventory as a **young PVC pipe with no break history**. The 15.4% of break records that don't match `WATMAINID` are the visible edge of this. The consequence is that the model systematically **understates** risk for the oldest cohorts, because the worst pipes have been selectively removed from the population.

This cannot be fixed with the available data. It can be quantified (compare the material/age mix of unmatched-break pipes vs. matched) and stated plainly. Naming a bias you can't fix is a stronger portfolio signal than a model that pretends it isn't there.

---

## 4. Target architecture

```
ArcGIS Feature Server (live REST)
  │  extract/  — Python, paginated, writes raw parquet + _extracted_at
  ▼
data/raw/{water_mains,water_main_breaks}/extracted_at=YYYY-MM-DD/*.parquet
  │
  ▼  DuckDB  ← weather: ECCC Waterloo Wellington A daily climate
  │
  ├── dbt snapshot: snap_water_mains (SCD2 on the inventory)
  │
  ├── staging/     stg_water_mains, stg_water_main_breaks, stg_weather_daily
  │                 └─ rename, cast, null-code cleanup (ASSET_SIZE=0, MATERIAL='XXX')
  │
  ├── intermediate/ int_breaks_matched      (ASSETID → WATMAINID + match_status)
  │                 int_pipe_year_spine     (cross join pipes × eligible years)
  │                 int_pipe_year_breaks    (break counts per pipe-year)
  │                 int_pipe_year_history   (prior_breaks, years_since_last — as-of)
  │                 int_winter_severity      (freeze-thaw cycles, frost index by year)
  │
  ├── marts/       dim_pipe
  │                fct_break_incident
  │                fct_pipe_year        ← THE training table
  │                mart_network_health  (breaks per 100 km/yr by material, zone, decade)
  │                mart_pipe_risk       (fct_pipe_year ⋈ scores — what the app reads)
  │
  ▼
ml/  train (temporal CV) → evaluate → score current year → risk scores back into DuckDB
  │
  ▼
Streamlit app: risk map · inspection list · model card · network health
```

**Storage:** DuckDB, single file, committed nowhere but rebuilt from raw parquet in ~10 seconds. It handles 380k rows trivially, has native parquet and spatial extensions, and needs no server. MotherDuck free tier if a hosted endpoint is wanted for the deployed app; otherwise ship the `.duckdb` file into the container.

**Why dbt here and not just pandas:** the whole point of the analytics-engineering framing is that the transformation logic is declarative, tested, documented, and lineage-tracked — not buried in notebook cells. `dbt-duckdb` gives all of that with zero infrastructure.

### Repo structure

```
.
├── README.md
├── docs/
│   ├── project-plan.md              ← this file
│   ├── data-profile-breaks.md       ← existing, keep
│   ├── data-profile-mains.md        ← to write
│   └── model-card.md
├── pyproject.toml                   ← uv/pip, pinned; replaces requirements.txt
├── extract/
│   ├── arcgis.py                    ← refactored from fetch_data.py
│   └── weather.py
├── transform/                       ← dbt project
│   ├── dbt_project.yml
│   ├── models/{staging,intermediate,marts}/
│   ├── snapshots/
│   ├── macros/
│   └── tests/
├── ml/
│   ├── features.py  train.py  evaluate.py  score.py
│   └── survival.py
├── app/
│   └── streamlit_app.py  +  pages/
├── notebooks/                       ← analysis only, reads marts, never writes
├── tests/                           ← pytest for extract/ and ml/
└── .github/workflows/{ci.yml,refresh.yml}
```

---

## 5. Execution phases

Effort estimates assume focused part-time work. Total ≈ **3–4 weeks**.

### Phase 0 — Repo reset (≈1 day)

- [ ] Delete `src/features/process_data.py` and `src/models/train.py` (both contain committed merge conflicts and are superseded)
- [ ] `.gitignore`: `data/`, `*.duckdb`, `mlruns/`, `.DS_Store`, `__pycache__/`, `.ipynb_checkpoints/`
- [ ] `git rm --cached` the committed data artifacts (`water_data.db`, `cleaned_break_data.csv` at repo root, `test_predict_data.csv`)
- [ ] Replace `requirements.txt` with `pyproject.toml`, pinned, Python 3.11
- [ ] Move the existing profile to `docs/data-profile-breaks.md`
- [ ] Archive current notebooks to `notebooks/archive/` — keep them, they're the project history

**Done when:** `pip install -e .` succeeds from a clean venv and `git status` is empty after a build.

### Phase 1 — Extraction (≈1–2 days)

- [ ] Refactor `fetch_data.py` into `extract/arcgis.py`. Keep the pagination logic — it's correct. Strip the Prefect decorators (orchestration comes back in Phase 8, and Prefect 2.10 is long past EOL).
- [ ] Preserve **geometry**. The CSV exports have no coordinates for mains — only `Shape__Length`. Request `f=geojson` and write WKT/GeoJSON so pipe centrelines survive. Without geometry there is no line map and no spatial features.
- [ ] Write partitioned parquet with an `_extracted_at` column
- [ ] `extract/weather.py` — ECCC daily climate, 1996–present

  **Correction, found during execution.** This plan originally named *Waterloo Wellington A* (climate ID 6149387) as the weather station. The ECCC station inventory shows that station **stopped reporting daily observations in 2003**, so it cannot cover the panel period. The series has to be spliced:

  | Station | ID | Daily coverage | Role |
  |---|---|---|---|
  | `WATERLOO WELLINGTON A` | 4832 | 1970–2003 | Airport site, legacy record |
  | `KITCHENER/WATERLOO` | 48569 | 2010–2026 | Same airport site, renamed and re-indexed |
  | `ROSEVILLE` | 4816 | 1972–2026 | ~18 km south; covers the 2004–2009 gap |

  The two airport records are one physical site but leave a six-year hole that only ROSEVILLE spans. Each output row records `source_station_id`, so the splice is visible in the warehouse rather than hidden in the extractor.
- [ ] pytest with a recorded fixture response — no network calls in CI

**Done when:** `python -m extract.run` produces fresh parquet for mains, breaks, and weather, and the breaks file contains records after 2023-01-09.

### Phase 2 — The dbt layer (≈3–4 days) — *the core deliverable*

**Staging** — one model per source, rename to snake_case, cast types, and encode the profile's findings as code:
- `ASSET_SIZE = 0` → null; `ASSET_MATERIAL = 'XXX'` → null
- Collapse materials with <20 segments into `OTHER`
- Filter breaks to `BREAK_TYPE = 'MAIN'` and `STATUS != 'CANCELLED'` (documented, not silent)

**Snapshot** — `snapshots/snap_water_mains.sql`, SCD2 on `watmainid`. This is what makes the project defensible: it captures when `condition_score`, `lined`, or `status` change, so future models can use point-in-time-correct attributes instead of today's values retro-applied to 2005. It only starts accumulating from first run — say so in the docs.

**Intermediate**
- `int_breaks_matched` — the `ASSETID → WATMAINID` join, with an explicit `match_status` column (`matched` / `orphan_asset` / `null_asset`) so the 15.4% is *measured every run*, not discovered once
- `int_pipe_year_spine` — pipes × years, gated on install year and 1997 floor
- `int_pipe_year_history` — as-of-year-start aggregates. Window functions, strictly `< year_start`.
- `int_winter_severity` — freeze-thaw cycle count, cumulative degree-days below 0 °C, coldest 7-day mean, per winter season

**Marts** — `dim_pipe`, `fct_break_incident`, `fct_pipe_year` (incremental on year), `mart_network_health`, `mart_pipe_risk`

**Tests** — this is where the AE credibility lives:
- Generic: `unique`/`not_null` on all keys, `relationships` from breaks to `dim_pipe`, `accepted_values` on material and pressure zone
- Composite uniqueness on `(watmainid, year)` in `fct_pipe_year` — **the grain contract**
- Singular tests: no break dated before its pipe's install date; no panel year in the future; positive rate within a plausible band (0.2–2%) — a canary that catches a silently broken join
- `dbt-expectations` for distributional checks on `age_years`, `length_m`
- Freshness on sources

**Done when:** `dbt build` is green, `dbt docs generate` produces a browsable lineage graph, and `fct_pipe_year` has one row per pipe-year with a positive rate near 0.6%.

### Phase 3 — Analysis (≈1–2 days)

Notebooks read from marts and write nothing. Questions worth answering:

- Breaks per 100 km per year by material — is cast iron actually worse once you normalise for length and age? (The raw counts say CI dominates breaks; CI is only 2,184 of 15,903 segments. The normalised rate is the real finding.)
- The winter spike: breaks vs. freeze-thaw cycles by month
- Hazard curve by age cohort — where does the bathtub curve turn up?
- Repeat-failure structure: does a break predict another break on the same segment, controlling for age and material?
- Spatial clustering — Moran's I on break density, or a straightforward hex-bin
- Quantify the survivorship bias (§3)

**Done when:** there are 4–6 charts good enough for the README and the app's network-health page.

### Phase 4 — Modelling (≈3–4 days)

**Validation protocol — set this before touching a model.**

Rolling-origin temporal CV:

| Fold | Train | Validate |
|---|---|---|
| 1 | 1997–2017 | 2018 |
| 2 | 1997–2018 | 2019 |
| 3 | 1997–2019 | 2020 |
| 4 | 1997–2020 | 2021 |
| **Test (touch once)** | 1997–2021 | **2022+** |

**Baselines to beat — build these first.** If the ML model can't beat them, that is the finding.
1. Random ranking
2. Rank by age descending
3. Rank by prior break count, ties broken by age
4. Rank by `condition_score`

**Models**
- Primary: gradient-boosted classifier (LightGBM/XGBoost) on `broke_in_year`, `scale_pos_weight` tuned, monotonic constraint on age if it helps stability
- Rate model: Poisson / negative binomial GLM with `log(length_km)` offset — interpretable, gives breaks-per-100-km directly, and is the form a utility engineer will actually recognise
- Survival: Weibull AFT for time-to-first-break; Andersen–Gill for recurrent events. Handles right-censoring properly, which the classifier ignores, and produces a survival curve per pipe — a genuinely better artifact for the app than a bare probability.

**Metrics — report all of these, lead with the third**
- PR-AUC (not ROC-AUC; at 0.6% positives ROC-AUC flatters everything)
- Brier score + a calibration curve — a "12% chance" must mean 12%
- **Precision@k / lift, expressed in kilometres:** *"Inspecting the top 5% of network length captures X% of next year's breaks, vs. Y% for age-ranking."* This is the number the whole project exists to produce.
- Per-cohort breakdown (material, install decade, zone) to expose where the model fails

**Tracking:** MLflow is already partly wired and is fine. Log every run against a fixed dataset hash so results are comparable.

**Done when:** the test-year evaluation is written up with the baseline comparison, honest about whatever it shows.

### Phase 5 — Scoring pipeline (≈1–2 days)

- [ ] `ml/score.py` — load the registered model, score the current panel year, write `fct_pipe_risk_score` back to DuckDB with `model_version` and `scored_at`
- [ ] Persist per-pipe SHAP values so the app can say *why* a pipe ranks high ("1961 cast iron, 210 m, 3 prior breaks, zone KIT 4")
- [ ] Prediction-drift check: compare this run's score distribution to the last

### Phase 6 — The app (≈2–3 days)

Rebuild `st_app.py`. Current version has real problems: `st.cache` no longer exists in modern Streamlit, and the maps are point-density heatmaps of *break locations* — the visual answers "where did breaks happen" when the product question is "which pipes are at risk."

**Fix:** draw **pipe centrelines coloured by risk**, using the geometry from Phase 1 — `pydeck` `PathLayer` or `folium`. That single change is the difference between a data viz and a decision tool.

Four pages:
1. **Risk map** — network drawn as lines, coloured by predicted probability; filter by pressure zone, material, install decade; click a pipe for its attributes, score, and top SHAP drivers
2. **Inspection list** — top-N ranked table with a running cumulative-km column and "expected breaks captured", CSV export. *This is the product.*
3. **Model card** — performance vs. baselines, calibration plot, the survivorship-bias and condition-score-leakage caveats, data vintage
4. **Network health** — historical trends from `mart_network_health`

**Deploy:** Streamlit Community Cloud (free; the README badge already points there). Drop Heroku — the five repeated Dockerfile commits are a symptom of fighting it. Keep the Dockerfile for local reproducibility only.

### Phase 7 — Orchestration & CI (≈1–2 days)

- `.github/workflows/ci.yml` — ruff, pytest, `dbt build` against a seeded fixture DB, on every PR
- `.github/workflows/refresh.yml` — weekly cron: extract → dbt build → score → publish; opens an issue on failure
- Branch protection on `main`; conventional commits from here on

### Phase 8 — Write-up (≈1–2 days)

Rewrite the README around the *result*, not the process. Current version narrates notebooks; it should lead with the headline number from Phase 4 and the honest limitations. Add `docs/model-card.md`. Optionally a blog post — the survivorship-bias finding is the most interesting thing in this project and is genuinely publishable.

---

## 6. Open decisions

**Weather features — resolve before Phase 4.** Winter severity is real signal (the 2014 event in the README was a cold-snap year), but a model that uses year *t*'s weather can't forecast year *t+1* until the winter has happened. Three options:
- (a) Use observed weather → explains history, can't forecast. Fine if the product is framed as "which pipes are most sensitive to a hard winter."
- (b) Use climatological normals → forecastable, weaker.
- (c) **Recommended:** two models. A structural model (no weather) for the forward-looking inspection list, and a weather-sensitivity model for a "cold snap scenario" toggle in the app. The comparison between them *is* an analysis result.

**Condition score.** Train with and without; decide based on the gap and document either way.

**Scope of "Waterloo".** The data is City of Kitchener only. Waterloo is a separate municipality with its own portal. Either rename the project to Kitchener or check whether Waterloo publishes a comparable layer — a two-city model would be a strong extension but doubles the ingestion work. **Recommend:** Kitchener only for v1, note it explicitly.

**Region of Waterloo transmission mains** are a separate layer from Kitchener's distribution mains. Out of scope for v1.

---

## 7. What "done" looks like

- `git clone && make build` reproduces the entire warehouse from the live API in under five minutes
- `dbt build` green, with tests that would actually catch the ROADSEGMENTID-style bug if it were reintroduced
- A test-year evaluation that states, in kilometres, how much better than age-ranking the model is — including if the answer is "not much"
- A deployed app where someone can filter to their pressure zone and export an inspection list
- A README whose first screen contains a number, a map, and a limitation

---

## 8. Verified facts underpinning this plan

Measured directly from `data/raw/` on 2026-09-06:

| Fact | Value |
|---|---|
| Break records | 2,766 (1985-01-01 → 2023-01-09) |
| Break records after 1997 | dense; only 10 before |
| Inventory segments | 15,903 (15,900 `ACTIVE`) |
| Total network length | 928.9 km |
| `WATMAINID` unique | yes |
| Breaks matching inventory on `ASSETID` | 84.6% |
| Inventory pipes with ≥1 break | 1,198 (7.53%) |
| Max mains per `ROADSEGMENTID` | 45 |
| Rows in current bad join | 10,761 |
| Material mix | PVC 7,662 · DI 5,077 · CI 2,184 · PVCO 624 · other 356 |
| Install date range | 1889-06 → 2023-05 (0.8% null) |
| `CONDITION_SCORE` | 0% null, range −1 to 10 |
| Pressure zones | 15 |
| Lined segments | 58 of 15,903 |
| Recent break counts | 2019: 97 · 2020: 72 · 2021: 86 · 2022: 106 |

### Live server, measured 2026-09-06

The local CSVs are a January 2023 snapshot. Against the live feature server:

| Fact | Local CSV | Live API | Delta |
|---|---|---|---|
| Break records | 2,766 | **3,018** | +252 |
| Inventory segments | 15,903 | **16,207** | +304 |
| Latest break | 2023-01-09 | **2026-09-02** | +3.6 years |

Both layers report `supportsPagination: true`, so the extractor pages with `resultOffset` rather than bisecting OBJECTID ranges as the original script did. Native SR is EPSG:26917; the extractor requests `outSR=4326`.

The API returns **37 fields for breaks against the CSV's 52**. Every dropped field is one this profile already flagged as fully-null, constant, or >90% null — plus `X`/`Y`, superseded by real geometry. Six of them (`POSITIVE_PRESSURE_MAINTANED`, `AIR_GAP_MAINTANED`, `MECHANICAL_REMOVAL`, `FLUSHING_EXCAVATION`, `HIGHER_VELOCITY_FLUSHING`, `ANODE_INSTALLED`) were features in `model_data.csv`. They describe crew response *after* a break, so they were leakage regardless; their absence from the API settles the question.
