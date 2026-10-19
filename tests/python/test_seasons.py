"""Unit tests for the multi-season helpers: seasons.py, the V3 archive import's
normalization, and the liveData window points used by the source check."""
from __future__ import annotations

import json

import polars as pl
import pytest

from conftest import load_script


@pytest.fixture(scope="module")
def seasons_mod():
    return load_script("python/seasons.py", "pbp_seasons")


@pytest.fixture(scope="module")
def importer():
    return load_script("python/01b_import_v3_archive.py", "pbp_import_v3")


@pytest.fixture(scope="module")
def source_check():
    return load_script("python/10_check_sources.py", "pbp_source_check")


def test_prefixes_encode_league_and_season(seasons_mod):
    assert seasons_mod.prefix("nba", "2023-24") == "00223"
    assert seasons_mod.prefix("nba", "2025-26") == "00225"
    assert seasons_mod.prefix("wnba", "2024") == "10224"
    with pytest.raises(ValueError):
        seasons_mod.prefix("nba", "2019-20")   # not a season in this study


def test_original_season_keeps_its_published_paths(seasons_mod):
    root = seasons_mod.ROOT
    assert seasons_mod.out_dir("nba", "2023-24") == root / "output"
    assert seasons_mod.out_dir("wnba", "2026") == root / "output" / "seasons" / "wnba_2026"


def test_archive_rows_normalize_to_the_api_format(importer, tmp_path, monkeypatch):
    # The three representation differences found on 0022400001: gameId loses
    # its leading zeros, missing scores are null, and some text is right-padded.
    row = {c: "" for c in importer.COLUMNS}
    row.update(gameId="22400001", actionNumber="7", period="1",
               actionType="Instant Replay      ", scoreHome=None, scoreAway=None)
    name = importer.archive_name("nba", "2024-25")
    monkeypatch.setattr(importer, "BULK", tmp_path)
    pl.DataFrame([row]).write_csv(tmp_path / f"{name}.csv")
    (tmp_path / f"{name}.tar.xz").write_bytes(b"")   # present, so nothing downloads
    out = importer.load_archive("nba", "2024-25").row(0, named=True)
    assert out["gameId"] == "0022400001"
    assert out["actionType"] == "Instant Replay"
    assert out["scoreHome"] == "" and out["scoreAway"] == ""


def test_archive_name_by_league(importer):
    assert importer.archive_name("nba", "2025-26") == "nbastatsv3_2025"
    assert importer.archive_name("wnba", "2026") == "wnba_nbastatsv3_2026"


def test_live_window_points_use_the_60_second_mark(source_check, tmp_path, monkeypatch):
    acts = [
        {"period": 1, "orderNumber": 1, "clock": "PT01M10.00S", "scoreHome": "10", "scoreAway": "8"},
        {"period": 1, "orderNumber": 2, "clock": "PT00M45.00S", "scoreHome": "12", "scoreAway": "8"},
        {"period": 1, "orderNumber": 3, "clock": "PT00M00.00S", "scoreHome": "12", "scoreAway": "11"},
    ]
    monkeypatch.setattr(source_check, "LIVE", tmp_path)
    (tmp_path / "live_0029900001.json").write_text(json.dumps({"game": {"actions": acts}}))
    pts = {r["location"]: r["points_live"] for r in source_check.live_window_points("0029900001")}
    assert pts == {"h": 2.0, "v": 3.0}
