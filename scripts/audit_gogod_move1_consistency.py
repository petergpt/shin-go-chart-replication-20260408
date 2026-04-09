#!/usr/bin/env python3
"""Audit move-1 consistency using exact GoGoD SGFs matched to OSF games."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.extend_shin_yearly_proxy import (
    build_bridge_crosswalk,
    load_gle_games,
    load_osf_dt,
    match_gle_games_to_osf,
    normalise_name,
)

PAT_KM = re.compile(r"KM\[([^\]]*)\]")
PAT_FIRST = re.compile(r";([BW])\[([a-s]{2})\]")


def load_gogod_metadata(game_data_zip: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(game_data_zip) as zf:
        with zf.open("GameData.txt") as fh:
            for raw in fh:
                parts = raw.decode("utf-8", "ignore").rstrip("\n").rstrip("\r").split("|")
                if len(parts) < 18:
                    continue
                rows.append(
                    {
                        "stem": parts[0],
                        "white_name_norm": normalise_name(parts[1]),
                        "black_name_norm": normalise_name(parts[4]),
                        "date": parts[9][:10],
                    }
                )
    return pd.DataFrame(rows)


def build_stem_map(zip_paths: list[Path]) -> dict[str, tuple[Path, str]]:
    stem_map: dict[str, tuple[Path, str]] = {}
    for zip_path in zip_paths:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                if not member.endswith(".sgf"):
                    continue
                stem = Path(member).stem
                stem_map.setdefault(stem, (zip_path, member))
    return stem_map


def extract_move1_records(unique_match: pd.DataFrame, stem_map: dict[str, tuple[Path, str]]) -> pd.DataFrame:
    grouped = unique_match.groupby("archive_zip")
    rows: list[dict[str, object]] = []

    for archive_zip, chunk in grouped:
        zip_path = Path(archive_zip)
        with zipfile.ZipFile(zip_path) as zf:
            for rec in chunk[["game_id", "stem"]].itertuples(index=False):
                _, member = stem_map[rec.stem]
                text = zf.read(member).decode("utf-8", "ignore")
                km = PAT_KM.search(text)
                first = PAT_FIRST.search(text)
                rows.append(
                    {
                        "game_id": int(rec.game_id),
                        "stem": rec.stem,
                        "komi_num": float(km.group(1)) if km else None,
                        "first_player": first.group(1) if first else None,
                        "first_move": first.group(2) if first else None,
                    }
                )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--osf-data", type=Path, default=ROOT / "osf/shin et al 2023 data v001.RData")
    parser.add_argument("--gle-games", type=Path, default=ROOT / "public_refs/go_learning_eras/data/games.csv")
    parser.add_argument("--gle-players", type=Path, default=ROOT / "public_refs/go_learning_eras/data/players.csv")
    parser.add_argument("--game-data-zip", type=Path, default=Path("/Users/peter/Downloads/GameData.zip"))
    parser.add_argument(
        "--gogod-zips",
        type=Path,
        nargs="+",
        default=[
            Path("/Users/peter/Downloads/0196-1980-Database-Jan2026.zip"),
            Path("/Users/peter/Downloads/1981-1990-Database-Jan2026.zip"),
            Path("/Users/peter/Downloads/1991-2000-Database-Jan2026.zip"),
            Path("/Users/peter/Downloads/2001-2010-Database-Jan2026.zip"),
            Path("/Users/peter/Downloads/2011-2020-Database-Jan2026.zip"),
            ROOT / "data/private/2021-2026-Database-Jan2026.zip",
        ],
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/katago_validation/gogod_move1_position_consistency",
    )
    args = parser.parse_args()

    osf_dt = load_osf_dt(args.osf_data)
    gle_games = load_gle_games(args.gle_players, args.gle_games)
    crosswalk = build_bridge_crosswalk(osf_dt, gle_games)
    matched = match_gle_games_to_osf(osf_dt, gle_games, crosswalk).copy()
    matched["date"] = matched["game_date"].dt.strftime("%Y-%m-%d")
    matched["black_name_norm"] = matched["black_name"].map(normalise_name)
    matched["white_name_norm"] = matched["white_name"].map(normalise_name)

    meta = load_gogod_metadata(args.game_data_zip)
    joined = matched.merge(meta, on=["date", "black_name_norm", "white_name_norm"], how="left")
    candidate_counts = joined.groupby("game_id")["stem"].nunique(dropna=True)
    unique_ids = candidate_counts.loc[candidate_counts == 1].index

    unique_match = joined.loc[joined["game_id"].isin(unique_ids)].drop_duplicates("game_id").copy()
    stem_map = build_stem_map(args.gogod_zips)
    unique_match["archive_zip"] = unique_match["stem"].map(lambda stem: str(stem_map[stem][0]))

    move1_records = extract_move1_records(unique_match, stem_map)
    move1_osf = osf_dt.loc[osf_dt["move_number"] == 1, ["game_id", "dqi"]].copy()
    audit = move1_osf.merge(move1_records, on="game_id", how="inner")

    q16 = audit.loc[(audit["first_move"] == "pd") & (audit["komi_num"] == 5.5)].copy()
    contradictions = (
        audit.groupby(["first_move", "komi_num"])["dqi"]
        .agg(count="count", unique_dqi=lambda s: s.nunique())
        .reset_index()
    )
    contradictions = contradictions.loc[
        (contradictions["count"] >= 10) & (contradictions["unique_dqi"] >= 2)
    ].sort_values(["count", "unique_dqi"], ascending=[False, False])

    summary = {
        "unique_gogod_matched_games": int(len(unique_match)),
        "move1_audit_rows": int(len(audit)),
        "q16_komi55_count": int(len(q16)),
        "q16_komi55_unique_dqi": sorted({round(float(x), 1) for x in q16["dqi"].dropna().tolist()}),
        "q16_komi55_top_dqi_counts": q16["dqi"].round(1).value_counts().head(20).to_dict(),
        "positions_with_multiple_dqi_count_ge10": int(len(contradictions)),
        "top_position_contradictions": contradictions.head(15).to_dict(orient="records"),
        "gogod_unique_match_rate": float(len(unique_match) / matched["game_id"].nunique()),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    audit.to_csv(args.output_dir / "matched_move1_positions_gogod.csv", index=False)
    q16.to_csv(args.output_dir / "q16_komi55_move1_gogod.csv", index=False)
    contradictions.to_csv(args.output_dir / "position_contradictions_gogod.csv", index=False)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print()
    print(q16[["game_id", "stem", "dqi"]].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
