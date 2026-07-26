# Does the end-of-quarter "2-for-1" actually pay? --- R / tidyverse implementation
#
# Independent implementation of python/02_analysis.py: same definitions, written
# from the definitions rather than ported from the Python code, so that
# python/04_reconcile.py is a real check instead of a formality.
#
# That check has already earned its keep once: the Python implementation
# originally sorted events by actionNumber AS TEXT ("100" before "2"), which
# scrambled the score forward-fill and corrupted every window score. A second
# implementation reading the same feed independently is exactly the kind of
# guard that catches that class of bug.
#
# Inputs : data/raw_pbp/*.parquet   (from python/01_harvest_pbp.py)
# Outputs: output/team_period_windows_r.csv
#          output/two_for_one_summary_r.csv
#          output/first_shot_timing_r.csv
#          output/efg_by_seconds_left_r.csv
#          output/bootstrap_points_diff_r.csv, output/bootstrap_net_diff_r.csv
#          output/bootstrap_restricted_r.csv,  output/bootstrap_net_restricted_r.csv
#
# Run:  Rscript R/02_analysis.R

suppressPackageStartupMessages({
  library(nanoparquet)
  library(dplyr)
  library(tidyr)
  library(stringr)
  library(purrr)
  library(readr)
})

ROOT <- normalizePath(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[1])), ".."))
if (is.na(ROOT) || !dir.exists(ROOT)) ROOT <- normalizePath(".")

RAW_DIR <- file.path(ROOT, "data", "raw_pbp")
source(file.path(ROOT, "R", "functions.R"))  # pure functions, unit-tested
OUT_DIR <- file.path(ROOT, "output")
dir.create(OUT_DIR, showWarnings = FALSE, recursive = TRUE)

WINDOW_SEC <- 60
TWO_FOR_ONE_SEC <- 32

# ---- Load -------------------------------------------------------------------
files <- sort(list.files(RAW_DIR, pattern = "\\.parquet$", full.names = TRUE))
if (!length(files)) stop("No play-by-play in ", RAW_DIR, ". Run python/01_harvest_pbp.py first.")

message("Reading ", length(files), " game files...")
events <- map_dfr(files, read_parquet)

events <- events %>%
  mutate(
    period = as.integer(period),
    # actionNumber arrives as text; MUST be numeric before ordering, or
    # "100" sorts before "2" and the score forward-fill is scrambled.
    action_num = as.integer(actionNumber),
    secs_left = parse_clock_secs(clock),
    is_fga = isFieldGoal == "1",
    made = shotResult == "Made",
    shot_value = suppressWarnings(as.numeric(shotValue)),
    score_h = suppressWarnings(as.numeric(if_else(scoreHome == "", NA_character_, scoreHome))),
    score_a = suppressWarnings(as.numeric(if_else(scoreAway == "", NA_character_, scoreAway)))
  ) %>%
  arrange(gameId, period, action_num) %>%
  # Scores are only stamped on scoring events; carry forward across the whole
  # game (periods start from the running total, so not within period).
  group_by(gameId) %>%
  fill(score_h, score_a, .direction = "down") %>%
  ungroup() %>%
  mutate(score_h = replace_na(score_h, 0), score_a = replace_na(score_a, 0)) %>%
  filter(!is.na(secs_left))

message(sprintf("Loaded %s events from %s games",
                format(nrow(events), big.mark = ","),
                format(n_distinct(events$gameId), big.mark = ",")))

per <- events %>% filter(period %in% 1:3)

# ---- Points scored by each side in the final WINDOW_SEC of each period ------
window_pts <- per %>%
  group_by(gameId, period) %>%
  summarise(
    h0 = last(score_h[secs_left > WINDOW_SEC]),
    a0 = last(score_a[secs_left > WINDOW_SEC]),
    h1 = last(score_h),
    a1 = last(score_a),
    .groups = "drop"
  ) %>%
  filter(!is.na(h0)) %>%
  mutate(h = h1 - h0, v = a1 - a0) %>%
  select(gameId, period, h, v) %>%
  pivot_longer(c(h, v), names_to = "location", values_to = "points")

# ---- Shot behaviour inside the window ---------------------------------------
window_shots <- per %>%
  filter(secs_left <= WINDOW_SEC, is_fga, location %in% c("h", "v")) %>%
  group_by(gameId, period, location) %>%
  summarise(
    first_fga_sec = max(secs_left),
    n_fga = n(),
    fgm = sum(made),
    fg3m = sum(made & shot_value == 3),
    .groups = "drop"
  )

