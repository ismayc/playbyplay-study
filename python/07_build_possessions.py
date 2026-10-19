"""Build possession tables with the pbpstats library, one league-season at a time.

Why
---
05_possession_analysis.py first ran on the shufinskiy/nba_data bulk archive of
pbpstats possessions. That archive stops at NBA 2024-25 and WNBA 2025, so the
seasons it lacks (NBA 2025-26, WNBA 2026) are built here with the pbpstats
library itself. Every season is built the same way, including the ones the
archive covers, so 08_reconcile_possessions.py can check this builder against
the archive before any season that has only this builder is trusted.

Source
------
pbpstats' "live" data provider: the NBA's liveData play-by-play JSON
(nba-prod-us-east-1-mediaops-stats.s3.amazonaws.com/<league>/liveData/...),
which serves both leagues (game IDs 00... and 10...). It is a different host
from stats.nba.com, so this can run while 01_harvest_pbp.py is harvesting.

Output
------
data/possessions/<league>_<season>.parquet, one row per possession, in the
archive's shape so 05 reads either source the same way:
    game_id, PERIOD, start_secs, end_secs, offense_team_id, TURNOVERS
start_secs and end_secs are seconds left in the period, floored to whole
seconds because the archive stores MM:SS (30.1s left is "00:30" there).

The raw JSON cache (data/pbpstats_live/, ~450 KB a game, ~2 GB in all) is
gitignored; the parquet tables are committed.

Missing starters
----------------
pbpstats infers each period's five starters per team from the events and
raises InvalidNumberOfStartersException when it finds fewer (9 of 1,230 NBA
2023-24 games, eight of them in overtime). Possession boundaries and the team
on offense come from the events, not the lineups, so those games are rebuilt
in a second, serial pass with the starter check off (pbpstats' own
ignore_missing_starters flag, which its loader never passes) and flagged
lenient_starters=True. 08_reconcile_possessions.py checks them separately.

Blank-subtype fouls
-------------------
pbpstats raises AttributeError ('LiveFoul' object has no attribute
'sub_type') on a foul whose subType is empty, as in 0022400322's "TEAM foul"
at 0:00 of Q4. Such a game is rebuilt from a copy of its JSON with only those
foul actions removed (data/pbpstats_live_sanitized/, also gitignored) and
flagged sanitized=True.

Usage:
    python python/07_build_possessions.py --league nba --season 2025-26
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import polars as pl
from pbpstats.client import Client
from pbpstats.resources.enhanced_pbp import (FieldGoal, FreeThrow,
                                              InvalidNumberOfStartersException, Turnover)
from pbpstats.resources.enhanced_pbp.live.start_of_period import LiveStartOfPeriod

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seasons  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "pbpstats_live"
SANITIZED = ROOT / "data" / "pbpstats_live_sanitized"
WORKERS = 4


def game_ids(league: str, season: str) -> list[str]:
    """The regular season's games, taken from the harvested V3 cache so both
    layers describe exactly the same games."""
    return [p.stem for p in seasons.raw_files(league, season)]


def clock_secs(clock: str) -> float:
    m = re.fullmatch(r"PT(\d+)M([\d.]+)S", clock)
    if not m:
        raise ValueError(f"unparsed clock {clock!r}")
    return int(m.group(1)) * 60 + float(m.group(2))


def client(source: str, root: Path = CACHE) -> Client:
    for sub in ("pbp", "game_details", "overrides", "schedule", "boxscore"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return Client({"dir": str(root),
                   "Possessions": {"source": source, "data_provider": "live"}})


def build_game(game_id: str, lenient: bool = False, sanitized: bool = False) -> list[dict]:
    if sanitized:
        game = client("file", SANITIZED).Game(game_id)
    else:
        cached = (CACHE / "pbp" / f"live_{game_id}.json").exists()
        game = client("file" if cached else "web").Game(game_id)
    rows = []
    for p in game.possessions.items:
        rows.append({
            "game_id": int(game_id),
            "PERIOD": int(p.period),
            # floor, matching the archive's MM:SS resolution
            "start_secs": float(int(clock_secs(p.start_time))),
            "end_secs": float(int(clock_secs(p.end_time))),
            "offense_team_id": int(p.offense_team_id),
            "TURNOVERS": sum(1 for e in p.events if isinstance(e, Turnover)
                             and not getattr(e, "is_no_turnover", False)),
            # what the possession did with the ball; 05 counts "later
            # possessions" as those that used it (a shot, a free-throw trip,
            # or a turnover), a definition both sources can compute
            "FGA": sum(1 for e in p.events if isinstance(e, FieldGoal)),
            "FTA": sum(1 for e in p.events if isinstance(e, FreeThrow)),
            "lenient_starters": lenient,
            "sanitized": sanitized,
        })
    return rows


def build_sanitized(game_id: str) -> list[dict]:
    """Rebuild from a copy of the cached JSON without blank-subtype fouls."""
    src = CACHE / "pbp" / f"live_{game_id}.json"
    data = json.loads(src.read_text())
    actions = data["game"]["actions"]
    keep = [a for a in actions if not (a.get("actionType") == "foul"
                                       and not a.get("subType"))]
    if len(keep) == len(actions):
        raise RuntimeError("no blank-subtype foul to remove")
    data["game"]["actions"] = keep
    (SANITIZED / "pbp").mkdir(parents=True, exist_ok=True)
    (SANITIZED / "pbp" / src.name).write_text(json.dumps(data))
    try:
        return build_game(game_id, sanitized=True)
    except InvalidNumberOfStartersException:
        return build_lenient(game_id, sanitized=True)


def build_lenient(game_id: str, sanitized: bool = False) -> list[dict]:
    """Rebuild one game with pbpstats' starter check off. Serial only: the
    patch is class-wide, so it must never overlap a strict build."""
    original = LiveStartOfPeriod.get_period_starters

    def lenient_starters(self, file_directory=None, ignore_missing_starters=True):
        return original(self, file_directory, ignore_missing_starters=True)

    LiveStartOfPeriod.get_period_starters = lenient_starters
    try:
        return build_game(game_id, lenient=True, sanitized=sanitized)
    finally:
        LiveStartOfPeriod.get_period_starters = original


def main() -> int:
    ap = argparse.ArgumentParser()
    seasons.add_args(ap)
    args = ap.parse_args()

    ids = game_ids(args.league, args.season)
    print(f"{len(ids)} games for {args.league} {args.season}", flush=True)
    rows: list[dict] = []
    failed: list[str] = []
    no_starters: list[str] = []
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(build_game, gid): gid for gid in ids}
        for i, fut in enumerate(as_completed(futures), 1):
            gid = futures[fut]
            try:
                rows.extend(fut.result())
            except InvalidNumberOfStartersException:
                no_starters.append(gid)
            except Exception as exc:  # noqa: BLE001 - pbpstats raises many types
                failed.append(gid)
                print(f"    FAILED {gid}: {type(exc).__name__}: {str(exc)[:160]}",
                      flush=True)
            if i % 100 == 0:
                print(f"  {i}/{len(ids)}  starters-missing={len(no_starters)} "
                      f"failed={len(failed)}", flush=True)

    for gid in sorted(no_starters):
        try:
            rows.extend(build_lenient(gid))
        except Exception as exc:  # noqa: BLE001
            failed.append(gid)
            print(f"    FAILED (lenient) {gid}: {type(exc).__name__}: "
                  f"{str(exc)[:160]}", flush=True)
    print(f"rebuilt {len(no_starters) - sum(g in failed for g in no_starters)} of "
          f"{len(no_starters)} missing-starter games with the starter check off",
          flush=True)

    for gid in [g for g in failed if g not in no_starters]:
        try:
            rows.extend(build_sanitized(gid))
            failed.remove(gid)
            print(f"    rebuilt {gid} without its blank-subtype foul(s)", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"    FAILED (sanitized) {gid}: {type(exc).__name__}: "
                  f"{str(exc)[:160]}", flush=True)

    out = seasons.possessions_file(args.league, args.season)
    out.parent.mkdir(parents=True, exist_ok=True)
    table = pl.DataFrame(rows).sort(["game_id", "PERIOD", "start_secs"],
                                    descending=[False, False, True])
    table.write_parquet(out)
    print(f"\nWrote {table.height:,} possessions from "
          f"{table['game_id'].n_unique():,} games to {out}")
    if failed:
        print(f"FAILED games ({len(failed)}): {' '.join(sorted(failed))}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
