# Data profile: `raw/Water_Main_Breaks.csv`

## Overview

- **Grain**: one row per water main break incident (`WATBREAKINCIDENTID`, `OBJECTID`, `GLOBALID` are all 100% unique — no duplicate rows or IDs)
- **Rows / columns**: 2,766 rows x 52 columns
- **Date range**: 1985-01-01 to 2023-01-09, but only 10 records before 1997 — usable coverage really starts in **1997** and the series looks reasonably dense through **2022** (72–150 breaks/year)
- **Coverage**: `BREAK_TYPE` is 2,736 MAIN / 30 SERVICE — this file is overwhelmingly main breaks despite the filename covering both
- A cleaning pipeline already exists downstream (`processed/cleaned_break_data.csv`, 25 cols/2,585 rows, and `processed/model_data.csv`, 16 cols/2,036 rows engineered for modeling) — findings below are framed against what that pipeline already handles and what it doesn't.

## Column groups

| Role | Columns |
|---|---|
| Identifiers | `OBJECTID`, `WATBREAKINCIDENTID`, `GLOBALID`, `ASSETID`, `ROADSEGMENTID` |
| Location | `X`, `Y` (lon/lat), `STREET`, `CIVIC_NUMBER` |
| Break event | `INCIDENT_DATE`, `STATUS`, `STATUS_DATE`, `BREAK_TYPE`, `BREAK_NATURE`, `BREAK_APPARENT_CAUSE`, `BREAK_CATEGORIZATION`, `REPAIR_TYPE` |
| Asset attributes | `ASSET_MATERIAL`, `ASSET_SIZE`, `ASSET_YEAR_INSTALLED`, `ASSET_DEPTH`, `FROST_DEPTH`, `ASSET_EXISTS` |
| Response/ops detail | `ROAD_CLOSED`, `SIDEWALK_CLOSED`, `HOUR_IMPACTED`, `UNITS_IMPACTED`, `HYDRANTS_*`, `VALVES_*`, `POSITIVE_PRESSURE_MAINTANED`, etc. |
| Regulatory/admin | `MOECC_SAC_NOTIFICATION`, `LOCAL_MOE_OFFICE`, `BWA_DWA*`, `HEALTH_DEPT_NOTIFICATION`, `PROCEEDURES_FOLLOWED` |

## Data quality findings

**Fully null (drop):** `MAINTENANCE_DESC`, `VALVES_OPENED`, `HEALTH_DEPT_NOTIFICATION`, `SAC_REFERENCE_NO` — 100% empty, zero information.

**Constant or near-constant (drop):** `VALVES_CLOSED`, `DISINFECTED`, `BWA_DWA`, `BWA_DWA_DECLARED`, `PROCEEDURES_FOLLOWED` — one distinct value across all non-null rows, no predictive signal.

**>90% null (drop unless you have a specific reason to keep):** `UNITS_IMPACTED` (89%), `CW_SERVICE_REQUEST` (99%), `RETURN_TO_NORMAL` (96%), `REPAIR_TYPE` (94%), `NEW_SECTION_LENGTH` (99%), `HYDRANTS_CALLED_OUT/BACK_IN` (~100%), `BACTERIA_TESTING_DATE` (100%), `MOECC_SAC_NOTIFICATION` (100%), `LOCAL_MOE_OFFICE` (100%), `ASSET_DEPTH` (99%), `FROST_DEPTH` (97%).

**Usable with moderate nulls:**
- `WORKORDER` — 42% null, high cardinality; useful mainly as a join key, not a feature
- `BREAK_NATURE` — 4% null, but 72% of non-null values are `UNKNOWN`, so its real information content is thin
- `BREAK_APPARENT_CAUSE` — 6% null, 73% `OTHER` — same issue, low signal as-is
- `ASSET_MATERIAL`, `ASSET_SIZE`, `ASSET_YEAR_INSTALLED` — all ~6% null, good completeness, core modeling features
- `CIVIC_NUMBER` (3.5% null), `STREET` (0.6% null) — fine for geocoding/joins

**Consistency / accuracy flags:**
- `ASSET_SIZE` has 4 rows with value `0` — not a physically valid pipe diameter, likely placeholder; treat as missing.
- `ASSET_MATERIAL` includes `XXX` (21 rows) — reads as an "unknown" placeholder code rather than a real material; treat as missing/its own category, not a true material class.
- `ASSET_EXISTS = N` (712 rows, 26%) has a **median install year of 2008** vs. **1963** for `ASSET_EXISTS = Y`. That's counterintuitive — newer assets are disproportionately "no longer existing." Worth confirming with whoever maintains this GIS layer before trusting `ASSET_EXISTS` as a feature; it may reflect asset replacement after failure rather than pipe age.
- No exact duplicate rows and no duplicate ID columns — referential integrity on the primary key is clean.

## Patterns

- **Repeat failures are common**: of 1,400 distinct assets in this file, 597 (43%) have more than one recorded break, up to 14 on a single asset. This repeat-failure structure is exactly what `processed/model_data.csv` captures via `num_breaks` / `failure_rate` — confirms that's the right target framing.
- **Material mix**: CI (cast iron, 1,581), DI (ductile iron, 565), PVC (323) dominate; AC, CPP, HDPE, PE, COP are thin (<20 rows each) and will need grouping into an "other" bucket for modeling to avoid sparse categories.
- **Install year** ranges 1889–2018, median 1964 — consistent with an aging-infrastructure failure story; pairs naturally with incident year to derive `age_at_break` (already done in `model_data.csv`).
- **Temporal gap**: 1985–1996 has almost no records (10 total) — if you're building a time-indexed feature (e.g., breaks per segment per year), truncate history to 1997+ rather than treating the sparse early years as "no breaks."

## Recommendations for an ML-ready dataset

1. Drop the ~15 fully-null/constant/near-empty columns listed above — the existing `cleaned_break_data.csv` already does most of this (52 → 25 cols); it retained `HOUR_IMPACTED`, `POSITIVE_PRESSURE_MAINTANED` and a few other operational fields that have effectively no variance once you check them — worth trimming further.
2. Recode `ASSET_SIZE == 0` and `ASSET_MATERIAL == 'XXX'` to null before imputing, rather than leaving them as valid values.
3. Collapse rare `ASSET_MATERIAL` categories (AC, CPP, PVCB, COP, PE — all <20 rows) into an `OTHER` bucket to avoid one-hot columns with near-zero support.
4. Investigate the `ASSET_EXISTS` vs. install-year inversion before using it as a feature — it may leak post-break information (asset replaced *because* it broke) rather than being a pre-break predictor.
5. `BREAK_NATURE` and `BREAK_APPARENT_CAUSE` are dominated by `UNKNOWN`/`OTHER` — fine as weak categorical features but don't expect much lift from them; consider treating "unknown cause" itself as a category rather than dropping those rows.
6. For a failure-prediction pipeline, the natural unit of prediction is asset (`ASSETID`) or road segment (`ROADSEGMENTID`) x time window, not raw incident rows — join this file to `raw/Water_Mains.csv` (the full asset inventory, including pipes that never broke) so the model sees negative examples, not just break events. Right now this file alone only contains pipes that *did* break.

## Known issues for the team

- Filename says "Water_Main_Breaks" but includes 30 service-line breaks — filter on `BREAK_TYPE == 'MAIN'` if the model is specifically about mains.
- `STATUS` includes 30 `CANCELLED` records — decide whether cancelled call-outs should be excluded from a "confirmed break" label.
