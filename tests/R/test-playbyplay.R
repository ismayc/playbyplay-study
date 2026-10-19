# Unit tests for playbyplay-study/R/functions.R

source(file.path(REPO, "R", "functions.R"))

test_that("parse_clock_secs converts the PT..M..S format", {
  expect_equal(parse_clock_secs("PT11M42.50S"), 11 * 60 + 42.5)
  expect_equal(parse_clock_secs("PT0M05.00S"), 5)
  expect_true(is.na(parse_clock_secs("garbage")))
})

test_that("season_prefix matches the game-ID prefixes in python/seasons.py", {
  expect_equal(season_prefix("nba", "2023-24"), "00223")
  expect_equal(season_prefix("nba", "2025-26"), "00225")
  expect_equal(season_prefix("wnba", "2024"), "10224")
  expect_equal(season_prefix("wnba", "2026"), "10226")
  expect_error(season_prefix("gleague", "2024"))
})

test_that("boot_diff estimates the group mean difference with a sane CI", {
  frame <- tibble::tibble(
    two_for_one = rep(c(TRUE, FALSE), each = 200),
    points = c(rnorm(200, mean = 2), rnorm(200, mean = 1))
  )
  b <- boot_diff(frame, "points", seed = 1, reps = 500)
  expect_equal(b$estimate,
               mean(frame$points[frame$two_for_one]) -
                 mean(frame$points[!frame$two_for_one]))
  expect_lt(b$ci_lo, b$estimate)
  expect_gt(b$ci_hi, b$estimate)
  expect_equal(b$n_treated, 200)
  # deterministic under the same seed
  b2 <- boot_diff(frame, "points", seed = 1, reps = 500)
  expect_equal(b$ci_lo, b2$ci_lo)
})
