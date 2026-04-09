########################################################################
#
# R code to accompany the paper below.
# Written by Jin Kim (jin.m.kim@yale.edu)
# Please email Jin Kim directly if you see any errors or have any questions.
# Last update: January 16, 2023
#
# Shin, M., Kim, J., Van Opheusden, B., & Griffiths, T. L. (2023).
# Superhuman Artificial Intelligence Can Improve Human Decision-Making
# by Increasing Novelty.
# Proceedings of the National Academy of Sciences
# doi: To Be Assigned
#
########################################################################

# Code for replicating analyses in the main text --------------------------

# It takes about 2 minutes 10 seconds on Jin Kim's PC to ------------------
# run the entire code below (with all packages installed) -----------------

# Install Package 'kim' (v0.5.133) if necessary ---------------------------
if (require(kim) == FALSE) install.packages("kim")

# Update Package 'kim' if necessary ---------------------------------------
# kim::update_kim()

# Install all dependencies (recommended but may not be necessary) ---------
# kim::install_all_dependencies()

# Attach and start using the Package 'kim' --------------------------------
# The code below will clear the console and global environment ------------
library(kim); start_kim()

# Attach packages ---------------------------------------------------------
prep(data.table, ggplot2, lfe, coefplot, lubridate)

# Read the data -----------------------------------------------------------
load("shin et al 2023 data v001.RData")


###########################################################################
#
# Fig. 1, Panel A ---------------------------------------------------------
#
###########################################################################

# Create a separate year column -------------------------------------------
dt[, year := as.factor(substr(game_date, 1, 4))]

# Create a data set with median DQI for each player-year combination ------
d1 <- na.omit(dt[, .(
  median_dqi = median(dqi, na.rm = TRUE)),
  keyby = c("player_id", "year")])
head(d1)

# Yearly fixed effects ----------------------------------------------------
felm_1 <- felm(
  formula = median_dqi ~ year | player_id | 0 | player_id,
  data = d1)

# Obtain the coefficient for each year ------------------------------------
coefplot_1 <- coefplot::coefplot(
  felm_1, outerCI = qnorm(0.95 / 2 + 0.5), innerCI = 0)
coefplot_1_obj <- ggplot_build(coefplot_1)

# Yearly fixed effects on DQI with 95% CI ---------------------------------
# "fe" is short for fixed effect ------------------------------------------
dqi_yearly_fe <- coefplot_1_obj$data[[2]]$x
dqi_yearly_fe_ci_ll <- coefplot_1_obj$data[[2]]$xmin
dqi_yearly_fe_ci_ul <- coefplot_1_obj$data[[2]]$xmax
dqi_yearly_fe_year <- as.numeric(gsub(
  "year", "", coefplot_1_obj$layout$panel_params[[1]]$y.sec$breaks))

# Data for plotting -------------------------------------------------------
d2 <- data.table(
  year = dqi_yearly_fe_year,
  fe = dqi_yearly_fe, 
  fe_ci_ll = dqi_yearly_fe_ci_ll,
  fe_ci_ul = dqi_yearly_fe_ci_ul)

# The period marking the advent of superhuman AI --------------------------
alphago_defeat_sedol_date <- as.Date("2016-03-15")
leela_zero_release_date <- as.Date("2017-10-25")
alphago_defeat_sedol_date_as_decimal_year <- lubridate::decimal_date(
  alphago_defeat_sedol_date)
leela_zero_release_date_as_decimal_year <- lubridate::decimal_date(
  leela_zero_release_date)

# Convert the last date observed in the data set to a decimal year --------
last_date_observed_to_decimal_year <- lubridate::decimal_date(
  as.Date(tail(su(dt[, game_date]), 1)))

# Begin plotting ----------------------------------------------------------
# Mark the period after the advent of superhuman AI -----------------------
g1 <- ggplot(data = d2)
g1 <- g1 + annotate(
  geom = "rect", fill = "orange", alpha = 0.3,
  xmin = alphago_defeat_sedol_date_as_decimal_year,
  xmax = last_date_observed_to_decimal_year, ymin = -0.8, ymax = 1.2)
