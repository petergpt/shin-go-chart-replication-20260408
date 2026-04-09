# Reverse-Engineering Evaluation Contract

## Goal

Reverse-engineer a historically paper-like yearly uplift metric that can later be
extended post-`2021` without pretending to recover the authors' exact hidden
move-level pipeline.

Primary target:

- [fig1_panel_a_yearly.csv](../original_r_full/fig1_panel_a_yearly.csv)

Sealed follow-up target after yearly candidate selection:

- [fig1_panel_b_monthly.csv](../original_r_full/fig1_panel_b_monthly.csv)

## Search Protocol

Use broad historical candidate search on the released OSF `dt` table first.
Do not inspect post-`2021` data during candidate selection.

### Split A: Search Split

- train: `1951-2008`
- validation: `2009-2015`
- holdout: `2016-2021`

Purpose:

- pick the live candidate family
- reject obvious overfit windows that look good only on pre-AlphaGo validation

### Split B: Robustness Split

- train: `1951-2000`
- validation: `2001-2010`
- holdout: `2011-2021`

Purpose:

- check that the live candidate is not specific to one historical partition
- confirm that wins survive a harder blind period

### Monthly Seal

Monthly comparison against [fig1_panel_b_monthly.csv](../original_r_full/fig1_panel_b_monthly.csv)
is not used during coarse candidate search.

Use monthly only after yearly finalists are frozen.

Recommended sealed window:

- `2016-01` to `2021-10`
- `month_index 793-862`

This is a resolution-blind audit rather than a fully time-blind holdout,
because yearly candidate selection already saw the same years at annual
resolution.

## Metrics

Primary yearly metrics:

- `overall_corr`
- `overall_mae`
- `holdout_corr`
- `holdout_mae`
- `modern_uplift_error`
- `late_level_error`
- `peak_year_error`
- `post_event_first_diff_corr`
- `post_event_direction_match_rate`

Definitions:

- `modern_uplift_error`:
  `| (mean 2016-2021 - mean 2006-2015)_candidate - (same)_target |`
- `late_level_error`:
  absolute difference in mean level over `2018-2021`
- `peak_year_error`:
  absolute difference in `2021`
- `post_event_first_diff_corr`:
  correlation of yearly first differences over `2016+`

## Success Bands

### Promising

- `overall_corr >= 0.94`
- `overall_mae <= 0.10`
- `holdout_corr >= 0.98`
- `holdout_mae <= 0.12`
- `modern_uplift_error <= 0.10`
- `peak_year_error <= 0.12`

### Strong

- `overall_corr >= 0.97`
- `overall_mae <= 0.05`
- `holdout_corr >= 0.99`
- `holdout_mae <= 0.08`
- `modern_uplift_error <= 0.07`
- `peak_year_error <= 0.08`
- `post_event_first_diff_corr >= 0.75`

### Publishable-Like Historical Match

- `overall_corr >= 0.98`
- `overall_mae <= 0.03`
- `holdout_corr >= 0.995`
- `holdout_mae <= 0.05`
- `modern_uplift_error <= 0.04`
- `late_level_error <= 0.07`
- `peak_year_error <= 0.06`
- `post_event_first_diff_corr >= 0.80`

## Anti-Overfitting Rules

- Do not tune against monthly before yearly finalists are frozen.
- Any affine calibration must be fit on train years only.
- A wave is one decision object only if it tests one explicit claim.
- Prefer small orthogonal candidate families over large combinatorial sweeps.
- Do not use post-`2021` extension behavior to select the historical metric.
- A candidate is not a real improvement if it only rescales levels without
  improving holdout shape metrics.

### Monthly Audit Metrics

- `monthly_corr_raw`
- `monthly_mae_raw`
- `monthly_mae_centered`
- `monthly_diff_corr`
- `monthly_direction_match`
- `onset_window_error`
- `late_plateau_error`
- `peak_value_error`
- `peak_timing_error`

Strong monthly audit:

- `monthly_corr_raw >= 0.80`
- `monthly_mae_raw <= 0.15`
- `monthly_diff_corr >= 0.45`
- `monthly_direction_match >= 0.60`
