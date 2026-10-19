# Pure functions for the play-by-play analysis, extracted so both the pipeline
# script (02_analysis.R) and the test suite (../../tests/R) can source them.

#' "PT11M42.50S" -> 702.5 seconds remaining in the period; NA if unparseable.
parse_clock_secs <- function(clock) {
  as.numeric(stringr::str_match(clock, "PT(\\d+)M")[, 2]) * 60 +
    as.numeric(stringr::str_match(clock, "M([\\d.]+)S")[, 2])
}

#' Game-ID prefix of a league-season: ("nba", "2025-26") -> "00225",
#' ("wnba", "2026") -> "10226". Mirrors python/seasons.py's prefix().
season_prefix <- function(league, season) {
  lead <- c(nba = "002", wnba = "102")[[league]]
  paste0(lead, substr(season, 3, 4))
}

#' Bootstrap the difference in mean `outcome` between two-for-one and held
#' team-periods. `frame` needs logical `two_for_one` and the outcome column.
boot_diff <- function(frame, outcome, seed, reps = 4000) {
  a <- frame[[outcome]][frame$two_for_one]
  b <- frame[[outcome]][!frame$two_for_one]
  set.seed(seed)
  boots <- purrr::map_dbl(seq_len(reps), function(i) {
    mean(sample(a, replace = TRUE)) - mean(sample(b, replace = TRUE))
  })
  ci <- quantile(boots, c(0.025, 0.975))
  tibble::tibble(estimate = mean(a) - mean(b), ci_lo = ci[[1]], ci_hi = ci[[2]],
                 reps = reps, n_treated = length(a), n_control = length(b))
}
