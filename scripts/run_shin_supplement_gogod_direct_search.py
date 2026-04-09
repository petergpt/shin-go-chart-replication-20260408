#!/usr/bin/env python3
"""Search direct GoGoD sequence filters against released novelty outputs.

This script bypasses go-learning-eras for the human game corpus. It parses the
downloaded GoGoD SGFs directly, builds a cached one-row-per-game sequence table,
and evaluates a small set of plausible inclusion filters against the released
Fig. 1C/D novelty trends.
"""

from __future__ import annotations

import csv
import json
import re
import zipfile
from pathlib import Path

import pandas as pd
import pyreadr

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replicate_shin_panel_ab import month_index_from_ym
from scripts.extend_shin_yearly_proxy import normalise_name
from scripts.run_shin_supplement_sequence_reconstruction import (
    compare_counts,
    compare_fe,
    compute_prefix_novelty_rows,
    fit_monthly_novelty_fe,
    fit_yearly_novelty_fe,
)


SGF_PROP_PATTERNS = {
    key: re.compile(rf"{key}\[([^\]]*)\]")
    for key in ("SZ", "DT", "PB", "PW", "KM", "HA", "RE", "RU")
}
MOVE_PAT = re.compile(r";([BW])\[([a-s]{2})\]")

DEFAULT_ZIPS = [
    Path("/Users/peter/Downloads/0196-1980-Database-Jan2026.zip"),
    Path("/Users/peter/Downloads/1981-1990-Database-Jan2026.zip"),
    Path("/Users/peter/Downloads/1991-2000-Database-Jan2026.zip"),
    Path("/Users/peter/Downloads/2001-2010-Database-Jan2026.zip"),
    Path("/Users/peter/Downloads/2011-2020-Database-Jan2026.zip"),
    ROOT / "data/private/2021-2026-Database-Jan2026.zip",
]


def parse_prop(text: str, key: str) -> str | None:
    match = SGF_PROP_PATTERNS[key].search(text)
    if not match:
        return None
    return match.group(1).replace("\\]", "]").strip()


def parse_iso_date(raw: str | None) -> pd.Timestamp | None:
    if not raw:
        return None
    match = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if not match:
        return None
    ts = pd.to_datetime(match.group(1), errors="coerce")
    if pd.isna(ts):
        return None
    return ts


