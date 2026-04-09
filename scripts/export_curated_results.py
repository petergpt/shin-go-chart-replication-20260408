#!/usr/bin/env python3
"""Copy the repo-facing curated artifact bundle from scratch outputs."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXPORT_SUFFIXES = {".csv", ".json", ".md", ".txt"}

COPY_MAP = {
    "outputs/original_r_full/fig1_panel_a_yearly.csv": "results/exact_replication/fig1_panel_a_yearly.csv",
    "outputs/original_r_full/fig1_panel_b_monthly.csv": "results/exact_replication/fig1_panel_b_monthly.csv",
    "outputs/original_r_full/fig1_panel_c_yearly.csv": "results/exact_replication/fig1_panel_c_yearly.csv",
    "outputs/original_r_full/fig1_panel_d_monthly.csv": "results/exact_replication/fig1_panel_d_monthly.csv",
    "outputs/original_r_full/fig 1 panel a v01.png": "results/exact_replication/fig1_panel_a_reproduced.png",
    "outputs/original_r_full/fig 1 panel b v01.png": "results/exact_replication/fig1_panel_b_reproduced.png",
    "outputs/original_r_full/table_1_model_1_coefficients.csv": "results/exact_replication/table_1_model_1_coefficients.csv",
    "outputs/original_r_full/table_1_model_2_coefficients.csv": "results/exact_replication/table_1_model_2_coefficients.csv",
    "outputs/original_r_full/table_1_model_n.csv": "results/exact_replication/table_1_model_n.csv",
    "outputs/original_r_full/figure_comparison.json": "results/exact_replication/figure_comparison.json",
    "outputs/reverse_engineering/evaluation_contract.md": "results/reverse_engineering/evaluation_contract.md",
    "outputs/reverse_engineering/wave_002_refinement_candidates.csv": "results/reverse_engineering/wave_002_refinement_candidates.csv",
    "outputs/reverse_engineering/wave_002_refinement_candidates_robustness.csv": "results/reverse_engineering/wave_002_refinement_candidates_robustness.csv",
    "outputs/reverse_engineering/wave_002_refinement_spec.json": "results/reverse_engineering/wave_002_refinement_spec.json",
    "outputs/reverse_engineering/wave_002_refinement_spec_robustness.json": "results/reverse_engineering/wave_002_refinement_spec_robustness.json",
    "outputs/reverse_engineering/wave_002_refinement_search_leaderboard.csv": "results/reverse_engineering/wave_002_refinement_search_leaderboard.csv",
    "outputs/reverse_engineering/wave_002_refinement_robustness_leaderboard.csv": "results/reverse_engineering/wave_002_refinement_robustness_leaderboard.csv",
    "outputs/reverse_engineering/wave_002_monthly_audit_leaderboard.csv": "results/reverse_engineering/wave_002_monthly_audit_leaderboard.csv",
    "outputs/reverse_engineering/wave_002_monthly_audit_monthly_series.csv": "results/reverse_engineering/wave_002_monthly_audit_monthly_series.csv",
    "outputs/reverse_engineering/paper_like_extension/paper_like_raw_2_60_affine_visits_20/combined_yearly_fe.csv": "results/paper_like_extension/combined_yearly_fe.csv",
    "outputs/reverse_engineering/paper_like_extension/paper_like_raw_2_60_affine_visits_20/summary.json": "results/paper_like_extension/summary.json",
    "outputs/reverse_engineering/paper_like_extension/paper_like_raw_2_60_affine_visits_20/paper_like_extension_chart.png": "results/paper_like_extension/paper_like_extension_chart.png",
    "outputs/reverse_engineering/paper_like_extension/paper_like_raw_2_60_affine_visits_20/postprocessed/paper_like_extension_prealphago_centered.png": "results/paper_like_extension/paper_like_extension_prealphago_centered.png",
    "outputs/reverse_engineering/paper_like_extension/paper_like_raw_2_60_affine_visits_20/postprocessed/paper_like_extension_overlay.png": "results/paper_like_extension/paper_like_extension_overlay.png",
    "outputs/reverse_engineering/paper_like_extension/paper_like_raw_2_60_affine_visits_20/postprocessed/paper_like_extension_centered_summary.json": "results/paper_like_extension/paper_like_extension_centered_summary.json",
}


def sanitize_exported_text(path: Path) -> None:
    if path.suffix not in TEXT_EXPORT_SUFFIXES:
        return
    text = path.read_text()
    sanitized = text.replace(f"{ROOT}/", "")
    sanitized = sanitized.replace(
        "outputs/reverse_engineering/wave_002_refinement_candidates.csv",
        "results/reverse_engineering/wave_002_refinement_candidates.csv",
    )
    sanitized = sanitized.replace(
        "outputs/reverse_engineering/wave_002_refinement_candidates_robustness.csv",
        "results/reverse_engineering/wave_002_refinement_candidates_robustness.csv",
    )
    if sanitized != text:
        path.write_text(sanitized)


def main() -> None:
    for src_rel, dst_rel in COPY_MAP.items():
        src = ROOT / src_rel
        dst = ROOT / dst_rel
        if not src.exists():
            raise SystemExit(f"Missing source artifact: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        sanitize_exported_text(dst)
    print(f"Exported {len(COPY_MAP)} curated artifacts.")


if __name__ == "__main__":
    main()
