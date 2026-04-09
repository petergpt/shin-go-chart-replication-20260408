args <- commandArgs(trailingOnly = TRUE)

get_arg_value <- function(flag, default = NULL) {
  idx <- match(flag, args)
  if (is.na(idx) || idx == length(args)) {
    return(default)
  }
  args[[idx + 1]]
}

project_root <- normalizePath(get_arg_value("--project-root", getwd()), mustWork = TRUE)
output_dir <- get_arg_value(
  "--output-dir",
  file.path(project_root, "outputs", "supplement_public_partial_r")
)
if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
}
output_dir <- normalizePath(output_dir, mustWork = TRUE)

suppressPackageStartupMessages({
  library(data.table)
  library(ggplot2)
  library(lfe)
  library(coefplot)
  library(lubridate)
  library(lemon)
  library(gridExtra)
  library(kim)
})

load(file.path(project_root, "osf", "shin et al 2023 data v001.RData"))
load(file.path(project_root, "osf", "shin et al 2023 simulated ai move data v001.RData"))

dt <- as.data.table(dt)
simulated_ai_move_data <- as.data.table(simulated_ai_move_data)

dt[, year := as.factor(substr(game_date, 1, 4))]
dt[, year_month := substr(game_date, 1, 7)]
dt[, month_index := as.factor(
  (as.numeric(substr(year_month, 1, 4)) - 1950) * 12 +
    as.numeric(substr(year_month, 6, 7))
)]

alphago_defeat_sedol_date <- as.Date("2016-03-15")
alphago_defeat_sedol_date_as_decimal_year <- lubridate::decimal_date(
  alphago_defeat_sedol_date
)
last_date_observed_to_decimal_year <- lubridate::decimal_date(
  as.Date(tail(unique(dt[, game_date]), 1))
)
alphago_defeat_sedol_month_index <- as.numeric(
  dt[year_month == "2016-03", unique(month_index)]
)
year_month_min_and_max <- c(head(unique(dt[, year_month]), 1), tail(unique(dt[, year_month]), 1))
monthly_fe_plot_x_axis_range <- (
  (as.numeric(substr(year_month_min_and_max, 1, 4)) - 1950) * 12 +
    as.numeric(substr(year_month_min_and_max, 6, 7))
)
monthly_fe_plot_x_axis_tick_mark_year_months <- c(
  paste0(seq(1950, 2010, 10), "-01"),
  tail(unique(dt[, year_month]), 1)
)
monthly_fe_plot_x_axis_tick_mark_month_indices <- (
  (as.numeric(substr(monthly_fe_plot_x_axis_tick_mark_year_months, 1, 4)) - 1950) * 12 +
    as.numeric(substr(monthly_fe_plot_x_axis_tick_mark_year_months, 6, 7))
)
monthly_fe_plot_x_axis_tick_mark_labels <- c(
  paste0(seq(1950, 2010, 10), "\n(Jan)"),
  "2021\n(Oct)"
)

extract_coef_frame <- function(model, prefix, index_name) {
  coefplot_obj <- ggplot_build(
    coefplot::coefplot(model, outerCI = qnorm(0.95 / 2 + 0.5), innerCI = 0)
  )
  idx <- as.numeric(gsub(prefix, "", coefplot_obj$layout$panel_params[[1]]$y.sec$breaks))
  data.table(
    index = idx,
    fe = coefplot_obj$data[[2]]$x,
    fe_ci_ll = coefplot_obj$data[[2]]$xmin,
    fe_ci_ul = coefplot_obj$data[[2]]$xmax
  )[
    , (index_name) := index
  ][
    , index := NULL
  ][]
}

fit_yearly_fe <- function(source_dt, value_col) {
  aggregated <- na.omit(source_dt[, .(
    value = median(get(value_col), na.rm = TRUE)
  ), keyby = c("player_id", "year")])
  model <- felm(value ~ year | player_id | 0 | player_id, data = aggregated)
  list(
    aggregated = aggregated,
    model = model,
    fe = extract_coef_frame(model, "year", "year")
  )
}

