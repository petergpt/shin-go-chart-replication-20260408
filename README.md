# Replicating And Extending The Shin Et Al. Go Chart

This repo does two things:

1. reruns the released historical results from Shin et al.'s public archive
2. builds a separate paper-like continuation of the main yearly chart beyond `2021`

Reference paper:

- Minkyu Shin, Jin Kim, Bas van Opheusden, and Thomas L. Griffiths, "Superhuman artificial intelligence can improve human decision-making by increasing novelty," [PNAS](https://www.pnas.org/doi/10.1073/pnas.2214840120)
- Public records: [PubMed](https://pubmed.ncbi.nlm.nih.gov/36913582/), [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10041097/), [OSF](https://osf.io/xpf3q/)

## Main Result

This is the main interpretive chart in the repo.

- one dot = one year
- higher = stronger human moves by the AI evaluator's standard
- `0` = pre-AlphaGo average
- blue years are the post-`2021` continuation

![Pre-AlphaGo-centered chart](results/paper_like_extension/paper_like_extension_prealphago_centered.png)

Raw-reference version:

- [results/paper_like_extension/paper_like_extension_chart.png](results/paper_like_extension/paper_like_extension_chart.png)

Short conclusion:

- the released historical uplift pattern reruns from the authors' public package
- the continuation built here stays above the pre-AlphaGo norm after `2021`
- this continuation is paper-like, not claimed to be the authors' exact hidden post-`2021` metric

## What Is Exact Vs. Reconstructed

Exact historical replication:

- reruns the released `1950-2021` results from the authors' public OSF package
- matches the released series and Table 1 coefficients to reported precision
- outputs live in [results/exact_replication](results/exact_replication)

Paper-like continuation:

- extends the main yearly chart with a frozen independently reconstructed metric
- uses KataGo plus recent GoGoD game records
- excludes move `1`
- uses a linked recent-player sample rather than the paper authors' unreleased full pipeline
- outputs live in [results/paper_like_extension](results/paper_like_extension)

## Key Files

- main chart: [results/paper_like_extension/paper_like_extension_prealphago_centered.png](results/paper_like_extension/paper_like_extension_prealphago_centered.png)
- continuation summary: [results/paper_like_extension/summary.json](results/paper_like_extension/summary.json)
- historical yearly rerun: [results/exact_replication/fig1_panel_a_yearly.csv](results/exact_replication/fig1_panel_a_yearly.csv)
- methods: [docs/METHODS.md](docs/METHODS.md)
- data and licensing boundaries: [docs/DATA.md](docs/DATA.md), [LICENSE.md](LICENSE.md)
- environment details: [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md)

## Quick Start

Public exact historical rerun:

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements_replication.txt && python3 scripts/fetch_public_osf_release.py && python3 scripts/verify_public_inputs.py && Rscript scripts/install_r_deps.R && Rscript scripts/run_shin_main_text_full_r.R
```

That public path reproduces the released historical results only.

The post-`2021` continuation is not a clean-clone rerun target. It also needs:

- private GoGoD game archives
- a local KataGo installation and model

## Repo Layout

- `scripts/`: reruns, validation, metric search, packaging
- `results/`: small review-facing artifact bundle
- `docs/`: methods, data notes, environment details
- `public_refs/go_learning_eras/`: public bridge data
- `osf/`: local fetch target for the authors' public archive

## Data Boundary

This repo does not include:

- proprietary GoGoD archives
- KataGo binaries or model weights
- large scratch outputs

It does include:

- code and docs from this project
- public bridge data
- exact historical rerun artifacts
- aggregate continuation artifacts

See [docs/DATA.md](docs/DATA.md) for the full boundary.
