#!/usr/bin/env python3
"""Reproduce Shin et al. Figure 1 Panel A/B from a flat move-level table.

Input requirements
------------------
A table with at least these columns:
    - game_date : YYYY-MM-DD
    - player_id : player identifier
    - dqi       : Decision Quality Index for each move

Supported input formats:
    - .RData / .rda (via pyreadr)
    - .csv
    - .parquet
    - .feather

Outputs:
    - panel_a_yearly_coefficients.csv
    - panel_b_monthly_coefficients.csv
    - panel_a_yearly.png
    - panel_b_monthly.png

Notes
-----
This script ports the *released chart logic* from shin_main_text.R.
It does NOT compute DQI from raw SGFs.
"""

from __future__ import annotations

import argparse
import calendar
import math
import re
from pathlib import Path
from typing import Iterable, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    import pyreadr  # type: ignore
except Exception:  # pragma: no cover
    pyreadr = None

try:
    from linearmodels.panel import PanelOLS  # type: ignore
    HAVE_LINEARMODELS = True
except Exception:  # pragma: no cover
    PanelOLS = None
    HAVE_LINEARMODELS = False

import statsmodels.formula.api as smf

Z_975 = 1.959963984540054
ALPHAGO_DATE = pd.Timestamp("2016-03-15")


def decimal_year(ts: pd.Timestamp) -> float:
    year = ts.year
    start = pd.Timestamp(year=year, month=1, day=1)
    end = pd.Timestamp(year=year + 1, month=1, day=1)
    return year + (ts - start).total_seconds() / (end - start).total_seconds()


def month_index_from_ym(ym: str) -> int:
    year = int(ym[:4])
    month = int(ym[5:7])
    return (year - 1950) * 12 + month


