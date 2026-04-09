#!/usr/bin/env python3
"""Postprocess the frozen paper-like extension into presentation-friendly views.

This script does not change the underlying metric. It only recenters the final
yearly fixed-effects series on a chosen pre-AlphaGo baseline window and writes
derived artifacts that are easier to interpret.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt

GREEN = "#69AA45"
BLUE = "#2A6F9E"
ORANGE = "#D9B25A"
LIGHT_BLUE = "#C9DDF1"
GRAY = "#8E8E8E"
PAPER = "#333333"
ALPHAGO_DATE = date(2016, 3, 15)


@dataclass
class YearRow:
    year: int
    fe: float
    fe_ci_ll: float
    fe_ci_ul: float
    raw: dict[str, str]


def decimal_year(d: date) -> float:
    start = date(d.year, 1, 1)
    end = date(d.year + 1, 1, 1)
    return d.year + ((d - start).days / ((end - start).days))


def read_year_rows(path: Path) -> list[YearRow]:
    rows: list[YearRow] = []
    with path.open() as f:
        for raw in csv.DictReader(f):
            rows.append(
                YearRow(
                    year=int(raw["year"]),
                    fe=float(raw["fe"]),
                    fe_ci_ll=float(raw["fe_ci_ll"]),
                    fe_ci_ul=float(raw["fe_ci_ul"]),
                    raw=dict(raw),
                )
            )
    rows.sort(key=lambda r: r.year)
    return rows


def write_centered_csv(rows: list[YearRow], outpath: Path, baseline_mean: float) -> None:
    fieldnames = list(rows[0].raw.keys()) + [
        "fe_centered",
        "fe_ci_ll_centered",
        "fe_ci_ul_centered",
        "pre_alphago_baseline_mean",
    ]
    with outpath.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            raw = dict(row.raw)
            raw["fe_centered"] = row.fe - baseline_mean
            raw["fe_ci_ll_centered"] = row.fe_ci_ll - baseline_mean
            raw["fe_ci_ul_centered"] = row.fe_ci_ul - baseline_mean
            raw["pre_alphago_baseline_mean"] = baseline_mean
            writer.writerow(raw)


def write_summary_json(
    rows: list[YearRow],
    outpath: Path,
    baseline_mean: float,
    center_start_year: int,
    center_end_year: int,
    latest_date: date | None,
) -> None:
    def mean_for(start_year: int, end_year: int) -> float | None:
        vals = [row.fe for row in rows if start_year <= row.year <= end_year]
        if not vals:
            return None
        return sum(vals) / len(vals)

    recent = {str(row.year): row.fe - baseline_mean for row in rows if row.year >= 2022}
    selected_years = {
        str(row.year): row.fe - baseline_mean
        for row in rows
        if row.year in {2015, 2019, 2021, 2022, 2023, 2024, 2025, 2026}
    }
    pre_mean = mean_for(center_start_year, center_end_year)
    ai_mean = mean_for(2016, 2021)
    latest_year = max(row.year for row in rows)
    latest_year_partial = bool(latest_date and latest_date.year == latest_year and latest_date < date(latest_year, 12, 31))
    payload = {
        "baseline_window": [center_start_year, center_end_year],
        "baseline_mean": baseline_mean,
        "pre_alphago_mean": pre_mean,
        "ai_era_mean_2016_2021": ai_mean,
        "uplift_vs_prealphago_mean": None if pre_mean is None or ai_mean is None else ai_mean - pre_mean,
        "latest_date": latest_date.isoformat() if latest_date else None,
        "latest_year": latest_year,
        "latest_year_partial": latest_year_partial,
        "recent_values_centered": recent,
        "selected_years_centered": selected_years,
    }
    outpath.write_text(json.dumps(payload, indent=2))


def plot_centered_chart(
    rows: list[YearRow],
    baseline_mean: float,
    cutoff_year: int,
    last_date: date | None,
    outpath: Path,
) -> None:
    hist = [row for row in rows if row.year <= cutoff_year]
    ext = [row for row in rows if row.year > cutoff_year]
    last_year = max(row.year for row in rows)
    latest_year_partial = bool(last_date and last_date.year == last_year and last_date < date(last_year, 12, 31))
    last_tick = decimal_year(last_date) if latest_year_partial and last_date else last_year
    last_label = f"{last_year}\n({last_date.strftime('%b')})" if latest_year_partial and last_date else str(last_year)
    alpha_x = decimal_year(ALPHAGO_DATE)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axhline(0, color=GRAY, linewidth=1.0, linestyle=(0, (2, 5)))
    ax.axvspan(alpha_x, cutoff_year + 0.5, alpha=0.14, color=ORANGE, zorder=0)
    ax.axvspan(cutoff_year + 0.5, last_tick, alpha=0.30, color=LIGHT_BLUE, zorder=0)
    ax.axvline(alpha_x, color=ORANGE, linewidth=1.1, linestyle=(0, (3, 3)))
    ax.axvline(cutoff_year + 0.5, color=BLUE, linewidth=1.2, linestyle=(0, (2, 3)))

    if hist:
        ax.errorbar(
            [row.year for row in hist],
            [row.fe - baseline_mean for row in hist],
            yerr=[
                [row.fe - row.fe_ci_ll for row in hist],
                [row.fe_ci_ul - row.fe for row in hist],
            ],
            fmt="o",
            color=GREEN,
            ecolor=GREEN,
            elinewidth=1.25,
            markersize=4.3,
            capsize=0,
        )
    if ext:
        ax.errorbar(
            [row.year for row in ext],
            [row.fe - baseline_mean for row in ext],
            yerr=[
                [row.fe - row.fe_ci_ll for row in ext],
                [row.fe_ci_ul - row.fe for row in ext],
            ],
            fmt="o",
            color=BLUE,
            ecolor=BLUE,
            elinewidth=1.25,
            markersize=4.8,
            capsize=0,
        )
        if len(ext) >= 2:
            ax.plot(
                [row.year for row in ext],
                [row.fe - baseline_mean for row in ext],
                color=BLUE,
                linewidth=1.0,
                alpha=0.7,
            )

    xticks = [1950] + list(range(1960, 2021, 10)) + [2021, last_tick]
    xlabels = ["1950"] + [str(year) for year in range(1960, 2021, 10)] + ["2021", last_label]
    ax.set_xlim(1948, max(last_year + 1, 2027))
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#333333")
    ax.spines["left"].set_color("#333333")
    ax.tick_params(axis="both", labelsize=11, colors="#555555")
    ax.set_xlabel("")
    ax.set_ylabel("Move quality vs\npre-AlphaGo average", color="#444444")
    y_min, y_max = ax.get_ylim()
    y_span = y_max - y_min
    partial_note = ""
    if latest_year_partial and last_date:
        label = last_date.strftime("%b %d, %Y").replace(" 0", " ")
        partial_note = f" {last_year} uses games through {label}."
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


def plot_overlay(
    rows: list[YearRow],
    paper_rows: list[YearRow],
    cutoff_year: int,
    last_date: date | None,
    outpath: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.axhline(0, color=GRAY, linewidth=1.0, linestyle=(0, (2, 5)))
    last_x = decimal_year(last_date) if last_date else float(max(row.year for row in rows))
    alpha_x = decimal_year(ALPHAGO_DATE)
    ax.axvspan(alpha_x, cutoff_year + 0.5, alpha=0.12, color=ORANGE, zorder=0)
    ax.axvspan(cutoff_year + 0.5, last_x, alpha=0.24, color=LIGHT_BLUE, zorder=0)
    ax.axvline(alpha_x, color=ORANGE, linewidth=1.1, linestyle=(0, (3, 3)))
    ax.axvline(cutoff_year + 0.5, color=BLUE, linewidth=1.2, linestyle=(0, (2, 3)))

    ax.plot(
        [row.year for row in paper_rows],
        [row.fe for row in paper_rows],
        color=PAPER,
        linewidth=1.4,
        linestyle="--",
        label="paper",
    )

    hist = [row for row in rows if row.year <= cutoff_year]
    ext = [row for row in rows if row.year > cutoff_year]
    ax.plot([row.year for row in hist], [row.fe for row in hist], color=GREEN, linewidth=1.5, label="paper-like")
    if ext:
        ax.plot([row.year for row in ext], [row.fe for row in ext], color=BLUE, linewidth=1.5)
        ax.scatter([row.year for row in ext], [row.fe for row in ext], color=BLUE, s=18)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="both", labelsize=11, colors="#555555")
    ax.set_ylabel("Relative move quality\n(0 = reference level)", color="#444444")
    y_min, y_max = ax.get_ylim()
    y_span = y_max - y_min
    partial_note = ""
    if last_date and last_date < date(last_date.year, 12, 31):
        label = last_date.strftime("%b %d, %Y").replace(" 0", " ")
        partial_note = f" {last_date.year} uses games through {label}."
    ax.legend(frameon=False, loc="upper left")
    fig.text(
        0.015,
        0.01,
        "Historical line matches the paper closely through 2021; 2022+ is linked GoGoD continuation."
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
    parser.add_argument("--combined-yearly", type=Path, required=True)
    parser.add_argument("--paper-yearly", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--center-start-year", type=int, default=1951)
    parser.add_argument("--center-end-year", type=int, default=2015)
    parser.add_argument("--cutoff-year", type=int, default=2021)
    parser.add_argument("--latest-date")
    args = parser.parse_args()

    outdir = args.output_dir or args.combined_yearly.parent
    outdir.mkdir(parents=True, exist_ok=True)

    rows = read_year_rows(args.combined_yearly)
    baseline_vals = [row.fe for row in rows if args.center_start_year <= row.year <= args.center_end_year]
    if not baseline_vals:
        raise SystemExit("No rows found in the requested centering window.")
    baseline_mean = sum(baseline_vals) / len(baseline_vals)
    latest_date = date.fromisoformat(args.latest_date) if args.latest_date else None

    write_centered_csv(rows, outdir / "combined_yearly_fe_prealphago_centered.csv", baseline_mean)
    write_summary_json(
        rows,
        outdir / "paper_like_extension_centered_summary.json",
        baseline_mean,
        args.center_start_year,
        args.center_end_year,
        latest_date,
    )
    plot_centered_chart(
        rows,
        baseline_mean,
        cutoff_year=args.cutoff_year,
        last_date=latest_date,
        outpath=outdir / "paper_like_extension_prealphago_centered.png",
    )

    if args.paper_yearly and args.paper_yearly.exists():
        paper_rows = read_year_rows(args.paper_yearly)
        plot_overlay(
            rows,
            paper_rows,
            cutoff_year=args.cutoff_year,
            last_date=latest_date,
            outpath=outdir / "paper_like_extension_overlay.png",
        )


if __name__ == "__main__":
    main()