g1 <- g1 + geom_segment(aes(
  x = alphago_defeat_sedol_date_as_decimal_year,
  xend = alphago_defeat_sedol_date_as_decimal_year,
  y = -0.8,
  yend = 1.2),
  linetype = "dashed",
  color = "red",
  linewidth = 0.7)
# Plot the yearly fixed effects on DQI (and the CI) -----------------------
g1 <- g1 + geom_point(
  aes(x = year, y = fe),
  size = 2.5, color = "blue")
g1 <- g1 + geom_errorbar(aes(
  x = year, ymin = fe_ci_ll, ymax = fe_ci_ul),
  width = 0, linewidth = 0.7, color = "blue")
# Adjust the ranges for the axes ------------------------------------------
g1 <- g1 + scale_x_continuous(
  expand = expansion(add = c(0, 2)),
  limits = c(1948, 2022),
  breaks = c(
    1950, seq(1960, 2010, 10),
    last_date_observed_to_decimal_year),
  labels = c(
    1950, seq(1960, 2010, 10), "2021\n(Oct)"))
g1 <- g1 + scale_y_continuous(
  limits = c(-0.8, 1.2),
  breaks = seq(-0.8, 1.2, 0.4))
# Make the plot look nicer ------------------------------------------------
g1 <- g1 + theme_kim(
  base_size = 20, axis_tick_font_size = 20)
g1 <- g1 + lemon::coord_capped_cart(
  ylim = c(-0.8, 1.2), bottom = "both", left = "both")
g1 <- g1 + theme(
  axis.title.x = element_blank(),
  axis.title.y = element_blank())
g1
# Save the plot as a PNG file ---------------------------------------------
ggsave_quick("fig 1 panel a v01", width = 8, height = 4.5)


###########################################################################
#
# Fig. 1, Panel B ---------------------------------------------------------
#
###########################################################################

# Create a separate year-month column -------------------------------------
dt[, year_month := substr(game_date, 1, 7)]

# Create a data set with median DQI for each ------------------------------
# player-year-month combination -------------------------------------------
d3 <- na.omit(dt[, .(
  median_dqi = median(dqi, na.rm = TRUE)),
  keyby = c("player_id", "year_month")])
head(d3)
# Assign month indices as a factor variable -------------------------------
d3[, month_index := 
     as.factor((as.numeric(substr(year_month, 1, 4)) - 1950) * 12 + 
     as.numeric(substr(year_month, 6, 7)))]

# Monthly fixed effects ---------------------------------------------------
# It takes about 52 seconds on Jin Kim's PC to run the code below ---------
felm_2 <- felm(
  formula = median_dqi ~ month_index | player_id | 0 | player_id,
  data = d3)

# Obtain the coefficient for each year ------------------------------------
coefplot_2 <- coefplot::coefplot(
  felm_2, outerCI = qnorm(0.95 / 2 + 0.5), innerCI = 0)
coefplot_2_obj <- ggplot_build(coefplot_2)

# Monthly fixed effects on DQI with 95% CI --------------------------------
# "fe" is short for fixed effect ------------------------------------------
dqi_monthly_fe <- coefplot_2_obj$data[[2]]$x
dqi_monthly_fe_ci_ll <- coefplot_2_obj$data[[2]]$xmin
dqi_monthly_fe_ci_ul <- coefplot_2_obj$data[[2]]$xmax
dqi_monthly_fe_month_index <- as.numeric(gsub(
  "month_index", "", coefplot_2_obj$layout$panel_params[[1]]$y.sec$breaks))

# Data for plotting -------------------------------------------------------
d4 <- data.table(
  month_index = dqi_monthly_fe_month_index,
  fe = dqi_monthly_fe, 
  fe_ci_ll = dqi_monthly_fe_ci_ll,
  fe_ci_ul = dqi_monthly_fe_ci_ul)

# The month index marking the advent of superhuman AI ---------------------
alphago_defeat_sedol_month_index <- as.numeric(d3[
  year_month == "2016-03", unique(month_index)])

# Range of the horizontal axis for plotting -------------------------------
year_month_min_and_max <- c(
  head(su(dt[, year_month]), 1),
  tail(su(dt[, year_month]), 1))
