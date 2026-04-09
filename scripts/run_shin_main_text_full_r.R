args <- commandArgs(trailingOnly = TRUE)

get_arg_value <- function(flag, default = NULL) {
  idx <- match(flag, args)
  if (is.na(idx) || idx == length(args)) {
    return(default)
  }
  args[[idx + 1]]
}

project_root <- get_arg_value("--project-root", getwd())
output_dir <- get_arg_value(
  "--output-dir",
  file.path(project_root, "outputs", "original_r_full")
)

project_root <- normalizePath(project_root, mustWork = TRUE)
if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
}
output_dir <- normalizePath(output_dir, mustWork = TRUE)

script_path <- file.path(project_root, "shin_main_text.R")
data_path <- file.path(project_root, "osf", "shin et al 2023 data v001.RData")

if (!file.exists(script_path)) {
  stop("Missing script: ", script_path)
}
if (!file.exists(data_path)) {
  stop("Missing data file: ", data_path)
}

main <- function(project_root_arg, output_dir_arg, script_path_arg, data_path_arg) {
  project_root <- project_root_arg
  output_dir <- output_dir_arg
  script_path <- script_path_arg
  data_path <- data_path_arg

  link_input_file_local <- function(source_path, target_dir) {
    target_path <- file.path(target_dir, basename(source_path))
    if (file.exists(target_path)) {
      return(target_path)
    }
    ok <- file.symlink(from = source_path, to = target_path)
    if (!isTRUE(ok)) {
      copied <- file.copy(from = source_path, to = target_path, overwrite = TRUE)
      if (!isTRUE(copied)) {
        stop("Failed to stage input file: ", source_path)
      }
    }
    target_path
  }

  write_table_text_local <- function(path, obj) {
    writeLines(capture.output(obj), con = path)
  }

  write_coefficients_csv_local <- function(path, model) {
    coef_table <- as.data.frame(summary(model)$coefficients)
    coef_table$term <- rownames(coef_table)
    rownames(coef_table) <- NULL
    coef_table <- coef_table[, c("term", setdiff(names(coef_table), "term"))]
    utils::write.csv(coef_table, file = path, row.names = FALSE)
  }

  old_wd <- getwd()
  on.exit(setwd(old_wd), add = TRUE)
  setwd(output_dir)

  staged_data_path <- link_input_file_local(data_path, output_dir)
  staged_script_path <- file.path(output_dir, basename(script_path))
  if (!file.exists(staged_script_path)) {
    ok <- file.symlink(from = script_path, to = staged_script_path)
    if (!isTRUE(ok)) {
      file.copy(from = script_path, to = staged_script_path, overwrite = TRUE)
    }
  }

  log_path <- file.path(output_dir, "shin_main_text_console.log")
  log_con <- file(log_path, open = "wt")
  sink(log_con, split = TRUE)
  sink(log_con, type = "message")
  on.exit({
    while (sink.number(type = "message") > 0) {
      sink(type = "message")
    }
    while (sink.number() > 0) {
      sink()
    }
    close(log_con)
  }, add = TRUE)

  cat("Running full Shin main-text replication at", format(Sys.time()), "\n")
  cat("Project root:", project_root, "\n")
  cat("Output dir:", output_dir, "\n")
  cat("Staged data:", staged_data_path, "\n")
  cat("R version:", R.version.string, "\n\n")

  source(script_path, local = FALSE)

  expected_pngs <- c(
    "fig 1 panel a v01.png",
    "fig 1 panel b v01.png",
    "fig 1 panel c v01.png",
    "fig 1 panel d v01.png",
    "fig 2 v01.png",
    "fig 3 v01.png"
  )

  plot_tables <- list(
    "fig1_panel_a_yearly.csv" = d2,
    "fig1_panel_b_monthly.csv" = d4,
    "fig1_panel_c_yearly.csv" = d6,
    "fig1_panel_d_monthly.csv" = d8,
    "fig2_yearly.csv" = d10,
    "fig3_yearly.csv" = d12
  )

  for (name in names(plot_tables)) {
    data.table::fwrite(plot_tables[[name]], file.path(output_dir, name))
  }

  write_table_text_local(file.path(output_dir, "table_1_model_1_summary.txt"), summary(table_1_felm_1))
  write_table_text_local(file.path(output_dir, "table_1_model_2_summary.txt"), summary(table_1_felm_2))
  write_coefficients_csv_local(file.path(output_dir, "table_1_model_1_coefficients.csv"), table_1_felm_1)
  write_coefficients_csv_local(file.path(output_dir, "table_1_model_2_coefficients.csv"), table_1_felm_2)

  utils::write.csv(
    data.frame(
      model = c("table_1_model_1", "table_1_model_2"),
      n = c(table_1_felm_1$N, table_1_felm_2$N)
    ),
    file = file.path(output_dir, "table_1_model_n.csv"),
    row.names = FALSE
  )

  write_table_text_local(file.path(output_dir, "session_info.txt"), sessionInfo())
  writeLines(expected_pngs, con = file.path(output_dir, "expected_figures.txt"))
  save(
    d2, d4, d6, d8, d10, d12,
    felm_1, felm_2, felm_3, felm_4, felm_5, felm_6,
    table_1_felm_1, table_1_felm_2,
    file = file.path(output_dir, "shin_main_text_selected_objects.RData")
  )
}

main(project_root, output_dir, script_path, data_path)