fit_monthly_fe <- function(source_dt, value_col) {
  aggregated <- na.omit(source_dt[, .(
    value = median(get(value_col), na.rm = TRUE)
  ), keyby = c("player_id", "year_month", "month_index")])
  model <- felm(value ~ month_index | player_id | 0 | player_id, data = aggregated)
  list(
    aggregated = aggregated,
    model = model,
    fe = extract_coef_frame(model, "month_index", "month_index")
  )
}

pretty_limits <- function(min_val, max_val, step) {
  c(floor(min_val / step) * step, ceiling(max_val / step) * step)
}

make_yearly_plot <- function(plot_dt, y_limits, y_breaks, color, point_size = 2.5, title = NULL) {
  g <- ggplot(data = plot_dt)
  g <- g + annotate(
    geom = "rect", fill = "orange", alpha = 0.3,
    xmin = alphago_defeat_sedol_date_as_decimal_year,
    xmax = last_date_observed_to_decimal_year,
    ymin = y_limits[1], ymax = y_limits[2]
  )
  g <- g + geom_segment(
    aes(
      x = alphago_defeat_sedol_date_as_decimal_year,
      xend = alphago_defeat_sedol_date_as_decimal_year,
      y = y_limits[1],
      yend = y_limits[2]
    ),
    linetype = "dashed",
    color = "red",
    linewidth = 0.7
  )
  g <- g + geom_point(aes(x = year, y = fe), size = point_size, color = color)
  g <- g + geom_errorbar(
    aes(x = year, ymin = fe_ci_ll, ymax = fe_ci_ul),
    width = 0,
    linewidth = 0.7,
    color = color
  )
  g <- g + scale_x_continuous(
    expand = expansion(add = c(0, 2)),
    limits = c(1948, 2022),
    breaks = c(1950, seq(1960, 2010, 10), last_date_observed_to_decimal_year),
    labels = c(1950, seq(1960, 2010, 10), "2021\n(Oct)")
  )
  g <- g + scale_y_continuous(limits = y_limits, breaks = y_breaks)
  g <- g + theme_kim(base_size = 18, axis_tick_font_size = 16)
  g <- g + lemon::coord_capped_cart(ylim = y_limits, bottom = "both", left = "both")
  g <- g + theme(
    axis.title.x = element_blank(),
    axis.title.y = element_blank(),
    plot.title = element_text(hjust = 0.5, size = 16)
  )
  if (!is.null(title)) {
    g <- g + ggtitle(title)
  }
  g
}

make_monthly_plot <- function(plot_dt, y_limits, y_breaks, color, point_size = 0.5, linewidth = 0.2, title = NULL) {
  g <- ggplot(data = plot_dt)
  g <- g + annotate(
    geom = "rect", fill = "orange", alpha = 0.3,
    xmin = alphago_defeat_sedol_month_index,
    xmax = max(plot_dt[, month_index]),
    ymin = y_limits[1], ymax = y_limits[2]
  )
  g <- g + geom_segment(
    aes(
      x = alphago_defeat_sedol_month_index,
      xend = alphago_defeat_sedol_month_index,
      y = y_limits[1],
      yend = y_limits[2]
    ),
    linetype = "dashed",
    color = "red",
    linewidth = 0.7
  )
  g <- g + geom_point(aes(x = month_index, y = fe), size = point_size, color = color)
  g <- g + geom_errorbar(
    aes(x = month_index, ymin = fe_ci_ll, ymax = fe_ci_ul),
    width = 0,
    linewidth = linewidth,
    color = color
  )
  g <- g + scale_x_continuous(
    expand = expansion(add = c(0, 0)),
    limits = monthly_fe_plot_x_axis_range + c(-24, 36),
    breaks = monthly_fe_plot_x_axis_tick_mark_month_indices,
    labels = monthly_fe_plot_x_axis_tick_mark_labels
  )
  g <- g + scale_y_continuous(limits = y_limits, breaks = y_breaks)
  g <- g + theme_kim(base_size = 18, axis_tick_font_size = 16)
  g <- g + lemon::coord_capped_cart(ylim = y_limits, bottom = "both", left = "both")
  g <- g + theme(
    axis.title.x = element_blank(),
    axis.title.y = element_blank(),
    plot.title = element_text(hjust = 0.5, size = 16)
  )
  if (!is.null(title)) {
    g <- g + ggtitle(title)
  }
  g
}