def load_input(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()

    if suffix in {".csv"}:
        df = pd.read_csv(path)
    elif suffix in {".parquet"}:
        df = pd.read_parquet(path)
    elif suffix in {".feather"}:
        df = pd.read_feather(path)
    elif suffix in {".rdata", ".rda"}:
        if pyreadr is None:
            raise RuntimeError("pyreadr is required to load .RData/.rda files")
        objs = pyreadr.read_r(str(path))
        if "dt" in objs and isinstance(objs["dt"], pd.DataFrame):
            df = objs["dt"]
        else:
            frames = [(k, v) for k, v in objs.items() if isinstance(v, pd.DataFrame)]
            if not frames:
                raise RuntimeError(f"No DataFrame object found in {path}")
            df = frames[0][1]
    else:
        raise ValueError(f"Unsupported file type: {path}")

    required = {"game_date", "player_id", "dqi"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.copy()
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df = df.loc[df["game_date"].notna()].copy()
    df["player_id"] = df["player_id"].astype(str)
    df["dqi"] = pd.to_numeric(df["dqi"], errors="coerce")
    df = df.loc[df["dqi"].notna()].copy()
    return df


def build_yearly_player_medians(dt: pd.DataFrame) -> pd.DataFrame:
    d1 = dt.copy()
    d1["year"] = d1["game_date"].dt.year.astype(str)
    d1 = (
        d1.groupby(["player_id", "year"], as_index=False)["dqi"]
        .median()
        .rename(columns={"dqi": "median_dqi"})
    )
    return d1


def build_monthly_player_medians(dt: pd.DataFrame) -> pd.DataFrame:
    d3 = dt.copy()
    d3["year_month"] = d3["game_date"].dt.strftime("%Y-%m")
    d3 = (
        d3.groupby(["player_id", "year_month"], as_index=False)["dqi"]
        .median()
        .rename(columns={"dqi": "median_dqi"})
    )
    d3["month_index"] = d3["year_month"].map(month_index_from_ym).astype(int)
    return d3


def _fit_with_linearmodels(
    df: pd.DataFrame,
    entity_col: str,
    time_col: str,
    outcome_col: str,
    baseline: str,
) -> pd.DataFrame:
    work = df.copy()
    work[time_col] = work[time_col].astype(str)
    dummy_prefix = "T"
    dummies = pd.get_dummies(work[time_col], prefix=dummy_prefix, dtype=float)
    baseline_col = f"{dummy_prefix}_{baseline}"
    keep_cols = [c for c in dummies.columns if c != baseline_col]
    if not keep_cols:
        raise ValueError("No non-baseline time indicators found")

    work = pd.concat([work[[entity_col, time_col, outcome_col]], dummies[keep_cols]], axis=1)
    work = work.set_index([entity_col, time_col])

    mod = PanelOLS(work[outcome_col], work[keep_cols], entity_effects=True, drop_absorbed=True)
    res = mod.fit(cov_type="clustered", cluster_entity=True)

    rows = []
    for name in keep_cols:
        coef = float(res.params[name])
        se = float(res.std_errors[name])
        label = name.split("_", 1)[1]
        rows.append(
            {
                "label": label,
                "fe": coef,
                "fe_ci_ll": coef - Z_975 * se,
                "fe_ci_ul": coef + Z_975 * se,
            }
        )
    out = pd.DataFrame(rows)
    return out


def _fit_with_statsmodels(
    df: pd.DataFrame,
    entity_col: str,
    time_col: str,
    outcome_col: str,
    baseline: str,
) -> pd.DataFrame:
    work = df.copy()
    work[time_col] = work[time_col].astype(str)
    work[entity_col] = work[entity_col].astype(str)

    formula = (
        f"{outcome_col} ~ C({time_col}, Treatment(reference='{baseline}')) + C({entity_col})"
    )
    res = smf.ols(formula, data=work).fit(
        cov_type="cluster",
        cov_kwds={"groups": work[entity_col]},
    )

    patt = re.compile(rf"C\({re.escape(time_col)}, Treatment\(reference='[^']+'\)\)\[T\.(.+)\]")
    rows = []
    for name, coef in res.params.items():
        m = patt.fullmatch(name)
        if not m:
            continue
        label = m.group(1)
        se = float(res.bse[name])
        coef = float(coef)
        rows.append(
            {
                "label": label,
                "fe": coef,
                "fe_ci_ll": coef - Z_975 * se,
                "fe_ci_ul": coef + Z_975 * se,
            }
        )
    out = pd.DataFrame(rows)
    return out


def fit_time_effects(
    df: pd.DataFrame,
    entity_col: str,
    time_col: str,
    outcome_col: str,
    baseline: str,
) -> pd.DataFrame:
    if HAVE_LINEARMODELS:
        try:
            return _fit_with_linearmodels(df, entity_col, time_col, outcome_col, baseline)
        except Exception:
            pass
    return _fit_with_statsmodels(df, entity_col, time_col, outcome_col, baseline)


def plot_panel_a(coeffs: pd.DataFrame, last_date: pd.Timestamp, outpath: Path) -> None:
    coeffs = coeffs.copy()
    coeffs["year"] = coeffs["label"].astype(int)
    coeffs = coeffs.sort_values("year")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axvspan(decimal_year(ALPHAGO_DATE), decimal_year(last_date), alpha=0.3)
    ax.axvline(decimal_year(ALPHAGO_DATE), linestyle="--", linewidth=1.0)
    ax.errorbar(
        coeffs["year"],
        coeffs["fe"],
        yerr=[coeffs["fe"] - coeffs["fe_ci_ll"], coeffs["fe_ci_ul"] - coeffs["fe"]],
        fmt="o",
        capsize=0,
    )

    last_label = f"{last_date.year}\n({calendar.month_abbr[last_date.month]})"
    xticks = [1950] + list(range(1960, 2020, 10)) + [decimal_year(last_date)]
    xlabels = ["1950"] + [str(y) for y in range(1960, 2020, 10)] + [last_label]

    ax.set_xlim(1948, max(2022, last_date.year + 1))
    ax.set_ylim(-0.8, 1.2)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels)
    ax.set_yticks(np.arange(-0.8, 1.2001, 0.4))
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(outpath, dpi=200)
    plt.close(fig)


def plot_panel_b(coeffs: pd.DataFrame, last_date: pd.Timestamp, outpath: Path) -> None:
    coeffs = coeffs.copy()
    coeffs["month_index"] = coeffs["label"].astype(int)
    coeffs = coeffs.sort_values("month_index")

    alphago_month_index = month_index_from_ym("2016-03")
    last_month_index = month_index_from_ym(last_date.strftime("%Y-%m"))

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axvspan(alphago_month_index, last_month_index, alpha=0.3)
    ax.axvline(alphago_month_index, linestyle="--", linewidth=1.0)
    ax.errorbar(
        coeffs["month_index"],
        coeffs["fe"],
        yerr=[coeffs["fe"] - coeffs["fe_ci_ll"], coeffs["fe_ci_ul"] - coeffs["fe"]],
        fmt="o",
        markersize=2,
        linewidth=0.7,
        capsize=0,
    )

    tick_ym = [f"{y}-01" for y in range(1950, 2020, 10)] + [last_date.strftime("%Y-%m")]
    xticks = [month_index_from_ym(x) for x in tick_ym]
    xlabels = [f"{y}\n(Jan)" for y in range(1950, 2020, 10)] + [f"{last_date.year}\n({calendar.month_abbr[last_date.month]})"]

    xmin = month_index_from_ym(dt_floor_month(last_date, year=1950).strftime("%Y-%m"))
    xmax = last_month_index + 36
    ax.set_xlim(xmin - 24, xmax)
    ax.set_ylim(-3.0, 1.5)
    ax.set_yticks(np.arange(-3.0, 1.5001, 1.5))
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels)
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(outpath, dpi=200)
    plt.close(fig)


def dt_floor_month(last_date: pd.Timestamp, year: int = 1950) -> pd.Timestamp:
    return pd.Timestamp(year=year, month=1, day=1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    outdir = args.output_dir
    outdir.mkdir(parents=True, exist_ok=True)

    dt = load_input(args.input)
    last_date = dt["game_date"].max().normalize()

    # Panel A
    d1 = build_yearly_player_medians(dt)
    yearly = fit_time_effects(d1, entity_col="player_id", time_col="year", outcome_col="median_dqi", baseline="1950")
    yearly = yearly.sort_values("label")
    yearly.to_csv(outdir / "panel_a_yearly_coefficients.csv", index=False)
    plot_panel_a(yearly, last_date, outdir / "panel_a_yearly.png")

    # Panel B
    d3 = build_monthly_player_medians(dt)
    monthly = fit_time_effects(d3, entity_col="player_id", time_col="month_index", outcome_col="median_dqi", baseline="1")
    monthly = monthly.sort_values("label", key=lambda s: s.astype(int))
    monthly.to_csv(outdir / "panel_b_monthly_coefficients.csv", index=False)
    plot_panel_b(monthly, last_date, outdir / "panel_b_monthly.png")

    print(f"Wrote outputs to: {outdir}")


if __name__ == "__main__":
    main()
