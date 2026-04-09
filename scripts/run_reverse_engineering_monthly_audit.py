#!/usr/bin/env python3
"""Audit yearly-finalist reverse-engineering candidates against the sealed monthly paper series."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OSF = ROOT / "osf/shin et al 2023 data v001.RData"
DEFAULT_TARGET = ROOT / "outputs/original_r_full/fig1_panel_b_monthly.csv"
SEALED_START = 793  # 2016-01
SEALED_END = 862  # 2021-10
ONSET_START = 795  # 2016-03
ONSET_END = 816  # 2017-12
PLATEAU_START = 829  # 2019-01
PLATEAU_END = 862  # 2021-10
Z_975 = 1.959963984540054


def load_helpers():
    uplift_script = ROOT / "scripts/build_independent_uplift_chart.py"
    uplift_spec = importlib.util.spec_from_file_location("build_uplift", uplift_script)
    if uplift_spec is None or uplift_spec.loader is None:
        raise RuntimeError(f"Unable to load helper module from {uplift_script}")
    uplift = importlib.util.module_from_spec(uplift_spec)
    uplift_spec.loader.exec_module(uplift)
    return uplift


def month_index_from_date(series: pd.Series) -> pd.Series:
    return ((series.dt.year - 1950) * 12 + series.dt.month).astype(int)


def fit_panel_numeric(
    df: pd.DataFrame,
    entity_col: str,
    time_numeric_col: str,
    label_col: str,
    outcome_col: str,
    baseline_label: str,
) -> pd.DataFrame:
    work = df.copy()
    work[entity_col] = work[entity_col].astype(str)
    work[time_numeric_col] = pd.to_numeric(work[time_numeric_col], errors="raise").astype(int)
    work[label_col] = work[label_col].astype(str)

    dummies = pd.get_dummies(work[label_col], prefix="T", dtype=float)
    baseline_col = f"T_{baseline_label}"
    keep_cols = [c for c in dummies.columns if c != baseline_col]
    if not keep_cols:
        raise ValueError("No non-baseline time indicators found")

    panel = pd.concat([work[[entity_col, time_numeric_col, outcome_col]], dummies[keep_cols]], axis=1)
    panel = panel.set_index([entity_col, time_numeric_col]).sort_index()
    model = PanelOLS(panel[outcome_col], panel[keep_cols], entity_effects=True, drop_absorbed=True)
    result = model.fit(cov_type="clustered", cluster_entity=True)

    rows = []
    for name in result.params.index:
        coef = float(result.params[name])
        se = float(result.std_errors[name])
        label = name.split("_", 1)[1]
        rows.append(
            {
                "label": label,
                "fe": coef,
                "fe_ci_ll": coef - Z_975 * se,
                "fe_ci_ul": coef + Z_975 * se,
            }
        )
    return pd.DataFrame(rows)


def fit_monthly_dqi(rows: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        rows.groupby(["player_id", "year_month", "month_index"], as_index=False)["dqi"]
        .median()
        .rename(columns={"dqi": "median_dqi"})
    )
    grouped["month_label"] = grouped["month_index"].astype(str)
    fe = fit_panel_numeric(grouped, "player_id", "month_index", "month_label", "median_dqi", "1")
    fe["month_index"] = fe["label"].astype(int)
    return fe[["month_index", "fe", "fe_ci_ll", "fe_ci_ul"]].sort_values("month_index").reset_index(drop=True)


def safe_corr(a: pd.Series, b: pd.Series) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    if a.nunique(dropna=True) < 2 or b.nunique(dropna=True) < 2:
        return None
    out = a.corr(b)
    return None if pd.isna(out) else float(out)


def mean_abs(a: pd.Series, b: pd.Series) -> float | None:
    if len(a) == 0:
        return None
    return float((a - b).abs().mean())


def compare_monthly(candidate: pd.DataFrame, target: pd.DataFrame) -> dict[str, float | int]:
    merged = target.merge(candidate, on="month_index", suffixes=("_target", "_candidate")).sort_values("month_index")
    sealed = merged.loc[merged["month_index"].between(SEALED_START, SEALED_END)].copy()
    if sealed.empty:
        return {"n_sealed": 0}

    dev = merged.loc[merged["month_index"] < SEALED_START].copy()
    target_anchor = float(dev["fe_target"].mean()) if not dev.empty else 0.0
    candidate_anchor = float(dev["fe_candidate"].mean()) if not dev.empty else 0.0

    sealed_target_centered = sealed["fe_target"] - target_anchor
    sealed_candidate_centered = sealed["fe_candidate"] - candidate_anchor

    diffs_target = sealed["fe_target"].diff().dropna()
    diffs_candidate = sealed["fe_candidate"].diff().dropna()
    direction_match = float((np.sign(diffs_target) == np.sign(diffs_candidate)).mean()) if len(diffs_target) else None

    onset = sealed.loc[sealed["month_index"].between(ONSET_START, ONSET_END)].copy()
    plateau = sealed.loc[sealed["month_index"].between(PLATEAU_START, PLATEAU_END)].copy()

    peak_target_row = sealed.loc[sealed["fe_target"].idxmax()]
    peak_candidate_row = sealed.loc[sealed["fe_candidate"].idxmax()]

    return {
        "n_sealed": int(len(sealed)),
        "sealed_month_min": int(sealed["month_index"].min()),
        "sealed_month_max": int(sealed["month_index"].max()),
        "monthly_corr_raw": safe_corr(sealed["fe_target"], sealed["fe_candidate"]),
        "monthly_mae_raw": mean_abs(sealed["fe_target"], sealed["fe_candidate"]),
        "monthly_mae_centered": mean_abs(sealed_target_centered, sealed_candidate_centered),
        "monthly_diff_corr": safe_corr(diffs_target, diffs_candidate),
        "monthly_direction_match": direction_match,
        "onset_window_error": mean_abs(onset["fe_target"], onset["fe_candidate"]) if not onset.empty else None,
        "late_plateau_error": mean_abs(plateau["fe_target"], plateau["fe_candidate"]) if not plateau.empty else None,
        "peak_value_error": abs(float(peak_target_row["fe_target"]) - float(peak_candidate_row["fe_candidate"])),
        "peak_timing_error": abs(int(peak_target_row["month_index"]) - int(peak_candidate_row["month_index"])),
    }


def rank_key(row: dict[str, float | int | str | None]):
    def val(key: str, default: float) -> float:
        x = row.get(key)
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return default
        return float(x)

    return (
        val("monthly_mae_raw", float("inf")),
        -val("monthly_corr_raw", float("-inf")),
        val("monthly_mae_centered", float("inf")),
        val("late_plateau_error", float("inf")),
        val("peak_value_error", float("inf")),
        val("peak_timing_error", float("inf")),
        -val("monthly_diff_corr", float("-inf")),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-wave", type=Path, required=True)
    parser.add_argument("--candidates", nargs="+", required=True)
    parser.add_argument("--output-prefix", required=True)
    parser.add_argument("--osf", type=Path, default=DEFAULT_OSF)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()

    uplift = load_helpers()
    osf = uplift.load_osf_dt(args.osf)
    osf = osf.copy()
    osf["year_month"] = osf["game_date"].dt.strftime("%Y-%m")
    osf["month_index"] = month_index_from_date(osf["game_date"])

    target = pd.read_csv(args.target)[["month_index", "fe"]].rename(columns={"fe": "fe_target"})
    wave = pd.read_csv(args.candidate_wave)

    results = []
    monthly_outputs: list[pd.DataFrame] = []

    for candidate_name in args.candidates:
        candidate_rows = wave.loc[wave["candidate"] == candidate_name].copy()
        if candidate_rows.empty:
            raise ValueError(f"Candidate {candidate_name!r} not found in {args.candidate_wave}")
        kind = str(candidate_rows["kind"].dropna().iloc[0]) if "kind" in candidate_rows.columns else "raw"

        if kind == "raw":
            start = int(candidate_rows["move_start"].dropna().iloc[0])
            end = int(candidate_rows["move_end"].dropna().iloc[0])
            match_filter = None
            if "matches_ai_move_filter" in candidate_rows.columns:
                raw_filter = candidate_rows["matches_ai_move_filter"].dropna().iloc[0]
                if str(raw_filter) != "all":
                    match_filter = str(raw_filter)
        elif kind == "affine":
            base_name = str(candidate_rows["base_candidate"].dropna().iloc[0])
            base_rows = wave.loc[wave["candidate"] == base_name].copy()
            start = int(base_rows["move_start"].dropna().iloc[0])
            end = int(base_rows["move_end"].dropna().iloc[0])
            match_filter = None
            if "matches_ai_move_filter" in base_rows.columns:
                raw_filter = base_rows["matches_ai_move_filter"].dropna().iloc[0]
                if str(raw_filter) != "all":
                    match_filter = str(raw_filter)
            intercept = float(candidate_rows["affine_intercept"].dropna().iloc[0])
            slope = float(candidate_rows["affine_slope"].dropna().iloc[0])
        else:
            raise ValueError(f"Unsupported candidate kind {kind!r}")

        subset = osf.loc[osf["move_number"].between(start, end)].copy()
        if match_filter is not None:
            subset = subset.loc[subset["matches_ai_move"].astype(str) == match_filter].copy()
        monthly = fit_monthly_dqi(subset).rename(columns={"fe": "fe_candidate"})
        if kind == "affine":
            monthly["fe_candidate"] = intercept + slope * monthly["fe_candidate"]
        compare = compare_monthly(monthly[["month_index", "fe_candidate"]], target)
        compare["candidate_name"] = candidate_name
        compare["kind"] = kind
        compare["move_start"] = start
        compare["move_end"] = end
        monthly_outputs.append(monthly.assign(candidate=candidate_name))
        results.append(compare)

    leaderboard = sorted(results, key=rank_key)

    outdir = ROOT / "outputs/reverse_engineering"
    csv_path = outdir / f"{args.output_prefix}_leaderboard.csv"
    json_path = outdir / f"{args.output_prefix}_leaderboard.json"
    monthly_path = outdir / f"{args.output_prefix}_monthly_series.csv"

    pd.DataFrame(leaderboard).to_csv(csv_path, index=False)
    json_path.write_text(json.dumps({"candidates": leaderboard}, indent=2))
    pd.concat(monthly_outputs, ignore_index=True).to_csv(monthly_path, index=False)

    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    print(f"Wrote {monthly_path}")
    for rank, row in enumerate(leaderboard, start=1):
        print(
            f"{rank:>3} {row['candidate_name']:<28} "
            f"monthly_mae={row.get('monthly_mae_raw')} "
            f"monthly_corr={row.get('monthly_corr_raw')} "
            f"late_plateau_error={row.get('late_plateau_error')}"
        )


if __name__ == "__main__":
    main()
