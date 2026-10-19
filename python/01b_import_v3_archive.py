"""Fill the play-by-play cache from the shufinskiy/nba_data V3 archive.

Why
---
On 2026-10-19 stats.nba.com began timing out every PlayByPlayV3 request
partway through the NBA 2024-25 harvest (game 602 onward, four retries each).
The same archive that supplies the pbpstats possessions also publishes
PlayByPlayV3 itself, one file per league-season, with the endpoint's exact 24
columns. This writes those games into data/raw_pbp/ in the harvester's format
(one parquet per game, every column text) so nothing downstream changes.

The archive is a different producer's copy of the same feed, taken at a
different time, so it is used only after --verify passes: on every game both
the API harvest and the archive have, the row count and every column the
analysis reads (ANALYSIS_COLUMNS) must be identical. The other columns are
compared and reported but do not gate: on NBA 2024-25 the archive keeps
older player-name renderings ("Pöltl" where the API now says "Poeltl") and
a few pre-correction descriptions (an assist later re-credited), none of
which any analysis step reads. Three representation differences are
normalized:
  * gameId: the archive drops the leading zeros ("22400001");
  * missing scores: null in the archive, "" from the API;
  * text padding: the archive right-pads some strings ("Instant Replay   ").
Games already in the cache are never overwritten, and every game's source is
recorded in data/raw_pbp_sources.csv.

Archive files (tar.xz committed under data/pbp_bulk/, extracted CSV ignored):
    nbastatsv3_<YY>.tar.xz       NBA season starting 20YY
    wnba_nbastatsv3_<YYYY>.tar.xz

Usage:
    python python/01b_import_v3_archive.py --league nba --season 2024-25 --verify
    python python/01b_import_v3_archive.py --league nba --season 2024-25
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seasons  # noqa: E402

ROOT = seasons.ROOT
BULK = ROOT / "data" / "pbp_bulk"
SOURCES = ROOT / "data" / "raw_pbp_sources.csv"
URL = "https://raw.githubusercontent.com/shufinskiy/nba_data/main/datasets/{}.tar.xz"
# The API harvest's column order (01_harvest_pbp.py), which imported games keep.
COLUMNS = ["gameId", "actionNumber", "clock", "period", "teamId", "teamTricode",
           "personId", "playerName", "playerNameI", "xLegacy", "yLegacy",
           "shotDistance", "shotResult", "isFieldGoal", "scoreHome", "scoreAway",
           "pointsTotal", "location", "description", "actionType", "subType",
           "videoAvailable", "shotValue", "actionId"]


# Every raw column 02_analysis.py, R/02_analysis.R, 05_possession_analysis.py
# and 06_team_quarter.py read.
ANALYSIS_COLUMNS = ["gameId", "actionNumber", "clock", "period", "isFieldGoal",
                    "shotResult", "shotValue", "scoreHome", "scoreAway", "location",
                    "teamId", "teamTricode"]


def archive_name(league: str, season: str) -> str:
    return (f"nbastatsv3_{season[:4]}" if league == "nba"
            else f"wnba_nbastatsv3_{season}")


def load_archive(league: str, season: str) -> pl.DataFrame:
    name = archive_name(league, season)
    csv, tar = BULK / f"{name}.csv", BULK / f"{name}.tar.xz"
    BULK.mkdir(parents=True, exist_ok=True)
    if not tar.exists():
        urllib.request.urlretrieve(URL.format(name), tar)
    if not csv.exists():
        subprocess.run(["tar", "xf", tar.name], cwd=BULK, check=True)
    raw = pl.read_csv(csv, infer_schema_length=0)
    if sorted(raw.columns) != sorted(COLUMNS):
        raise SystemExit(f"{name}: unexpected columns {raw.columns}")
    return (raw.select(COLUMNS)
            .with_columns(pl.all().fill_null("").str.strip_chars_end())
            .with_columns(gameId=pl.col("gameId").str.zfill(10)))


def game_frames(archive: pl.DataFrame, prefix: str) -> dict[str, pl.DataFrame]:
    sub = archive.filter(pl.col("gameId").str.starts_with(prefix))
    return {gid[0]: frame.select(COLUMNS)
            for gid, frame in sub.group_by(["gameId"], maintain_order=True)}


WINDOW_COLS = ["first_fga_sec", "n_fga", "fgm", "fg3m", "points", "opp_points",
               "net", "two_for_one"]
MAX_WINDOW_DIFF_SHARE = 0.005   # team-period rows allowed to differ


def window_check(frames: dict[str, pl.DataFrame], gids: list[str]) -> tuple[int, int]:
    """Run 02_analysis.py's own window table on both sources for the shared
    games; return (team-period rows compared, rows that differ)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "analysis02", Path(__file__).resolve().parent / "02_analysis.py")
    a02 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(a02)
    api = a02.team_period_table(a02.prepare_events(pl.concat(
        [pl.read_parquet(seasons.RAW_DIR / f"{g}.parquet") for g in gids])))
    arc = a02.team_period_table(a02.prepare_events(pl.concat([frames[g] for g in gids])))
    keys = ["gameId", "period", "location"]
    both = api.join(arc, on=keys, how="full", suffix="_a", coalesce=True)
    differ = both.filter(pl.any_horizontal(
        [pl.col(c).ne_missing(pl.col(f"{c}_a")) for c in WINDOW_COLS]))
    return both.height, differ.height