team_periods <- window_shots %>%
  inner_join(window_pts, by = c("gameId", "period", "location")) %>%
  mutate(
    two_for_one = first_fga_sec >= TWO_FOR_ONE_SEC,
    efg = (fgm + 0.5 * fg3m) / n_fga
  )

# NET outcome: holding for the last shot is valuable precisely because it
# denies the opponent a reply, so own points alone miss half the trade.
opp <- window_pts %>%
  mutate(location = if_else(location == "h", "v", "h")) %>%
  rename(opp_points = points)
team_periods <- team_periods %>%
  left_join(opp, by = c("gameId", "period", "location")) %>%
  mutate(net = points - opp_points)
stopifnot(!anyNA(team_periods$opp_points))

write_csv(team_periods %>% arrange(gameId, period, location),
          file.path(OUT_DIR, "team_period_windows_r.csv"))
message(sprintf("%s team-periods with at least one shot in the final %ds of Q1-Q3",
                format(nrow(team_periods), big.mark = ","), WINDOW_SEC))

# ---- First-shot timing histogram --------------------------------------------
team_periods %>%
  mutate(bucket = floor(first_fga_sec)) %>%
  count(bucket, name = "n") %>%
  arrange(bucket) %>%
  write_csv(file.path(OUT_DIR, "first_shot_timing_r.csv"))

# ---- Group summary ----------------------------------------------------------
summary_tbl <- team_periods %>%
  group_by(two_for_one) %>%
  summarise(
    team_periods_n = n(),
    mean_points = mean(points),
    mean_opp_points = mean(opp_points),
    mean_net = mean(net),
    mean_fga = mean(n_fga),
    mean_efg = (sum(fgm) + 0.5 * sum(fg3m)) / sum(n_fga),
    .groups = "drop"
  ) %>%
  arrange(desc(two_for_one))
write_csv(summary_tbl, file.path(OUT_DIR, "two_for_one_summary_r.csv"))
print(as.data.frame(summary_tbl))

# ---- Bootstraps (R RNG, so reconciliation compares CI overlap, not equality) -
# boot_diff() lives in R/functions.R and is unit-tested.

full_pts <- boot_diff(team_periods, "points", seed = 42)
full_net <- boot_diff(team_periods, "net", seed = 43)
write_csv(full_pts %>% mutate(quantity = "points_diff_2for1_minus_hold", .before = 1),
          file.path(OUT_DIR, "bootstrap_points_diff_r.csv"))
write_csv(full_net %>% mutate(quantity = "net_diff_2for1_minus_hold", .before = 1),
          file.path(OUT_DIR, "bootstrap_net_diff_r.csv"))
message(sprintf("Own-points gap: %+.3f [%+.3f, %+.3f]",
                full_pts$estimate, full_pts$ci_lo, full_pts$ci_hi))
message(sprintf("Net-points gap: %+.3f [%+.3f, %+.3f]",
                full_net$estimate, full_net$ci_lo, full_net$ci_hi))

narrow <- team_periods %>% filter(between(first_fga_sec, 20, 45))
if (sum(narrow$two_for_one) > 30 && sum(!narrow$two_for_one) > 30) {
  r_pts <- boot_diff(narrow, "points", seed = 44)
  r_net <- boot_diff(narrow, "net", seed = 45)
  write_csv(r_pts %>% mutate(quantity = "points_diff_restricted_20_45s", .before = 1),
            file.path(OUT_DIR, "bootstrap_restricted_r.csv"))
  write_csv(r_net %>% mutate(quantity = "net_diff_restricted_20_45s", .before = 1),
            file.path(OUT_DIR, "bootstrap_net_restricted_r.csv"))
  message(sprintf("Restricted own: %+.3f [%+.3f, %+.3f] | net: %+.3f [%+.3f, %+.3f]",
                  r_pts$estimate, r_pts$ci_lo, r_pts$ci_hi,
                  r_net$estimate, r_net$ci_lo, r_net$ci_hi))
}

# ---- Shot quality by clock ---------------------------------------------------
per %>%
  filter(secs_left <= WINDOW_SEC, is_fga) %>%
  mutate(bucket = floor(secs_left / 4) * 4) %>%
  group_by(bucket) %>%
  summarise(n = n(),
            efg = (sum(made) + 0.5 * sum(made & shot_value == 3)) / n(),
            .groups = "drop") %>%
  filter(n >= 100, bucket < WINDOW_SEC) %>%
  arrange(bucket) %>%
  write_csv(file.path(OUT_DIR, "efg_by_seconds_left_r.csv"))

message("R analysis complete.")