monthly_fe_plot_x_axis_range <- 
  (as.numeric(substr(year_month_min_and_max, 1, 4)) - 1950) * 12 + 
  as.numeric(substr(year_month_min_and_max, 6, 7))

# Tick marks for the horizontal axis --------------------------------------
monthly_fe_plot_x_axis_tick_mark_year_months <- c(
  p0(seq(1950, 2010, 10), "-01"), tail(su(dt[, year_month]), 1))
monthly_fe_plot_x_axis_tick_mark_month_indices <- 
  (as.numeric(substr(
    monthly_fe_plot_x_axis_tick_mark_year_months, 1, 4)) - 1950) * 12 +
  as.numeric(substr(monthly_fe_plot_x_axis_tick_mark_year_months, 6, 7))
monthly_fe_plot_x_axis_tick_mark_labels <- c(
  p0(seq(1950, 2010, 10), "\n(Jan)"), 
  "2021\n(Oct)")

# Begin plotting ----------------------------------------------------------
# Mark the period after the advent of superhuman AI -----------------------
g2 <- ggplot(data = d4)
g2 <- g2 + annotate(
  geom = "rect", fill = "orange", alpha = 0.3,
  xmin = alphago_defeat_sedol_month_index,
  xmax = max(d4[, month_index]),
  ymin = -3, ymax = 1.5)
g2 <- g2 + geom_segment(aes(
  x = alphago_defeat_sedol_month_index,
  xend = alphago_defeat_sedol_month_index,
  y = -3,
  yend = 1.5),
  linetype = "dashed",
  color = "red",
  size = 0.7)
# Plot the monthly fixed effects on DQI (and the CI) ----------------------
g2 <- g2 + geom_point(
  aes(x = month_index, y = fe),
  size = 0.5, color = "#008000")
g2 <- g2 + geom_errorbar(aes(
  x = month_index,
  ymin = fe_ci_ll,
  ymax = fe_ci_ul),
  width = 0, size = 0.2, color = "#008000")
# Adjust the ranges for the axes ------------------------------------------
g2 <- g2 + scale_x_continuous(
  expand = expansion(add = c(0, 0)),
  limits = monthly_fe_plot_x_axis_range + c(-24, 36),
  breaks = monthly_fe_plot_x_axis_tick_mark_month_indices,
  labels = monthly_fe_plot_x_axis_tick_mark_labels)
g2 <- g2 + scale_y_continuous(
  limits = c(-3, 1.5),
  breaks = seq(-3, 1.5, 1.5))
# Make the plot look nicer ------------------------------------------------
g2 <- g2 + theme_kim(
  base_size = 20, axis_tick_font_size = 20)
g2 <- g2 + lemon::coord_capped_cart(
  ylim = c(-3, 1.5), bottom = "both", left = "both")
g2 <- g2 + theme(
  axis.title.x = element_blank(),
  axis.title.y = element_blank())
g2
# Save the plot as a PNG file ---------------------------------------------
ggsave_quick("fig 1 panel b v01", width = 8, height = 4.5)


###########################################################################
#
# Fig. 1, Panel C ---------------------------------------------------------
#
###########################################################################

# Create a data set with median Novelty Index for  ------------------------
# each player-year combination --------------------------------------------
d5 <- na.omit(dt[, .(
  median_novelty_index = median(novelty_index, na.rm = TRUE)),
  keyby = c("player_id", "year")])
head(d5)

# Yearly fixed effects ----------------------------------------------------
felm_3 <- felm(
  formula = median_novelty_index ~ year | player_id | 0 | player_id,
  data = d5)

# Obtain the coefficient for each year ------------------------------------
coefplot_3 <- coefplot::coefplot(
  felm_3, outerCI = qnorm(0.95 / 2 + 0.5), innerCI = 0)
coefplot_3_obj <- ggplot_build(coefplot_3)

