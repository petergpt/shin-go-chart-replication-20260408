# Data Notes

This repository mixes three kinds of inputs:

- public replication materials released by the paper's authors
- public bridge data used to match players across datasets
- non-public inputs needed only for the post-`2021` continuation

## Included In The Repository

### Authors' public OSF release

`osf/` is a local fetch target, not a vendored data directory.

To populate it from the authors' public OSF project, run:

- `python3 scripts/fetch_public_osf_release.py`
- `python3 scripts/verify_public_inputs.py`

That script downloads:

- `shin et al 2023 data v001.RData`
- `shin et al 2023 simulated ai move data v001.RData`
- `shin et al 2023 analyses in the main text v01.R`
- released Figure 1 and Figure 2/3 PNGs used for comparison

These files are the public basis for the exact historical replication.
Their pinned file hashes are recorded in `docs/PUBLIC_INPUT_MANIFEST.json`.

### Public bridge data

Committed in `public_refs/go_learning_eras/data/`:

- `games.csv`
- `players.csv`

These files come from the public `go-learning-eras` project and were used as the bridge between the historical OSF player population and the recent GoGoD continuation population.

They are redistributed here under the upstream `CC BY-NC-SA 4.0` terms. See:

- `public_refs/go_learning_eras/README.md`
- `public_refs/go_learning_eras/LICENSE.md`
- `docs/PUBLIC_INPUT_MANIFEST.json`

In plain language:

- `OSF` is the paper's public replication archive
- `GoGoD` is the proprietary Go game database used for recent SGF files
- `KataGo` is the Go engine used to rescore moves
- `go-learning-eras` is the public helper dataset used to match player identities

### Curated results

Committed in `results/`:

- exact replication outputs
- candidate-search artifacts
- the final paper-like extension CSVs, summaries, and figures

These are aggregate derived outputs and review artifacts. They do not include raw SGFs or row-level GoGoD game records.
Licensing is split by subtree:

- `results/exact_replication/` stays tied to the surrounding upstream public-release context
- `results/reverse_engineering/` and `results/paper_like_extension/` are original aggregate outputs from this repository and are released under `CC BY-NC-SA 4.0`

## Not Included In The Repository

### Proprietary GoGoD files

Not committed:

- purchased GoGoD database archives
- raw SGF extractions derived from those archives

The continuation scripts expect a private zip path such as:

- `data/private/2021-2026-Database-Jan2026.zip`

That directory is intentionally gitignored.

Some audit and provenance scripts need additional private files under `data/private/`, including:

- `GameData.zip`
- older GoGoD decade archives such as `0196-1980-Database-Jan2026.zip` through `2011-2020-Database-Jan2026.zip`

Those extra archives are not required for the main paper-like extension chart, but they are required for some of the auxiliary audit scripts committed in `scripts/`.

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

- authors' public OSF release: fetched locally from the authors' public OSF project, not re-hosted in git
- public `go-learning-eras` bridge CSVs: committed
- proprietary GoGoD corpus: not committed
- KataGo runtime assets: not committed

If you plan to rerun the continuation pipeline, make sure your local use of GoGoD and KataGo complies with their respective licenses and redistribution terms.

The top-level mixed-license notice for this repository is in `LICENSE.md`.
