"""League-seasons in the study and where each one's files live.

The original study is NBA 2023-24, and its outputs stay exactly where they
were (output/, figures/), so the published README, pages, and number
bindings keep pointing at the same files. Every other league-season writes to
output/seasons/<tag>/, with its diagnostic figures in a gitignored figures/
folder there.

All harvested play-by-play shares one flat cache, data/raw_pbp/, keyed by
game ID. The ID encodes league and season: "0022400123" is NBA ("002"),
2024-25 ("24"); "1022600017" is WNBA ("102"), 2026 ("26"). Each step selects
its games by that prefix, never by globbing the whole cache.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw_pbp"

LEAGUE_PREFIX = {"nba": "002", "wnba": "102"}

# (league, season) in display order. Team counts gate the team table.
SEASONS = [
    ("nba", "2023-24"), ("nba", "2024-25"), ("nba", "2025-26"),
    ("wnba", "2024"), ("wnba", "2025"), ("wnba", "2026"),
]
N_TEAMS = {
    ("nba", "2023-24"): 30, ("nba", "2024-25"): 30, ("nba", "2025-26"): 30,
    ("wnba", "2024"): 12, ("wnba", "2025"): 13, ("wnba", "2026"): 15,
}
ORIGINAL = ("nba", "2023-24")

# The shufinskiy/nba_data pbpstats archive, where it has the season.
ARCHIVE = {
    ("nba", "2023-24"): ROOT.parent / "lineup-valuation-study" / "data"
                        / "pbp_bulk" / "pbpstats_2023.csv",
    ("nba", "2024-25"): ROOT / "data" / "pbp_bulk" / "pbpstats_2024.csv",
    ("wnba", "2024"): ROOT / "data" / "pbp_bulk" / "wnba_pbpstats_2024.csv",
    ("wnba", "2025"): ROOT / "data" / "pbp_bulk" / "wnba_pbpstats_2025.csv",
}


def tag(league: str, season: str) -> str:
    return f"{league}_{season}"


def label(league: str, season: str) -> str:
    return f"{league.upper()} {season}"


def prefix(league: str, season: str) -> str:
    """Game-ID prefix: NBA 2025-26 -> "00225", WNBA 2026 -> "10226"."""
    if (league, season) not in N_TEAMS:
        raise ValueError(f"unknown league-season {league} {season}")
    return LEAGUE_PREFIX[league] + season[2:4]


def raw_files(league: str, season: str) -> list[Path]:
    files = sorted(RAW_DIR.glob(f"{prefix(league, season)}*.parquet"))
    if not files:
        raise SystemExit(f"No play-by-play for {label(league, season)} in {RAW_DIR}. "
                         f"Run 01_harvest_pbp.py --league {league} --season {season}.")
    return files


def out_dir(league: str, season: str) -> Path:
    if (league, season) == ORIGINAL:
        return ROOT / "output"
    return ROOT / "output" / "seasons" / tag(league, season)


def fig_dir(league: str, season: str) -> Path:
    """Per-season figures stay out of figures/: report_builder publishes every
    figure under figures/, and these are local diagnostics no page links.
    They go to a gitignored folder next to the season's outputs."""
    if (league, season) == ORIGINAL:
        return ROOT / "figures"
    return ROOT / "output" / "seasons" / tag(league, season) / "figures"


def possessions_file(league: str, season: str) -> Path:
    """The pbpstats-library possession table built by 07_build_possessions.py."""
    return ROOT / "data" / "possessions" / f"{tag(league, season)}.parquet"


def add_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--league", choices=sorted(LEAGUE_PREFIX), default=ORIGINAL[0])
    ap.add_argument("--season", default=ORIGINAL[1])
