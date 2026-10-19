# Pooled 2-for-1 window gaps per league, R side of python/09_seasons.py.
#
# Reads the R implementation's own per-season team-period tables
# (team_period_windows_r.csv, written by R/02_analysis.R for each
# league-season), pools each league's three seasons, and bootstraps the same
# four differences as the Python side. python/04_reconcile.py --pooled
# compares the two (different RNGs, so intervals are compared for overlap and
# group sizes for equality).
#
# Output: output/seasons_pooled_r.csv
# Run:    Rscript R/09_pooled.R

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(purrr)
})

ROOT <- normalizePath(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1])), ".."))
if (is.na(ROOT) || !dir.exists(ROOT)) ROOT <- normalizePath(".")
source(file.path(ROOT, "R", "functions.R"))

SEASONS <- list(nba = c("2023-24", "2024-25", "2025-26"),
                wnba = c("2024", "2025", "2026"))
SEEDS <- c(own = 4101, net = 4102, own_restricted = 4103, net_restricted = 4104)

season_dir <- function(league, season) {
  if (league == "nba" && season == "2023-24") file.path(ROOT, "output")
  else file.path(ROOT, "output", "seasons", paste0(league, "_", season))
}

rows <- list()
for (league in names(SEASONS)) {
  ss <- SEASONS[[league]]
  windows <- map_dfr(ss, function(s) {
    read_csv(file.path(season_dir(league, s), "team_period_windows_r.csv"),
             show_col_types = FALSE) %>% mutate(season = s)
  }) %>% arrange(season, gameId, period, location)
  narrow <- windows %>% filter(first_fga_sec >= 20, first_fga_sec <= 45)
  label <- paste0(toupper(league), " ", ss[[1]], " to ", ss[[length(ss)]])
  specs <- list(own = list(windows, "points"), net = list(windows, "net"),
                own_restricted = list(narrow, "points"),
                net_restricted = list(narrow, "net"))
  for (q in names(specs)) {
    b <- boot_diff(specs[[q]][[1]], specs[[q]][[2]], seed = SEEDS[[q]])
    rows[[length(rows) + 1]] <- tibble::tibble(league = league, seasons = label,
                                               quantity = q) %>% bind_cols(b)
  }
}
pooled <- bind_rows(rows)
write_csv(pooled, file.path(ROOT, "output", "seasons_pooled_r.csv"))
print(pooled %>% select(league, quantity, estimate, ci_lo, ci_hi, n_treated, n_control))