# Yearly fixed effects on Novelty Index with 95% CI -----------------------
# "fe" is short for fixed effect ------------------------------------------
novelty_index_yearly_fe <- coefplot_3_obj$data[[2]]$x
novelty_index_yearly_fe_ci_ll <- coefplot_3_obj$data[[2]]$xmin
novelty_index_yearly_fe_ci_ul <- coefplot_3_obj$data[[2]]$xmax
novelty_index_yearly_fe_year <- as.numeric(gsub(
  "year", "", coefplot_3_obj$layout$panel_params[[1]]$y.sec$breaks))

# Data for plotting -------------------------------------------------------
d6 <- data.table(
  year = novelty_index_yearly_fe_year,
  fe = novelty_index_yearly_fe, 
  fe_ci_ll = novelty_index_yearly_fe_ci_ll,
  fe_ci_ul = novelty_index_yearly_fe_ci_ul)

# Begin plotting ----------------------------------------------------------
# Mark the period after the advent of superhuman AI -----------------------
g3 <- ggplot(data = d6)
g3 <- g3 + annotate(
  geom = "rect", fill = "orange", alpha = 0.3,
  xmin = alphago_defeat_sedol_date_as_decimal_year,
  xmax = last_date_observed_to_decimal_year, ymin = -7.5, ymax = 0)
g3 <- g3 + geom_segment(aes(
  x = alphago_defeat_sedol_date_as_decimal_year,
  xend = alphago_defeat_sedol_date_as_decimal_year,
  y = -7.5,
  yend = 0),
  linetype = "dashed",
  color = "red",
  size = 0.7)
# Plot the yearly fixed effects on Novelty Index (and the CI) -------------
g3 <- g3 + geom_point(
  aes(x = year, y = fe),
  size = 2.5, color = "blue")
g3 <- g3 + geom_errorbar(aes(
  x = year, ymin = fe_ci_ll, ymax = fe_ci_ul),
  width = 0, linewidth = 0.7, color = "blue")
# Adjust the ranges for the axes ------------------------------------------
g3 <- g3 + scale_x_continuous(
  expand = expansion(add = c(0, 2)),
  limits = c(1948, 2022),
  breaks = c(
    1950, seq(1960, 2010, 10),
    last_date_observed_to_decimal_year),
  labels = c(
    1950, seq(1960, 2010, 10), "2021\n(Oct)"))
g3 <- g3 + scale_y_continuous(
  limits = c(-7.5, 0),
  breaks = seq(-7.5, 0, 2.5))
# Make the plot look nicer ------------------------------------------------
g3 <- g3 + theme_kim(
  base_size = 20, axis_tick_font_size = 20)
g3 <- g3 + lemon::coord_capped_cart(
  ylim = c(-7.5, 0), bottom = "both", left = "both")
g3 <- g3 + theme(
  axis.title.x = element_blank(),
  axis.title.y = element_blank())
g3
# Save the plot as a PNG file ---------------------------------------------
ggsave_quick("fig 1 panel c v01", width = 8, height = 4.5)


###########################################################################
#
# Fig. 1, Panel D ---------------------------------------------------------
#
###########################################################################

# Create a data set with median Novelty Index for each --------------------
# player-year-month combination -------------------------------------------
d7 <- na.omit(dt[, .(
  median_novelty_index = median(novelty_index, na.rm = TRUE)),
  keyby = c("player_id", "year_month")])
head(d7)
# Assign month indices as a factor variable -------------------------------
d7[, month_index := 
     as.factor((as.numeric(substr(year_month, 1, 4)) - 1950) * 12 + 
                 as.numeric(substr(year_month, 6, 7)))]

# Monthly fixed effects ---------------------------------------------------
# It takes about 53 seconds on Jin Kim's PC to run the code below ---------
felm_4 <- felm(
  formula = median_novelty_index ~ month_index | player_id | 0 | player_id,
  data = d7)

# Obtain the coefficient for each year ------------------------------------
coefplot_4 <- coefplot::coefplot(
  felm_4, outerCI = qnorm(0.95 / 2 + 0.5), innerCI = 0)
coefplot_4_obj <- ggplot_build(coefplot_4)

