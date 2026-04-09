#!/usr/bin/env python3
"""Build a robust independent continuation of the Shin uplift chart.

Method:
- Historical foundation: exact OSF DQI rows for a frozen move window.
- Population: only players that can be crosswalked cleanly into GoGoD recent games.
- Recent continuation: fresh KataGo scoring on GoGoD 2021-2026 games.
- Known move-1 provenance issues are avoided by design by starting the move window at 2.

This is not presented as the authors' exact post-2021 series. It is an
independent continuation anchored historically on the released OSF DQI table
and checked against matched 2021 overlap rows, while remaining explicitly
paper-like rather than exact.
"""

from __future__ import annotations

import argparse
import atexit
import csv
import json
import math
import os
import re
import signal
import subprocess
import tempfile
import time
import traceback
import zipfile
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replicate_shin_panel_ab import ALPHAGO_DATE, decimal_year
from scripts.extend_shin_yearly_proxy import build_bridge_crosswalk, load_gle_games, load_osf_dt, normalise_name
from scripts.run_shin_supplement_gogod_direct_search import MOVE_PAT, parse_float, parse_iso_date, parse_prop
from scripts.validate_katago_dqi_sample import (
    KataGoAnalysis,
    perspective_winrate,
    select_best_move_info,
    sgf_coord_to_gtp,
)

GREEN = "#69AA45"
BLUE = "#2A6F9E"
ORANGE = "#D9B25A"
LIGHT_BLUE = "#C9DDF1"
GRAY = "#8E8E8E"
Z_975 = 1.959963984540054

RECENT_ZIP = ROOT / "data/private/2021-2026-Database-Jan2026.zip"
DEFAULT_PAPER_YEARLY = ROOT / "results/exact_replication/fig1_panel_a_yearly.csv"
DEFAULT_KATAGO_PATH = Path(os.environ.get("KATAGO_PATH", "katago"))
DEFAULT_KATAGO_CONFIG = Path(
    os.environ.get("KATAGO_CONFIG", str(ROOT / "data/private/katago/analysis_example.cfg"))
)
DEFAULT_KATAGO_MODEL = Path(
    os.environ.get("KATAGO_MODEL", str(ROOT / "data/private/katago/g170e-b20-model.bin.gz"))
)
WORKER_KATAGO: KataGoAnalysis | None = None


def build_recent_name_to_osf(players_path: Path, crosswalk: pd.DataFrame) -> dict[str, int]:
    players = pd.read_csv(players_path, usecols=["player_id", "name"])
    players["name_norm"] = players["name"].map(normalise_name)
    counts = players["name_norm"].value_counts()
    unique_names = counts[counts == 1].index
    gle_name_to_player = (
        players.loc[players["name_norm"].isin(unique_names), ["name_norm", "player_id"]]
        .drop_duplicates("name_norm")
        .set_index("name_norm")["player_id"]
        .to_dict()
    )
    gle_to_osf = dict(zip(crosswalk["gle_player_id"], crosswalk["osf_player_id"]))
    out: dict[str, int] = {}
    for name_norm, gle_player_id in gle_name_to_player.items():
        osf_player_id = gle_to_osf.get(gle_player_id)
        if osf_player_id is not None:
            out[name_norm] = int(osf_player_id)
    return out


def normalize_recent_rules(raw_rules: str | None, default_rules: str) -> str:
    text = (raw_rules or "").strip().lower()
    if not text:
        return default_rules
    if "chinese" in text or "ing" in text:
        return "chinese"
    if "japanese" in text:
        return "japanese"
    if "korean" in text:
        return "korean"
    if "aga" in text or "american" in text:
        return "aga"
    return default_rules


def round_half_up(value: float) -> float:
    scaled = value * 2.0
    if scaled >= 0:
        return math.floor(scaled + 0.5) / 2.0
    return math.ceil(scaled - 0.5) / 2.0


def normalize_komi_for_katago(komi: float) -> float:
    scaled = komi * 2.0
    if math.isclose(scaled, round(scaled), abs_tol=1e-9):
        return float(komi)
    return round_half_up(komi)


def record_rules_komi(rec: dict[str, object], default_rules: str) -> tuple[str, float]:
    rules_value = rec.get("katago_rules")
    if rules_value is None or (isinstance(rules_value, float) and math.isnan(rules_value)):
        rules = default_rules
    else:
        rules = str(rules_value)

    komi_value = rec.get("katago_komi", rec.get("komi"))
    if komi_value is None or (isinstance(komi_value, float) and math.isnan(komi_value)):
        raise RuntimeError(f"Missing komi for recent game {rec.get('game_key')}")
    komi = float(komi_value)
    return rules, komi


