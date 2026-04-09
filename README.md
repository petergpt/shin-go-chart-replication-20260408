# Replicating And Extending The Shin Et Al. Go Decision-Quality Chart

This repository revisits a claim from Shin et al. about the board game Go: after strong AI systems such as AlphaGo appeared, did the quality of professional human moves rise?

It contains two separate products:

1. A numerical rerun of the released historical results from the authors' public OSF package, matching the released series to reported precision.
2. A separate paper-like continuation of the main yearly chart beyond `2021`, built with a frozen independently reconstructed metric.

Reference paper:

- Minkyu Shin, Jin Kim, Bas van Opheusden, and Thomas L. Griffiths, "Superhuman artificial intelligence can improve human decision-making by increasing novelty," [PNAS / DOI 10.1073/pnas.2214840120](https://www.pnas.org/doi/10.1073/pnas.2214840120)
- Public metadata and open-access record: [PubMed](https://pubmed.ncbi.nlm.nih.gov/36913582/), [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10041097/), [OSF project](https://osf.io/xpf3q/)

## What This Chart Shows

Go is a strategy board game. AlphaGo is the AI system that defeated top human player Lee Sedol in March 2016.

The chart is not a win-rate chart. It is a year-by-year summary of move quality.

At a high level, move quality here means:

- take the moves human professionals actually played
- score those moves against alternatives using a very strong Go engine
- then estimate how each year compares after mostly comparing players against themselves over time

For the continuation chart, the engine is KataGo and the recent game records come from GoGoD, a proprietary archive of professional Go games.

The main chart in this repo asks:

`After the AlphaGo era began, did the quality of human professional Go decisions rise?`

How to read it:

- each dot is one year
- higher means the played moves were closer to what the AI evaluator judged to be stronger choices
- `0` is a reference level, not “perfect play”
- the bars show 95% confidence intervals from the yearly fixed-effects regression
- the centered version simply shifts the pre-AlphaGo average to zero so the uplift is easier to read

The main result in plain English:

- the paper's released historical uplift pattern reruns from the public data package
- a separate paper-like continuation built here remains above the pre-AlphaGo norm for a linked recent-player sample after `2021`
- this continuation is not claimed to be the authors' exact hidden post-`2021` metric

## Main Result

The chart below is the main interpretive view. It is a committed audit artifact generated from private GoGoD inputs plus KataGo, included for inspection in the repo rather than as part of the public clean-clone rerun path.

![Pre-AlphaGo-centered chart](results/paper_like_extension/paper_like_extension_prealphago_centered.png)

Alternate raw-reference view:

- [results/paper_like_extension/paper_like_extension_chart.png](results/paper_like_extension/paper_like_extension_chart.png)

Important note:

- these values are relative year effects, not raw move-quality scores or percentages

Headline numbers for the final continuation metric:

- historical fit to the paper's yearly line: `corr = 0.9884`, `MAE = 0.0192`
- historical uplift vs pre-AlphaGo mean:
  - paper: `+0.5410`
  - final paper-like metric: `+0.5448`
- latest extension values:
  - `2022`: `1.1949`
  - `2023`: `1.2070`
  - `2024`: `1.1848`
  - `2025`: `1.1939`
  - `2026`: `1.0706` (partial year through `2026-01-12`)

What those checks mean in plain English:

- `corr` close to `1` means the reconstructed historical line moves almost the same way as the paper's released line
- lower `MAE` means the reconstructed line stays numerically close to the paper's released line year by year
- the check that compares the reconstructed `2021` splice directly to matched recent data is only moderate, which is why this repo calls the extension paper-like rather than exact

## If You Just Want The Results

Start here:

- primary chart: [results/paper_like_extension/paper_like_extension_prealphago_centered.png](results/paper_like_extension/paper_like_extension_prealphago_centered.png)
- alternate raw-reference chart: [results/paper_like_extension/paper_like_extension_chart.png](results/paper_like_extension/paper_like_extension_chart.png)
- exact historical rerun artifacts: [results/exact_replication](results/exact_replication)
- methods note: [docs/METHODS.md](docs/METHODS.md)

Those first two chart links are committed audit artifacts built from private GoGoD inputs. The public clean-clone rerun product is the exact historical replication.

## What Is In This Repository

- `osf/`
  - a local fetch target for the authors' public OSF replication files
- `public_refs/go_learning_eras/`
  - a public bridge dataset used to match recent GoGoD players to the historical player population
- `scripts/`
  - the R and Python code used for reruns, validation, metric search, and packaging
- `results/`
  - the small GitHub-facing artifact bundle
- `docs/`
  - methods and data notes

The top-level licensing notice is [LICENSE.md](LICENSE.md). It covers the repository's original code and documentation, with separate exceptions for third-party and data-derived materials.

This repo does not commit:

- proprietary GoGoD game archives
- KataGo binaries or model weights
- large scratch outputs and runtime logs

## Quick Glossary

- `OSF`: the paper authors' public replication archive on the Open Science Framework
- `fixed effects`: a regression setup that mostly compares each player against themselves over time
- `corr`: correlation, or how closely two lines move together; `1` is a perfect match
- `MAE`: mean absolute error, or the average gap between two lines; lower is better

## Exact Replication Vs. Paper-Like Continuation

These are different claims.

### 1. Exact historical replication

The historical `1950-2021` outputs are rerun directly from the authors' public release:

- yearly Figure 1A series: [results/exact_replication/fig1_panel_a_yearly.csv](results/exact_replication/fig1_panel_a_yearly.csv)
- monthly Figure 1B series: [results/exact_replication/fig1_panel_b_monthly.csv](results/exact_replication/fig1_panel_b_monthly.csv)
- yearly Figure 1C series: [results/exact_replication/fig1_panel_c_yearly.csv](results/exact_replication/fig1_panel_c_yearly.csv)
- monthly Figure 1D series: [results/exact_replication/fig1_panel_d_monthly.csv](results/exact_replication/fig1_panel_d_monthly.csv)
- Table 1 coefficients:
  - [results/exact_replication/table_1_model_1_coefficients.csv](results/exact_replication/table_1_model_1_coefficients.csv)
  - [results/exact_replication/table_1_model_2_coefficients.csv](results/exact_replication/table_1_model_2_coefficients.csv)

This should be read as:

- exact numerical rerun of the released historical series and coefficients
- regenerated figures are close to the released PNGs, but not pixel-identical

Reference artifacts:

- [results/exact_replication/fig1_panel_a_reproduced.png](results/exact_replication/fig1_panel_a_reproduced.png)
- [results/exact_replication/figure_comparison.json](results/exact_replication/figure_comparison.json)

### 2. Paper-like continuation

The post-`2021` chart is not the authors' exact hidden metric.

Instead, it is a frozen independently reconstructed metric chosen in three stages:

1. a yearly search split to narrow candidates
2. a yearly robustness split to check they survive a different historical partition
3. a manual shortlist monthly follow-up audit on a sealed monthly window, used as the final tie-break among a manually chosen set of strong yearly candidates

`raw_2_60_affine` was not the top row on every yearly leaderboard. In plain English, the label means:

- use the raw reconstructed move-quality signal on moves `2-60`
- then apply a simple fixed linear rescaling fitted on historical years only

It was chosen because it stayed in the top candidate group on the yearly tests and then came out best on that manual shortlist monthly follow-up audit.

The relevant selection artifacts are:

- [results/reverse_engineering/wave_002_refinement_search_leaderboard.csv](results/reverse_engineering/wave_002_refinement_search_leaderboard.csv)
- [results/reverse_engineering/wave_002_refinement_robustness_leaderboard.csv](results/reverse_engineering/wave_002_refinement_robustness_leaderboard.csv)
- [results/reverse_engineering/wave_002_monthly_audit_leaderboard.csv](results/reverse_engineering/wave_002_monthly_audit_leaderboard.csv)
- [results/reverse_engineering/wave_002_monthly_audit_shortlist.json](results/reverse_engineering/wave_002_monthly_audit_shortlist.json)

The final selected metric is `raw_2_60_affine`:

- moves `2-60` are used
- move `1` is excluded because it could not be reconstructed cleanly from public provenance
- the yearly fixed-effects structure matches the paper, which means each year is estimated while controlling for persistent player-specific differences
- the historical calibration is frozen before the post-`2021` extension is read

## How The Continuation Differs From The Original Paper

The differences are methodological, not cosmetic:

- the original historical chart is reproduced from the released public analysis objects, but the authors' full unreleased move-level post-`2021` pipeline is not available
- the final continuation does not claim to be that hidden pipeline
- move `1` is excluded, because the public data were not enough to reconstruct it to a standard we were willing to defend
- the recent continuation uses only players that can be matched cleanly between the historical and recent datasets, using the public `go-learning-eras` bridge and a strict reciprocal activity match
- for recent years, up to `3` evenly spaced games are sampled per player-year
- recent moves are rescored with KataGo under one frozen setup
- the uncertainty bars on the continuation chart come from player-clustered regression standard errors only; they do not include extra uncertainty from player matching, game sampling, or engine choice
- `2026` is only partial-year data through `2026-01-12`

In plain language:

- the exact released historical line is available separately in `results/exact_replication`
- the historical segment drawn inside the continuation chart is a reconstructed line calibrated to match that released history closely, not a verbatim reuse of Figure 1A
- the post-`2021` part is a close, clearly labeled continuation study on a linked recent-player sample

## Validation Snapshot

The full validation summary is in [results/paper_like_extension/summary.json](results/paper_like_extension/summary.json).

These historical fit numbers are post-selection fit for the chosen paper-like metric, not independent proof that the authors' hidden post-`2021` metric has been recovered.

Key checks:

- historical fit to the paper's yearly line:
  - `corr = 0.9884`
  - `MAE = 0.0192`
- historical sampling sensitivity under the frozen `k = 3` rule:
  - `corr = 0.9912`
  - `MAE = 0.1411`
- matched `2021` overlap:
  - game-player: `n = 730`, `corr = 0.4344`, `MAE = 0.4501`
  - player-year: `n = 142`, `corr = 0.7068`, `MAE = 0.4678`
- internal bridge sensitivity check at the splice:
  - `corr = 0.9999`
  - `MAE = 0.0024`

The evidence supports this narrower statement:

- the final continuation metric tracks the historical paper line very closely
- the post-`2021` continuation for the linked recent-player sample remains above the pre-AlphaGo norm
- the result should be read as a paper-like continuation with moderate splice validation, not as exact method identity

In plain language:

- the historical match numbers say the reconstructed line is very close to the paper's released line
- the matched-`2021` overlap numbers are only moderate, so the splice is checked but not exact
- the tiny internal splice-sensitivity gap says the recent continuation is not being driven by one fragile fitting choice

## Reproducing The Repository Outputs

There are three different states to keep separate:

1. public clean-clone reruns
2. private-only regeneration steps that need GoGoD and KataGo
3. committed audit artifacts already checked into `results/`

Only the first of those is a public rerun path from scratch.

### Python environment

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements_replication.txt
```

For the closest match to the committed Python outputs, see the tested versions in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) and [requirements_lock.txt](requirements_lock.txt).

### Fetch The Public OSF Release

```bash
python3 scripts/fetch_public_osf_release.py
```

Then verify the fetched public inputs against the local snapshot manifest:

```bash
python3 scripts/verify_public_inputs.py
```

### R packages

```bash
Rscript scripts/install_r_deps.R
```

This installs the pinned package versions listed in:

- `r_requirements_lock.csv`

### Exact historical rerun

```bash
Rscript scripts/run_shin_main_text_full_r.R
```

Minor numerical drift is possible with newer R package versions. The committed exact-replication artifacts were generated under the tested environment listed in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).

This rerun writes its raw outputs to:

- `outputs/original_r_full/`

The committed GitHub-facing copies live separately under:

- `results/exact_replication/`

## Private-Only Regeneration

### Paper-like continuation

This step requires private GoGoD inputs and a local KataGo installation.

```bash
python3 scripts/build_independent_uplift_chart.py --output-dir outputs/reverse_engineering/paper_like_extension --metric-label paper_like_raw_2_60_affine_visits_20 --move-start 2 --move-end 60 --sample-games-per-player-year 3 --recent-score-start-date 2022-01-01 --max-visits 20 --affine-intercept 0.0022387165680807 --affine-slope 0.9404497155357116 --paper-yearly-target results/exact_replication/fig1_panel_a_yearly.csv --recent-zip data/private/2021-2026-Database-Jan2026.zip --katago-path /path/to/katago --katago-config /path/to/analysis_example.cfg --katago-model /path/to/g170e-b20-model.bin.gz
```

This continuation run writes its raw outputs to:

- `outputs/reverse_engineering/paper_like_extension/paper_like_raw_2_60_affine_visits_20/`

### Postprocess The Continuation Views

This writes the centered chart and the overlay against the paper:

```bash
python3 scripts/postprocess_paper_like_extension.py --combined-yearly outputs/reverse_engineering/paper_like_extension/paper_like_raw_2_60_affine_visits_20/combined_yearly_fe.csv --paper-yearly results/exact_replication/fig1_panel_a_yearly.csv --output-dir outputs/reverse_engineering/paper_like_extension/paper_like_raw_2_60_affine_visits_20/postprocessed --latest-date 2026-01-12
```

Those postprocessed files appear under:

- `outputs/reverse_engineering/paper_like_extension/paper_like_raw_2_60_affine_visits_20/postprocessed/`

## Maintainer Packaging Step

### Refresh The Curated `results/` Bundle

This is a maintainer packaging step, not a clean-clone rerun target by itself. It assumes the full scratch `outputs/` tree already contains:

- the exact historical rerun outputs
- the figure-comparison metadata
- the reverse-engineering wave artifacts
- the finished continuation outputs

```bash
python3 scripts/export_curated_results.py
```

More detail:

- methods: [docs/METHODS.md](docs/METHODS.md)
- data and redistribution notes: [docs/DATA.md](docs/DATA.md)
- public-input manifest: [docs/PUBLIC_INPUT_MANIFEST.json](docs/PUBLIC_INPUT_MANIFEST.json)
- curated results guide: [results/README.md](results/README.md)

## Reproducibility Scope

The public clean-clone rerun path covers:

- fetching the authors' public OSF release into `osf/`
- verifying those fetched files against the local snapshot manifest
- rerunning the released historical outputs into `outputs/original_r_full/`

The repository also commits some audit snapshots that are useful for review but are not the minimal rerun target from a fresh clone:

- `results/exact_replication/figure_comparison.json`
- `results/reverse_engineering/`
- the final curated charts and summaries under `results/paper_like_extension/`

Those files are included so reviewers can inspect the final evidence package directly. The heavier exploratory scratch workflow that originally produced them lives in the private `outputs/` tree and is intentionally not required for a basic public rerun.
