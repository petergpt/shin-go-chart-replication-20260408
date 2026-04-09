# Methods

This document describes the methodology behind the two main outputs in this repository.

At a high level, "decision quality" here does not mean win rate. It means a move-quality score derived from comparing the move a human actually played with alternatives evaluated by a very strong Go engine. Higher values mean the played moves look closer to the engine's stronger choices.

Short glossary for the terms used below:

- `DQI`: the paper's decision-quality index, a move-quality score rather than a win-rate measure
- `affine`: a simple straight-line rescaling of the form `a + b x`
- `SGF`: the standard file format used to store Go game records
- `komi`: the starting point compensation given to White in Go
- `corr`: correlation, where values closer to `1` mean two lines move together more closely
- `MAE`: mean absolute error, the average gap between two lines
- `FE`: fixed effects, meaning the regression mostly compares each player against themselves over time

## 1. Goal

The project had two separate goals:

1. Reproduce the released historical outputs behind the Shin et al. paper to reported precision, as far as the public OSF release allows.
2. Build a post-`2021` continuation of the uplift chart that is robust on its own terms, even if it is not the authors' unreleased exact metric.

Those goals required different standards.

## 2. Exact Historical Replication

For the published `1950-2021` historical series, the repository uses the authors' public OSF materials directly after fetching them into `osf/` with `scripts/fetch_public_osf_release.py`:

- `osf/shin et al 2023 data v001.RData`
- `osf/shin et al 2023 simulated ai move data v001.RData`
- `osf/shin et al 2023 analyses in the main text v01.R`

The exact rerun is driven by:

- `scripts/run_shin_main_text_full_r.R`
- `scripts/replicate_shin_panel_ab_r.R`

This yields the released yearly and monthly series and the released Table 1 coefficients to reported precision.

The figures regenerated here are close to the released PNGs, but not pixel-identical. The exact claim is about the numerical series and coefficients.

## 3. Why The Final Extension Does Not Claim To Be The Authors' Exact Post-2021 Metric

We pushed hard on the exact end-to-end move-level reconstruction path and did not stop at a vague mismatch.

The key blocker was move `1`:

- move-`1` DQI from the public release could not be reconstructed deterministically from public provenance
- identical apparent move-`1` situations in the released data can carry different published move-`1` DQI values
- that indicates a missing non-public step, hidden code path, or provenance gap in the original move-level construction

Because of that, the repository does not present the final extension as the authors' exact hidden metric continued forward.

Instead, it presents a separately defined paper-like continuation metric that was selected by historical scorecards plus a documented manual shortlist-and-audit follow-up step.

## 4. Candidate Search For A Paper-Like Metric

The reverse-engineering workflow is documented in:

- `results/reverse_engineering/evaluation_contract.md`
- `scripts/build_reverse_engineering_wave.py`
- `scripts/run_paper_like_metric_wave.py`
- `scripts/run_reverse_engineering_monthly_audit.py`

The candidate family varied:

- move windows
- limited calibrations
- simple transforms
- historical-only fit choices

Selection discipline:

- yearly search split
  - train: `1951-2008`
  - validation: `2009-2015`
  - holdout: `2016-2021`
- yearly robustness split
  - train: `1951-2000`
  - validation: `2001-2010`
  - holdout: `2011-2021`
- manual monthly follow-up audit on a sealed monthly window opened only after yearly candidates were narrowed

Scoring criteria included:

- yearly correlation
- yearly MAE
- uplift-shape error
- late-level error
- peak-year error
- monthly agreement
- direction-match statistics

The final selected metric was `raw_2_60_affine`.

That selection should be read carefully:

- the yearly search and yearly robustness waves narrowed the candidate set
- the manual monthly follow-up audit was used as the decisive tie-break among a manually chosen shortlist of strong yearly candidates
- `raw_2_60_affine` was not the top row on every yearly leaderboard; it was selected because it held up as a top-tier yearly candidate and then came out best on the committed monthly audit of that manual shortlist

