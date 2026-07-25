"""Harvest NBA play-by-play for a full season.

Source
------
stats.nba.com `PlayByPlayV3`, via the `nba_api` package. One request returns every
logged event for one game (~450-550 rows): period, game clock, action type, the
acting player, running score, and — for shot events — court coordinates
(xLegacy, yLegacy) and shot distance.

Game IDs come from `LeagueGameFinder`, which returns one row per team per game;
de-duplicating on GAME_ID gives the 1,230-game regular season.

Design
------
Resumable and cached: one parquet per game under data/raw_pbp/. An interrupted run
picks up where it stopped and the analysis never re-hits the network.

Usage:
    python 01_harvest_pbp.py --season 2023-24 [--limit N]
"""
from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

import polars as pl
from nba_api.stats.endpoints import leaguegamefinder, playbyplayv3

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw_pbp"

BASE_SLEEP = 0.5
MAX_RETRIES = 4
TIMEOUT = 45


def game_ids(season: str) -> list[str]:
    df = leaguegamefinder.LeagueGameFinder(
        season_nullable=season, league_id_nullable="00",
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
    ap.add_argument("--season", default="2023-24")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ids = game_ids(args.season)
    if args.limit:
        ids = ids[:args.limit]
    print(f"{len(ids)} games for {args.season}", flush=True)

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