# Monthly fixed effects on Novelty Index with 95% CI ----------------------
# "fe" is short for fixed effect ------------------------------------------
novelty_index_monthly_fe <- coefplot_4_obj$data[[2]]$x
novelty_index_monthly_fe_ci_ll <- coefplot_4_obj$data[[2]]$xmin
novelty_index_monthly_fe_ci_ul <- coefplot_4_obj$data[[2]]$xmax
novelty_index_monthly_fe_month_index <- as.numeric(gsub(
  "month_index", "", coefplot_4_obj$layout$panel_params[[1]]$y.sec$breaks))

# Data for plotting -------------------------------------------------------
d8 <- data.table(
  month_index = novelty_index_monthly_fe_month_index,
  fe = novelty_index_monthly_fe, 
  fe_ci_ll = novelty_index_monthly_fe_ci_ll,
  fe_ci_ul = novelty_index_monthly_fe_ci_ul)

# Begin plotting ----------------------------------------------------------
# Mark the period after the advent of superhuman AI -----------------------
g4 <- ggplot(data = d8)
g4 <- g4 + annotate(
  geom = "rect", fill = "orange", alpha = 0.3,
  xmin = alphago_defeat_sedol_month_index,
  xmax = max(d8[, month_index]),
  ymin = -10, ymax = 0)
g4 <- g4 + geom_segment(aes(
  x = alphago_defeat_sedol_month_index,
  xend = alphago_defeat_sedol_month_index,
  y = -10,
  yend = 0),
  linetype = "dashed",
  color = "red",
  size = 0.7)
# Plot the monthly fixed effects on Novelty Index (and the CI) ------------
g4 <- g4 + geom_point(
  aes(x = month_index, y = fe),
  size = 0.5, color = "#008000")
g4 <- g4 + geom_errorbar(aes(
  x = month_index,
  ymin = fe_ci_ll,
  ymax = fe_ci_ul),
  width = 0, size = 0.2, color = "#008000")
# Adjust the ranges for the axes ------------------------------------------
g4 <- g4 + scale_x_continuous(
  expand = expansion(add = c(0, 0)),
  limits = monthly_fe_plot_x_axis_range + c(-24, 36),
  breaks = monthly_fe_plot_x_axis_tick_mark_month_indices,
  labels = monthly_fe_plot_x_axis_tick_mark_labels)
g4 <- g4 + scale_y_continuous(
  limits = c(-10.2, 1),
  breaks = c(-10, -5, 0))
# Make the plot look nicer ------------------------------------------------
g4 <- g4 + theme_kim(
  base_size = 20, axis_tick_font_size = 20)
g4 <- g4 + lemon::coord_capped_cart(
  ylim = c(-10, 0), bottom = "both", left = "both")
g4 <- g4 + theme(
  axis.title.x = element_blank(),
  axis.title.y = element_blank())
g4
# Save the plot as a PNG file ---------------------------------------------
ggsave_quick("fig 1 panel d v01", width = 8, height = 4.5)


###########################################################################
#
# Table 1 -----------------------------------------------------------------
#
###########################################################################

# Create a column for game date in the date format ------------------------
dt[, game_date_date_format := as.Date(game_date, format = "%Y-%m-%d")]

# Create a column indicating whether a move is novel ----------------------
dt[, move_number_of_novel_move := 60 - novelty_index]

# Create the dummy variables ----------------------------------------------
dt[, after_ai_dummy := ifelse(
  game_date_date_format >= alphago_defeat_sedol_date, 1, 0)]
dt[, novelty_dummy := fcase(
  move_number_of_novel_move == move_number, 1, 
  is.na(move_number_of_novel_move), 0)]

# Table 1, Model 1 --------------------------------------------------------
# It takes about 10 seconds on Jin Kim's PC to run the code below ---------
table_1_felm_1 <- felm(
  dqi ~ after_ai_dummy * novelty_dummy | as.factor(move_number) + 
    player_id | 0 | player_id,
  data = dt)
summary(table_1_felm_1)
table_1_felm_1$N

# Table 1, Model 2 --------------------------------------------------------
# It takes about 14 seconds on Jin Kim's PC to run the code below ---------
table_1_felm_2 <- felm(
  dqi ~ novelty_dummy + after_ai_dummy:novelty_dummy | 
    as.factor(year_month) + as.factor(move_number) + 
    player_id | 0 | player_id,
  data = dt)
