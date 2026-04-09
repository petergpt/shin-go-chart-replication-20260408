#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(data.table)
  library(lfe)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) {
  stop("Usage: replicate_shin_panel_ab_r.R <input_rdata> <output_dir>")
}

input_rdata <- args[[1]]
output_dir <- args[[2]]
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

load(input_rdata)

if (!exists("dt")) {
  stop("Expected object `dt` in input RData")
}

extract_felm <- function(model, prefix) {
  summ <- summary(model)
  cf <- as.data.frame(summ$coefficients)
  cf$term <- rownames(cf)
  rownames(cf) <- NULL

  se_col <- grep("s.e.", names(cf), value = TRUE)[1]
  if (is.na(se_col)) {
    stop("Could not locate standard error column in felm summary output")
  }

  out <- data.table(
    label = sub(paste0("^", prefix), "", cf$term),
    fe = cf$Estimate,
    fe_ci_ll = cf$Estimate - qnorm(0.95 / 2 + 0.5) * cf[[se_col]],
    fe_ci_ul = cf$Estimate + qnorm(0.95 / 2 + 0.5) * cf[[se_col]]
  )
  out[]
}

# Panel A
dt[, year := as.factor(substr(game_date, 1, 4))]
d1 <- na.omit(dt[, .(median_dqi = median(dqi, na.rm = TRUE)), keyby = c("player_id", "year")])
felm_1 <- felm(formula = median_dqi ~ year | player_id | 0 | player_id, data = d1)
yearly <- extract_felm(felm_1, "year")
yearly[, year := as.integer(label)]
setorder(yearly, year)
fwrite(yearly, file.path(output_dir, "panel_a_yearly_coefficients_r.csv"))

# Panel B
dt[, year_month := substr(game_date, 1, 7)]
d3 <- na.omit(dt[, .(median_dqi = median(dqi, na.rm = TRUE)), keyby = c("player_id", "year_month")])
d3[, month_index := as.factor((as.numeric(substr(year_month, 1, 4)) - 1950) * 12 + as.numeric(substr(year_month, 6, 7)))]
felm_2 <- felm(formula = median_dqi ~ month_index | player_id | 0 | player_id, data = d3)
monthly <- extract_felm(felm_2, "month_index")
monthly[, month_index := as.integer(label)]
setorder(monthly, month_index)
fwrite(monthly, file.path(output_dir, "panel_b_monthly_coefficients_r.csv"))

cat(sprintf("Wrote R coefficients to: %s\n", output_dir))
