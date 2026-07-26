"""Unit tests for playbyplay-study/python/02_analysis.py.

Includes a regression test for the actionNumber text-sort bug: events must be
ordered numerically, or the score forward-fill scrambles ("100" < "2" as text).
"""
from __future__ import annotations

import polars as pl
import pytest


def _write_game(tmp_path, rows):
    """Minimal PlayByPlayV3-shaped parquet (all-text columns, like the feed)."""
    cols = ["gameId", "actionNumber", "clock", "period", "isFieldGoal",
            "shotResult", "shotValue", "scoreHome", "scoreAway", "location"]
    data = {c: [str(r.get(c, "")) for r in rows] for c in cols}
    (tmp_path / "raw_pbp").mkdir(exist_ok=True)
    pl.DataFrame(data).write_parquet(tmp_path / "raw_pbp" / "g1.parquet")


def test_actionnumber_sorted_numerically(pbp, tmp_path, monkeypatch):
    # Three scoring events whose TEXT order (100, 2, 30) differs from their
    # numeric order (2, 30, 100). After load_events the forward-filled score
    # at the last event must be the chronologically-last score (6-0), not the
    # lexicographically-last.
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
    _write_game(tmp_path, rows)
    monkeypatch.setattr(pbp, "RAW_DIR", tmp_path / "raw_pbp")
    df = pbp.load_events()
    assert df["actionNumber"].to_list() == [2, 30, 100]
    assert df["score_h"].to_list() == [2.0, 4.0, 6.0]


def test_clock_parse(pbp, tmp_path, monkeypatch):
    rows = [{"gameId": "1", "actionNumber": "1", "clock": "PT11M42.50S",
             "period": "1", "isFieldGoal": "0", "shotResult": "", "shotValue": "0",
             "scoreHome": "0", "scoreAway": "0", "location": ""}]
    _write_game(tmp_path, rows)
    monkeypatch.setattr(pbp, "RAW_DIR", tmp_path / "raw_pbp")
    df = pbp.load_events()
    assert df["secs_left"][0] == pytest.approx(11 * 60 + 42.5)


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