write_plot_csv <- function(dt_obj, file_name) {
  fwrite(dt_obj, file.path(output_dir, file_name))
}

write_text <- function(file_name, lines) {
  writeLines(lines, con = file.path(output_dir, file_name))
}

## Table S1 ---------------------------------------------------------------

table_s1 <- data.table(
  time = c(
    "Mar 2016",
    "Jan 2017",
    "May 2017",
    "Jul 2017",
    "Oct 2017",
    "Dec 2017",
    "2017 - Present"
  ),
  event = c(
    "AlphaGo (Lee version)",
    "AlphaGo (Master version)",
    "The Future of Go Summit",
    "WeiQi TV - 5",
    "AlphaGo (Zero version)",
    "AlphaGo teaching tool",
    "Various AlphaGo-based AI engines (e.g., FineArt, LeelaZero, KataGo, and etc)"
  ),
  implication = c(
    "5 games against a former world Go champion Sedol Lee",
    "60 games against human top players were released (AlphaGo won all 60 games)",
    "3 games against a world Go champion, Ke Jie (+ a special set of 50 AlphaGo vs. AlphaGo games)",
    "5 games were released",
    "80 games against different versions of AlphaGo",
    "Analyzing winning rates of different Go openings",
    "Provided with teaching tools to help review any game (e.g., GoreviewPartner, Lizzie, and etc.)"
  )
)
fwrite(table_s1, file.path(output_dir, "table_s1_advent_events.csv"))

## Fig. S2 ---------------------------------------------------------------

s2_fit <- fit_monthly_fe(dt[matches_ai_move == "no"], "dqi")
s2_fe <- copy(s2_fit$fe)
y_limits_s2 <- pretty_limits(min(s2_fe$fe_ci_ll), max(s2_fe$fe_ci_ul), 0.5)
y_breaks_s2 <- pretty(y_limits_s2, n = 4)
write_plot_csv(s2_fe, "fig_s2_monthly_dqi_no_ai_match.csv")
g_s2 <- make_monthly_plot(
  s2_fe, y_limits_s2, y_breaks_s2,
  color = "#008000", point_size = 0.5, linewidth = 0.2
)
ggsave(file.path(output_dir, "fig_s2_monthly_dqi_no_ai_match.png"), g_s2, width = 8, height = 4.5, dpi = 300)

## Fig. S3 ---------------------------------------------------------------

move_bins <- data.table(
  panel = c("A", "B", "C", "D", "E", "F"),
  move_from = c(1, 11, 21, 31, 41, 51),
  move_to = c(10, 20, 30, 40, 50, 60)
)

s3_results <- vector("list", nrow(move_bins))
for (i in seq_len(nrow(move_bins))) {
  row <- move_bins[i]
  subset_dt <- dt[move_number >= row$move_from & move_number <= row$move_to]
  fit <- fit_yearly_fe(subset_dt, "dqi")
  fe_dt <- copy(fit$fe)
  fe_dt[, panel := row$panel]
  fe_dt[, move_range := paste0("Moves ", row$move_from, "-", row$move_to)]
  s3_results[[i]] <- list(meta = row, fit = fit, fe = fe_dt)
}
s3_fe <- rbindlist(lapply(s3_results, function(x) x$fe), fill = TRUE)
write_plot_csv(s3_fe, "fig_s3_yearly_dqi_by_move_range.csv")
y_limits_s3 <- pretty_limits(min(s3_fe$fe_ci_ll), max(s3_fe$fe_ci_ul), 0.2)
y_breaks_s3 <- pretty(y_limits_s3, n = 5)
s3_plots <- lapply(s3_results, function(x) {
  make_yearly_plot(
    x$fe,
    y_limits_s3,
    y_breaks_s3,
    color = "blue",
    point_size = 1.8,
    title = paste0("Panel ", x$meta$panel, ": Moves ", x$meta$move_from, "-", x$meta$move_to)
  )
})
g_s3 <- gridExtra::arrangeGrob(grobs = s3_plots, ncol = 2)
ggsave(file.path(output_dir, "fig_s3_yearly_dqi_by_move_range.png"), g_s3, width = 12, height = 10, dpi = 300)

