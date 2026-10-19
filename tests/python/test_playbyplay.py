"""Unit tests for playbyplay-study/python/02_analysis.py and its helpers.

Includes regression tests for two ordering bugs in the score forward-fill:
  * actionNumber sorted as TEXT ("100" < "2") scrambled the fill;
  * actionNumber order itself let late-inserted events (high number, early
    clock) carry the period-end score into the 60-second mark, which zeroed
    15% of 2023-24 windows until 2026-10-19. Events are now in clock order.
"""
from __future__ import annotations

import polars as pl
import pytest


def _raw(rows):
    """Minimal PlayByPlayV3-shaped frame (all-text columns, like the feed)."""
    cols = ["gameId", "actionNumber", "clock", "period", "isFieldGoal",
            "shotResult", "shotValue", "scoreHome", "scoreAway", "location"]
    return pl.DataFrame({c: [str(r.get(c, "")) for r in rows] for c in cols})


def test_actionnumber_sorted_numerically(pbp):
    # Three scoring events whose TEXT order (100, 2, 30) differs from their
    # numeric order (2, 30, 100). After prepare_events the forward-filled
    # score at the last event must be the chronologically-last score (6-0),
    # not the lexicographically-last.
    rows = [
        {"gameId": "1", "actionNumber": "2", "clock": "PT10M00.00S", "period": "1",
         "isFieldGoal": "1", "shotResult": "Made", "shotValue": "2",
         "scoreHome": "2", "scoreAway": "0", "location": "h"},
        {"gameId": "1", "actionNumber": "30", "clock": "PT08M00.00S", "period": "1",
         "isFieldGoal": "1", "shotResult": "Made", "shotValue": "2",
         "scoreHome": "4", "scoreAway": "0", "location": "h"},
        {"gameId": "1", "actionNumber": "100", "clock": "PT02M00.00S", "period": "1",
         "isFieldGoal": "1", "shotResult": "Made", "shotValue": "2",
         "scoreHome": "6", "scoreAway": "0", "location": "h"},
    ]
    df = pbp.prepare_events(_raw(list(reversed(rows))))
    assert df["actionNumber"].to_list() == [2, 30, 100]
    assert df["score_h"].to_list() == [2.0, 4.0, 6.0]


def test_late_inserted_event_does_not_zero_the_window(pbp):
    # The shape of 0022300002 Q1: score 21-22 at 63s; the visitors hit a three
    # at 19.2s (21-25); the period ends; then three events logged LATE carry
    # high action numbers but a 5:05 clock. In action-number order the last
    # event "with more than 60s left" was a stray carrying 21-25, so the
    # window read 0 points for the visitors. In clock order it reads 3.
    rows = [
        {"gameId": "1", "actionNumber": "139", "clock": "PT01M06.00S", "period": "1",
         "isFieldGoal": "0", "scoreHome": "21", "scoreAway": "22", "location": "v"},
        {"gameId": "1", "actionNumber": "140", "clock": "PT01M03.00S", "period": "1",
         "isFieldGoal": "0", "location": "h"},
        {"gameId": "1", "actionNumber": "148", "clock": "PT00M19.20S", "period": "1",
         "isFieldGoal": "1", "shotResult": "Made", "shotValue": "3",
         "scoreHome": "21", "scoreAway": "25", "location": "v"},
        {"gameId": "1", "actionNumber": "152", "clock": "PT00M00.00S", "period": "1",
         "isFieldGoal": "0", "scoreHome": "21", "scoreAway": "25"},
        {"gameId": "1", "actionNumber": "244", "clock": "PT05M05.00S", "period": "1",
         "isFieldGoal": "0", "location": "h"},
        {"gameId": "1", "actionNumber": "246", "clock": "PT05M04.00S", "period": "1",
         "isFieldGoal": "0", "location": "v"},
    ]
    df = pbp.prepare_events(_raw(rows))
    # the strays sit at their game time and inherit that time's score
    stray = df.filter(pl.col("actionNumber") == 244).row(0, named=True)
    assert (stray["score_h"], stray["score_a"]) == (0.0, 0.0)
    pts = {r["location"]: r["points"] for r in pbp.window_points(df).iter_rows(named=True)}
    assert pts == {"h": 0.0, "v": 3.0}


