#!/usr/bin/env python3
"""Reconstruct the remaining sequence-based supplement figures.

This script uses GoGoD-derived human opening sequences from go-learning-eras and
the released 10,000 simulated AI games to rebuild:
  - Fig. S1: yearly share of games with novel 8-move strategies
  - Fig. S6: yearly/monthly fixed effects on Novelty Index after adding AI games

It also validates the human-only novelty reconstruction against the released
main-text novelty trends (Fig. 1C/D) before freezing outputs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyreadr
from linearmodels.panel import PanelOLS

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replicate_shin_panel_ab import ALPHAGO_DATE, decimal_year, month_index_from_ym


ORANGE = "#D9B25A"
GREEN = "#69AA45"
GRAY = "#8E8E8E"
Z_975 = 1.959963984540054


@dataclass(frozen=True)
class HumanFilter:
    name: str
    description: str


FILTERS = [
    HumanFilter("all", "All GoGoD-derived games in go-learning-eras within 1950-01-01 to 2021-10-31."),
    HumanFilter("komi_known", "Require non-null komi."),
    HumanFilter("komi_positive", "Require komi > 0."),
    HumanFilter("result_known", "Require known game result."),
    HumanFilter("komi_known_result_known", "Require non-null komi and known result."),
]


def get_arg_value(args: list[str], flag: str, default: str | None = None) -> str | None:
    try:
        idx = args.index(flag)
    except ValueError:
        return default
    if idx == len(args) - 1:
        return default
    return args[idx + 1]


def load_human_games(players_path: Path, games_path: Path) -> pd.DataFrame:
    players = pd.read_csv(
        players_path,
        usecols=["player_id", "name", "is_bot", "is_sus"],
    ).rename(columns={"name": "player_name"})

    games = pd.read_csv(
        games_path,
        usecols=[
            "hash_id",
            "date",
            "year",
            "player_id_black",
            "player_id_white",
            "opening",
            "komi",
            "result",
            "language_black",
            "language_white",
        ],
    ).rename(columns={"hash_id": "game_key"})

    games["game_date"] = pd.to_datetime(games["date"], errors="coerce")
    games = games.loc[games["game_date"].notna()].copy()
    games["year"] = games["game_date"].dt.year.astype(int)
    games["year_month"] = games["game_date"].dt.strftime("%Y-%m")
    games["month_index"] = games["year_month"].map(month_index_from_ym).astype(int)
    games["opening_moves"] = games["opening"].fillna("").map(
        lambda x: [tok for tok in str(x).split(";") if tok][:50]
    )
    games["opening_len"] = games["opening_moves"].map(len)

    player_meta = players.set_index("player_id")[["is_bot", "is_sus"]]
    for side in ("black", "white"):
        pid_col = f"player_id_{side}"
        games[f"{side}_is_bot"] = games[pid_col].map(player_meta["is_bot"])
        games[f"{side}_is_sus"] = games[pid_col].map(player_meta["is_sus"])

    games = games.loc[
        (games["game_date"] >= pd.Timestamp("1950-01-01"))
        & (games["game_date"] <= pd.Timestamp("2021-10-31"))
        & (games["opening_len"] >= 35)
    ].copy()
    return games.sort_values(["game_date", "game_key"]).reset_index(drop=True)


def apply_human_filter(games: pd.DataFrame, filt: HumanFilter) -> pd.DataFrame:
    work = games.copy()
    if filt.name == "komi_known":
        work = work.loc[work["komi"].notna()].copy()
    elif filt.name == "komi_positive":
        work = work.loc[pd.to_numeric(work["komi"], errors="coerce").fillna(-1) > 0].copy()
    elif filt.name == "result_known":
        work = work.loc[work["result"].fillna("?") != "?"].copy()
    elif filt.name == "komi_known_result_known":
        work = work.loc[work["komi"].notna() & (work["result"].fillna("?") != "?")].copy()
    elif filt.name != "all":
        raise ValueError(f"Unknown filter: {filt.name}")
    return work.sort_values(["game_date", "game_key"]).reset_index(drop=True)


def load_ai_games(sim_ai_path: Path) -> pd.DataFrame:
    sim = pyreadr.read_r(str(sim_ai_path))["simulated_ai_move_data"].copy()
    sim["move_number"] = pd.to_numeric(sim["move_number"], errors="coerce")
    sim = sim.loc[sim["move_number"].notna()].copy()
    sim["move_number"] = sim["move_number"].astype(int)
    sim = sim.loc[(sim["move_number"] >= 1) & (sim["move_number"] <= 50)].copy()
    sim = sim.sort_values(["file_name", "move_number"])

    grouped = (
        sim.groupby("file_name")
        .agg(opening_moves=("move_choice", list), komi=("komi", "first"))
        .reset_index()
        .rename(columns={"file_name": "game_key"})
    )
    grouped["opening_len"] = grouped["opening_moves"].map(len)
    grouped = grouped.loc[grouped["opening_len"] >= 35].copy()
    return grouped.sort_values("game_key").reset_index(drop=True)


def compute_prefix_novelty_rows(
    games: pd.DataFrame,
    base_prefixes: set[str] | None = None,
) -> tuple[pd.DataFrame, set[str]]:
    seen = set() if base_prefixes is None else set(base_prefixes)
    rows: list[dict[str, object]] = []

    for rec in games.itertuples(index=False):
        prefix_parts: list[str] = []
        game_prefixes: list[str] = []
        novel_move_number: int | None = None

        for idx, move in enumerate(rec.opening_moves, start=1):
            prefix_parts.append(move)
            key = ";".join(prefix_parts)
            game_prefixes.append(key)
            if novel_move_number is None and key not in seen:
                novel_move_number = idx

        seen.update(game_prefixes)
        if novel_move_number is None:
            continue

        player_id = rec.player_id_black if novel_move_number % 2 == 1 else rec.player_id_white
        rows.append(
            {
                "game_key": rec.game_key,
                "game_date": rec.game_date,
                "year": str(rec.year),
                "year_month": rec.year_month,
                "month_index": int(rec.month_index),
                "player_id": str(player_id),
                "novel_move_number": int(novel_move_number),
                "novelty_index": int(60 - novel_move_number),
            }
        )

    return pd.DataFrame(rows), seen


def build_ai_prefix_library(ai_games: pd.DataFrame) -> set[str]:
    seen: set[str] = set()
    for moves in ai_games["opening_moves"]:
        prefix_parts: list[str] = []
        for move in moves:
            prefix_parts.append(move)
            seen.add(";".join(prefix_parts))
    return seen


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


def fit_yearly_novelty_fe(rows: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        rows.groupby(["player_id", "year"], as_index=False)["novelty_index"]
        .median()
        .rename(columns={"novelty_index": "median_novelty"})
    )
    grouped["year_num"] = grouped["year"].astype(int)
    fe = fit_panel_numeric(grouped, "player_id", "year_num", "year", "median_novelty", "1950")
    fe["year"] = fe["label"].astype(int)
    return fe[["year", "fe", "fe_ci_ll", "fe_ci_ul"]].sort_values("year").reset_index(drop=True)


def fit_monthly_novelty_fe(rows: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        rows.groupby(["player_id", "year_month", "month_index"], as_index=False)["novelty_index"]
        .median()
        .rename(columns={"novelty_index": "median_novelty"})
    )
    grouped["month_label"] = grouped["month_index"].astype(str)
    fe = fit_panel_numeric(grouped, "player_id", "month_index", "month_label", "median_novelty", "1")
    fe["month_index"] = fe["label"].astype(int)
    return fe[["month_index", "fe", "fe_ci_ll", "fe_ci_ul"]].sort_values("month_index").reset_index(drop=True)


def compare_fe(reconstructed: pd.DataFrame, released: pd.DataFrame, key: str) -> dict[str, float | int]:
    merged = reconstructed.merge(released, on=key, suffixes=("_recon", "_released"))
    if merged.empty:
        return {"n_overlap": 0}
    return {
        "n_overlap": int(len(merged)),
        "corr": float(merged["fe_recon"].corr(merged["fe_released"])),
        "mae": float((merged["fe_recon"] - merged["fe_released"]).abs().mean()),
        "max_abs_err": float((merged["fe_recon"] - merged["fe_released"]).abs().max()),
    }


def compare_counts(candidate: pd.DataFrame, osf_counts: pd.Series) -> dict[str, float]:
    year_counts = candidate.groupby("year").size().reindex(osf_counts.index, fill_value=0)
    diff = year_counts - osf_counts
    return {
        "game_count_mae": float(diff.abs().mean()),
        "game_count_max_abs_err": float(diff.abs().max()),
        "game_count_corr": float(year_counts.corr(osf_counts)),
    }


def choose_best_filter(score_rows: list[dict[str, object]]) -> dict[str, object]:
    def score(row: dict[str, object]) -> tuple[float, float, float, float]:
        return (
            float(row["yearly_corr"]),
            float(row["monthly_corr"]),
            -float(row["yearly_mae"]),
            -float(row["monthly_mae"]),
        )

    return sorted(score_rows, key=score, reverse=True)[0]


def compute_fig_s1(human_games: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    human_games = human_games.copy()
    human_games["prefix8"] = human_games["opening_moves"].map(lambda x: ";".join(x[:8]))
    for cutoff in range(2000, 2011):
        baseline = set(human_games.loc[human_games["year"] <= cutoff, "prefix8"])
        future = human_games.loc[human_games["year"] >= cutoff + 1, ["year", "prefix8"]].copy()
        future["is_novel_strategy"] = ~future["prefix8"].isin(baseline)
        yearly = future.groupby("year", as_index=False)["is_novel_strategy"].mean()
        yearly["cutoff_year"] = cutoff
        yearly["novel_strategy_pct"] = yearly["is_novel_strategy"] * 100.0
        rows.append(yearly[["cutoff_year", "year", "novel_strategy_pct"]])
    return pd.concat(rows, ignore_index=True)


def plot_fig_s1(df: pd.DataFrame, outpath: Path) -> None:
    fig, ax = plt.subplots(figsize=(10.5, 6.0))
    cmap = plt.get_cmap("plasma", 11)
    for idx, cutoff in enumerate(sorted(df["cutoff_year"].unique())):
        sub = df.loc[df["cutoff_year"] == cutoff].sort_values("year")
        ax.plot(
            sub["year"],
            sub["novel_strategy_pct"],
            color=cmap(idx),
            linewidth=2.0,
            label=f"1950-{cutoff}",
        )

    ax.axvspan(decimal_year(ALPHAGO_DATE), 2021.83, color=ORANGE, alpha=0.25)
    ax.axvline(decimal_year(ALPHAGO_DATE), color="red", linestyle="--", linewidth=1.0)
    ax.set_xlim(2001, 2021.9)
    ax.set_ylim(35, 100)
    ax.set_xticks([2001, 2005, 2010, 2015, 2021])
    ax.set_yticks([40, 50, 60, 70, 80, 90, 100])
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="lower right", fontsize=8, ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(outpath, dpi=220)
    plt.close(fig)


def plot_fe_panel(
    ax: plt.Axes,
    df: pd.DataFrame,
    xcol: str,
    last_date: pd.Timestamp,
    monthly: bool,
) -> None:
    ax.axhline(0, color=GRAY, linewidth=1.0, linestyle=(0, (2, 5)))
    if monthly:
        alpha_start = month_index_from_ym("2016-03")
        alpha_end = int(df[xcol].max())
        ax.axvspan(alpha_start, alpha_end, color=ORANGE, alpha=0.25)
        ax.axvline(alpha_start, color="red", linestyle="--", linewidth=0.9)
        xticks = [1] + [month_index_from_ym(f"{y}-01") for y in range(1960, 2020, 10)] + [int(df[xcol].max())]
        xlabels = ["1950\n(Jan)"] + [f"{y}\n(Jan)" for y in range(1960, 2020, 10)] + ["2021\n(Oct)"]
        ax.set_xlim(-10, int(df[xcol].max()) + 20)
        ax.tick_params(axis="x", labelsize=9)
    else:
        alpha_start = decimal_year(ALPHAGO_DATE)
        alpha_end = decimal_year(last_date)
        ax.axvspan(alpha_start, alpha_end, color=ORANGE, alpha=0.25)
        ax.axvline(alpha_start, color="red", linestyle="--", linewidth=0.9)
        xticks = [1950] + list(range(1960, 2020, 10)) + [decimal_year(last_date)]
        xlabels = ["1950"] + [str(y) for y in range(1960, 2020, 10)] + ["2021\n(Oct)"]
        ax.set_xlim(1948, 2022.2)
        ax.tick_params(axis="x", labelsize=10)

    ax.errorbar(
        df[xcol],
        df["fe"],
        yerr=[df["fe"] - df["fe_ci_ll"], df["fe_ci_ul"] - df["fe"]],
        fmt="o",
        color=GREEN,
        ecolor=GREEN,
        elinewidth=0.8 if monthly else 1.1,
        markersize=1.6 if monthly else 3.8,
        capsize=0,
    )
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels)
    ax.set_ylabel("")
    ax.set_xlabel("")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_fig_s6(yearly: pd.DataFrame, monthly: pd.DataFrame, outpath: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 8.5), height_ratios=[1, 1.05])
    last_date = pd.Timestamp("2021-10-31")
    plot_fe_panel(axes[0], yearly, "year", last_date, monthly=False)
    plot_fe_panel(axes[1], monthly, "month_index", last_date, monthly=True)
    yearly_min = float(yearly["fe_ci_ll"].min())
    yearly_max = float(yearly["fe_ci_ul"].max())
    monthly_min = float(monthly["fe_ci_ll"].min())
    monthly_max = float(monthly["fe_ci_ul"].max())
    axes[0].set_ylim(yearly_min - 0.4, yearly_max + 0.4)
    axes[1].set_ylim(monthly_min - 0.4, monthly_max + 0.4)
    fig.tight_layout()
    fig.savefig(outpath, dpi=220)
    plt.close(fig)


def main() -> None:
    args = sys.argv[1:]
    project_root = Path(get_arg_value(args, "--project-root", str(ROOT))).resolve()
    output_dir = Path(
        get_arg_value(
            args,
            "--output-dir",
            str(project_root / "outputs" / "supplement_sequence_reconstruction"),
        )
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    human_games_all = load_human_games(
        project_root / "public_refs/go_learning_eras/data/players.csv",
        project_root / "public_refs/go_learning_eras/data/games.csv",
    )
    ai_games = load_ai_games(project_root / "osf/shin et al 2023 simulated ai move data v001.RData")

    released_yearly = pd.read_csv(project_root / "outputs/original_r_full/fig1_panel_c_yearly.csv")
    released_monthly = pd.read_csv(project_root / "outputs/original_r_full/fig1_panel_d_monthly.csv")
    osf_unique = pyreadr.read_r(str(project_root / "osf/shin et al 2023 data v001.RData"))["dt"][
        ["game_id", "game_date"]
    ].drop_duplicates()
    osf_unique["game_date"] = pd.to_datetime(osf_unique["game_date"], errors="coerce")
    osf_unique = osf_unique.loc[osf_unique["game_date"].notna()].copy()
    osf_unique["year"] = osf_unique["game_date"].dt.year.astype(int)
    osf_counts = osf_unique.groupby("year").size()

    score_rows: list[dict[str, object]] = []
    per_filter_outputs: dict[str, dict[str, pd.DataFrame]] = {}

    for filt in FILTERS:
        candidate = apply_human_filter(human_games_all, filt)
        human_only_rows, _ = compute_prefix_novelty_rows(candidate)
        yearly_fe = fit_yearly_novelty_fe(human_only_rows)
        monthly_fe = fit_monthly_novelty_fe(human_only_rows)
        yearly_cmp = compare_fe(yearly_fe, released_yearly, "year")
        monthly_cmp = compare_fe(monthly_fe, released_monthly, "month_index")
        count_cmp = compare_counts(candidate, osf_counts)

        row = {
            "filter": filt.name,
            "description": filt.description,
            "n_games": int(len(candidate)),
            "n_players_with_novel_rows": int(human_only_rows["player_id"].nunique()),
            "yearly_corr": yearly_cmp.get("corr", float("nan")),
            "yearly_mae": yearly_cmp.get("mae", float("nan")),
            "monthly_corr": monthly_cmp.get("corr", float("nan")),
            "monthly_mae": monthly_cmp.get("mae", float("nan")),
            "count_corr": count_cmp["game_count_corr"],
            "count_mae": count_cmp["game_count_mae"],
        }
        score_rows.append(row)
        per_filter_outputs[filt.name] = {
            "candidate": candidate,
            "human_only_rows": human_only_rows,
            "yearly_fe": yearly_fe,
            "monthly_fe": monthly_fe,
        }

    best = choose_best_filter(score_rows)
    best_name = str(best["filter"])
    best_candidate = per_filter_outputs[best_name]["candidate"]
    best_human_rows = per_filter_outputs[best_name]["human_only_rows"]
    best_yearly_fe = per_filter_outputs[best_name]["yearly_fe"]
    best_monthly_fe = per_filter_outputs[best_name]["monthly_fe"]

    ai_prefixes = build_ai_prefix_library(ai_games)
    with_ai_rows, _ = compute_prefix_novelty_rows(best_candidate, base_prefixes=ai_prefixes)
    with_ai_yearly_fe = fit_yearly_novelty_fe(with_ai_rows)
    with_ai_monthly_fe = fit_monthly_novelty_fe(with_ai_rows)
    fig_s1 = compute_fig_s1(best_candidate)

    pd.DataFrame(score_rows).sort_values(
        ["yearly_corr", "monthly_corr", "count_corr"], ascending=[False, False, False]
    ).to_csv(output_dir / "filter_search_scores.csv", index=False)
    best_candidate.groupby("year").size().rename("n_games").reset_index().to_csv(
        output_dir / "best_filter_year_counts.csv",
        index=False,
    )
    best_human_rows.to_csv(output_dir / "human_only_novelty_rows.csv", index=False)
    best_yearly_fe.to_csv(output_dir / "fig1c_reconstructed_yearly.csv", index=False)
    best_monthly_fe.to_csv(output_dir / "fig1d_reconstructed_monthly.csv", index=False)
    with_ai_rows.to_csv(output_dir / "fig_s6_novelty_rows_with_ai.csv", index=False)
    with_ai_yearly_fe.to_csv(output_dir / "fig_s6_panel_a_yearly.csv", index=False)
    with_ai_monthly_fe.to_csv(output_dir / "fig_s6_panel_b_monthly.csv", index=False)
    fig_s1.to_csv(output_dir / "fig_s1_novel_strategy_pct.csv", index=False)

    plot_fig_s1(fig_s1, output_dir / "fig_s1_novel_strategy_pct.png")
    plot_fig_s6(with_ai_yearly_fe, with_ai_monthly_fe, output_dir / "fig_s6_with_ai.png")

    summary = {
        "selected_filter": best,
        "candidate_scores": score_rows,
        "human_only_validation": {
            "yearly_vs_released": compare_fe(best_yearly_fe, released_yearly, "year"),
            "monthly_vs_released": compare_fe(best_monthly_fe, released_monthly, "month_index"),
        },
        "ai_library": {
            "n_ai_games": int(len(ai_games)),
            "n_ai_prefixes": int(len(ai_prefixes)),
        },
        "human_corpus": {
            "selected_games": int(len(best_candidate)),
            "selected_year_range": [int(best_candidate["year"].min()), int(best_candidate["year"].max())],
            "selected_game_count_2021": int((best_candidate["year"] == 2021).sum()),
        },
        "with_ai_vs_human_only": {
            "yearly": compare_fe(
                with_ai_yearly_fe.rename(columns={"fe": "fe"}),
                best_yearly_fe.rename(columns={"fe": "fe"}),
                "year",
            ),
            "monthly": compare_fe(
                with_ai_monthly_fe.rename(columns={"fe": "fe"}),
                best_monthly_fe.rename(columns={"fe": "fe"}),
                "month_index",
            ),
        },
        "notes": [
            "Human novelty was reconstructed from GoGoD-derived first-50-move openings in go-learning-eras.",
            "Fig. S6 was computed by seeding the novelty prefix library with all released simulated AI games as a static prior set.",
            "This closes the sequence-based supplement figures as a reconstruction, but it does not solve the separate move-1 DQI provenance gap.",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
