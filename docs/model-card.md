# Model card — KW water main break risk

**Status:** phase 4 complete. **The recommended production ranker is a SQL group-by, not the machine-learning model.** That is a finding, not a shortcut.

---

## What is being predicted

For each of 16,207 pipe segments, the probability it breaks in the next 12 months — used to produce a ranked inspection list.

- **Grain:** one row per `(watmainid, panel_year)`
- **Training data:** 261,374 pipe-years, 2005–2025 complete years
- **Positive rate:** 0.52%
- **Evaluation:** walk-forward across 10 years (2016–2025), training only on prior years

## Headline metric

**`capture@5%`** — rank every segment, walk down the list accumulating kilometres, and read off the share of that year's breaks in the top 5% of network length (~47 km).

Not accuracy (99.5% by predicting "no break"), not ROC-AUC (flattering at this base rate). The metric is in kilometres because a 300 m main and a 12 m stub are not equal units of work.

Random ranking captures 5% by construction, so `lift@5% = capture / 0.05`.

---

## Results

Mean `capture@5%` across ten walk-forward years. **Bold = best legitimate method per stratum.**

| Method | all | no prior break | has prior break |
|---|---|---|---|
| `stratified_rate` (SQL group-by) | **0.301** | 0.266 | **0.108** |
| `model:cold_start` (LightGBM) | 0.302 | 0.187 | 0.084 |
| `model:full` (LightGBM) | 0.281 | 0.206 | 0.064 |
| `baseline:prior_breaks` | 0.299 | 0.176 | 0.105 |
| `baseline:material_decade_rate` | 0.197 | **0.277** | 0.061 |
| `baseline:decade_rate` | 0.179 | 0.274 | 0.057 |
| `baseline:age` | 0.106 | 0.176 | 0.045 |
| `baseline:random` | 0.052 | 0.054 | 0.059 |
| ~~`condition_score`~~ | ~~0.507~~ | ~~0.747~~ | ~~0.142~~ |

### The recommendation

Ship **`stratified_rate`**: the empirical breaks-per-km of each `(prior_break_count, material, install_decade)` cell, fitted on training years. It is within noise of the best method in every stratum, it is a `GROUP BY`, and the engineer acting on the list can audit it.

At 5% of network length (~47 km) it captures **30% of next year's breaks — a 6× lift over random and 2.8× over ranking by age.**

### The machine-learning model does not earn its place

- On the **90% of the network with no break history**, LightGBM captures 20.6% against the lookup table's 27.7%, and beats it in **1 of 10 years**.
- On pipes **with** break history, it captures 6.4% against `prior_breaks`' 10.5%.
- Only on the pooled `all` row does it look competitive (0.302 vs 0.301) — and that row is an artifact of ranking *across* strata, not skill *within* either.

Segmenting was tested and rejected: a model trained only on never-broken pipe-years scores 0.193, worse than one trained on everything (0.206) and well behind the lookup table.

---

## Why the stratified scorecard exists

The `all` column alone says the model is the best method available. Both stratum columns say it is the worst of the serious contenders. Pipes with break history are 6% of pipe-years and 56% of breaks, so a method that merely re-finds them scores well overall while telling the city nothing its work-order system does not already contain.

A single headline number would have shipped the wrong model with a plausible-looking result attached.

---

## Leakage found and excluded

### `condition_score` — the outcome wearing a feature's clothes

It outranks everything, capturing 75% of breaks in the top 5% of never-broken network length. That is not skill:

| Lifetime breaks | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| Mean condition score | 9.02 | 6.35 | 5.68 | 5.05 | 5.01 | 4.80 | 4.48 |

It is a near-deterministic function of break count (r = −0.64). Decisively: among pipes that had **never broken as of 2022**, those that broke in 2022–25 already carry a mean score of **7.17 against 9.02** for those that did not. The inventory snapshot is from September 2026 — the score was marked down in response to breaks that had not yet happened at prediction time.

Excluded from features, quarantined in `LEAKING_BASELINES`, and never quoted as a result. Fixing it needs point-in-time scores, which `snap_water_mains` accumulates from its first run forward — so it cannot be repaired for historical evaluation.

### Also excluded

- **`ASSET_*` columns on break records** — denormalised copies of *current* inventory (98.4% material agreement), not the pipe that failed.
- **Winter severity features** — describe weather that has already happened, so they cannot serve a forward-looking list. Reserved for the scenario view.
- **`predecessor_break_count`** kept separate from `prior_break_count`. Merging them inverts the signal: re-piped locations run 1.8 per 100 km/yr against a network average of 8.7.

---

## A bug worth recording

The first evaluation run reported the model losing to every baseline. The cause was not the model but the fit: early stopping on `average_precision`, with 20–40 positives in a single validation year, peaked on the **first tree** and never recovered. Every "gradient-boosted model" was a one-tree stump.

The same code also early-stopped on the year being scored — a quiet version of the leakage it was meant to avoid.

Both fixed: early stopping now uses AUC on the last three *training* years, with a guard that refits on a fixed budget if stopping fires implausibly early. The corrected model improved from 0.265 to 0.281 on `all` — and still lost to the lookup table where it matters.

---

## Limitations

1. **Survivorship.** Pipes replaced after failing leave the inventory; 311 breaks are dated before the install year of the pipe now holding that asset ID. The model understates risk for the oldest cohorts.
2. **Attributes are retro-applied.** `fct_pipe_year` uses today's inventory values for every historical year. The snapshot fixes this going forward only.
3. **Roughly 20–40 breaks per year** in the stratum that matters. Single-window results are noise; that is why everything here is ten-year walk-forward.
4. **No soil, pressure-transient, traffic-loading or work-order cost data.** These are the obvious next features, and their absence is the most likely reason a flexible model cannot beat a three-column lookup.
5. **Kitchener only.** Waterloo is a separate municipality with its own portal.

## Not yet done

Poisson/negative-binomial rate model with a `log(length_km)` offset, and survival models (Weibull AFT, Andersen–Gill) for recurrent events. Both are in the plan; neither is required for the recommendation above, which is that the simple ranker ships.