def parse_float(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except Exception:
        return None


def build_player_id_mapper(players_path: Path):
    players = pd.read_csv(players_path, usecols=["player_id", "name"])
    players["name_norm"] = players["name"].map(normalise_name)
    counts = players["name_norm"].value_counts()
    unique_names = counts[counts == 1].index
    mapping = (
        players.loc[players["name_norm"].isin(unique_names), ["name_norm", "player_id"]]
        .drop_duplicates("name_norm")
        .set_index("name_norm")["player_id"]
        .to_dict()
    )

    def map_name(name: str) -> str:
        norm = normalise_name(name)
        pid = mapping.get(norm)
        return str(pid) if pid is not None else f"name::{norm}"

    return map_name


def parse_direct_gogod_games(cache_path: Path, players_path: Path) -> pd.DataFrame:
    if cache_path.exists():
        df = pd.read_csv(cache_path)
        df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
        df["opening_moves"] = df["opening"].fillna("").map(lambda x: [tok for tok in str(x).split(";") if tok])
        return df

    map_name = build_player_id_mapper(players_path)
    rows: list[dict[str, object]] = []

    for zip_path in DEFAULT_ZIPS:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                if not member.endswith(".sgf"):
                    continue
                text = zf.read(member).decode("utf-8", "ignore")

                size = parse_prop(text, "SZ")
                if size != "19":
                    continue

                game_date = parse_iso_date(parse_prop(text, "DT"))
                if game_date is None or game_date < pd.Timestamp("1950-01-01") or game_date > pd.Timestamp("2021-10-31"):
                    continue

                pb = parse_prop(text, "PB")
                pw = parse_prop(text, "PW")
                if not pb or not pw:
                    continue

                moves = [coord for _, coord in MOVE_PAT.findall(text)][:50]
                if len(moves) < 35:
                    continue

                stem = Path(member).stem
                year_month = game_date.strftime("%Y-%m")
                rows.append(
                    {
                        "game_key": stem,
                        "archive_member": member,
                        "game_date": game_date,
                        "year": int(game_date.year),
                        "year_month": year_month,
                        "month_index": int(month_index_from_ym(year_month)),
                        "player_name_black": normalise_name(pb),
                        "player_name_white": normalise_name(pw),
                        "player_id_black": map_name(pb),
                        "player_id_white": map_name(pw),
                        "komi": parse_float(parse_prop(text, "KM")),
                        "handicap": parse_float(parse_prop(text, "HA")),
                        "result": parse_prop(text, "RE") or "?",
                        "rules": parse_prop(text, "RU"),
                        "opening": ";".join(moves),
                    }
                )

    df = pd.DataFrame(rows).sort_values(["game_date", "game_key"]).reset_index(drop=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False, quoting=csv.QUOTE_MINIMAL)
    df["opening_moves"] = df["opening"].map(lambda x: [tok for tok in str(x).split(";") if tok])
    return df


def apply_variant(df: pd.DataFrame, variant: str) -> pd.DataFrame:
    work = df.copy()
    if variant == "all":
        pass
    elif variant == "ha_zero":
        work = work.loc[work["handicap"].fillna(0).eq(0)].copy()
    elif variant == "ha_zero_komi_known":
        work = work.loc[work["handicap"].fillna(0).eq(0) & work["komi"].notna()].copy()
    elif variant == "ha_zero_komi_pos":
        work = work.loc[work["handicap"].fillna(0).eq(0) & work["komi"].fillna(-1).gt(0)].copy()
    elif variant == "ha_zero_result_known":
        work = work.loc[work["handicap"].fillna(0).eq(0) & work["result"].fillna("?").ne("?")].copy()
    elif variant == "ha_zero_komi_pos_result_known":
        work = work.loc[
            work["handicap"].fillna(0).eq(0)
            & work["komi"].fillna(-1).gt(0)
            & work["result"].fillna("?").ne("?")
        ].copy()
    elif variant == "ha_zero_komi_pos_standard_rules":
        rules_norm = work["rules"].fillna("").str.lower()
        standard = rules_norm.str.contains("japanese|chinese|korean")
        work = work.loc[work["handicap"].fillna(0).eq(0) & work["komi"].fillna(-1).gt(0) & standard].copy()
    else:
        raise ValueError(f"Unknown variant: {variant}")
    return work.sort_values(["game_date", "game_key"]).reset_index(drop=True)


def main() -> None:
    output_dir = ROOT / "outputs/gogod_direct_sequence_search"
    cache_path = output_dir / "gogod_direct_games.csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    games = parse_direct_gogod_games(cache_path, ROOT / "public_refs/go_learning_eras/data/players.csv")
    released_yearly = pd.read_csv(ROOT / "outputs/original_r_full/fig1_panel_c_yearly.csv")
    released_monthly = pd.read_csv(ROOT / "outputs/original_r_full/fig1_panel_d_monthly.csv")

    osf_dt = pyreadr.read_r(str(ROOT / "osf/shin et al 2023 data v001.RData"))["dt"][["game_id", "game_date"]].drop_duplicates()
    osf_dt["game_date"] = pd.to_datetime(osf_dt["game_date"], errors="coerce")
    osf_dt = osf_dt.loc[osf_dt["game_date"].notna()].copy()
    osf_dt["year"] = osf_dt["game_date"].dt.year.astype(int)
    osf_counts = osf_dt.groupby("year").size()

    variants = [
        "all",
        "ha_zero",
        "ha_zero_komi_known",
        "ha_zero_komi_pos",
        "ha_zero_result_known",
        "ha_zero_komi_pos_result_known",
        "ha_zero_komi_pos_standard_rules",
    ]

    rows: list[dict[str, object]] = []
    best_payload: dict[str, pd.DataFrame] | None = None
    best_score: tuple[float, float, float, float] | None = None

    for variant in variants:
        candidate = apply_variant(games, variant)
        candidate["opening_moves"] = candidate["opening"].map(lambda x: [tok for tok in str(x).split(";") if tok])
        novelty_rows, _ = compute_prefix_novelty_rows(candidate)
        yearly = fit_yearly_novelty_fe(novelty_rows)
        monthly = fit_monthly_novelty_fe(novelty_rows)
        yearly_cmp = compare_fe(yearly, released_yearly, "year")
        monthly_cmp = compare_fe(monthly, released_monthly, "month_index")
        count_cmp = compare_counts(candidate, osf_counts)
        row = {
            "variant": variant,
            "n_games": int(len(candidate)),
            "yearly_corr": yearly_cmp.get("corr", float("nan")),
            "yearly_mae": yearly_cmp.get("mae", float("nan")),
            "monthly_corr": monthly_cmp.get("corr", float("nan")),
            "monthly_mae": monthly_cmp.get("mae", float("nan")),
            "count_corr": count_cmp["game_count_corr"],
            "count_mae": count_cmp["game_count_mae"],
        }
        rows.append(row)

        score = (
            float(row["yearly_corr"]),
            float(row["monthly_corr"]),
            -float(row["yearly_mae"]),
            -float(row["monthly_mae"]),
        )
        if best_score is None or score > best_score:
            best_score = score
            best_payload = {
                "candidate": candidate.copy(),
                "novelty_rows": novelty_rows.copy(),
                "yearly": yearly.copy(),
                "monthly": monthly.copy(),
                "row": pd.DataFrame([row]),
            }

    score_df = pd.DataFrame(rows).sort_values(["yearly_corr", "monthly_corr"], ascending=[False, False])
    score_df.to_csv(output_dir / "variant_scores.csv", index=False)

    assert best_payload is not None
    best_variant = str(best_payload["row"].iloc[0]["variant"])
    best_payload["candidate"].drop(columns=["opening_moves"], errors="ignore").to_csv(
        output_dir / "best_variant_games.csv",
        index=False,
        quoting=csv.QUOTE_MINIMAL,
    )
    best_payload["novelty_rows"].to_csv(output_dir / "best_variant_novelty_rows.csv", index=False)
    best_payload["yearly"].to_csv(output_dir / "best_variant_fig1c_yearly.csv", index=False)
    best_payload["monthly"].to_csv(output_dir / "best_variant_fig1d_monthly.csv", index=False)

    summary = {
        "parsed_games": int(len(games)),
        "variants": rows,
        "best_variant": rows[[r["variant"] for r in rows].index(best_variant)],
        "cache_path": str(cache_path),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
