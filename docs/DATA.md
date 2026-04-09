# Data Notes

This repository mixes public replication materials, public bridge data, and non-public dependencies that are required only for the post-`2021` continuation.

## Included In The Repository

### Authors' public OSF release

Committed in `osf/`:

- `shin et al 2023 data v001.RData`
- `shin et al 2023 simulated ai move data v001.RData`
- `shin et al 2023 analyses in the main text v01.R`
- released Figure 1 PNGs used for comparison

These files are the public basis for the exact historical replication.

### Public bridge data

Committed in `public_refs/go_learning_eras/data/`:

- `games.csv`
- `players.csv`

These files come from the public `go-learning-eras` project and were used as the bridge between the historical OSF player population and the recent GoGoD continuation population.

### Curated results

Committed in `results/`:

- exact replication outputs
- candidate-search artifacts
- the final paper-like extension CSVs, summaries, and figures

## Not Included In The Repository

### Proprietary GoGoD files

Not committed:

- purchased GoGoD database archives
- raw SGF extractions derived from those archives

The continuation scripts expect a private zip path such as:

- `data/private/2021-2026-Database-Jan2026.zip`

That directory is intentionally gitignored.

### KataGo binaries and model files

Not committed:

- KataGo executable
- KataGo config files
- KataGo model weights

The repository documents the commands used, but does not redistribute third-party engine binaries or model weights.

### Large scratch outputs

Not committed:

- the full exploratory `outputs/` tree
- `analysis_logs/`
- temporary runtime chunks and caches
- local provenance-hunting files

Those files remain in the original project working directory but are deliberately excluded from the GitHub package.

## Copyright / Redistribution Notes

The main redistribution boundary is:

- authors' public OSF release: committed
- public `go-learning-eras` bridge CSVs: committed
- proprietary GoGoD corpus: not committed
- KataGo runtime assets: not committed

If you plan to rerun the continuation pipeline, make sure your local use of GoGoD and KataGo complies with their respective licenses and redistribution terms.
