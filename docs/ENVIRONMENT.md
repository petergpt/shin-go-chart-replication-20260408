# Tested Environment

The committed artifacts in this repository were generated under the environment below.

This matters most for the exact historical rerun. The released historical series and coefficients are reproducible from the public OSF package, but small numerical drift is still possible if you rerun the scripts under meaningfully newer package versions.

## Python

- Python `3.12.12`
- pandas `3.0.2`
- numpy `2.4.4`
- matplotlib `3.10.8`
- statsmodels `0.14.6`
- linearmodels `7.0`
- pyreadr `0.5.4`
- pyarrow `23.0.1`
- requests `2.33.1`
- sgfmill `1.1.1`
- scikit-learn `1.8.0`
- osfclient `0.0.5`
- Pillow `12.2.0`

For a close Python match, install from `requirements_lock.txt`.

## R

- R `4.5.3`
- data.table `1.18.2.1`
- lfe `3.1.1`
- ggplot2 `4.0.2`
- coefplot `1.2.9`
- lubridate `1.9.5`
- lemon `0.5.2`
- gridExtra `2.3`
- kim `0.6.4`

## Practical Guidance

- `requirements_replication.txt` is the lightweight install list.
- `requirements_lock.txt` is the tested Python package set used for the committed outputs.
- `r_requirements_lock.csv` is the pinned R package set used for the committed outputs.
- `scripts/install_r_deps.R` installs the pinned R package versions from `r_requirements_lock.csv`.
