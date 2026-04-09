#!/usr/bin/env python3
"""Build historical reverse-engineering candidate waves from the released OSF dt table.

Supports:
- raw move-window yearly FE candidates
- train-only affine calibrations of a raw candidate against the released paper line
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OSF = ROOT / "osf/shin et al 2023 data v001.RData"
DEFAULT_TARGET = ROOT / "outputs/original_r_full/fig1_panel_a_yearly.csv"
DEFAULT_OUTPUT_DIR = ROOT / "outputs/reverse_engineering"


def load_helpers():
    script = ROOT / "scripts/build_independent_uplift_chart.py"
    spec = importlib.util.spec_from_file_location("build_uplift", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load helper module from {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def raw_yearly_series(osf: pd.DataFrame, start: int, end: int, match_filter: str | None):
    hist = osf.loc[osf["move_number"].between(start, end)].copy()
    if match_filter is not None:
        hist = hist.loc[hist["matches_ai_move"].astype(str) == match_filter].copy()
    hist["year"] = hist["game_date"].dt.year.astype(int)
    panel = (
        hist.groupby(["player_id", "year"], as_index=False)["dqi"]
        .median()
        .rename(columns={"dqi": "median_dqi"})
        .sort_values(["player_id", "year"])
        .reset_index(drop=True)
    )
    return panel


def fit_affine(candidate: pd.DataFrame, target: pd.DataFrame, train_years: set[int]) -> tuple[float, float]:
    merged = target.merge(candidate, on="year", how="inner", suffixes=("_target", "_candidate"))
    merged = merged.loc[merged["year"].isin(train_years)].copy()
    if len(merged) < 2:
        raise ValueError("Need at least two overlapping train years to fit affine calibration")
    x = merged["fe_candidate"].to_numpy(dtype=float)
    y = merged["fe_target"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    return float(intercept), float(slope)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True, help="JSON spec describing the wave to build")
    parser.add_argument("--output", type=Path, required=True, help="CSV path to write")
    parser.add_argument("--osf", type=Path, default=DEFAULT_OSF)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()

    helpers = load_helpers()
    osf = helpers.load_osf_dt(args.osf)
    target = pd.read_csv(args.target).rename(columns={"fe": "fe_target"})[["year", "fe_target"]]

    spec = json.loads(args.spec.read_text())
    train_years = set()
    for token in spec.get("train_years", []):
        if isinstance(token, list) and len(token) == 2:
            start, end = token
            train_years.update(range(int(start), int(end) + 1))
        else:
            train_years.add(int(token))

    raw_cache: dict[str, pd.DataFrame] = {}
    rows: list[pd.DataFrame] = []

    for candidate in spec["candidates"]:
        kind = candidate["kind"]
        name = candidate["name"]
        if kind == "raw":
            start = int(candidate["move_start"])
            end = int(candidate["move_end"])
            match_filter = candidate.get("matches_ai_move")
            panel = raw_yearly_series(osf, start, end, match_filter)
            yearly = helpers.fit_yearly_panel(panel).rename(columns={"fe": "fe_candidate"})
            yearly["candidate"] = name
            yearly["kind"] = kind
            yearly["move_start"] = start
            yearly["move_end"] = end
            yearly["matches_ai_move_filter"] = "all" if match_filter is None else str(match_filter)
            rows.append(yearly.rename(columns={"fe_candidate": "fe"}))
            raw_cache[name] = yearly
            continue

        if kind == "affine":
            base_name = candidate["base"]
            if base_name not in raw_cache:
                raise ValueError(f"Affine candidate {name!r} refers to missing base {base_name!r}")
            base = raw_cache[base_name][["year", "fe_candidate"]].copy()
            intercept, slope = fit_affine(base, target, train_years)
            yearly = base.copy()
            yearly["fe"] = intercept + slope * yearly["fe_candidate"]
            yearly["candidate"] = name
            yearly["kind"] = kind
            yearly["base_candidate"] = base_name
            yearly["affine_intercept"] = intercept
            yearly["affine_slope"] = slope
            rows.append(yearly.drop(columns=["fe_candidate"]))
            continue

        raise ValueError(f"Unsupported candidate kind: {kind!r}")

    out = pd.concat(rows, ignore_index=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    print(args.output)
    print(f"candidates {out['candidate'].nunique()} rows {len(out)}")


if __name__ == "__main__":
    main()
