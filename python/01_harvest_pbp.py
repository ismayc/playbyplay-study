"""Harvest NBA or WNBA play-by-play for a full regular season.

Source
------
stats.nba.com `PlayByPlayV3`, via the `nba_api` package. One request returns every
logged event for one game (~450-550 rows): period, game clock, action type, the
acting player, running score, and — for shot events — court coordinates
(xLegacy, yLegacy) and shot distance.

Game IDs come from `LeagueGameFinder`, which returns one row per team per game;
de-duplicating on GAME_ID gives the 1,230-game NBA regular season. The WNBA
(LeagueID 10) is served by the same endpoints with single-year season strings
("2025"); its regular seasons ran 240, 286, and 330 games in 2024-2026.

Design
------
Resumable and cached: one parquet per game under data/raw_pbp/. An interrupted run
picks up where it stopped and the analysis never re-hits the network. League and
season are encoded in the game ID ("00224..." is NBA 2024-25, "10225..." is WNBA
2025), so every league-season shares one flat cache.

Usage:
    python 01_harvest_pbp.py --season 2023-24 [--limit N]
    python 01_harvest_pbp.py --league wnba --season 2025
"""
from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

import polars as pl
from nba_api.stats.endpoints import leaguegamefinder, playbyplayv3
from nba_api.stats.library import http

# nba_api's shipped Firefox/72 User-Agent hangs on stats.nba.com; a generic one
# without a browser token returns at once (same fix as basketball-analysis-tools'
# nba_api_compat.fix_user_agent, inlined so this repo runs standalone).
http.STATS_HEADERS["User-Agent"] = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                    "AppleWebKit/537.36")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw_pbp"

BASE_SLEEP = 0.5
MAX_RETRIES = 4
TIMEOUT = 45

LEAGUE_IDS = {"nba": "00", "wnba": "10"}


def game_ids(season: str, league: str = "nba") -> list[str]:
    df = leaguegamefinder.LeagueGameFinder(
        season_nullable=season, league_id_nullable=LEAGUE_IDS[league],
        season_type_nullable="Regular Season", timeout=60,
    ).get_data_frames()[0]
    return sorted(df["GAME_ID"].unique().tolist())


def fetch_game(game_id: str) -> bool:
    """Fetch one game's play-by-play. Returns True if cached or fetched."""
    cache = RAW_DIR / f"{game_id}.parquet"
    if cache.exists():
        return True

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = playbyplayv3.PlayByPlayV3(game_id=game_id, timeout=TIMEOUT).get_data_frames()[0]
            # Every column to string: the endpoint is inconsistent about numeric
            # types across games (empty score fields early in a game, etc.).
            pl.from_pandas(df.astype(str)).write_parquet(cache)
            time.sleep(BASE_SLEEP + random.uniform(0, 0.25))
            return True
        except Exception as exc:  # noqa: BLE001 - endpoint raises many error types
            wait = BASE_SLEEP * (2 ** attempt) + random.uniform(0, 1)
            print(f"    retry {attempt}/{MAX_RETRIES} {game_id}: "
                  f"{type(exc).__name__} (waiting {wait:.1f}s)", flush=True)
            time.sleep(wait)
    print(f"    FAILED {game_id}", flush=True)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", choices=sorted(LEAGUE_IDS), default="nba")
    ap.add_argument("--season", default="2023-24")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ids = game_ids(args.season, args.league)
    if args.limit:
        ids = ids[:args.limit]
    print(f"{len(ids)} games for {args.league} {args.season}", flush=True)

    ok = fail = 0
    for i, gid in enumerate(ids, 1):
        if fetch_game(gid):
            ok += 1
        else:
            fail += 1
        if i % 50 == 0:
            print(f"  {i}/{len(ids)}  ok={ok} fail={fail}", flush=True)

    print(f"\nDone. {ok} games cached, {fail} failed -> {RAW_DIR}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