## Fig. S4 ---------------------------------------------------------------

dt_ordered <- copy(dt)
setorder(dt_ordered, game_id, move_number)
first_deviation <- dt_ordered[, .(
  first_deviation_move = as.integer(
    if (any(matches_ai_move == "no", na.rm = TRUE)) min(move_number[matches_ai_move == "no"], na.rm = TRUE) else NA_integer_
  )
), by = game_id]
dt_s4 <- merge(dt_ordered, first_deviation, by = "game_id", all.x = TRUE)
dt_s4 <- dt_s4[!is.na(first_deviation_move) & move_number == first_deviation_move + 1]
s4_fit <- fit_yearly_fe(dt_s4, "dqi")
s4_fe <- copy(s4_fit$fe)
write_plot_csv(s4_fe, "fig_s4_yearly_dqi_after_opponent_first_deviation.csv")
y_limits_s4 <- pretty_limits(min(s4_fe$fe_ci_ll), max(s4_fe$fe_ci_ul), 0.2)
y_breaks_s4 <- pretty(y_limits_s4, n = 5)
g_s4 <- make_yearly_plot(s4_fe, y_limits_s4, y_breaks_s4, color = "blue")
ggsave(file.path(output_dir, "fig_s4_yearly_dqi_after_opponent_first_deviation.png"), g_s4, width = 8, height = 4.5, dpi = 300)

## Fig. S5 ---------------------------------------------------------------

novel_move_rows <- dt[!is.na(novelty_index) & move_number == (60 - novelty_index)]
s5_match_fit <- fit_yearly_fe(novel_move_rows[matches_ai_move == "yes"], "novelty_index")
s5_diff_fit <- fit_yearly_fe(novel_move_rows[matches_ai_move == "no"], "novelty_index")
s5_match_fe <- copy(s5_match_fit$fe)[, panel := "A"]
s5_diff_fe <- copy(s5_diff_fit$fe)[, panel := "B"]
s5_fe <- rbindlist(list(
  s5_match_fe[, subset := "Novel move matches AI"],
  s5_diff_fe[, subset := "Novel move differs from AI"]
), fill = TRUE)
write_plot_csv(s5_fe, "fig_s5_yearly_novelty_by_novel_move_ai_match.csv")
y_limits_s5 <- pretty_limits(min(s5_fe$fe_ci_ll), max(s5_fe$fe_ci_ul), 0.5)
y_breaks_s5 <- pretty(y_limits_s5, n = 5)
g_s5a <- make_yearly_plot(s5_match_fe, y_limits_s5, y_breaks_s5, color = "blue", title = "Panel A: Novel move matches AI")
g_s5b <- make_yearly_plot(s5_diff_fe, y_limits_s5, y_breaks_s5, color = "blue", title = "Panel B: Novel move differs from AI")
g_s5 <- gridExtra::arrangeGrob(g_s5a, g_s5b, ncol = 2)
ggsave(file.path(output_dir, "fig_s5_yearly_novelty_by_novel_move_ai_match.png"), g_s5, width = 12, height = 5, dpi = 300)

## Scope note ------------------------------------------------------------

write_text(
  "supplement_scope_limits.txt",
  c(
    "Public supplement reconstruction status:",
    "- Reconstructed from public processed data: Table S1, Fig. S2, Fig. S3, Fig. S4, Fig. S5",
    "- Still blocked from public processed data alone: Fig. S1, Fig. S6",
    "- Reason: the released human dt table does not include raw move choices / move sequences, which are needed to recompute novel strategy sequences and novelty after adding simulated AI moves."
  )
)

write_text("session_info.txt", capture.output(sessionInfo()))
