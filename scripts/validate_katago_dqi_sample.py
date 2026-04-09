#!/usr/bin/env python3
"""Validate a direct KataGo DQI reconstruction on a matched historical sample."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import pandas as pd
from sgfmill import sgf

ROOT = Path(__file__).resolve().parents[1]

import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.extend_shin_yearly_proxy import (
    build_bridge_crosswalk,
    load_gle_games,
    load_osf_dt,
    match_gle_games_to_osf,
)

GTP_COLS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


def sgf_coord_to_gtp(move: str) -> str:
    x = ord(move[0]) - ord("a")
    y = ord(move[1]) - ord("a")
    return f"{GTP_COLS[x]}{19 - y}"


def load_game_from_sgf(sgf_path: Path, move_count: int, game_id: int | None = None) -> pd.Series:
    game = sgf.Sgf_game.from_bytes(sgf_path.read_bytes())
    root = game.get_root()

    if game.get_size() != 19:
        raise RuntimeError(f"Expected 19x19 SGF, got {game.get_size()} from {sgf_path}")

    date_text = (root.get("DT") or "")[:10]
    game_date = pd.to_datetime(date_text, errors="coerce")
    if pd.isna(game_date):
        raise RuntimeError(f"Could not parse SGF date from {sgf_path}: {date_text!r}")

    komi_raw = root.get("KM")
    try:
        komi = float(komi_raw)
    except Exception as exc:
        raise RuntimeError(f"Could not parse SGF komi from {sgf_path}: {komi_raw!r}") from exc

    opening_moves: list[str] = []
    for node in game.get_main_sequence()[1:]:
        _, move = node.get_move()
        if move is None:
            continue
        row, col = move
        opening_moves.append(f"{chr(ord('a') + col)}{chr(ord('a') + (18 - row))}")
        if len(opening_moves) >= move_count:
            break

    if len(opening_moves) < move_count:
        raise RuntimeError(
            f"SGF {sgf_path} contains only {len(opening_moves)} playable moves, need {move_count}"
        )

    return pd.Series(
        {
            "game_id": game_id if game_id is not None else -1,
            "game_key": sgf_path.stem,
            "game_date": game_date,
            "komi": komi,
            "opening_moves": opening_moves,
            "source": "raw_sgf",
            "sgf_path": str(sgf_path),
        }
    )


def select_best_move_info(move_infos: list[dict]) -> dict:
    return max(
        move_infos,
        key=lambda info: (
            int(info.get("visits", -1)),
            -int(info.get("order", 10**9)),
        ),
    )


class KataGoAnalysis:
    def __init__(
        self,
        katago_path: Path,
        config_path: Path,
        model_path: Path,
        override_config: list[str] | None = None,
    ) -> None:
        cmd = [str(katago_path), "analysis", "-config", str(config_path), "-model", str(model_path)]
        for entry in override_config or []:
            cmd.extend(["-override-config", entry])
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._wait_until_ready()

    def _wait_until_ready(self) -> None:
        assert self.proc.stderr is not None
        while True:
            line = self.proc.stderr.readline()
            if line == "":
                raise RuntimeError("KataGo exited before becoming ready")
            if "Started, ready to begin handling requests" in line:
                return

    def query(self, payload: dict) -> dict:
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if line == "":
                raise RuntimeError("KataGo exited unexpectedly while waiting for response")
            resp = json.loads(line)
            if resp.get("id") != payload["id"]:
                continue
            if "error" in resp:
                raise RuntimeError(f"KataGo query failed for {payload['id']}: {resp}")
            if resp.get("isDuringSearch") is False:
                return resp

    def close(self) -> None:
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def choose_game(matched_games: pd.DataFrame, move_count: int, game_id: int | None = None, candidate_index: int = 0) -> pd.Series:
    candidates = matched_games.copy()
    candidates = candidates.loc[candidates["opening_moves"].map(len) >= move_count].copy()
    candidates = candidates.loc[candidates["komi"].fillna(0).astype(float).between(5.5, 7.5)].copy()
    if game_id is not None:
        candidates = candidates.loc[candidates["game_id"] == game_id].copy()
    if candidates.empty:
        raise RuntimeError("No matched game with sufficient opening moves and standard komi found")
    candidates = candidates.sort_values(["game_date", "game_id"])
    if candidate_index >= len(candidates):
        raise RuntimeError(f"candidate_index {candidate_index} out of range for {len(candidates)} candidates")
    return candidates.iloc[candidate_index]


def perspective_winrate(black_winrate: float, player: str) -> float:
    return black_winrate if player == "B" else 1.0 - black_winrate


def build_base_query(game: pd.Series, gtp_moves: list[tuple[str, str]], rules: str, max_visits: int) -> dict:
    return {
        "moves": gtp_moves,
        "initialStones": [],
        "rules": rules,
        "komi": float(game["komi"]),
        "boardXSize": 19,
        "boardYSize": 19,
        "maxVisits": max_visits,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--osf-data", type=Path, default=ROOT / "osf/shin et al 2023 data v001.RData")
    parser.add_argument("--gle-games", type=Path, default=ROOT / "public_refs/go_learning_eras/data/games.csv")
    parser.add_argument("--gle-players", type=Path, default=ROOT / "public_refs/go_learning_eras/data/players.csv")
    parser.add_argument("--katago-path", type=Path, default=Path("/opt/homebrew/bin/katago"))
    parser.add_argument(
        "--katago-config",
        type=Path,
        default=Path("/opt/homebrew/Cellar/katago/1.16.4/share/katago/configs/analysis_example.cfg"),
    )
    parser.add_argument(
        "--katago-model",
        type=Path,
        default=Path("/opt/homebrew/Cellar/katago/1.16.4/share/katago/g170e-b20c256x2-s5303129600-d1228401921.bin.gz"),
    )
    parser.add_argument("--rules", default="japanese")
    parser.add_argument("--moves", type=int, default=20)
    parser.add_argument("--max-visits", type=int, default=1000)
    parser.add_argument("--game-id", type=int)
    parser.add_argument("--candidate-index", type=int, default=0)
    parser.add_argument("--method", choices=["child", "afterstate"], default="child")
    parser.add_argument("--sgf-path", type=Path, help="Use a raw SGF instead of matched go-learning-eras moves")
    parser.add_argument("--override-config", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/katago_validation")
    args = parser.parse_args()

    osf_dt = load_osf_dt(args.osf_data)
    if args.sgf_path is not None:
        game = load_game_from_sgf(args.sgf_path, move_count=args.moves, game_id=args.game_id)
    else:
        gle_games = load_gle_games(args.gle_players, args.gle_games)
        crosswalk = build_bridge_crosswalk(osf_dt, gle_games)
        matched_games = match_gle_games_to_osf(osf_dt, gle_games, crosswalk)
        game = choose_game(
            matched_games,
            move_count=args.moves,
            game_id=args.game_id,
            candidate_index=args.candidate_index,
        )

    opening_moves = game["opening_moves"][: args.moves]
    gtp_moves = [("B" if i % 2 == 0 else "W", sgf_coord_to_gtp(mv)) for i, mv in enumerate(opening_moves)]

    katago = KataGoAnalysis(
        args.katago_path,
        args.katago_config,
        args.katago_model,
        override_config=args.override_config,
    )
    rows: list[dict[str, object]] = []

    try:
        for move_number in range(1, args.moves + 1):
            player = "B" if move_number % 2 == 1 else "W"
            actual_move = gtp_moves[move_number - 1][1]
            turn_before_move = move_number - 1
            prefix_moves = gtp_moves[:turn_before_move]

            best_payload = build_base_query(game, gtp_moves, args.rules, args.max_visits)
            best_payload.update({"id": f"best-{move_number}", "analyzeTurns": [turn_before_move]})
            best_resp = katago.query(best_payload)
            best_info = select_best_move_info(best_resp["moveInfos"])

            if args.method == "child":
                forced_payload = build_base_query(game, gtp_moves, args.rules, args.max_visits)
                forced_payload.update(
                    {
                        "id": f"actual-{move_number}",
                        "analyzeTurns": [turn_before_move],
                        "allowMoves": [{"player": player, "moves": [actual_move], "untilDepth": 1}],
                    }
                )
                forced_resp = katago.query(forced_payload)
                forced_info = forced_resp["moveInfos"][0]
                best_wr = perspective_winrate(best_info["winrate"], player)
                actual_wr = perspective_winrate(forced_info["winrate"], player)
            else:
                actual_after_payload = build_base_query(
                    game,
                    prefix_moves + [(player, actual_move)],
                    args.rules,
                    args.max_visits,
                )
                actual_after_payload.update({"id": f"actual-after-{move_number}"})
                actual_after_resp = katago.query(actual_after_payload)

                best_after_payload = build_base_query(
                    game,
                    prefix_moves + [(player, best_info["move"])],
                    args.rules,
                    args.max_visits,
                )
                best_after_payload.update({"id": f"best-after-{move_number}"})
                best_after_resp = katago.query(best_after_payload)

                best_wr = perspective_winrate(best_after_resp["rootInfo"]["winrate"], player)
                actual_wr = perspective_winrate(actual_after_resp["rootInfo"]["winrate"], player)

            dqi_calc = 100.0 - 100.0 * (best_wr - actual_wr)

            osf_row = osf_dt.loc[
                (osf_dt["game_id"] == game["game_id"]) & (osf_dt["move_number"] == move_number),
                ["dqi", "player_id", "matches_ai_move"],
            ]
            if osf_row.empty:
                continue
            osf_row = osf_row.iloc[0]

            rows.append(
                {
                    "game_id": int(game["game_id"]),
                    "game_date": str(game["game_date"].date()),
                    "move_number": move_number,
                    "method": args.method,
                    "player_to_move": player,
                    "actual_move": actual_move,
                    "best_move": best_info["move"],
                    "best_black_winrate": best_info["winrate"] if args.method == "child" else None,
                    "actual_black_winrate": forced_info["winrate"] if args.method == "child" else None,
                    "best_player_winrate": best_wr,
                    "actual_player_winrate": actual_wr,
                    "dqi_calc": dqi_calc,
                    "dqi_osf": float(osf_row["dqi"]),
                    "dqi_abs_err": abs(dqi_calc - float(osf_row["dqi"])),
                    "matches_ai_move_osf": osf_row["matches_ai_move"],
                    "osf_player_id": str(osf_row["player_id"]),
                }
            )
    finally:
        katago.close()

    outdir = args.output_dir
    outdir.mkdir(parents=True, exist_ok=True)
    out_csv = outdir / "katago_sample_validation.csv"
    out_meta = outdir / "katago_sample_validation_meta.json"

    result = pd.DataFrame(rows)
    result.to_csv(out_csv, index=False)

    summary = {
        "game_id": int(game["game_id"]),
        "game_key": str(game["game_key"]),
        "game_date": str(game["game_date"].date()),
        "komi": float(game["komi"]),
        "rules_assumed": args.rules,
        "moves_evaluated": int(len(result)),
        "max_visits": int(args.max_visits),
        "katago_model": str(args.katago_model),
        "method": args.method,
        "override_config": args.override_config,
        "mean_abs_error": float(result["dqi_abs_err"].mean()) if not result.empty else None,
        "corr": float(result["dqi_calc"].corr(result["dqi_osf"])) if len(result) >= 2 else None,
        "move1_mae": float(result.loc[result["move_number"] == 1, "dqi_abs_err"].mean()) if not result.empty else None,
        "nonmove1_mae": float(result.loc[result["move_number"] > 1, "dqi_abs_err"].mean()) if not result.empty else None,
        "nonmove1_corr": (
            float(result.loc[result["move_number"] > 1, "dqi_calc"].corr(result.loc[result["move_number"] > 1, "dqi_osf"]))
            if (result["move_number"] > 1).sum() >= 2
            else None
        ),
        "sgf_path": str(args.sgf_path) if args.sgf_path is not None else None,
    }
    out_meta.write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    if not result.empty:
        print(result[["move_number", "actual_move", "best_move", "dqi_calc", "dqi_osf", "dqi_abs_err"]].to_string(index=False))


if __name__ == "__main__":
    main()
