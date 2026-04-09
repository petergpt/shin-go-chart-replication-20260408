#!/usr/bin/env python3
"""Rank candidate yearly series against the paper's main yearly series.

The harness is intentionally generic:
- candidate series can come from one or many CSV files
- simple inline specs or CSV/JSON manifests are supported
- train / validation / holdout year ranges are configurable
- raw correlation / MAE are reported on each split
- an uplift-shape MAE is reported after centering each series on the train
  split's pre-AlphaGo mean

Outputs are written under outputs/reverse_engineering.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = ROOT / "outputs/original_r_full/fig1_panel_a_yearly.csv"
DEFAULT_OUTPUT_DIR = ROOT / "outputs/reverse_engineering"
DEFAULT_EVENT_YEAR = 2016
DEFAULT_TRAIN_YEARS = "1951-2008"
DEFAULT_VALIDATION_YEARS = "2009-2015"
DEFAULT_HOLDOUT_YEARS = "2016-2021"
DEFAULT_PRE_MODERN_YEARS = "2006-2015"
DEFAULT_MODERN_YEARS = "2016-2021"
DEFAULT_LATE_YEARS = "2018-2021"
DEFAULT_PEAK_YEAR = 2021


@dataclass(frozen=True)
class SplitSpec:
    name: str
    years: tuple[int, ...]


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    path: Path
    year_col: str = "year"
    value_col: str = "fe"
    series_col: str | None = None
    note: str | None = None


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_corr(a: pd.Series, b: pd.Series) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    if a.nunique(dropna=True) < 2 or b.nunique(dropna=True) < 2:
        return None
    corr = a.corr(b)
    return None if pd.isna(corr) else float(corr)


def _mae(a: pd.Series, b: pd.Series) -> float | None:
    if len(a) == 0:
        return None
    return float((a - b).abs().mean())


def _mean(series: pd.Series) -> float | None:
    if len(series) == 0:
        return None
    value = series.mean()
    return None if pd.isna(value) else float(value)


def _direction_match_rate(a: pd.Series, b: pd.Series) -> float | None:
    if len(a) == 0 or len(b) == 0 or len(a) != len(b):
        return None
    a_dir = np.sign(a.to_numpy())
    b_dir = np.sign(b.to_numpy())
    return float((a_dir == b_dir).mean())


def _first_diff_corr(a: pd.Series, b: pd.Series) -> float | None:
    if len(a) < 3 or len(b) < 3:
        return None
    return _safe_corr(a.diff().dropna(), b.diff().dropna())


def _unique_ordered(values: Iterable[int]) -> tuple[int, ...]:
    seen: set[int] = set()
    ordered: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(int(value))
    return tuple(ordered)


def parse_year_range_spec(spec: str) -> tuple[int, ...]:
    years: list[int] = []
    for token in re.split(r"[;,]\s*|\s+", str(spec).strip()):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                start, end = end, start
            years.extend(range(start, end + 1))
        else:
            years.append(int(token))
    if not years:
        raise ValueError(f"Empty year-range spec: {spec!r}")
    return _unique_ordered(years)


def parse_candidate_spec_text(text: str, *, base_dir: Path | None = None) -> list[CandidateSpec]:
    raw = text.strip()
    if not raw:
        return []
    if raw.startswith("{"):
        return [candidate_spec_from_mapping(json.loads(raw), base_dir=base_dir)]
    if "=" in raw:
        pieces = next(csv.reader([raw], skipinitialspace=True))
        mapping: dict[str, str] = {}
        for piece in pieces:
            if "=" not in piece:
                raise ValueError(f"Invalid candidate spec segment: {piece!r}")
            key, value = piece.split("=", 1)
            mapping[key.strip()] = value.strip()
        return [candidate_spec_from_mapping(mapping, base_dir=base_dir)]
    return [CandidateSpec(name=Path(raw).stem, path=resolve_path(raw, base_dir=base_dir))]


def resolve_path(path_text: str, base_dir: Path | None = None) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path.resolve()
    if base_dir is not None:
        return (base_dir / path).resolve()
    return path.resolve()


def candidate_spec_from_mapping(mapping: dict[str, object], *, base_dir: Path | None = None) -> CandidateSpec:
    def missing(value: object) -> bool:
        return value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == ""

    path_text = mapping.get("path") or mapping.get("csv") or mapping.get("file") or mapping.get("source")
    if missing(path_text):
        raise ValueError("Candidate spec is missing a path/csv/file/source field")
    path = resolve_path(str(path_text), base_dir=base_dir)
    name = str(mapping.get("name") or path.stem)
    year_col = str(mapping.get("year_col") or "year")
    value_col = str(mapping.get("value_col") or mapping.get("fe_col") or "fe")
    series_col = mapping.get("series_col")
    note = mapping.get("note")
    return CandidateSpec(
        name=name,
        path=path,
        year_col=year_col,
        value_col=value_col,
        series_col=None if missing(series_col) else str(series_col),
        note=None if missing(note) else str(note),
    )


def load_manifest(path: Path) -> list[CandidateSpec]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, dict) and "candidates" in data:
            entries = data["candidates"]
        elif isinstance(data, list):
            entries = data
        else:
            entries = [data]
        return [candidate_spec_from_mapping(entry, base_dir=path.parent) for entry in entries]
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
        return [candidate_spec_from_mapping(row, base_dir=path.parent) for row in frame.to_dict("records")]
    raise ValueError(f"Unsupported manifest format: {path}")


def load_target_series(path: Path, year_col: str, value_col: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    missing = [col for col in [year_col, value_col] if col not in frame.columns]
    if missing:
        raise ValueError(f"Target file {path} is missing columns: {missing}")
    out = frame[[year_col, value_col]].rename(columns={year_col: "year", value_col: "value"}).copy()
    out["year"] = pd.to_numeric(out["year"], errors="coerce")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.loc[out["year"].notna() & out["value"].notna()].copy()
    out["year"] = out["year"].astype(int)
    if out["year"].duplicated().any():
        raise ValueError(f"Target file {path} contains duplicate years")
    return out.sort_values("year").reset_index(drop=True)


def load_candidate_frames(spec: CandidateSpec, duplicate_policy: str) -> list[dict[str, object]]:
    if not spec.path.exists():
        raise FileNotFoundError(spec.path)
    frame = pd.read_csv(spec.path)
    missing = [col for col in [spec.year_col, spec.value_col] if col not in frame.columns]
    if missing:
        raise ValueError(f"Candidate file {spec.path} is missing columns: {missing}")

    if spec.series_col is None:
        series_items = [(spec.name, frame)]
    else:
        if spec.series_col not in frame.columns:
            raise ValueError(f"Candidate file {spec.path} is missing series_col {spec.series_col!r}")
        series_items = []
        for series_value, subframe in frame.groupby(spec.series_col, dropna=False):
            if pd.isna(series_value):
                continue
            label = f"{spec.name}:{series_value}"
            series_items.append((label, subframe))

    out: list[dict[str, object]] = []
    for series_name, subframe in series_items:
        series = subframe[[spec.year_col, spec.value_col]].rename(
            columns={spec.year_col: "year", spec.value_col: "value"}
        ).copy()
        series["year"] = pd.to_numeric(series["year"], errors="coerce")
        series["value"] = pd.to_numeric(series["value"], errors="coerce")
        series = series.loc[series["year"].notna() & series["value"].notna()].copy()
        series["year"] = series["year"].astype(int)
        if series.empty:
            raise ValueError(f"Candidate {series_name!r} from {spec.path} has no usable rows")
        if series["year"].duplicated().any():
            if duplicate_policy == "error":
                dups = series.loc[series["year"].duplicated(), "year"].tolist()
                raise ValueError(f"Candidate {series_name!r} from {spec.path} has duplicate years: {sorted(set(dups))}")
            if duplicate_policy == "mean":
                series = series.groupby("year", as_index=False)["value"].mean()
            elif duplicate_policy == "first":
                series = series.drop_duplicates("year", keep="first")
            else:
                raise ValueError(f"Unknown duplicate-policy: {duplicate_policy}")
        series = series.sort_values("year").reset_index(drop=True)
        out.append(
            {
                "name": series_name,
                "path": str(spec.path),
                "note": spec.note,
                "series": series,
                "series_col": spec.series_col,
                "series_value": None if spec.series_col is None else str(series_name).split(":", 1)[-1],
            }
        )
    return out


def uniquify_candidate_names(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: dict[str, int] = {}
    out: list[dict[str, object]] = []
    for candidate in candidates:
        name = str(candidate["candidate_name"])
        count = seen.get(name, 0) + 1
        seen[name] = count
        if count > 1:
            candidate = dict(candidate)
            candidate["candidate_name"] = f"{name}__{count}"
        out.append(candidate)
    return out


def compute_baseline(
    merged_train: pd.DataFrame,
    event_year: int,
    target_col: str,
    candidate_col: str,
) -> tuple[float, float]:
    pre_event = merged_train.loc[merged_train["year"] < event_year]
    baseline_source = pre_event if not pre_event.empty else merged_train
    if baseline_source.empty:
        raise ValueError("Cannot compute a baseline from an empty train split")
    return float(baseline_source[target_col].mean()), float(baseline_source[candidate_col].mean())


def evaluate_candidate(
    candidate_name: str,
    candidate_meta: dict[str, object],
    target: pd.DataFrame,
    split_defs: dict[str, SplitSpec],
    event_year: int,
    pre_modern_years: tuple[int, ...],
    modern_years: tuple[int, ...],
    late_years: tuple[int, ...],
    peak_year: int,
) -> dict[str, object]:
    candidate = candidate_meta["series"].copy()
    merged = target.merge(candidate, on="year", how="inner", suffixes=("_target", "_candidate"))
    merged = merged.sort_values("year").reset_index(drop=True)

    if merged.empty:
        return {
            "candidate_name": candidate_name,
            "source_path": candidate_meta["path"],
            "series_col": candidate_meta.get("series_col"),
            "series_value": candidate_meta.get("series_value"),
            "note": candidate_meta.get("note"),
            "overall_n_years": 0,
        }

    train_years = set(split_defs["train"].years)
    train_merged = merged.loc[merged["year"].isin(train_years)].copy()
    target_anchor, candidate_anchor = compute_baseline(
        train_merged,
        event_year=event_year,
        target_col="value_target",
        candidate_col="value_candidate",
    )

    all_metrics = score_split(
        merged,
        merged["year"].tolist(),
        target_anchor=target_anchor,
        candidate_anchor=candidate_anchor,
        split_name="overall",
    )

    result: dict[str, object] = {
        "candidate_name": candidate_name,
        "source_path": candidate_meta["path"],
        "series_col": candidate_meta.get("series_col"),
        "series_value": candidate_meta.get("series_value"),
        "note": candidate_meta.get("note"),
        "overall_n_years": int(all_metrics["n_years"]),
        "overall_year_min": int(all_metrics["year_min"]) if all_metrics["year_min"] is not None else None,
        "overall_year_max": int(all_metrics["year_max"]) if all_metrics["year_max"] is not None else None,
        "overall_corr": all_metrics["corr"],
        "overall_mae": all_metrics["mae"],
        "overall_uplift_shape_mae": all_metrics["uplift_shape_mae"],
        "overall_uplift_shape_corr": all_metrics["uplift_shape_corr"],
        "overall_first_diff_corr": all_metrics["first_diff_corr"],
        "overall_direction_match_rate": all_metrics["direction_match_rate"],
    }

    for split_name, split in split_defs.items():
        metrics = score_split(
            merged,
            split.years,
            target_anchor=target_anchor,
            candidate_anchor=candidate_anchor,
            split_name=split_name,
        )
        result.update(
            {
                f"{split_name}_n_years": int(metrics["n_years"]),
                f"{split_name}_year_min": int(metrics["year_min"]) if metrics["year_min"] is not None else None,
                f"{split_name}_year_max": int(metrics["year_max"]) if metrics["year_max"] is not None else None,
                f"{split_name}_corr": metrics["corr"],
                f"{split_name}_mae": metrics["mae"],
                f"{split_name}_uplift_shape_mae": metrics["uplift_shape_mae"],
                f"{split_name}_uplift_shape_corr": metrics["uplift_shape_corr"],
                f"{split_name}_first_diff_corr": metrics["first_diff_corr"],
                f"{split_name}_direction_match_rate": metrics["direction_match_rate"],
            }
        )

    modern_metrics = compare_periods(
        merged,
        pre_years=pre_modern_years,
        post_years=modern_years,
        target_anchor=target_anchor,
        candidate_anchor=candidate_anchor,
    )
    late_metrics = compare_means(
        merged,
        years=late_years,
        target_anchor=target_anchor,
        candidate_anchor=candidate_anchor,
    )
    peak_metrics = compare_peak_year(merged, peak_year)
    post_event_metrics = score_split(
        merged,
        [year for year in merged["year"].tolist() if year >= event_year],
        target_anchor=target_anchor,
        candidate_anchor=candidate_anchor,
        split_name="post_event",
    )
    result.update(
        {
            "modern_uplift_target": modern_metrics["target_delta"],
            "modern_uplift_candidate": modern_metrics["candidate_delta"],
            "modern_uplift_error": modern_metrics["delta_error"],
            "modern_uplift_shape_error": modern_metrics["anchored_delta_error"],
            "late_level_target": late_metrics["target_mean"],
            "late_level_candidate": late_metrics["candidate_mean"],
            "late_level_error": late_metrics["mean_error"],
            "late_level_shape_error": late_metrics["anchored_mean_error"],
            "peak_year": peak_year,
            "peak_year_target": peak_metrics["target_value"],
            "peak_year_candidate": peak_metrics["candidate_value"],
            "peak_year_error": peak_metrics["abs_error"],
            "post_event_corr": post_event_metrics["corr"],
            "post_event_mae": post_event_metrics["mae"],
            "post_event_uplift_shape_mae": post_event_metrics["uplift_shape_mae"],
            "post_event_uplift_shape_corr": post_event_metrics["uplift_shape_corr"],
            "post_event_first_diff_corr": post_event_metrics["first_diff_corr"],
            "post_event_direction_match_rate": post_event_metrics["direction_match_rate"],
        }
    )

    return result


def score_split(
    merged: pd.DataFrame,
    years: Iterable[int],
    *,
    target_anchor: float,
    candidate_anchor: float,
    split_name: str,
) -> dict[str, object]:
    years_set = set(int(y) for y in years)
    s = merged.loc[merged["year"].isin(years_set)].copy().sort_values("year")
    if s.empty:
        return {
            "split_name": split_name,
            "n_years": 0,
            "year_min": None,
            "year_max": None,
            "corr": None,
            "mae": None,
            "uplift_shape_mae": None,
            "uplift_shape_corr": None,
            "first_diff_corr": None,
            "direction_match_rate": None,
        }

    uplift_target = s["value_target"] - target_anchor
    uplift_candidate = s["value_candidate"] - candidate_anchor
    return {
        "split_name": split_name,
        "n_years": int(len(s)),
        "year_min": int(s["year"].min()),
        "year_max": int(s["year"].max()),
        "corr": _safe_float(_safe_corr(s["value_target"], s["value_candidate"])),
        "mae": _safe_float(_mae(s["value_target"], s["value_candidate"])),
        "uplift_shape_mae": _safe_float(_mae(uplift_target, uplift_candidate)),
        "uplift_shape_corr": _safe_float(_safe_corr(uplift_target, uplift_candidate)),
        "first_diff_corr": _safe_float(_first_diff_corr(s["value_target"], s["value_candidate"])),
        "direction_match_rate": _safe_float(_direction_match_rate(uplift_target, uplift_candidate)),
    }


def compare_periods(
    merged: pd.DataFrame,
    *,
    pre_years: Iterable[int],
    post_years: Iterable[int],
    target_anchor: float,
    candidate_anchor: float,
) -> dict[str, object]:
    pre = merged.loc[merged["year"].isin(set(int(y) for y in pre_years))].copy()
    post = merged.loc[merged["year"].isin(set(int(y) for y in post_years))].copy()
    if pre.empty or post.empty:
        return {
            "target_delta": None,
            "candidate_delta": None,
            "delta_error": None,
            "anchored_delta_error": None,
        }
    target_delta = _mean(post["value_target"]) - _mean(pre["value_target"])
    candidate_delta = _mean(post["value_candidate"]) - _mean(pre["value_candidate"])
    uplift_target_delta = _mean(post["value_target"] - target_anchor) - _mean(pre["value_target"] - target_anchor)
    uplift_candidate_delta = _mean(post["value_candidate"] - candidate_anchor) - _mean(
        pre["value_candidate"] - candidate_anchor
    )
    return {
        "target_delta": target_delta,
        "candidate_delta": candidate_delta,
        "delta_error": None if target_delta is None or candidate_delta is None else abs(target_delta - candidate_delta),
        "anchored_delta_error": None
        if uplift_target_delta is None or uplift_candidate_delta is None
        else abs(uplift_target_delta - uplift_candidate_delta),
    }


def compare_means(
    merged: pd.DataFrame,
    *,
    years: Iterable[int],
    target_anchor: float,
    candidate_anchor: float,
) -> dict[str, object]:
    subset = merged.loc[merged["year"].isin(set(int(y) for y in years))].copy()
    if subset.empty:
        return {
            "target_mean": None,
            "candidate_mean": None,
            "mean_error": None,
            "anchored_mean_error": None,
        }
    target_mean = _mean(subset["value_target"])
    candidate_mean = _mean(subset["value_candidate"])
    target_shape_mean = _mean(subset["value_target"] - target_anchor)
    candidate_shape_mean = _mean(subset["value_candidate"] - candidate_anchor)
    return {
        "target_mean": target_mean,
        "candidate_mean": candidate_mean,
        "mean_error": None if target_mean is None or candidate_mean is None else abs(target_mean - candidate_mean),
        "anchored_mean_error": None
        if target_shape_mean is None or candidate_shape_mean is None
        else abs(target_shape_mean - candidate_shape_mean),
    }


def compare_peak_year(merged: pd.DataFrame, peak_year: int) -> dict[str, object]:
    subset = merged.loc[merged["year"] == peak_year].copy()
    if subset.empty:
        return {"target_value": None, "candidate_value": None, "abs_error": None}
    target_value = _mean(subset["value_target"])
    candidate_value = _mean(subset["value_candidate"])
    return {
        "target_value": target_value,
        "candidate_value": candidate_value,
        "abs_error": None if target_value is None or candidate_value is None else abs(target_value - candidate_value),
    }


def build_split_defs(train_spec: str, validation_spec: str, holdout_spec: str) -> dict[str, SplitSpec]:
    return {
        "train": SplitSpec("train", parse_year_range_spec(train_spec)),
        "validation": SplitSpec("validation", parse_year_range_spec(validation_spec)),
        "holdout": SplitSpec("holdout", parse_year_range_spec(holdout_spec)),
    }


def validate_splits(split_defs: dict[str, SplitSpec]) -> None:
    seen: set[int] = set()
    for split in split_defs.values():
        overlap = seen.intersection(split.years)
        if overlap:
            raise ValueError(f"Split year ranges overlap at {sorted(overlap)}")
        seen.update(split.years)


def rank_key(row: dict[str, object]) -> tuple[float, float, float, float, float, float]:
    def num(key: str) -> float:
        value = row.get(key)
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return float("inf")
        return float(value)

    return (
        num("validation_uplift_shape_mae"),
        num("validation_mae"),
        -num("validation_corr") if num("validation_corr") != float("inf") else float("inf"),
        num("holdout_uplift_shape_mae"),
        num("holdout_mae"),
        -num("holdout_corr") if num("holdout_corr") != float("inf") else float("inf"),
    )


def flatten_for_csv(row: dict[str, object]) -> dict[str, object]:
    flat = dict(row)
    for key, value in list(flat.items()):
        if isinstance(value, Path):
            flat[key] = str(value)
        elif isinstance(value, tuple):
            flat[key] = ",".join(str(x) for x in value)
    return flat


def collect_candidate_specs(args: argparse.Namespace) -> list[CandidateSpec]:
    specs: list[CandidateSpec] = []

    for manifest_path in args.manifest or []:
        specs.extend(load_manifest(resolve_path(manifest_path)))

    for candidate_text in args.candidate or []:
        specs.extend(parse_candidate_spec_text(candidate_text, base_dir=Path.cwd()))

    for candidate_dir in args.candidate_dir or []:
        base = resolve_path(candidate_dir)
        if not base.exists():
            raise FileNotFoundError(base)
        for path in sorted(base.rglob("*.csv")):
            specs.append(CandidateSpec(name=path.stem, path=path))

    return specs


def dedupe_candidate_specs(specs: list[CandidateSpec]) -> list[CandidateSpec]:
    seen: set[tuple[str, str, str, str | None]] = set()
    out: list[CandidateSpec] = []
    for spec in specs:
        key = (spec.name, str(spec.path), spec.year_col, spec.series_col)
        if key in seen:
            continue
        seen.add(key)
        out.append(spec)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--target-year-col", default="year")
    parser.add_argument("--target-value-col", default="fe")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--train-years", default=DEFAULT_TRAIN_YEARS)
    parser.add_argument("--validation-years", default=DEFAULT_VALIDATION_YEARS)
    parser.add_argument("--holdout-years", default=DEFAULT_HOLDOUT_YEARS)
    parser.add_argument("--event-year", type=int, default=DEFAULT_EVENT_YEAR)
    parser.add_argument("--pre-modern-years", default=DEFAULT_PRE_MODERN_YEARS)
    parser.add_argument("--modern-years", default=DEFAULT_MODERN_YEARS)
    parser.add_argument("--late-years", default=DEFAULT_LATE_YEARS)
    parser.add_argument("--peak-year", type=int, default=DEFAULT_PEAK_YEAR)
    parser.add_argument("--candidate", action="append")
    parser.add_argument("--manifest", action="append")
    parser.add_argument("--candidate-dir", action="append")
    parser.add_argument("--duplicate-policy", choices=["error", "mean", "first"], default="error")
    parser.add_argument("--output-prefix", default="paper_like_metric_wave")
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()

    split_defs = build_split_defs(args.train_years, args.validation_years, args.holdout_years)
    validate_splits(split_defs)
    pre_modern_years = parse_year_range_spec(args.pre_modern_years)
    modern_years = parse_year_range_spec(args.modern_years)
    late_years = parse_year_range_spec(args.late_years)

    target = load_target_series(args.target, args.target_year_col, args.target_value_col)
    candidate_specs = dedupe_candidate_specs(collect_candidate_specs(args))
    if not candidate_specs:
        raise SystemExit(
            "No candidates provided. Use --candidate, --manifest, or --candidate-dir "
            "to point at one or more candidate yearly series."
        )

    resolved_candidates: list[dict[str, object]] = []
    for spec in candidate_specs:
        for candidate_meta in load_candidate_frames(spec, args.duplicate_policy):
            result = evaluate_candidate(
                candidate_meta["name"],
                candidate_meta,
                target,
                split_defs,
                args.event_year,
                pre_modern_years,
                modern_years,
                late_years,
                args.peak_year,
            )
            resolved_candidates.append(result)
    resolved_candidates = uniquify_candidate_names(resolved_candidates)

    ranked = sorted(resolved_candidates, key=rank_key)
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank

    outdir = args.output_dir
    outdir.mkdir(parents=True, exist_ok=True)
    prefix = args.output_prefix
    csv_path = outdir / f"{prefix}_leaderboard.csv"
    json_path = outdir / f"{prefix}_leaderboard.json"

    csv_rows = [flatten_for_csv(row) for row in ranked]
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False, quoting=csv.QUOTE_MINIMAL)

    payload = {
        "target": {
            "path": str(args.target),
            "year_col": args.target_year_col,
            "value_col": args.target_value_col,
            "n_years": int(len(target)),
            "year_min": int(target["year"].min()) if not target.empty else None,
            "year_max": int(target["year"].max()) if not target.empty else None,
        },
        "event_year": args.event_year,
        "pre_modern_years": list(pre_modern_years),
        "modern_years": list(modern_years),
        "late_years": list(late_years),
        "peak_year": args.peak_year,
        "splits": {name: list(split.years) for name, split in split_defs.items()},
        "ranking_basis": [
            "validation_uplift_shape_mae",
            "validation_mae",
            "-validation_corr",
            "holdout_uplift_shape_mae",
            "holdout_mae",
            "-holdout_corr",
        ],
        "candidates": [flatten_for_csv(row) for row in ranked],
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    print(f"Wrote {csv_path}")
    print(f"Wrote {json_path}")
    print(f"Ranked {len(ranked)} candidate series.")
    for row in ranked[: min(args.top_k, len(ranked))]:
        print(
            f"{row['rank']:>3} {row['candidate_name']:<32} "
            f"val_uplift_mae={row.get('validation_uplift_shape_mae')} "
            f"val_corr={row.get('validation_corr')} "
            f"hold_uplift_mae={row.get('holdout_uplift_shape_mae')}"
        )


if __name__ == "__main__":
    main()
