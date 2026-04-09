#!/usr/bin/env Rscript

repos <- "https://cloud.r-project.org"
script_arg <- commandArgs(trailingOnly = FALSE)
script_flag <- grep("^--file=", script_arg, value = TRUE)
script_path <- if (length(script_flag) > 0) sub("^--file=", "", script_flag[[1]]) else "scripts/install_r_deps.R"
root <- normalizePath(file.path(dirname(script_path), ".."), mustWork = FALSE)
lockfile <- file.path(root, "r_requirements_lock.csv")
lock <- read.csv(lockfile, stringsAsFactors = FALSE)

if (!"remotes" %in% rownames(installed.packages())) {
  install.packages("remotes", repos = repos)
}

needs_install <- function(pkg, version) {
  if (!pkg %in% rownames(installed.packages())) {
    return(TRUE)
  }
  as.character(packageVersion(pkg)) != version
}

to_install <- lock[apply(lock, 1, function(row) needs_install(row[["package"]], row[["version"]])), , drop = FALSE]

if (nrow(to_install) == 0) {
  cat("All pinned R packages already installed.\n")
} else {
  for (idx in seq_len(nrow(to_install))) {
    pkg <- to_install$package[[idx]]
    version <- to_install$version[[idx]]
    remotes::install_version(pkg, version = version, repos = repos, upgrade = "never")
  }
}