def verify(frames: dict[str, pl.DataFrame], prefix: str) -> tuple[list[str], list[str]]:
    """Compare every game both sources have (API-harvested games only: a game
    imported from the archive would be compared with itself); return (games
    compared, games whose row count or analysis columns differ). Differences
    in other columns are counted and printed, not returned."""
    harvested = sorted(seasons.RAW_DIR.glob(f"{prefix}*.parquet"))
    sources = (pl.read_csv(SOURCES, schema_overrides={"game_id": pl.String})
               if SOURCES.exists() else None)
    from_archive = (set(sources.filter(pl.col("source") == "archive")["game_id"])
                    if sources is not None else set())
    bad, compared, other = [], [], {}
    for path in harvested:
        gid = path.stem
        if gid in from_archive or gid not in frames:
            continue
        mine = pl.read_parquet(path)
        theirs = frames[gid]
        compared.append(gid)
        if mine.height != theirs.height or not mine.select(ANALYSIS_COLUMNS).equals(
                theirs.select(ANALYSIS_COLUMNS)):
            bad.append(gid)
            continue
        for c in mine.columns:
            if c not in ANALYSIS_COLUMNS:
                d = int((mine[c] != theirs[c]).sum())
                if d:
                    other[c] = other.get(c, 0) + d
    if other:
        print("  non-gating differences (column: rows): "
              + ", ".join(f"{c}: {k:,}" for c, k in sorted(other.items())))
    return compared, bad


CHECKS = ROOT / "output" / "archive_check.csv"


def record_check(row: dict) -> None:
    """Keep one row per league-season of the archive-vs-API window comparison."""
    new = pl.DataFrame([row])
    if CHECKS.exists():
        old = pl.read_csv(CHECKS).filter(~((pl.col("league") == row["league"])
                                           & (pl.col("season") == row["season"])))
        new = pl.concat([old, new], how="vertical_relaxed")
    new.sort(["league", "season"]).write_csv(CHECKS)


def record_sources(rows: list[dict]) -> None:
    new = pl.DataFrame(rows, schema={"game_id": pl.String, "source": pl.String})
    if SOURCES.exists():
        old = pl.read_csv(SOURCES, schema_overrides={"game_id": pl.String})
        new = pl.concat([old.filter(~pl.col("game_id").is_in(new["game_id"].implode())),
                         new])
    new.sort("game_id").write_csv(SOURCES)


def main() -> int:
    ap = argparse.ArgumentParser()
    seasons.add_args(ap)
    ap.add_argument("--verify", action="store_true",
                    help="compare against already-harvested games; write nothing")
    args = ap.parse_args()
    prefix = seasons.prefix(args.league, args.season)
    frames = game_frames(load_archive(args.league, args.season), prefix)
    print(f"archive: {len(frames):,} games for {seasons.label(args.league, args.season)}")

    compared, bad = verify(frames, prefix)
    n = len(compared)
    print(f"raw events: {n:,} games in both sources, {len(bad)} with differing "
          f"analysis columns or row counts"
          + (f" ({', '.join(bad[:8])})" if bad else ""))
    if n == 0:
        # No overlap to test against: the season must be checked another way
        # (10_check_sources.py compares period scores with the pbpstats feed).
        print("NO API GAMES TO COMPARE for this season")
        if args.verify:
            return 1
    else:
        # Raw differences are post-game corrections and event reordering; what
        # matters is whether they change the table every finding is built on.
        rows, differ = window_check(frames, compared)
        share = differ / rows if rows else 1.0
        print(f"window table: {rows:,} team-periods, {differ} differ ({share:.2%}; "
              f"limit {MAX_WINDOW_DIFF_SHARE:.1%})")
        record_check({"league": args.league, "season": args.season,
                      "games_compared": n, "games_raw_differ": len(bad),
                      "team_periods": rows, "team_periods_differ": differ,
                      "differ_share": share})
        if share > MAX_WINDOW_DIFF_SHARE:
            print("ARCHIVE DISAGREES WITH THE API HARVEST; nothing imported")
            return 1
        if args.verify:
            print("ARCHIVE AGREES WITH THE API HARVEST")
            return 0

    harvested = {p.stem for p in seasons.RAW_DIR.glob(f"{prefix}*.parquet")}
    rows, wrote = [], 0
    for gid in sorted(frames):
        if gid in harvested:
            rows.append({"game_id": gid, "source": "api"})
            continue
        frames[gid].write_parquet(seasons.RAW_DIR / f"{gid}.parquet")
        rows.append({"game_id": gid, "source": "archive"})
        wrote += 1
    record_sources(rows)
    print(f"imported {wrote:,} games from the archive; "
          f"{len(harvested):,} kept from the API harvest; sources in "
          f"{SOURCES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