def parse_recent_games(
    zip_path: Path,
    cache_path: Path,
    name_to_osf: dict[str, int],
    move_end: int,
    min_date: pd.Timestamp,
    max_date: pd.Timestamp,
    default_rules: str,
    max_games: int | None = None,
) -> pd.DataFrame:
    if cache_path.exists():
        games = pd.read_csv(cache_path)
        required_cols = {"rules_raw", "katago_rules", "katago_komi", "katago_komi_adjusted"}
        if required_cols.issubset(games.columns):
            games["game_date"] = pd.to_datetime(games["game_date"], errors="coerce")
            return games

    rows: list[dict[str, object]] = []
    parsed = 0
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            if not member.endswith(".sgf"):
                continue
            text = zf.read(member).decode("utf-8", "ignore")

            size = parse_prop(text, "SZ")
            if size != "19":
                continue

            game_date = parse_iso_date(parse_prop(text, "DT"))
            if game_date is None or game_date < min_date or game_date > max_date:
                continue

            handicap = parse_float(parse_prop(text, "HA")) or 0.0
            if handicap != 0.0:
                continue

            komi = parse_float(parse_prop(text, "KM"))
            if komi is None:
                continue
            rules_raw = parse_prop(text, "RU")
            katago_rules = normalize_recent_rules(rules_raw, default_rules)
            katago_komi = normalize_komi_for_katago(float(komi))

            pb = parse_prop(text, "PB")
            pw = parse_prop(text, "PW")
            if not pb or not pw:
                continue

            black_name = normalise_name(pb)
            white_name = normalise_name(pw)
            osf_black = name_to_osf.get(black_name)
            osf_white = name_to_osf.get(white_name)
            if osf_black is None and osf_white is None:
                continue

            moves = [coord for _, coord in MOVE_PAT.findall(text)][:move_end]
            if len(moves) < move_end:
                continue

            stem = Path(member).stem
            row = {
                "game_key": stem,
                "archive_member": member,
                "game_date": game_date,
                "year": int(game_date.year),
                "black_name": black_name,
                "white_name": white_name,
                "osf_black": osf_black,
                "osf_white": osf_white,
                "komi": float(komi),
                "rules_raw": rules_raw,
                "katago_rules": katago_rules,
                "katago_komi": katago_komi,
                "katago_komi_adjusted": bool(not math.isclose(float(komi), katago_komi, abs_tol=1e-9)),
                "handicap": handicap,
            }
            for idx, move in enumerate(moves, start=1):
                row[f"move_{idx}"] = move
            rows.append(row)
            parsed += 1
            if max_games is not None and parsed >= max_games:
                break

    games = pd.DataFrame(rows).sort_values(["game_date", "game_key"]).reset_index(drop=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    games.to_csv(cache_path, index=False, quoting=csv.QUOTE_MINIMAL)
    return games


def build_historical_player_year_panel(
    osf_dt: pd.DataFrame,
    move_start: int,
    move_end: int,
    player_subset: set[int] | None = None,
) -> pd.DataFrame:
    hist = osf_dt.loc[osf_dt["move_number"].between(move_start, move_end)].copy()
    if player_subset is not None:
        hist = hist.loc[hist["player_id"].isin(player_subset)].copy()
    hist["year"] = hist["game_date"].dt.year.astype(int)
    return (
        hist.groupby(["player_id", "year"], as_index=False)["dqi"]
        .median()
        .rename(columns={"dqi": "median_dqi"})
        .sort_values(["player_id", "year"])
        .reset_index(drop=True)
    )


def build_osf_game_pairs(osf_dt: pd.DataFrame) -> pd.DataFrame:
    return (
        osf_dt[["game_id", "game_date", "player_id"]]
        .drop_duplicates()
        .assign(date=lambda x: x["game_date"].dt.strftime("%Y-%m-%d"))
        .groupby("game_id")
        .agg(date=("date", "first"), min_pid=("player_id", "min"), max_pid=("player_id", "max"))
        .reset_index()
    )


def build_recent_overlap_match(recent_games: pd.DataFrame, osf_game_pairs: pd.DataFrame) -> pd.DataFrame:
    recent = recent_games.copy()
    recent = recent.loc[
        recent["osf_black"].notna()
        & recent["osf_white"].notna()
        & (recent["game_date"] <= pd.Timestamp("2021-10-31"))
    ].copy()
    if recent.empty:
        return recent.assign(game_id=pd.Series(dtype="Int64"))
    recent["osf_black"] = recent["osf_black"].astype(int)
    recent["osf_white"] = recent["osf_white"].astype(int)
    recent["min_pid"] = recent[["osf_black", "osf_white"]].min(axis=1)
    recent["max_pid"] = recent[["osf_black", "osf_white"]].max(axis=1)
    recent["date"] = recent["game_date"].dt.strftime("%Y-%m-%d")
    return recent.merge(osf_game_pairs, on=["date", "min_pid", "max_pid"], how="inner")


def select_evenly_spaced(group: pd.DataFrame, max_per_group: int) -> pd.DataFrame:
    if len(group) <= max_per_group:
        return group
    sort_cols = [col for col in ["game_date", "game_key", "game_id"] if col in group.columns]
    ordered = group.sort_values(sort_cols).reset_index(drop=True)
    positions = np.linspace(0, len(ordered) - 1, num=max_per_group)
    positions = sorted({int(round(x)) for x in positions})
    return ordered.iloc[positions].copy()


def sort_by_existing(frame: pd.DataFrame, preferred_cols: list[str]) -> pd.DataFrame:
    sort_cols = [col for col in preferred_cols if col in frame.columns]
    if not sort_cols:
        return frame.reset_index(drop=True)
    return frame.sort_values(sort_cols).reset_index(drop=True)


def sample_recent_games_by_player_year(recent_games: pd.DataFrame, max_per_player_year: int | None) -> pd.DataFrame:
    if max_per_player_year is None:
        return sort_by_existing(recent_games, ["game_date", "game_key"])
    rows = []
    for side_col in ["osf_black", "osf_white"]:
        tmp = recent_games[["game_key", "game_date", "year", side_col]].rename(columns={side_col: "player_id"})
        rows.append(tmp)
    player_games = pd.concat(rows, ignore_index=True)
    sampled_parts = [
        select_evenly_spaced(group, max_per_group=max_per_player_year)
        for _, group in player_games.groupby(["player_id", "year"], sort=False)
    ]
    sampled = pd.concat(sampled_parts, ignore_index=True) if sampled_parts else player_games.iloc[0:0].copy()
    keep_keys = set(sampled["game_key"].astype(str))
    return recent_games.loc[recent_games["game_key"].astype(str).isin(keep_keys)].copy()


def sample_exact_games_by_player_year(rows: pd.DataFrame, max_per_player_year: int | None) -> pd.DataFrame:
    if max_per_player_year is None:
        return sort_by_existing(rows, ["player_id", "year", "game_date", "game_id"])
    game_level = rows[["game_id", "game_date", "year", "player_id"]].drop_duplicates()
    sampled_parts = [
        select_evenly_spaced(group, max_per_group=max_per_player_year)
        for _, group in game_level.groupby(["player_id", "year"], sort=False)
    ]
    sampled = pd.concat(sampled_parts, ignore_index=True) if sampled_parts else game_level.iloc[0:0].copy()
    keep_pairs = sampled[["game_id", "player_id"]].drop_duplicates()
    out = rows.merge(keep_pairs, on=["game_id", "player_id"], how="inner")
    return sort_by_existing(out, ["player_id", "year", "game_date", "game_id"])


def build_exact_game_player_rows(
    osf_dt: pd.DataFrame,
    move_start: int,
    move_end: int,
    game_ids: set[int] | None = None,
) -> pd.DataFrame:
    dt = osf_dt.loc[osf_dt["move_number"].between(move_start, move_end)].copy()
    if game_ids is not None:
        dt = dt.loc[dt["game_id"].isin(game_ids)].copy()
    rows = (
        dt.groupby(["game_id", "game_date", "player_id"], as_index=False)["dqi"]
        .median()
        .rename(columns={"dqi": "median_dqi"})
    )
    rows["year"] = rows["game_date"].dt.year.astype(int)
    return sort_by_existing(rows, ["game_date", "game_id", "player_id"])


def chunk_records(df: pd.DataFrame, chunk_size: int) -> Iterable[list[dict[str, object]]]:
    records = df.to_dict("records")
    for idx in range(0, len(records), chunk_size):
        yield records[idx : idx + chunk_size]


def score_batch(
    records: list[dict[str, object]],
    katago_path: str,
    katago_config: str,
    katago_model: str,
    override_config: list[str],
    move_start: int,
    move_end: int,
    max_visits: int,
    rules: str,
) -> list[dict[str, object]]:
    os.environ["OMP_NUM_THREADS"] = "1"
    katago = KataGoAnalysis(
        Path(katago_path),
        Path(katago_config),
        Path(katago_model),
        override_config=override_config,
    )
    rows: list[dict[str, object]] = []
    try:
        for rec in records:
            all_moves = [rec[f"move_{idx}"] for idx in range(1, move_end + 1)]
            gtp_moves = [("B" if i % 2 == 0 else "W", sgf_coord_to_gtp(mv)) for i, mv in enumerate(all_moves)]
            game_rules, game_komi = record_rules_komi(rec, rules)
            dqi_by_player: dict[int, list[float]] = {}
            queries_used = 0
            forced_queries = 0
            best_cache: dict[int, tuple[dict, list[dict]]] = {}
            for move_number in range(move_start, move_end + 1):
                player = "B" if move_number % 2 == 1 else "W"
                player_id = rec["osf_black"] if player == "B" else rec["osf_white"]
                if player_id is None or (isinstance(player_id, float) and math.isnan(player_id)):
                    continue
                player_id = int(player_id)

                turn_before = move_number - 1
                if turn_before not in best_cache:
                    payload = {
                        "id": f"{rec['game_key']}-best-{move_number}",
                        "moves": gtp_moves[:turn_before],
                        "initialStones": [],
                        "rules": game_rules,
                        "komi": game_komi,
                        "boardXSize": 19,
                        "boardYSize": 19,
                        "maxVisits": max_visits,
                    }
                    best_resp = katago.query(payload)
                    best_info = select_best_move_info(best_resp["moveInfos"])
                    best_cache[turn_before] = (best_info, best_resp["moveInfos"])
                    queries_used += 1
                best_info, move_infos = best_cache[turn_before]
                actual_move = gtp_moves[move_number - 1][1]
                actual_info = next((x for x in move_infos if x.get("move") == actual_move), None)
                if actual_info is None:
                    forced_payload = {
                        "id": f"{rec['game_key']}-actual-{move_number}",
                        "moves": gtp_moves[:turn_before],
                        "initialStones": [],
                        "rules": game_rules,
                        "komi": game_komi,
                        "boardXSize": 19,
                        "boardYSize": 19,
                        "maxVisits": max_visits,
                        "allowMoves": [{"player": player, "moves": [actual_move], "untilDepth": 1}],
                    }
                    forced_resp = katago.query(forced_payload)
                    actual_info = forced_resp["moveInfos"][0]
                    queries_used += 1
                    forced_queries += 1
                best_wr = perspective_winrate(float(best_info["winrate"]), player)
                actual_wr = perspective_winrate(float(actual_info["winrate"]), player)
                dqi = 100.0 - 100.0 * (best_wr - actual_wr)
                dqi_by_player.setdefault(player_id, []).append(float(dqi))

            for player_id, values in dqi_by_player.items():
                rows.append(
                    {
                        "game_key": rec["game_key"],
                        "game_date": rec["game_date"],
                        "year": int(pd.Timestamp(rec["game_date"]).year),
                        "player_id": player_id,
                        "median_dqi": float(pd.Series(values).median()),
                        "n_window_moves": int(len(values)),
                        "queries_used": int(queries_used),
                        "forced_queries": int(forced_queries),
                    }
                )
    finally:
        katago.close()
    return rows


def score_batch_helper(
    chunk_input: Path,
    chunk_output: Path,
    katago_path: Path,
    katago_config: Path,
    katago_model: Path,
    override_config: list[str],
    move_start: int,
    move_end: int,
    max_visits: int,
    rules: str,
) -> None:
    records = pd.read_json(chunk_input, orient="records").to_dict("records")
    try:
        rows = score_batch(
            records,
            str(katago_path),
            str(katago_config),
            str(katago_model),
            override_config,
            move_start,
            move_end,
            max_visits,
            rules,
        )
        payload = {"status": "ok", "rows": rows}
    except Exception as exc:
        payload = {
            "status": "error",
            "error": repr(exc),
            "traceback": traceback.format_exc(),
        }
    chunk_output.write_text(json.dumps(payload))


def init_worker_katago(
    katago_path: str,
    katago_config: str,
    katago_model: str,
    override_config: list[str],
) -> None:
    global WORKER_KATAGO
    os.environ["OMP_NUM_THREADS"] = "1"
    WORKER_KATAGO = KataGoAnalysis(
        Path(katago_path),
        Path(katago_config),
        Path(katago_model),
        override_config=override_config,
    )
    atexit.register(close_worker_katago)


def close_worker_katago() -> None:
    global WORKER_KATAGO
    if WORKER_KATAGO is not None:
        WORKER_KATAGO.close()
        WORKER_KATAGO = None


def score_batch_with_worker_engine(
    records: list[dict[str, object]],
    move_start: int,
    move_end: int,
    max_visits: int,
    rules: str,
) -> list[dict[str, object]]:
    global WORKER_KATAGO
    if WORKER_KATAGO is None:
        raise RuntimeError("Worker KataGo engine is not initialized")

    rows: list[dict[str, object]] = []
    for rec in records:
        all_moves = [rec[f"move_{idx}"] for idx in range(1, move_end + 1)]
        gtp_moves = [("B" if i % 2 == 0 else "W", sgf_coord_to_gtp(mv)) for i, mv in enumerate(all_moves)]
        game_rules, game_komi = record_rules_komi(rec, rules)
        dqi_by_player: dict[int, list[float]] = {}
        queries_used = 0
        forced_queries = 0
        best_cache: dict[int, tuple[dict, list[dict]]] = {}
        for move_number in range(move_start, move_end + 1):
            player = "B" if move_number % 2 == 1 else "W"
            player_id = rec["osf_black"] if player == "B" else rec["osf_white"]
            if player_id is None or (isinstance(player_id, float) and math.isnan(player_id)):
                continue
            player_id = int(player_id)

            turn_before = move_number - 1
            if turn_before not in best_cache:
                payload = {
                    "id": f"{rec['game_key']}-best-{move_number}",
                    "moves": gtp_moves[:turn_before],
                    "initialStones": [],
                    "rules": game_rules,
                    "komi": game_komi,
                    "boardXSize": 19,
                    "boardYSize": 19,
                    "maxVisits": max_visits,
                }
                best_resp = WORKER_KATAGO.query(payload)
                best_info = select_best_move_info(best_resp["moveInfos"])
                best_cache[turn_before] = (best_info, best_resp["moveInfos"])
                queries_used += 1
            best_info, move_infos = best_cache[turn_before]
            actual_move = gtp_moves[move_number - 1][1]
            actual_info = next((x for x in move_infos if x.get("move") == actual_move), None)
            if actual_info is None:
                forced_payload = {
                    "id": f"{rec['game_key']}-actual-{move_number}",
                    "moves": gtp_moves[:turn_before],
                    "initialStones": [],
                    "rules": game_rules,
                    "komi": game_komi,
                    "boardXSize": 19,
                    "boardYSize": 19,
                    "maxVisits": max_visits,
                    "allowMoves": [{"player": player, "moves": [actual_move], "untilDepth": 1}],
                }
                forced_resp = WORKER_KATAGO.query(forced_payload)
                actual_info = forced_resp["moveInfos"][0]
                queries_used += 1
                forced_queries += 1
            best_wr = perspective_winrate(float(best_info["winrate"]), player)
            actual_wr = perspective_winrate(float(actual_info["winrate"]), player)
            dqi = 100.0 - 100.0 * (best_wr - actual_wr)
            dqi_by_player.setdefault(player_id, []).append(float(dqi))

        for player_id, values in dqi_by_player.items():
            rows.append(
                {
                    "game_key": rec["game_key"],
                    "game_date": rec["game_date"],
                    "year": int(pd.Timestamp(rec["game_date"]).year),
                    "player_id": player_id,
                    "median_dqi": float(pd.Series(values).median()),
                    "n_window_moves": int(len(values)),
                    "queries_used": int(queries_used),
                    "forced_queries": int(forced_queries),
                }
            )
    return rows


def append_rows(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    frame = pd.DataFrame(rows)
    mode = "a" if path.exists() else "w"
    frame.to_csv(path, mode=mode, index=False, header=(mode == "w"), quoting=csv.QUOTE_MINIMAL)


def append_skips(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    frame = pd.DataFrame(rows)
    mode = "a" if path.exists() else "w"
    frame.to_csv(path, mode=mode, index=False, header=(mode == "w"), quoting=csv.QUOTE_MINIMAL)


def split_records(records: list[dict[str, object]]) -> list[list[dict[str, object]]]:
    if len(records) <= 1:
        return [records]
    mid = len(records) // 2
    return [records[:mid], records[mid:]]


def chunk_timeout_seconds(record_count: int, timeout_base_sec: int, timeout_per_game_sec: int) -> int:
    return int(timeout_base_sec + timeout_per_game_sec * record_count)


def run_recent_scoring(
    recent_games: pd.DataFrame,
    scored_path: Path,
    katago_path: Path,
    katago_config: Path,
    katago_model: Path,
    override_config: list[str],
    move_start: int,
    move_end: int,
    max_visits: int,
    rules: str,
    workers: int,
    chunk_size: int,
    timeout_base_sec: int,
    timeout_per_game_sec: int,
    max_single_game_retries: int,
) -> pd.DataFrame:
    runtime_dir = scored_path.parent / "_runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    skip_path = scored_path.parent / "recent_game_player_dqi_skipped.csv"
    scheduler_log = runtime_dir / "scheduler.log"

    def log_scheduler(message: str) -> None:
        with scheduler_log.open("a", encoding="utf-8") as fh:
            fh.write(f"{pd.Timestamp.now('UTC').isoformat()} {message}\n")

    if scored_path.exists():
        scored_existing = pd.read_csv(scored_path)
        target_keys = set(recent_games["game_key"].astype(str))
        scored_existing = scored_existing.loc[scored_existing["game_key"].astype(str).isin(target_keys)].copy()
        scored_existing.to_csv(scored_path, index=False, quoting=csv.QUOTE_MINIMAL)
        completed_keys = set(scored_existing["game_key"].astype(str))
    else:
        scored_existing = pd.DataFrame()
        completed_keys = set()

    pending = recent_games.loc[~recent_games["game_key"].astype(str).isin(completed_keys)].copy()
    if not pending.empty:
        total_pending = int(len(pending))
        finished_games = 0
        job_counter = 0
        job_queue: deque[dict[str, object]] = deque(
            {"records": chunk, "attempt": 0}
            for chunk in chunk_records(pending, chunk_size)
        )
        active: list[dict[str, object]] = []

        def launch_job(job: dict[str, object]) -> dict[str, object]:
            nonlocal job_counter
            job_counter += 1
            job_id = f"chunk_{job_counter:05d}"
            input_path = runtime_dir / f"{job_id}.input.json"
            output_path = runtime_dir / f"{job_id}.output.json"
            stderr_path = runtime_dir / f"{job_id}.stderr.log"
            pd.DataFrame(job["records"]).to_json(input_path, orient="records", date_format="iso")
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--helper-chunk-input",
                str(input_path),
                "--helper-chunk-output",
                str(output_path),
                "--katago-path",
                str(katago_path),
                "--katago-config",
                str(katago_config),
                "--katago-model",
                str(katago_model),
                "--move-start",
                str(move_start),
                "--move-end",
                str(move_end),
                "--max-visits",
                str(max_visits),
                "--rules",
                rules,
            ]
            for entry in override_config:
                cmd.extend(["--override-config", entry])
            stderr_fh = open(stderr_path, "w", encoding="utf-8")
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=stderr_fh,
                start_new_session=True,
                text=True,
            )
            log_scheduler(f"launch {job_id} size={len(job['records'])} timeout={chunk_timeout_seconds(len(job['records']), timeout_base_sec, timeout_per_game_sec)}")
            return {
                "job_id": job_id,
                "records": job["records"],
                "attempt": job["attempt"],
                "proc": proc,
                "input_path": input_path,
                "output_path": output_path,
                "stderr_path": stderr_path,
                "stderr_fh": stderr_fh,
                "start_time": time.monotonic(),
                "timeout_sec": chunk_timeout_seconds(len(job["records"]), timeout_base_sec, timeout_per_game_sec),
            }

        def cleanup_active(entry: dict[str, object]) -> None:
            entry["stderr_fh"].close()
            for path_key in ["input_path", "output_path"]:
                path = entry[path_key]
                if Path(path).exists():
                    Path(path).unlink()

        while job_queue or active:
            while job_queue and len(active) < max(1, workers):
                active.append(launch_job(job_queue.popleft()))

            time.sleep(1.0)
            next_active: list[dict[str, object]] = []
            for entry in active:
                proc: subprocess.Popen = entry["proc"]
                elapsed = time.monotonic() - float(entry["start_time"])
                if int(elapsed) % 30 == 0:
                    log_scheduler(f"tick {entry['job_id']} elapsed={elapsed:.1f} alive={proc.poll() is None}")
                if proc.poll() is None and elapsed < float(entry["timeout_sec"]):
                    next_active.append(entry)
                    continue

                timed_out = proc.poll() is None and elapsed >= float(entry["timeout_sec"])
                if timed_out:
                    log_scheduler(f"timeout {entry['job_id']} elapsed={elapsed:.1f}")
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        proc.wait(timeout=5)

                output_path = Path(entry["output_path"])
                stderr_path = Path(entry["stderr_path"])
                status = "timeout" if timed_out else "error"
                payload: dict[str, object] | None = None
                if output_path.exists():
                    try:
                        payload = json.loads(output_path.read_text())
                        status = str(payload.get("status", status))
                    except Exception:
                        payload = None

                if status == "ok" and payload is not None:
                    log_scheduler(f"ok {entry['job_id']} rows={len(payload.get('rows', [])) if isinstance(payload.get('rows', []), list) else 'na'}")
                    rows = payload.get("rows", [])
                    append_rows(scored_path, rows if isinstance(rows, list) else [])
                    finished_games += len(entry["records"])
                    print(f"recent scoring progress: {finished_games}/{total_pending} games", flush=True)
                    cleanup_active(entry)
                    continue

                records = entry["records"]
                if len(records) > 1:
                    log_scheduler(f"recover-split {entry['job_id']} size={len(records)} status={status}")
                    for split_chunk in reversed(split_records(records)):
                        job_queue.appendleft({"records": split_chunk, "attempt": 0})
                    reason = f"{status}:split"
                else:
                    rec = records[0]
                    if int(entry["attempt"]) < max_single_game_retries:
                        log_scheduler(f"recover-retry {entry['job_id']} key={rec.get('game_key')} status={status} attempt={entry['attempt']}")
                        job_queue.appendleft({"records": records, "attempt": int(entry["attempt"]) + 1})
                        reason = f"{status}:retry"
                    else:
                        log_scheduler(f"skip {entry['job_id']} key={rec.get('game_key')} status={status}")
                        append_skips(
                            skip_path,
                            [
                                {
                                    "game_key": rec.get("game_key"),
                                    "archive_member": rec.get("archive_member"),
                                    "game_date": rec.get("game_date"),
                                    "osf_black": rec.get("osf_black"),
                                    "osf_white": rec.get("osf_white"),
                                    "reason": status,
                                    "attempts": int(entry["attempt"]) + 1,
                                    "stderr_path": str(stderr_path),
                                }
                            ],
                        )
                        finished_games += 1
                        print(
                            f"recent scoring skip: {rec.get('game_key')} ({status}) [{finished_games}/{total_pending}]",
                            flush=True,
                        )
                        reason = status
                print(
                    f"recent scoring recovery: {entry['job_id']} {reason} size={len(records)} elapsed={elapsed:.1f}s",
                    flush=True,
                )
                cleanup_active(entry)

            active = next_active

    if not scored_path.exists():
        return pd.DataFrame(
            columns=["game_key", "game_date", "year", "player_id", "median_dqi", "n_window_moves", "queries_used", "forced_queries"]
        )
    scored = pd.read_csv(scored_path)
    scored["game_date"] = pd.to_datetime(scored["game_date"], errors="coerce")
    scored["year"] = scored["year"].astype(int)
    scored["player_id"] = scored["player_id"].astype(int)
    return scored.sort_values(["game_date", "game_key", "player_id"]).reset_index(drop=True)


def compute_recent_player_year_panel(scored: pd.DataFrame) -> pd.DataFrame:
    return (
        scored.groupby(["player_id", "year"], as_index=False)["median_dqi"]
        .median()
        .rename(columns={"median_dqi": "median_dqi"})
        .sort_values(["player_id", "year"])
        .reset_index(drop=True)
    )


def fit_yearly_panel(panel: pd.DataFrame, baseline_year: str = "1950") -> pd.DataFrame:
    work = panel[["player_id", "year", "median_dqi"]].copy()
    work["year"] = work["year"].astype(str)
    if baseline_year not in set(work["year"]):
        raise ValueError(f"Baseline year {baseline_year} not present in panel")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        in_csv = tmpdir_path / "panel.csv"
        out_csv = tmpdir_path / "coeffs.csv"
        work.to_csv(in_csv, index=False, quoting=csv.QUOTE_MINIMAL)
        r_code = f"""
suppressPackageStartupMessages({{library(data.table); library(lfe)}})
d <- fread("{in_csv.as_posix()}")
d[, year := as.character(year)]
d[, player_id := as.character(player_id)]
d[, year := relevel(factor(year), ref = "{baseline_year}")]
fit <- felm(median_dqi ~ year | player_id | 0 | player_id, data = d)
co <- as.data.table(coef(summary(fit)), keep.rownames = "term")
setnames(co, old = c("Estimate", "Cluster s.e."), new = c("fe", "cluster_se"))
co[, label := sub("^year", "", term)]
co[, fe_ci_ll := fe - {Z_975} * cluster_se]
co[, fe_ci_ul := fe + {Z_975} * cluster_se]
fwrite(co[, .(label, fe, fe_ci_ll, fe_ci_ul)], "{out_csv.as_posix()}")
"""
        subprocess.run(["Rscript", "-e", r_code], check=True, capture_output=True, text=True)
        fe = pd.read_csv(out_csv)
    fe["year"] = fe["label"].astype(int)
    return fe.sort_values("year").reset_index(drop=True)


def compare_series(a: pd.DataFrame, b: pd.DataFrame, key: str, col_a: str, col_b: str) -> dict[str, float | int | None]:
    merged = a[[key, col_a]].merge(b[[key, col_b]], on=key, how="inner")
    if merged.empty:
        return {"n": 0, "corr": None, "mae": None}
    return {
        "n": int(len(merged)),
        "corr": float(merged[col_a].corr(merged[col_b])) if len(merged) >= 2 else None,
        "mae": float((merged[col_a] - merged[col_b]).abs().mean()),
    }


def apply_affine_to_yearly(yearly: pd.DataFrame, intercept: float, slope: float) -> pd.DataFrame:
    out = yearly.copy()
    out["fe_raw"] = out["fe"]
    out["fe_ci_ll_raw"] = out["fe_ci_ll"]
    out["fe_ci_ul_raw"] = out["fe_ci_ul"]
    out["fe"] = intercept + slope * out["fe_raw"]
    if slope >= 0:
        out["fe_ci_ll"] = intercept + slope * out["fe_ci_ll_raw"]
        out["fe_ci_ul"] = intercept + slope * out["fe_ci_ul_raw"]
    else:
        out["fe_ci_ll"] = intercept + slope * out["fe_ci_ul_raw"]
        out["fe_ci_ul"] = intercept + slope * out["fe_ci_ll_raw"]
    return out


def plot_combined_chart(coeffs: pd.DataFrame, last_date: pd.Timestamp, cutoff_year: int, outpath: Path) -> None:
    coeffs = coeffs.copy().sort_values("year")
    hist = coeffs.loc[coeffs["year"] <= cutoff_year].copy()
    ext = coeffs.loc[coeffs["year"] > cutoff_year].copy()
    alpha_x = decimal_year(ALPHAGO_DATE)
    last_tick = decimal_year(last_date)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axhline(0, color=GRAY, linewidth=1.0, linestyle=(0, (2, 5)))
    ax.axvspan(alpha_x, cutoff_year + 0.5, alpha=0.14, color=ORANGE, zorder=0)
    ax.axvspan(cutoff_year + 0.5, last_tick, alpha=0.30, color=LIGHT_BLUE, zorder=0)
    ax.axvline(alpha_x, color=ORANGE, linewidth=1.1, linestyle=(0, (3, 3)))
    ax.axvline(cutoff_year + 0.5, color=BLUE, linewidth=1.2, linestyle=(0, (2, 3)))

    if not hist.empty:
        ax.errorbar(
            hist["year"],
            hist["fe"],
            yerr=[hist["fe"] - hist["fe_ci_ll"], hist["fe_ci_ul"] - hist["fe"]],
            fmt="o",
            color=GREEN,
            ecolor=GREEN,
            elinewidth=1.25,
            markersize=4.3,
            capsize=0,
        )
    if not ext.empty:
        ax.errorbar(
            ext["year"],
            ext["fe"],
            yerr=[ext["fe"] - ext["fe_ci_ll"], ext["fe_ci_ul"] - ext["fe"]],
            fmt="o",
            color=BLUE,
            ecolor=BLUE,
            elinewidth=1.25,
            markersize=4.8,
            capsize=0,
        )
        if len(ext) >= 2:
            ax.plot(ext["year"], ext["fe"], color=BLUE, linewidth=1.0, alpha=0.7)

    last_label = f"{last_date.year}\n({last_date.strftime('%b')})"
    xticks = [1950] + list(range(1960, 2020, 10)) + [2021, last_tick]
    xlabels = ["1950"] + [str(y) for y in range(1960, 2020, 10)] + ["2021", last_label]
    y_min = min(-0.8, float(coeffs["fe_ci_ll"].min()) - 0.05)
    y_max = max(1.2, float(coeffs["fe_ci_ul"].max()) + 0.05)
    tick_min = math.floor(y_min / 0.4) * 0.4
    tick_max = math.ceil(y_max / 0.4) * 0.4
    ax.set_xlim(1948, max(2027, last_date.year + 1))
    ax.set_ylim(tick_min, tick_max)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels)
    ax.set_yticks(np.arange(tick_min, tick_max + 0.001, 0.4))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#333333")
    ax.spines["left"].set_color("#333333")
    ax.tick_params(axis="both", labelsize=11, colors="#555555")
    ax.set_xlabel("")
    ax.set_ylabel("Relative move quality\n(0 = reference level)", color="#444444")
    y_span = tick_max - tick_min
    partial_note = ""
    if last_date < pd.Timestamp(year=last_date.year, month=12, day=31):
        label = last_date.strftime("%b %d, %Y").replace(" 0", " ")
        partial_note = f" {last_date.year} uses games through {label}."
    fig.text(
        0.015,
        0.01,
        "95% intervals. Green = original-paper-aligned history; blue = new continuation."
        + partial_note,
        ha="left",
        va="bottom",
        fontsize=8,
        color="#666666",
    )
    fig.tight_layout()
    fig.savefig(outpath, dpi=240)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--osf-data", type=Path, default=ROOT / "osf/shin et al 2023 data v001.RData")
    parser.add_argument("--gle-games", type=Path, default=ROOT / "public_refs/go_learning_eras/data/games.csv")
    parser.add_argument("--gle-players", type=Path, default=ROOT / "public_refs/go_learning_eras/data/players.csv")
    parser.add_argument("--recent-zip", type=Path, default=RECENT_ZIP)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/independent_uplift_chart")
    parser.add_argument("--move-start", type=int, default=2)
    parser.add_argument("--move-end", type=int, default=4)
    parser.add_argument("--max-visits", type=int, default=20)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--rules", default="japanese")
    parser.add_argument("--max-games", type=int)
    parser.add_argument("--allow-one-sided-mapped", action="store_true")
    parser.add_argument("--sample-games-per-player-year", type=int, default=3)
    parser.add_argument("--recent-score-start-date", default="2022-01-01")
    parser.add_argument("--max-scoring-games", type=int)
    parser.add_argument("--timeout-base-sec", type=int, default=20)
    parser.add_argument("--timeout-per-game-sec", type=int, default=15)
    parser.add_argument("--max-single-game-retries", type=int, default=1)
    parser.add_argument("--metric-label")
    parser.add_argument("--affine-intercept", type=float)
    parser.add_argument("--affine-slope", type=float)
    parser.add_argument("--paper-yearly-target", type=Path, default=DEFAULT_PAPER_YEARLY)
    parser.add_argument("--katago-path", type=Path, default=DEFAULT_KATAGO_PATH)
    parser.add_argument(
        "--katago-config",
        type=Path,
        default=DEFAULT_KATAGO_CONFIG,
    )
    parser.add_argument(
        "--katago-model",
        type=Path,
        default=DEFAULT_KATAGO_MODEL,
    )
    parser.add_argument("--override-config", action="append", default=["logToStdout=false"])
    parser.add_argument("--helper-chunk-input", type=Path)
    parser.add_argument("--helper-chunk-output", type=Path)
    args = parser.parse_args()

    if args.helper_chunk_input is not None or args.helper_chunk_output is not None:
        if args.helper_chunk_input is None or args.helper_chunk_output is None:
            raise RuntimeError("Both --helper-chunk-input and --helper-chunk-output are required in helper mode")
        score_batch_helper(
            chunk_input=args.helper_chunk_input,
            chunk_output=args.helper_chunk_output,
            katago_path=args.katago_path,
            katago_config=args.katago_config,
            katago_model=args.katago_model,
            override_config=args.override_config,
            move_start=args.move_start,
            move_end=args.move_end,
            max_visits=args.max_visits,
            rules=args.rules,
        )
        return

    label = args.metric_label or f"moves_{args.move_start}_{args.move_end}_visits_{args.max_visits}"
    output_root = args.output_dir
    if output_root == ROOT / "outputs/independent_uplift_chart" and label.startswith("paper_like_"):
        output_root = ROOT / "outputs/reverse_engineering/paper_like_extension"
    outdir = output_root / label
    outdir.mkdir(parents=True, exist_ok=True)

    osf_dt = load_osf_dt(args.osf_data)
    gle_games = load_gle_games(args.gle_players, args.gle_games)
    crosswalk = build_bridge_crosswalk(osf_dt, gle_games)
    linked_players = set(crosswalk["osf_player_id"].astype(int))
    name_to_osf = build_recent_name_to_osf(args.gle_players, crosswalk)

    historical_panel_all = build_historical_player_year_panel(osf_dt, args.move_start, args.move_end)
    historical_panel_all.to_csv(outdir / "historical_all_player_year_exact.csv", index=False)
    historical_yearly = fit_yearly_panel(historical_panel_all)
    historical_yearly.to_csv(outdir / "historical_all_yearly_fe_exact.csv", index=False)

    historical_panel_linked = build_historical_player_year_panel(
        osf_dt,
        args.move_start,
        args.move_end,
        player_subset=linked_players,
    )
    historical_panel_linked.to_csv(outdir / "historical_linked_player_year_exact.csv", index=False)

    recent_games = parse_recent_games(
        args.recent_zip,
        outdir / "recent_games_raw_cache.csv",
        name_to_osf,
        move_end=args.move_end,
        min_date=pd.Timestamp("2021-01-01"),
        max_date=pd.Timestamp("2026-12-31"),
        default_rules=args.rules,
        max_games=args.max_games,
    )
    if not args.allow_one_sided_mapped:
        recent_games = recent_games.loc[recent_games["osf_black"].notna() & recent_games["osf_white"].notna()].copy()
    if recent_games.empty:
        raise RuntimeError("No recent GoGoD games remain after the mapping/filter rules")
    recent_games_all = recent_games.copy()
    recent_games = sample_recent_games_by_player_year(recent_games, args.sample_games_per_player_year)
    recent_games.to_csv(outdir / "recent_games.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    recent_score_start = pd.Timestamp(args.recent_score_start_date)
    recent_games_scoring = recent_games.loc[recent_games["game_date"] >= recent_score_start].copy()
    if recent_games_scoring.empty:
        raise RuntimeError("No recent games remain after applying recent-score-start-date")
    if args.max_scoring_games is not None:
        recent_games_scoring = (
            recent_games_scoring.sort_values(["game_date", "game_key"]).head(args.max_scoring_games).copy()
        )
    recent_games_scoring.to_csv(outdir / "recent_games_scoring.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    (
        recent_games_scoring.groupby(["katago_rules", "katago_komi", "katago_komi_adjusted"], dropna=False)
        .size()
        .reset_index(name="n_games")
        .sort_values(["katago_rules", "katago_komi", "katago_komi_adjusted"])
        .to_csv(outdir / "recent_rule_komi_summary.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    )

    scored = run_recent_scoring(
        recent_games=recent_games_scoring,
        scored_path=outdir / "recent_game_player_dqi.csv",
        katago_path=args.katago_path,
        katago_config=args.katago_config,
        katago_model=args.katago_model,
        override_config=args.override_config,
        move_start=args.move_start,
        move_end=args.move_end,
        max_visits=args.max_visits,
        rules=args.rules,
        workers=args.workers,
        chunk_size=args.chunk_size,
        timeout_base_sec=args.timeout_base_sec,
        timeout_per_game_sec=args.timeout_per_game_sec,
        max_single_game_retries=args.max_single_game_retries,
    )

    recent_player_year = compute_recent_player_year_panel(scored)
    recent_player_year.to_csv(outdir / "recent_player_year_reconstructed.csv", index=False)

    extension_panel = recent_player_year.loc[recent_player_year["year"] >= 2022].copy()
    extension_panel.to_csv(outdir / "extension_player_year_reconstructed.csv", index=False)

    combined_panel = pd.concat([historical_panel_all, extension_panel], ignore_index=True)
    combined_panel = combined_panel.sort_values(["player_id", "year"]).reset_index(drop=True)
    combined_panel.to_csv(outdir / "combined_player_year_panel.csv", index=False)
    combined_yearly_raw = fit_yearly_panel(combined_panel)
    combined_yearly_raw.to_csv(outdir / "combined_yearly_fe_raw.csv", index=False)
    combined_yearly = combined_yearly_raw.copy()

    orig_yearly = pd.read_csv(args.paper_yearly_target)[["year", "fe"]].rename(
        columns={"fe": "orig_fe"}
    )
    historical_yearly_for_comparison = historical_yearly.copy()

    if args.affine_intercept is not None or args.affine_slope is not None:
        if args.affine_intercept is None or args.affine_slope is None:
            raise RuntimeError("Both --affine-intercept and --affine-slope are required together")
        historical_yearly_for_comparison = apply_affine_to_yearly(
            historical_yearly_for_comparison, args.affine_intercept, args.affine_slope
        )
        combined_yearly = apply_affine_to_yearly(combined_yearly, args.affine_intercept, args.affine_slope)
    combined_yearly["segment"] = np.where(
        combined_yearly["year"] <= 2021,
        "historical_reconstructed_all_osf_players",
        "extension_linked_gogod_players",
    )
    combined_yearly["segment_population"] = np.where(
        combined_yearly["year"] <= 2021,
        "all OSF players under reconstructed historical metric",
        "crosswalk-linked recent GoGoD players",
    )
    combined_yearly.to_csv(outdir / "combined_yearly_fe.csv", index=False)

    historical_vs_original = compare_series(
        historical_yearly_for_comparison.rename(columns={"fe": "hist_fe"}), orig_yearly, "year", "hist_fe", "orig_fe"
    )

    osf_game_pairs = build_osf_game_pairs(osf_dt)
    overlap_games = build_recent_overlap_match(recent_games_all, osf_game_pairs)
    overlap_games.to_csv(outdir / "recent_2021_overlap_game_matches.csv", index=False)

    exact_overlap = build_exact_game_player_rows(
        osf_dt,
        args.move_start,
        args.move_end,
        game_ids=set(overlap_games["game_id"].astype(int).tolist()) if not overlap_games.empty else set(),
    )[["game_id", "player_id", "median_dqi"]].rename(columns={"median_dqi": "exact_median_dqi"})

    overlap_scored = run_recent_scoring(
        recent_games=overlap_games,
        scored_path=outdir / "recent_2021_overlap_scored.csv",
        katago_path=args.katago_path,
        katago_config=args.katago_config,
        katago_model=args.katago_model,
        override_config=args.override_config,
        move_start=args.move_start,
        move_end=args.move_end,
        max_visits=args.max_visits,
        rules=args.rules,
        workers=args.workers,
        chunk_size=args.chunk_size,
        timeout_base_sec=args.timeout_base_sec,
        timeout_per_game_sec=args.timeout_per_game_sec,
        max_single_game_retries=args.max_single_game_retries,
    ).merge(
        overlap_games[["game_key", "game_id"]],
        on="game_key",
        how="inner",
    )
    overlap_compare = overlap_scored.merge(exact_overlap, on=["game_id", "player_id"], how="inner")
    if not overlap_compare.empty:
        overlap_compare["abs_err"] = (overlap_compare["median_dqi"] - overlap_compare["exact_median_dqi"]).abs()
    else:
        overlap_compare["abs_err"] = pd.Series(dtype=float)
    overlap_compare.to_csv(outdir / "recent_2021_overlap_validation.csv", index=False)

    overlap_summary = {
        "n_game_player_rows": int(len(overlap_compare)),
        "corr": float(overlap_compare["median_dqi"].corr(overlap_compare["exact_median_dqi"]))
        if len(overlap_compare) >= 2
        else None,
        "mae": float(overlap_compare["abs_err"].mean()) if not overlap_compare.empty else None,
        "median_abs_err": float(overlap_compare["abs_err"].median()) if not overlap_compare.empty else None,
    }
    overlap_player_year = (
        overlap_compare.groupby("player_id", as_index=False)[["median_dqi", "exact_median_dqi"]].median()
        if not overlap_compare.empty
        else pd.DataFrame(columns=["player_id", "median_dqi", "exact_median_dqi"])
    )
    if not overlap_player_year.empty:
        overlap_player_year["abs_err"] = (
            overlap_player_year["median_dqi"] - overlap_player_year["exact_median_dqi"]
        ).abs()
    else:
        overlap_player_year["abs_err"] = pd.Series(dtype=float)
    overlap_player_year.to_csv(outdir / "recent_2021_overlap_player_year_validation.csv", index=False)
    overlap_player_year_summary = {
        "n_player_year_rows": int(len(overlap_player_year)),
        "corr": float(overlap_player_year["median_dqi"].corr(overlap_player_year["exact_median_dqi"]))
        if len(overlap_player_year) >= 2
        else None,
        "mae": float(overlap_player_year["abs_err"].mean()) if not overlap_player_year.empty else None,
        "median_abs_err": float(overlap_player_year["abs_err"].median()) if not overlap_player_year.empty else None,
    }

    linked = set(crosswalk["osf_player_id"].astype(int))
    exact_all_rows = build_exact_game_player_rows(osf_dt, args.move_start, args.move_end)
    exact_all_full_panel = exact_all_rows.groupby(["player_id", "year"], as_index=False)["median_dqi"].median()
    exact_all_baseline = str(int(exact_all_full_panel["year"].min()))
    exact_all_full_yearly = fit_yearly_panel(
        exact_all_full_panel,
        baseline_year=exact_all_baseline,
    )
    exact_all_sampled_rows = sample_exact_games_by_player_year(
        exact_all_rows,
        args.sample_games_per_player_year,
    )
    exact_all_sampled_panel = (
        exact_all_sampled_rows.groupby(["player_id", "year"], as_index=False)["median_dqi"].median()
    )
    exact_all_sampled_yearly = fit_yearly_panel(
        exact_all_sampled_panel,
        baseline_year=exact_all_baseline,
    )
    historical_sampling_validation = compare_series(
        exact_all_sampled_yearly.rename(columns={"fe": "sample_fe"}),
        exact_all_full_yearly.rename(columns={"fe": "full_fe"}),
        "year",
        "sample_fe",
        "full_fe",
    )
    sampling_tail = exact_all_sampled_yearly[["year", "fe"]].merge(
        exact_all_full_yearly[["year", "fe"]],
        on="year",
        suffixes=("_sample", "_full"),
    )
    sampling_tail = sampling_tail.loc[sampling_tail["year"] >= 2016]

    recent_yearly_raw = fit_yearly_panel(
        pd.concat(
            [
                historical_panel_all.loc[historical_panel_all["year"] <= 2020],
                recent_player_year.loc[recent_player_year["year"] >= 2021],
            ],
            ignore_index=True,
        ).sort_values(["player_id", "year"])
    )
    recent_yearly = recent_yearly_raw.copy()
    if args.affine_intercept is not None and args.affine_slope is not None:
        recent_yearly = apply_affine_to_yearly(recent_yearly, args.affine_intercept, args.affine_slope)
    recent_yearly.to_csv(outdir / "bridge_yearly_fe_with_recent_2021.csv", index=False)

    recent_2021_overlap = compare_series(
        recent_yearly.loc[recent_yearly["year"] >= 2021].rename(columns={"fe": "recent_fe"}),
        combined_yearly.loc[combined_yearly["year"] >= 2021].rename(columns={"fe": "combined_fe"}),
        "year",
        "recent_fe",
        "combined_fe",
    )

    last_recent_date = pd.Timestamp(recent_games["game_date"].max())
    chart_filename = "paper_like_extension_chart.png" if label.startswith("paper_like_") else "independent_uplift_chart.png"
    chart_path = outdir / chart_filename
    legacy_chart_path = outdir / "independent_uplift_chart.png"
    plot_combined_chart(combined_yearly, last_recent_date, cutoff_year=2021, outpath=chart_path)
    if chart_path != legacy_chart_path and legacy_chart_path.exists():
        legacy_chart_path.unlink()

    yearly_extension = combined_yearly.loc[combined_yearly["year"] >= 2014].copy()
    yearly_extension.to_csv(outdir / "combined_yearly_fe_recent_slice.csv", index=False)

    latest_year = int(last_recent_date.year)
    latest_year_partial = last_recent_date < pd.Timestamp(year=latest_year, month=12, day=31)

    summary = {
        "method": {
            "metric_label": label,
            "population": "mixed: reconstructed all-OSF-player historical segment through 2021, linked GoGoD continuation sample from 2022 onward",
            "move_window": [args.move_start, args.move_end],
            "recent_rules_fallback": args.rules,
            "recent_rules_handling": "per-game SGF rules normalized to KataGo-supported rules, with japanese fallback when SGF rules are missing or unsupported",
            "recent_komi_handling": "per-game SGF komi, with unsupported quarter-komi rounded half-up to the nearest KataGo-supported half-integer",
            "recent_max_visits": args.max_visits,
            "move_1_excluded": True,
            "historical_anchor_population": "all OSF players",
            "recent_continuation_population": "crosswalk-linked GoGoD players",
            "recent_sampling_games_per_player_year": args.sample_games_per_player_year,
            "recent_score_start_date": str(recent_score_start.date()),
            "recent_max_scoring_games": args.max_scoring_games,
            "affine_intercept": args.affine_intercept,
            "affine_slope": args.affine_slope,
            "chart_segments": {
                "historical_through_2021": "all OSF players under reconstructed historical metric",
                "continuation_2022_plus": "crosswalk-linked recent GoGoD players",
            },
        },
        "counts": {
            "linked_players": int(len(linked_players)),
            "recent_games_total": int(len(recent_games)),
            "recent_games_scored": int(len(recent_games_scoring)),
            "recent_games_2022_plus": int((recent_games["game_date"] > pd.Timestamp("2021-10-31")).sum()),
            "recent_game_player_rows": int(len(scored)),
            "recent_player_year_rows": int(len(recent_player_year)),
            "extension_player_year_rows": int(len(extension_panel)),
        },
        "validation": {
            "historical_vs_original": historical_vs_original,
            "historical_sampling_vs_full_all_players": {
                **historical_sampling_validation,
                "baseline_year": exact_all_baseline,
                "n_full_game_player_rows": int(len(exact_all_rows)),
                "n_sampled_game_player_rows": int(len(exact_all_sampled_rows)),
                "corr_2016_plus": float(sampling_tail["fe_sample"].corr(sampling_tail["fe_full"]))
                if len(sampling_tail) >= 2
                else None,
                "mae_2016_plus": float((sampling_tail["fe_sample"] - sampling_tail["fe_full"]).abs().mean())
                if not sampling_tail.empty
                else None,
            },
            "overlap_2021_game_player": overlap_summary,
            "overlap_2021_player_year": overlap_player_year_summary,
            "recent_2021_bridge_vs_combined": recent_2021_overlap,
        },
        "latest_date": str(last_recent_date.date()),
        "latest_year": latest_year,
        "latest_year_partial": bool(latest_year_partial),
        "latest_extension_rows": yearly_extension[["year", "fe", "fe_ci_ll", "fe_ci_ul"]].to_dict(orient="records"),
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
