#!/usr/bin/env python3
"""Build a proxy extension of the Shin et al. yearly chart through 2026.

This script does two separate jobs:
1. Reproduce the exact 1950-2021 yearly fixed-effects series from OSF.
2. Extend the yearly series with a public-data proxy that learns
   first-50-move game-level DQI medians from overlapping GoGoD-derived data
   and recent SGFs exposed by gotoeveryone.k2ss.info.

The extension is explicitly approximate. The goal is to keep the original
historical series exact while using the best public continuation source that
can be validated against overlap years.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyreadr
import requests
from requests.adapters import HTTPAdapter, Retry
from sgfmill import sgf
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, r2_score

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replicate_shin_panel_ab import ALPHAGO_DATE, decimal_year, fit_time_effects

GREEN = "#69AA45"
ORANGE = "#D9B25A"
GRAY = "#8E8E8E"
GTE_BASE = "https://gotoeveryone.k2ss.info"


@dataclass
class ProxyArtifacts:
    actual_60: pd.DataFrame
    actual_50: pd.DataFrame
    extended_50: pd.DataFrame
    extended_60_proxy: pd.DataFrame
    calibration: tuple[float, float]
    validation: dict[str, float]
    bridge_summary: dict[str, int | float]


def month_iter(start: str, end: str) -> Iterator[str]:
    for period in pd.period_range(start=start, end=end, freq="M"):
        yield period.strftime("%Y/%m")


def normalise_name(name: str) -> str:
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    text = re.sub(r"[·•]", " ", text)
    return text


def load_osf_dt(path: Path) -> pd.DataFrame:
    dt = pyreadr.read_r(str(path))["dt"].copy()
    dt["game_date"] = pd.to_datetime(dt["game_date"], errors="coerce")
    dt["move_number"] = pd.to_numeric(dt["move_number"], errors="coerce")
    dt["dqi"] = pd.to_numeric(dt["dqi"], errors="coerce")
    dt["player_id"] = pd.to_numeric(dt["player_id"], errors="coerce")
    dt["opponent_id"] = pd.to_numeric(dt["opponent_id"], errors="coerce")
    dt = dt.loc[
        dt["game_date"].notna()
        & dt["move_number"].notna()
        & dt["dqi"].notna()
        & dt["player_id"].notna()
    ].copy()
    dt["player_id"] = dt["player_id"].astype(int)
    dt["opponent_id"] = dt["opponent_id"].astype("Int64")
    dt["year"] = dt["game_date"].dt.year.astype(str)
    dt["year_month"] = dt["game_date"].dt.strftime("%Y-%m")
    return dt


def compute_yearly_fe_from_move_rows(dt: pd.DataFrame, move_cap: int | None = None) -> pd.DataFrame:
    work = dt.copy()
    if move_cap is not None:
        work = work.loc[(work["move_number"] >= 1) & (work["move_number"] <= move_cap)].copy()
    grouped = (
        work.groupby(["player_id", "year"], as_index=False)["dqi"]
        .median()
        .rename(columns={"dqi": "median_dqi"})
    )
    fe = fit_time_effects(grouped, "player_id", "year", "median_dqi", "1950")
    fe["year"] = fe["label"].astype(int)
    return fe.sort_values("year").reset_index(drop=True)


def compute_yearly_fe_from_game_player_rows(rows: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        rows.groupby(["player_id", "year"], as_index=False)["pred_game_player_median_dqi50"]
        .median()
        .rename(columns={"pred_game_player_median_dqi50": "median_dqi"})
    )
    fe = fit_time_effects(grouped, "player_id", "year", "median_dqi", "1950")
    fe["year"] = fe["label"].astype(int)
    return fe.sort_values("year").reset_index(drop=True)


def plot_yearly_extension(coeffs: pd.DataFrame, last_date: pd.Timestamp, outpath: Path) -> None:
    coeffs = coeffs.copy().sort_values("year")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axhline(0, color=GRAY, linewidth=1.0, linestyle=(0, (2, 5)))
    ax.axvspan(decimal_year(ALPHAGO_DATE), decimal_year(last_date), alpha=0.55, color=ORANGE)
    ax.errorbar(
        coeffs["year"],
        coeffs["fe"],
        yerr=[coeffs["fe"] - coeffs["fe_ci_ll"], coeffs["fe_ci_ul"] - coeffs["fe"]],
        fmt="o",
        color=GREEN,
        ecolor=GREEN,
        elinewidth=1.25,
        markersize=4.5,
        capsize=0,
    )

    last_label = f"{last_date.year}\n({last_date.strftime('%b')})"
    xticks = [1950] + list(range(1960, 2020, 10)) + [decimal_year(last_date)]
    xlabels = ["1950"] + [str(y) for y in range(1960, 2020, 10)] + [last_label]

    ax.set_xlim(1948, max(2027, last_date.year + 1))
    ax.set_ylim(-0.8, 1.2)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels)
    ax.set_yticks(np.arange(-0.8, 1.2001, 0.4))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#333333")
    ax.spines["left"].set_color("#333333")
    ax.tick_params(axis="both", labelsize=11, colors="#555555")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(outpath, dpi=220)
    plt.close(fig)


def load_gle_games(players_path: Path, games_path: Path) -> pd.DataFrame:
    players = pd.read_csv(players_path, usecols=["player_id", "name"])
    players["name"] = players["name"].map(normalise_name)
    name_map = players.set_index("player_id")["name"]

    games = pd.read_csv(
        games_path,
        usecols=["hash_id", "date", "player_id_black", "player_id_white", "opening", "komi", "result"],
    )
    games = games.rename(columns={"hash_id": "game_key"})
    games["game_date"] = pd.to_datetime(games["date"], errors="coerce")
    games = games.loc[games["game_date"].notna()].copy()
    games["year"] = games["game_date"].dt.year.astype(str)
    games["year_month"] = games["game_date"].dt.strftime("%Y-%m")
    games["black_name"] = games["player_id_black"].map(name_map)
    games["white_name"] = games["player_id_white"].map(name_map)
    games["opening_moves"] = games["opening"].fillna("").map(
        lambda x: [tok for tok in str(x).split(";") if tok][:50]
    )
    games["source"] = "gle"
    return games


def build_retry_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=4, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    return session


def fetch_gte_schedule_links(session: requests.Session, month: str) -> list[str]:
    url = f"{GTE_BASE}/json/schedules/{month}.json"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    links = []
    for day in resp.json():
        for item in day.get("items", []):
            link = item.get("link")
            if link:
                links.append(f"{GTE_BASE}{link}")
    return sorted(set(links))


def fetch_gte_kifu_links(session: requests.Session, news_url: str) -> list[str]:
    html = session.get(news_url, timeout=30).text
    links = re.findall(r'href="(/kifu/[^"]+)"', html)
    return sorted(set(f"{GTE_BASE}{x}" for x in links))


def parse_sgf_game(sgf_bytes: bytes, source_key: str) -> dict[str, object] | None:
    try:
        game = sgf.Sgf_game.from_bytes(sgf_bytes)
    except Exception:
        return None
    root = game.get_root()
    board_size = game.get_size()
    handicap = root.get("HA") if root.has_property("HA") else None
    if board_size != 19 or handicap not in (None, "", "0"):
        return None

    date = root.get("DT") or ""
    date = date[:10]
    try:
        game_date = pd.to_datetime(date, errors="raise")
    except Exception:
        return None

    pb = normalise_name(root.get("PB") or "")
    pw = normalise_name(root.get("PW") or "")
    if not pb or not pw:
        return None

    moves: list[str] = []
    for node in game.get_main_sequence()[1:]:
        color, move = node.get_move()
        if move is None:
            continue
        x, y = move
        coord = f"{chr(ord('a') + x)}{chr(ord('a') + y)}"
        moves.append(coord)
        if len(moves) >= 50:
            break

    if len(moves) < 20:
        return None

    return {
        "game_key": source_key,
        "source": "gte",
        "game_date": game_date,
        "year": str(game_date.year),
        "year_month": game_date.strftime("%Y-%m"),
        "black_name": pb,
        "white_name": pw,
        "komi": root.get("KM"),
        "result": root.get("RE"),
        "opening_moves": moves,
    }


def fetch_and_parse_gte_sgf(kifu_url: str) -> dict[str, object] | None:
    try:
        resp = requests.get(kifu_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return parse_sgf_game(resp.content, source_key=kifu_url.rsplit("/", 1)[-1])
    except Exception:
        return None


def load_or_scrape_gte_games(cache_path: Path, start_month: str, end_month: str) -> pd.DataFrame:
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    session = build_retry_session()
    news_links: set[str] = set()
    kifu_links: set[str] = set()

    for month in month_iter(start_month, end_month):
        try:
            month_news_links = fetch_gte_schedule_links(session, month)
        except Exception:
            continue
        news_links.update(month_news_links)

    print(f"Collected {len(news_links)} gotoeveryone news pages", flush=True)
    for idx, news_url in enumerate(sorted(news_links), start=1):
        try:
            kifu_links.update(fetch_gte_kifu_links(session, news_url))
        except Exception:
            continue
        if idx % 25 == 0:
            print(f"Scanned {idx}/{len(news_links)} news pages", flush=True)

    print(f"Collected {len(kifu_links)} unique SGF links", flush=True)
    rows: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        for idx, row in enumerate(pool.map(fetch_and_parse_gte_sgf, sorted(kifu_links)), start=1):
            if row is not None:
                rows.append(row)
            if idx % 250 == 0:
                print(f"Fetched {idx}/{len(kifu_links)} SGFs", flush=True)

    gte = pd.DataFrame(rows).drop_duplicates(subset=["game_key"]).sort_values("game_date")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    gte.to_parquet(cache_path, index=False)
    return gte


def build_bridge_crosswalk(osf_dt: pd.DataFrame, gle_games: pd.DataFrame, min_games: int = 20, min_score: float = 0.99) -> pd.DataFrame:
    start = "2018-01"
    end = "2021-10"
    months = pd.period_range(start=start, end=end, freq="M").astype(str)

    osf_unique = osf_dt[["game_id", "game_date", "player_id"]].drop_duplicates().copy()
    osf_unique["year_month"] = osf_unique["game_date"].dt.strftime("%Y-%m")
    osf_unique = osf_unique.loc[(osf_unique["year_month"] >= start) & (osf_unique["year_month"] <= end)]
    osf_pm = (
        osf_unique.groupby(["player_id", "year_month"])["game_id"]
        .nunique()
        .unstack(fill_value=0)
        .reindex(columns=months, fill_value=0)
    )
    osf_pm = osf_pm.loc[osf_pm.sum(axis=1) >= min_games]

    gle_slice = gle_games.loc[(gle_games["year_month"] >= start) & (gle_games["year_month"] <= end)].copy()
    long = pd.concat(
        [
            gle_slice[["player_id_black", "year_month"]].rename(columns={"player_id_black": "gle_player_id"}),
            gle_slice[["player_id_white", "year_month"]].rename(columns={"player_id_white": "gle_player_id"}),
        ],
        ignore_index=True,
    )
    gle_pm = (
        long.groupby(["gle_player_id", "year_month"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=months, fill_value=0)
    )
    gle_pm = gle_pm.loc[gle_pm.sum(axis=1) >= min_games]

    a = gle_pm.to_numpy(dtype=float)
    b = osf_pm.to_numpy(dtype=float)
    a_norm = np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = np.linalg.norm(b, axis=1, keepdims=True)
    sim = (a @ b.T) / np.clip(a_norm, 1e-12, None) / np.clip(b_norm.T, 1e-12, None)

    gle_best_idx = sim.argmax(axis=1)
    gle_best_score = sim.max(axis=1)
    osf_best_idx = sim.argmax(axis=0)

    rows = []
    for gle_idx, gle_player_id in enumerate(gle_pm.index):
        osf_idx = gle_best_idx[gle_idx]
        score = float(gle_best_score[gle_idx])
        if osf_best_idx[osf_idx] == gle_idx and score >= min_score:
            rows.append(
                {
                    "gle_player_id": gle_player_id,
                    "osf_player_id": int(osf_pm.index[osf_idx]),
                    "score": score,
                    "gle_games_2018_2021": int(gle_pm.iloc[gle_idx].sum()),
                    "osf_games_2018_2021": int(osf_pm.iloc[osf_idx].sum()),
                }
            )
    return pd.DataFrame(rows).sort_values(["score", "gle_games_2018_2021"], ascending=[False, False])


def match_gle_games_to_osf(osf_dt: pd.DataFrame, gle_games: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    cross = dict(zip(crosswalk["gle_player_id"], crosswalk["osf_player_id"]))
    gle = gle_games.copy()
    gle["osf_black"] = gle["player_id_black"].map(cross)
    gle["osf_white"] = gle["player_id_white"].map(cross)
    gle = gle.loc[gle["osf_black"].notna() & gle["osf_white"].notna()].copy()
    gle["osf_black"] = gle["osf_black"].astype(int)
    gle["osf_white"] = gle["osf_white"].astype(int)
    gle["min_pid"] = gle[["osf_black", "osf_white"]].min(axis=1)
    gle["max_pid"] = gle[["osf_black", "osf_white"]].max(axis=1)
    gle["date"] = gle["game_date"].dt.strftime("%Y-%m-%d")

    osf_game_pairs = (
        osf_dt[["game_id", "game_date", "player_id"]]
        .drop_duplicates()
        .assign(date=lambda x: x["game_date"].dt.strftime("%Y-%m-%d"))
        .groupby("game_id")
        .agg(date=("date", "first"), min_pid=("player_id", "min"), max_pid=("player_id", "max"))
        .reset_index()
    )
    return gle.merge(osf_game_pairs, on=["date", "min_pid", "max_pid"], how="inner")


def perspective_doc(moves: list[str], player_is_black: bool, self_token: str | None = None, opp_token: str | None = None) -> str:
    tokens: list[str] = []
    for idx, move in enumerate(moves[:50], start=1):
        rel = "P" if (idx % 2 == 1) == player_is_black else "O"
        tokens.append(f"n{idx}_{rel}_{move}")
        tokens.append(f"{rel}_{move}")
    if self_token:
        tokens.append(f"SELF_{self_token}")
    if opp_token:
        tokens.append(f"OPP_{opp_token}")
    return " ".join(tokens)


def build_training_rows(matched_games: pd.DataFrame, osf_dt: pd.DataFrame) -> pd.DataFrame:
    dt50 = osf_dt.loc[(osf_dt["move_number"] >= 1) & (osf_dt["move_number"] <= 50)].copy()
    targets = (
        dt50.groupby(["game_id", "player_id"], as_index=False)["dqi"]
        .median()
        .rename(columns={"dqi": "target_game_player_median_dqi50"})
    )

    black_rows = matched_games[
        ["game_key", "game_id", "game_date", "year", "player_id_black", "player_id_white", "opening_moves", "osf_black"]
    ].copy()
    black_rows["player_id"] = black_rows["osf_black"]
    black_rows["gle_player_id"] = black_rows["player_id_black"]
    black_rows["gle_opp_id"] = black_rows["player_id_white"]
    black_rows["doc"] = [
        perspective_doc(moves, True, self_token=pid, opp_token=opp)
        for moves, pid, opp in zip(
            black_rows["opening_moves"], black_rows["player_id_black"], black_rows["player_id_white"]
        )
    ]

    white_rows = matched_games[
        ["game_key", "game_id", "game_date", "year", "player_id_black", "player_id_white", "opening_moves", "osf_white"]
    ].copy()
    white_rows["player_id"] = white_rows["osf_white"]
    white_rows["gle_player_id"] = white_rows["player_id_white"]
    white_rows["gle_opp_id"] = white_rows["player_id_black"]
    white_rows["doc"] = [
        perspective_doc(moves, False, self_token=pid, opp_token=opp)
        for moves, pid, opp in zip(
            white_rows["opening_moves"], white_rows["player_id_white"], white_rows["player_id_black"]
        )
    ]

    rows = pd.concat([black_rows, white_rows], ignore_index=True)
    rows = rows.merge(targets, on=["game_id", "player_id"], how="inner")
    rows = rows.drop(columns=["osf_black", "osf_white"], errors="ignore")
    return rows


def fit_proxy(train_rows: pd.DataFrame, valid_rows: pd.DataFrame) -> tuple[TfidfVectorizer, Ridge, dict[str, float]]:
    vectorizer = TfidfVectorizer(
        analyzer="word",
        token_pattern=r"[^ ]+",
        lowercase=False,
        ngram_range=(1, 3),
        min_df=2,
        max_features=250_000,
    )
    x_train = vectorizer.fit_transform(train_rows["doc"])
    x_valid = vectorizer.transform(valid_rows["doc"])

    model = Ridge(alpha=2.0)
    model.fit(x_train, train_rows["target_game_player_median_dqi50"])
    valid_pred = model.predict(x_valid)
    metrics = {
        "row_mae": float(mean_absolute_error(valid_rows["target_game_player_median_dqi50"], valid_pred)),
        "row_r2": float(r2_score(valid_rows["target_game_player_median_dqi50"], valid_pred)),
    }

    valid_eval = valid_rows[["year", "player_id", "target_game_player_median_dqi50"]].copy()
    valid_eval["pred"] = valid_pred
    actual_py = (
        valid_eval.groupby(["player_id", "year"], as_index=False)["target_game_player_median_dqi50"]
        .median()
        .rename(columns={"target_game_player_median_dqi50": "actual"})
    )
    pred_py = (
        valid_eval.groupby(["player_id", "year"], as_index=False)["pred"]
        .median()
        .rename(columns={"pred": "pred"})
    )
    merged = actual_py.merge(pred_py, on=["player_id", "year"], how="inner")
    metrics["player_year_corr"] = float(merged["actual"].corr(merged["pred"]))
    metrics["player_year_mae"] = float(mean_absolute_error(merged["actual"], merged["pred"]))
    return vectorizer, model, metrics


def assign_extension_player_ids(
    rows: pd.DataFrame,
    crosswalk: pd.DataFrame,
    gle_players: pd.DataFrame,
) -> pd.DataFrame:
    rows = rows.copy()
    cross = dict(zip(crosswalk["gle_player_id"], crosswalk["osf_player_id"]))
    name_to_gle = {normalise_name(n): pid for pid, n in zip(gle_players["player_id"], gle_players["name"])}

    def map_side(source: str, gle_id: str | None, name: str | None) -> str:
        if source == "gle" and gle_id in cross:
            return str(cross[gle_id])
        if source == "gle" and gle_id:
            return f"gle::{gle_id}"
        norm = normalise_name(name or "")
        gle_id2 = name_to_gle.get(norm)
        if gle_id2 in cross:
            return str(cross[gle_id2])
        if gle_id2:
            return f"gle::{gle_id2}"
        return f"gte::{norm}"

    rows["black_pid_final"] = [
        map_side(src, gle_id, name)
        for src, gle_id, name in zip(rows["source"], rows.get("player_id_black"), rows["black_name"])
    ]
    rows["white_pid_final"] = [
        map_side(src, gle_id, name)
        for src, gle_id, name in zip(rows["source"], rows.get("player_id_white"), rows["white_name"])
    ]
    return rows


def build_extension_prediction_rows(games: pd.DataFrame) -> pd.DataFrame:
    black = games[
        ["source", "game_key", "game_date", "year", "black_name", "white_name", "opening_moves", "black_pid_final", "white_pid_final"]
    ].copy()
    black["player_id"] = black["black_pid_final"]
    black["doc"] = [
        perspective_doc(moves, True, self_token=self_token, opp_token=opp_token)
        for moves, self_token, opp_token in zip(black["opening_moves"], black["black_pid_final"], black["white_pid_final"])
    ]

    white = games[
        ["source", "game_key", "game_date", "year", "black_name", "white_name", "opening_moves", "black_pid_final", "white_pid_final"]
    ].copy()
    white["player_id"] = white["white_pid_final"]
    white["doc"] = [
        perspective_doc(moves, False, self_token=self_token, opp_token=opp_token)
        for moves, self_token, opp_token in zip(white["opening_moves"], white["white_pid_final"], white["black_pid_final"])
    ]

    return pd.concat([black, white], ignore_index=True)


def calibrate_to_full_scale(actual_50: pd.DataFrame, actual_60: pd.DataFrame) -> tuple[float, float]:
    merged = actual_50[["year", "fe"]].merge(actual_60[["year", "fe"]], on="year", suffixes=("_50", "_60"))
    reg = LinearRegression().fit(merged[["fe_50"]], merged["fe_60"])
    return float(reg.intercept_), float(reg.coef_[0])


def apply_calibration(coeffs_50: pd.DataFrame, intercept: float, slope: float) -> pd.DataFrame:
    coeffs = coeffs_50.copy()
    for col in ["fe", "fe_ci_ll", "fe_ci_ul"]:
        coeffs[col] = intercept + slope * coeffs[col]
    return coeffs


def build_artifacts(
    osf_dt: pd.DataFrame,
    gle_games: pd.DataFrame,
    gte_games: pd.DataFrame,
    gle_players: pd.DataFrame,
) -> ProxyArtifacts:
    actual_60 = compute_yearly_fe_from_move_rows(osf_dt, move_cap=None)
    actual_50 = compute_yearly_fe_from_move_rows(osf_dt, move_cap=50)

    crosswalk = build_bridge_crosswalk(osf_dt, gle_games)
    matched_games = match_gle_games_to_osf(osf_dt, gle_games, crosswalk)
    training_rows = build_training_rows(matched_games, osf_dt)

    train_rows = training_rows.loc[training_rows["year"].astype(int) <= 2017].copy()
    valid_rows = training_rows.loc[training_rows["year"].astype(int) >= 2018].copy()
    vectorizer, model, validation = fit_proxy(train_rows, valid_rows)

    all_train_x = vectorizer.fit_transform(training_rows["doc"])
    model.fit(all_train_x, training_rows["target_game_player_median_dqi50"])

    gle_ext = gle_games.loc[gle_games["game_date"] > pd.Timestamp("2021-10-31")].copy()
    recent_games = pd.concat([gle_ext, gte_games], ignore_index=True)
    recent_games = assign_extension_player_ids(recent_games, crosswalk, gle_players)
    pred_rows = build_extension_prediction_rows(recent_games)
    pred_rows["pred_game_player_median_dqi50"] = model.predict(vectorizer.transform(pred_rows["doc"]))

    actual_game_player = (
        osf_dt.loc[(osf_dt["move_number"] >= 1) & (osf_dt["move_number"] <= 50)]
        .groupby(["game_id", "player_id", "year"], as_index=False)["dqi"]
        .median()
        .rename(columns={"dqi": "pred_game_player_median_dqi50"})
    )
    actual_game_player["player_id"] = actual_game_player["player_id"].astype(str)

    combined = pd.concat(
        [
            actual_game_player[["player_id", "year", "pred_game_player_median_dqi50"]],
            pred_rows[["player_id", "year", "pred_game_player_median_dqi50"]],
        ],
        ignore_index=True,
    )
    extended_50 = compute_yearly_fe_from_game_player_rows(combined)

    intercept, slope = calibrate_to_full_scale(actual_50, actual_60)
    extended_60_proxy = apply_calibration(extended_50, intercept, slope)

    bridge_summary = {
        "crosswalk_rows": int(len(crosswalk)),
        "matched_games": int(matched_games["game_id"].nunique()),
        "matched_training_rows": int(len(training_rows)),
        "gle_extension_games": int(len(gle_ext)),
        "gte_extension_games": int(len(gte_games)),
        "pred_extension_rows": int(len(pred_rows)),
    }

    return ProxyArtifacts(
        actual_60=actual_60,
        actual_50=actual_50,
        extended_50=extended_50,
        extended_60_proxy=extended_60_proxy,
        calibration=(intercept, slope),
        validation=validation,
        bridge_summary=bridge_summary,
    )


def save_outputs(artifacts: ProxyArtifacts, outdir: Path, gte_games: pd.DataFrame) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    artifacts.actual_60.to_csv(outdir / "yearly_actual_60.csv", index=False)
    artifacts.actual_50.to_csv(outdir / "yearly_actual_50.csv", index=False)
    artifacts.extended_50.to_csv(outdir / "yearly_extended_proxy_50.csv", index=False)
    artifacts.extended_60_proxy.to_csv(outdir / "yearly_extended_proxy_on_60_scale.csv", index=False)

    summary = {
        "calibration_intercept": artifacts.calibration[0],
        "calibration_slope": artifacts.calibration[1],
        **artifacts.validation,
        **artifacts.bridge_summary,
    }
    (outdir / "proxy_summary.json").write_text(json.dumps(summary, indent=2))

    actual_2021 = artifacts.actual_60.loc[artifacts.actual_60["year"] <= 2021].copy()
    ext_only = artifacts.extended_60_proxy.loc[artifacts.extended_60_proxy["year"] >= 2022].copy()
    final_series = pd.concat([actual_2021, ext_only], ignore_index=True).sort_values("year")
    final_series.to_csv(outdir / "yearly_final_mixed_series.csv", index=False)
    last_date = pd.Timestamp(gte_games["game_date"].max()) if not gte_games.empty else pd.Timestamp("2024-07-09")
    plot_yearly_extension(final_series, last_date, outdir / "shin_yearly_extended_proxy.png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--osf-data", type=Path, default=Path("osf/shin et al 2023 data v001.RData"))
    parser.add_argument("--gle-games", type=Path, default=Path("public_refs/go_learning_eras/data/games.csv"))
    parser.add_argument("--gle-players", type=Path, default=Path("public_refs/go_learning_eras/data/players.csv"))
    parser.add_argument("--gte-cache", type=Path, default=Path("data/gte_games_2024_08_to_2026_04.parquet"))
    parser.add_argument("--gte-start", default="2024-08")
    parser.add_argument("--gte-end", default="2026-04")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/yearly_proxy_extension"))
    args = parser.parse_args()

    osf_dt = load_osf_dt(args.osf_data)
    gle_players = pd.read_csv(args.gle_players, usecols=["player_id", "name"])
    gle_players["name"] = gle_players["name"].map(normalise_name)
    gle_games = load_gle_games(args.gle_players, args.gle_games)
    gte_games = load_or_scrape_gte_games(args.gte_cache, args.gte_start, args.gte_end)

    artifacts = build_artifacts(osf_dt, gle_games, gte_games, gle_players)
    save_outputs(artifacts, args.output_dir, gte_games)
    print(f"Wrote proxy extension outputs to: {args.output_dir}")


if __name__ == "__main__":
    main()