## 5. Definition Of The Final Extension Metric

The final metric used for the chart in this repository is:

`paper_like_raw_2_60_affine_visits_20`

Its construction is:

1. Historical foundation:
   - use exact OSF DQI rows
   - restrict to move numbers `2-60`
   - aggregate to game-player median DQI
   - aggregate again to player-year median DQI
   - fit yearly fixed effects with player fixed effects and player-clustered SEs
   - in plain language, compare each player mostly against themselves over time so the line is less driven by who happened to be active in a given year

2. Historical calibration:
   - fit the historical yearly series
   - apply a frozen affine transform chosen from the historical candidate search
   - affine intercept: `0.0022387165680807`
   - affine slope: `0.9404497155357116`

3. Recent continuation:
   - use GoGoD `2021-2026` SGFs
   - score moves `2-60` with KataGo
   - respect per-game SGF rules when possible, with a documented fallback
   - respect per-game SGF komi, rounding unsupported quarter-komi to the nearest supported half-integer
   - restrict to players crosswalked between GoGoD and the historical OSF / `go-learning-eras` bridge
   - the current bridge uses the reciprocal monthly-activity matcher implemented in `build_bridge_crosswalk`, with defaults `min_games = 20` and `min_score = 0.99`
   - sample up to `3` evenly spaced games per player-year
   - aggregate to player-year medians
   - fit the same yearly fixed-effects structure
   - apply the frozen affine transform

4. Presentation:
   - report the raw yearly FE series
   - report a pre-AlphaGo-centered view for interpretation
   - show 95% confidence intervals from the player-clustered yearly FE regression
   - do not treat those intervals as full uncertainty bands for player matching, sampling, or engine choice
   - mark `2026` as partial-year data through `2026-01-12`

## 6. Validation Used For The Final Repository Result

The final validation fields are recorded in `results/paper_like_extension/summary.json`.

The most important ones are:

- historical yearly fit to the paper:
  - `corr = 0.9884`
  - `MAE = 0.0192`
- historical sampling sensitivity under the frozen `k = 3` rule:
  - `corr = 0.9912`
  - `MAE = 0.1411`
- matched `2021` splice validation:
  - game-player overlap:
    - `n = 730`
    - `corr = 0.4344`
    - `MAE = 0.4501`
  - player-year overlap:
    - `n = 142`
    - `corr = 0.7068`
    - `MAE = 0.4678`
- internal bridge sensitivity at the splice:
  - `corr = 0.9999`
  - `MAE = 0.0024`

That last number is not an external validation result. It is an internal sensitivity check comparing two nearby ways of fitting the reconstructed splice around `2021`.

These checks support a narrow claim: this is a close paper-like continuation metric. They do not support relabeling the metric as the authors' exact hidden post-`2021` DQI.

## 7. Differences From The Original Paper

The exact historical release and the final continuation should be compared carefully.

What remains identical in spirit:

- yearly fixed-effects estimand
- player-year aggregation logic
- focus on the AI-era uplift in decision quality
- direct historical comparison to the original line

What differs:

- the extension metric excludes move `1`
- the continuation population is restricted to crosswalk-linked recent GoGoD players
- recent years use a frozen sampled-game rule
- recent years use a fixed KataGo continuation setup rather than the authors' unrecovered original pipeline
- the historical segment inside the continuation chart is a reconstructed historical series calibrated to match the released Figure 1A line closely; it is not a literal reuse of the exact released yearly CSV
- the final extension is explicitly a paper-like continuation, not a claim of exact method identity

## 8. Interpretation

The strongest substantive conclusion supported by this repository is:

- the released historical uplift pattern is reproducible from the public release
- a frozen independently reconstructed metric that matches the historical paper line very closely still shows decision quality well above the pre-AlphaGo norm through the available post-`2021` data for the linked continuation population

The strongest unsupported conclusion would be:

- "this is exactly the authors' hidden metric continued forward"

This repository does not make that claim.