summary(table_1_felm_2)
table_1_felm_2$N


###########################################################################
#
# Fig. 2 ------------------------------------------------------------------
#
###########################################################################

# Create a data set with median DQI for each player-year combination ------
# Note we subset the data to include only the moves that ------------------
# do not match the AI moves -----------------------------------------------
d9 <- na.omit(dt[matches_ai_move == "no", .(
  median_dqi = median(dqi, na.rm = TRUE)),
  keyby = c("player_id", "year")])
head(d9)

# Yearly fixed effects ----------------------------------------------------
felm_5 <- felm(
  formula = median_dqi ~ year | player_id | 0 | player_id,
  data = d9)

# Obtain the coefficient for each year ------------------------------------
coefplot_5 <- coefplot::coefplot(
  felm_5, outerCI = qnorm(0.95 / 2 + 0.5), innerCI = 0)
coefplot_5_obj <- ggplot_build(coefplot_5)

# Yearly fixed effects on DQI with 95% CI ---------------------------------
# "fe" is short for fixed effect ------------------------------------------
# "mdfai" is short for moves different from AI moves ----------------------
dqi_mdfai_yearly_fe <- coefplot_5_obj$data[[2]]$x
dqi_mdfai_yearly_fe_ci_ll <- coefplot_5_obj$data[[2]]$xmin
dqi_mdfai_yearly_fe_ci_ul <- coefplot_5_obj$data[[2]]$xmax
dqi_mdfai_yearly_fe_year <- as.numeric(gsub(
  "year", "", coefplot_5_obj$layout$panel_params[[1]]$y.sec$breaks))

# Data for plotting -------------------------------------------------------
d10 <- data.table(
  year = dqi_mdfai_yearly_fe_year,
  fe = dqi_mdfai_yearly_fe, 
  fe_ci_ll = dqi_mdfai_yearly_fe_ci_ll,
  fe_ci_ul = dqi_mdfai_yearly_fe_ci_ul)

# Begin plotting ----------------------------------------------------------
# Mark the period after the advent of superhuman AI -----------------------
g5 <- ggplot(data = d10)
g5 <- g5 + annotate(
  geom = "rect", fill = "orange", alpha = 0.3,
  xmin = alphago_defeat_sedol_date_as_decimal_year,
  xmax = last_date_observed_to_decimal_year, ymin = -0.8, ymax = 1.7)
g5 <- g5 + geom_segment(aes(
  x = alphago_defeat_sedol_date_as_decimal_year,
  xend = alphago_defeat_sedol_date_as_decimal_year,
  y = -0.8,
  yend = 1.7),
  linetype = "dashed",
  color = "red",
  linewidth = 0.7)
# Plot the yearly fixed effects on DQI (and the CI) -----------------------
g5 <- g5 + geom_point(
  aes(x = year, y = fe),
  size = 2.5, color = "blue")
g5 <- g5 + geom_errorbar(aes(
  x = year, ymin = fe_ci_ll, ymax = fe_ci_ul),
  width = 0, linewidth = 0.7, color = "blue")
# Adjust the ranges for the axes ------------------------------------------
g5 <- g5 + scale_x_continuous(
  expand = expansion(add = c(0, 2)),
  limits = c(1948, 2022),
  breaks = c(
    1950, seq(1960, 2010, 10),
    last_date_observed_to_decimal_year),
  labels = c(
    1950, seq(1960, 2010, 10), "2021\n(Oct)"))
g5 <- g5 + scale_y_continuous(
  limits = c(-0.8, 1.7),
  breaks = c(-0.8, 0.0, 0.8, 1.7))
# Make the plot look nicer ------------------------------------------------
g5 <- g5 + theme_kim(
  base_size = 20, axis_tick_font_size = 20)
g5 <- g5 + lemon::coord_capped_cart(
  ylim = c(-0.8, 1.7), bottom = "both", left = "both")
g5 <- g5 + theme(
  axis.title.x = element_blank(),
  axis.title.y = element_blank())
g5
# Save the plot as a PNG file ---------------------------------------------
ggsave_quick("fig 2 v01", width = 8, height = 4.5)


