#!/usr/bin/env python3
"""Probe whether stochastic KataGo move-1 analysis can reproduce OSF DQI buckets."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

GTP_COLS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"


def perspective_winrate(black_winrate: float, player: str) -> float:
    return black_winrate if player == "B" else 1.0 - black_winrate


def select_best_move_info(move_infos: list[dict]) -> dict:
    return max(
        move_infos,
        key=lambda info: (
            int(info.get("visits", -1)),
            -int(info.get("order", 10**9)),
        ),
    )


class KataGoAnalysis:
    def __init__(self, katago_path: Path, config_path: Path, model_path: Path) -> None:
        cmd = [str(katago_path), "analysis", "-config", str(config_path), "-model", str(model_path)]
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
            if resp.get("id") == payload["id"] and resp.get("isDuringSearch") is False:
                return resp

    def close(self) -> None:
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def build_base_payload(max_visits: int, rules: str, komi: float) -> dict:
    return {
        "moves": [],
        "initialStones": [],
        "rules": rules,
        "komi": komi,
        "boardXSize": 19,
        "boardYSize": 19,
        "maxVisits": max_visits,
    }


def run_wave(
    katago: KataGoAnalysis,
    wave_name: str,
    method: str,
    repeats: int,
    max_visits: int,
    rules: str,
    komi: float,
    actual_move: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for trial in range(repeats):
        best_payload = build_base_payload(max_visits=max_visits, rules=rules, komi=komi)
        best_payload.update({"id": f"{wave_name}-best-{trial}", "analyzeTurns": [0]})
        best_resp = katago.query(best_payload)
        best_info = select_best_move_info(best_resp["moveInfos"])

        if method == "child":
            actual_payload = build_base_payload(max_visits=max_visits, rules=rules, komi=komi)
            actual_payload.update(
                {
                    "id": f"{wave_name}-actual-{trial}",
                    "analyzeTurns": [0],
                    "allowMoves": [{"player": "B", "moves": [actual_move], "untilDepth": 1}],
                }
            )
            actual_resp = katago.query(actual_payload)
            actual_info = actual_resp["moveInfos"][0]
            best_wr = perspective_winrate(float(best_info["winrate"]), "B")
            actual_wr = perspective_winrate(float(actual_info["winrate"]), "B")
        else:
            actual_payload = build_base_payload(max_visits=max_visits, rules=rules, komi=komi)
            actual_payload.update(
                {
                    "id": f"{wave_name}-actual-{trial}",
                    "moves": [("B", actual_move)],
                }
            )
            actual_resp = katago.query(actual_payload)

            best_after_payload = build_base_payload(max_visits=max_visits, rules=rules, komi=komi)
            best_after_payload.update(
                {
                    "id": f"{wave_name}-best-after-{trial}",
                    "moves": [("B", best_info["move"])],
                }
            )
            best_after_resp = katago.query(best_after_payload)

            best_wr = perspective_winrate(float(best_after_resp["rootInfo"]["winrate"]), "B")
            actual_wr = perspective_winrate(float(actual_resp["rootInfo"]["winrate"]), "B")

        dqi_calc = 100.0 - 100.0 * (best_wr - actual_wr)
        rows.append(
            {
                "wave_name": wave_name,
                "method": method,
                "trial": trial,
                "actual_move": actual_move,
                "best_move": best_info["move"],
                "best_visits": int(best_info["visits"]),
                "best_player_winrate": best_wr,
                "actual_player_winrate": actual_wr,
                "dqi_calc": dqi_calc,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
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
    parser.add_argument("--max-visits", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--rules", default="japanese")
    parser.add_argument("--komi", type=float, default=5.5)
    parser.add_argument("--actual-move", default="Q16")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/katago_validation/move1_stochastic_probe_10k",
    )
    args = parser.parse_args()

    katago = KataGoAnalysis(args.katago_path, args.katago_config, args.katago_model)
    try:
        rows = []
        rows.extend(
            run_wave(
                katago=katago,
                wave_name="default_child_10000",
                method="child",
                repeats=args.repeats,
                max_visits=args.max_visits,
                rules=args.rules,
                komi=args.komi,
                actual_move=args.actual_move,
            )
        )
        rows.extend(
            run_wave(
                katago=katago,
                wave_name="default_after_10000",
                method="afterstate",
                repeats=args.repeats,
                max_visits=args.max_visits,
                rules=args.rules,
                komi=args.komi,
                actual_move=args.actual_move,
            )
        )
    finally:
        katago.close()

    df = pd.DataFrame(rows)
    summary: dict[str, object] = {}
    for wave_name, chunk in df.groupby("wave_name"):
        summary[wave_name] = {
            "method": chunk["method"].iloc[0],
            "repeats": int(len(chunk)),
            "best_move_counts": chunk["best_move"].value_counts().to_dict(),
            "min_dqi": float(chunk["dqi_calc"].min()),
            "p05_dqi": float(chunk["dqi_calc"].quantile(0.05)),
            "median_dqi": float(chunk["dqi_calc"].median()),
            "p95_dqi": float(chunk["dqi_calc"].quantile(0.95)),
            "max_dqi": float(chunk["dqi_calc"].max()),
            "count_ge_106_2": int((chunk["dqi_calc"] >= 106.2).sum()),
            "count_ge_114_7": int((chunk["dqi_calc"] >= 114.7).sum()),
        }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output_dir / "move1_stochastic_probe_10k.csv", index=False)
    (args.output_dir / "move1_stochastic_probe_10k_summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