def test_clock_parse(pbp):
    rows = [{"gameId": "1", "actionNumber": "1", "clock": "PT11M42.50S",
             "period": "1", "isFieldGoal": "0", "shotResult": "", "shotValue": "0",
             "scoreHome": "0", "scoreAway": "0", "location": ""}]
    df = pbp.prepare_events(_raw(rows))
    assert df["secs_left"][0] == pytest.approx(11 * 60 + 42.5)


def test_team_period_table_is_sorted(pbp):
    # The bootstraps draw by row position, so the table must come back in key
    # order whatever order polars' joins produce.
    rows = []
    for g in ("2", "1"):
        rows += [
            {"gameId": g, "actionNumber": "1", "clock": "PT01M30.00S", "period": "1",
             "isFieldGoal": "0", "scoreHome": "10", "scoreAway": "10", "location": "h"},
            {"gameId": g, "actionNumber": "2", "clock": "PT00M40.00S", "period": "1",
             "isFieldGoal": "1", "shotResult": "Made", "shotValue": "2",
             "scoreHome": "10", "scoreAway": "12", "location": "v"},
            {"gameId": g, "actionNumber": "3", "clock": "PT00M10.00S", "period": "1",
             "isFieldGoal": "1", "shotResult": "Missed", "shotValue": "3",
             "location": "h"},
        ]
    t = pbp.team_period_table(pbp.prepare_events(_raw(rows)))
    assert t.select("gameId", "location").rows() == [("1", "h"), ("1", "v"),
                                                     ("2", "h"), ("2", "v")]
    v = t.filter(pl.col("location") == "v").row(0, named=True)
    assert (v["points"], v["opp_points"], v["net"], v["two_for_one"]) == (2.0, 0.0, 2.0, True)


def _processed(rows):
    """Frame shaped like load_events output for the window functions."""
    return pl.DataFrame(rows, schema={
        "gameId": pl.Utf8, "period": pl.Int32, "actionNumber": pl.Int64,
        "secs_left": pl.Float64, "is_fga": pl.Boolean, "made": pl.Boolean,
        "shot_value": pl.Float64, "score_h": pl.Float64, "score_a": pl.Float64,
        "location": pl.Utf8,
    })


def test_window_points_score_delta(pbp):
    # Score 10-8 at the 60s mark; period ends 15-10 -> h scored 5, v scored 2.
    df = _processed([
        {"gameId": "1", "period": 1, "actionNumber": 1, "secs_left": 120.0,
         "is_fga": False, "made": False, "shot_value": 0.0,
         "score_h": 10.0, "score_a": 8.0, "location": "h"},
        {"gameId": "1", "period": 1, "actionNumber": 2, "secs_left": 30.0,
         "is_fga": True, "made": True, "shot_value": 3.0,
         "score_h": 13.0, "score_a": 8.0, "location": "h"},
        {"gameId": "1", "period": 1, "actionNumber": 3, "secs_left": 5.0,
         "is_fga": True, "made": True, "shot_value": 2.0,
         "score_h": 15.0, "score_a": 10.0, "location": "v"},
    ])
    pts = pbp.window_points(df)
    by_loc = {r["location"]: r["points"] for r in pts.iter_rows(named=True)}
    assert by_loc == {"h": 5.0, "v": 2.0}


def test_window_shots_first_fga_and_efg_inputs(pbp):
    df = _processed([
        {"gameId": "1", "period": 1, "actionNumber": 1, "secs_left": 45.0,
         "is_fga": True, "made": True, "shot_value": 3.0,
         "score_h": 3.0, "score_a": 0.0, "location": "h"},
        {"gameId": "1", "period": 1, "actionNumber": 2, "secs_left": 10.0,
         "is_fga": True, "made": False, "shot_value": 2.0,
         "score_h": 3.0, "score_a": 0.0, "location": "h"},
        # Q4 shot must be excluded
        {"gameId": "1", "period": 4, "actionNumber": 3, "secs_left": 30.0,
         "is_fga": True, "made": True, "shot_value": 2.0,
         "score_h": 5.0, "score_a": 0.0, "location": "h"},
    ])
    shots = pbp.window_shots(df)
    assert shots.height == 1
    row = shots.row(0, named=True)
    assert row["first_fga_sec"] == 45.0      # max secs_left = FIRST shot
    assert row["n_fga"] == 2
    assert row["fgm"] == 1
    assert row["fg3m"] == 1
