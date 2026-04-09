# Curated Results

This directory contains the small, review-facing artifact bundle intended for GitHub.

These files are committed audit snapshots. They are meant for inspection and citation inside the repository.

They are not the same thing as the minimal clean-clone rerun path, which starts from:

- `python3 scripts/fetch_public_osf_release.py`
- `Rscript scripts/run_shin_main_text_full_r.R`

If you only open three files in this folder, start with:

- `paper_like_extension/paper_like_extension_chart.png`
- `paper_like_extension/paper_like_extension_prealphago_centered.png`
- `exact_replication/fig1_panel_a_yearly.csv`

## `exact_replication/`

Exact public-release replication artifacts for the historical paper outputs:

- Figure 1A yearly CSV and reproduced PNG
- Figure 1B monthly CSV and reproduced PNG
- Figure 1C yearly CSV and Figure 1D monthly CSV used by the supplement-side reconstruction scripts
- Table 1 coefficient CSVs
- figure-comparison metadata

These files stay close to the authors' public-release context. See the carve-out in [../LICENSE.md](../LICENSE.md).

## `reverse_engineering/`

Historical candidate-selection artifacts for the paper-like metric:

- evaluation contract
- refinement candidate manifests and specs
- refinement search leaderboard
- robustness leaderboard
- monthly audit leaderboard
- monthly audit shortlist manifest
- monthly audit series

These files explain why the final continuation metric was chosen and what
shortlist was sent to the manual monthly follow-up audit.

These aggregate audit artifacts are released under `CC BY-NC-SA 4.0`. See [../LICENSE.md](../LICENSE.md).

## `paper_like_extension/`

Final extension artifacts for the chart this repository is built around:

- yearly FE CSV
- validation summary JSON
- main chart
- pre-AlphaGo-centered chart produced by `scripts/postprocess_paper_like_extension.py`
- overlay against the paper produced by `scripts/postprocess_paper_like_extension.py`

Read the chart images with two caveats in mind:

- years through `2021` are the reconstructed historical segment, calibrated to match the released paper line closely
- years `2022+` are the linked GoGoD continuation sample, and the intervals are player-clustered regression intervals only

Use `paper_like_extension/summary.json` as supporting detail after looking at the chart images.

These aggregate continuation outputs are released under `CC BY-NC-SA 4.0`. See [../LICENSE.md](../LICENSE.md).