###########################################################################
#
# Fig. 3 ------------------------------------------------------------------
#
###########################################################################

# Create a data set with median Novelty Index for  ------------------------
# each player-year combination --------------------------------------------
# Note we subset the data to include only the moves that ------------------
# do not match the AI moves -----------------------------------------------
d11 <- na.omit(dt[matches_ai_move == "no", .(
  median_novelty_index = median(novelty_index, na.rm = TRUE)),
  keyby = c("player_id", "year")])
head(d11)

# Yearly fixed effects ----------------------------------------------------
felm_6 <- felm(
  formula = median_novelty_index ~ year | player_id | 0 | player_id,
  data = d11)

# Obtain the coefficient for each year ------------------------------------
coefplot_6 <- coefplot::coefplot(
  felm_6, outerCI = qnorm(0.95 / 2 + 0.5), innerCI = 0)
coefplot_6_obj <- ggplot_build(coefplot_6)

# Yearly fixed effects on Novelty Index with 95% CI -----------------------
# "fe" is short for fixed effect ------------------------------------------
# "mdfai" is short for moves different from AI moves ----------------------
novelty_index_mdfai_yearly_fe <- coefplot_6_obj$data[[2]]$x
novelty_index_mdfai_yearly_fe_ci_ll <- coefplot_6_obj$data[[2]]$xmin
novelty_index_mdfai_yearly_fe_ci_ul <- coefplot_6_obj$data[[2]]$xmax
novelty_index_mdfai_yearly_fe_year <- as.numeric(gsub(
  "year", "", coefplot_6_obj$layout$panel_params[[1]]$y.sec$breaks))

# Data for plotting -------------------------------------------------------
d12 <- data.table(
  year = novelty_index_mdfai_yearly_fe_year,
  fe = novelty_index_mdfai_yearly_fe, 
  fe_ci_ll = novelty_index_mdfai_yearly_fe_ci_ll,
  fe_ci_ul = novelty_index_mdfai_yearly_fe_ci_ul)

# Begin plotting ----------------------------------------------------------
# Mark the period after the advent of superhuman AI -----------------------
g6 <- ggplot(data = d12)
g6 <- g6 + annotate(
  geom = "rect", fill = "orange", alpha = 0.3,
  xmin = alphago_defeat_sedol_date_as_decimal_year,
  xmax = last_date_observed_to_decimal_year, ymin = -7.5, ymax = 0)
g6 <- g6 + geom_segment(aes(
  x = alphago_defeat_sedol_date_as_decimal_year,
  xend = alphago_defeat_sedol_date_as_decimal_year,
  y = -7.5,
  yend = 0),
  linetype = "dashed",
  color = "red",
  size = 0.7)
# Plot the yearly fixed effects on Novelty Index (and the CI) -------------
g6 <- g6 + geom_point(
  aes(x = year, y = fe),
  size = 2.5, color = "blue")
g6 <- g6 + geom_errorbar(aes(
  x = year, ymin = fe_ci_ll, ymax = fe_ci_ul),
  width = 0, linewidth = 0.7, color = "blue")
# Adjust the ranges for the axes ------------------------------------------
g6 <- g6 + scale_x_continuous(
  expand = expansion(add = c(0, 2)),
  limits = c(1948, 2022),
  breaks = c(
    1950, seq(1960, 2010, 10),
    last_date_observed_to_decimal_year),
  labels = c(
    1950, seq(1960, 2010, 10), "2021\n(Oct)"))
g6 <- g6 + scale_y_continuous(
  limits = c(-7.5, 0),
  breaks = seq(-7.5, 0, 2.5))
# Make the plot look nicer ------------------------------------------------
g6 <- g6 + theme_kim(
  base_size = 20, axis_tick_font_size = 20)
g6 <- g6 + lemon::coord_capped_cart(
  ylim = c(-7.5, 0), bottom = "both", left = "both")
g6 <- g6 + theme(
  axis.title.x = element_blank(),
  axis.title.y = element_blank())
g6
# Save the plot as a PNG file ---------------------------------------------
ggsave_quick("fig 3 v01", width = 8, height = 4.5)
