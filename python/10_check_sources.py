"""Check every season's window points against an independent feed.

The V3 play-by-play behind the analysis comes from two places (see
data/raw_pbp_sources.csv): the stats.nba.com harvest and, after the API began
timing out on 2026-10-19, the shufinskiy V3 archive. 01b_import_v3_archive.py
compares the archive with the harvest where both exist, but NBA 2025-26 and
WNBA 2025 have no harvested games to compare with.

This check covers every season the same way: the NBA's liveData feed (the
JSON 07_build_possessions.py caches for pbpstats) stamps the running score on
every action, so each Q1-Q3 window's points can be computed from it with the
same definition 02_analysis.py uses (score at the last event with more than
60 seconds left, versus the score at the period's last event). The two are
different feeds of the same games, so they are compared team-period by
team-period, and each league-season must agree on at least 99.5% of them.

Output: output/source_check.csv, one row per league-season
Run:    python python/10_check_sources.py          build
        python python/10_check_sources.py --check  rerun and compare with the
            committed table; the liveData cache is gitignored (~2 GB), so on a
            checkout without it this prints a SKIPPED line with the committed
            result instead of passing silently
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seasons  # noqa: E402

LIVE = seasons.ROOT / "data" / "pbpstats_live" / "pbp"
MIN_AGREE = 0.995

_spec = importlib.util.spec_from_file_location(
    "analysis02", Path(__file__).resolve().parent / "02_analysis.py")
a02 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(a02)


def live_window_points(game_id: str) -> list[dict]:
    path = LIVE / f"live_{game_id}.json"
    actions = json.loads(path.read_text())["game"]["actions"]
    rows = []
    for period in (1, 2, 3):
        acts = sorted((a for a in actions if a["period"] == period),
                      key=lambda a: a["orderNumber"])
        if not acts:
            continue
        before = [a for a in acts if a02_secs(a["clock"]) > a02.WINDOW_SEC]
        if not before:
            continue
        h0, v0 = int(before[-1]["scoreHome"]), int(before[-1]["scoreAway"])
        h1, v1 = int(acts[-1]["scoreHome"]), int(acts[-1]["scoreAway"])
        rows += [{"gameId": game_id, "period": period, "location": "h",
                  "points_live": float(h1 - h0)},
                 {"gameId": game_id, "period": period, "location": "v",
                  "points_live": float(v1 - v0)}]
    return rows


def a02_secs(clock: str) -> float:
    mins, rest = clock[2:].split("M")
    return int(mins) * 60 + float(rest.rstrip("S"))


def check(league: str, season: str) -> dict:
    files = seasons.raw_files(league, season)
    ids = [f.stem for f in files]
    have_live = [g for g in ids if (LIVE / f"live_{g}.json").exists()]
    v3 = (a02.window_points(a02.prepare_events(
              pl.concat([pl.read_parquet(f) for f in files], how="diagonal")))
          .with_columns(pl.col("gameId").cast(pl.String)))
    live = pl.DataFrame([r for g in have_live for r in live_window_points(g)])
    both = v3.join(live, on=["gameId", "period", "location"], how="inner")
    agree = (both["points"] == both["points_live"])
    sources = pl.read_csv(seasons.ROOT / "data" / "raw_pbp_sources.csv",
                          schema_overrides={"game_id": pl.String})
    from_archive = sources.filter(pl.col("game_id").is_in(ids)
                                  & (pl.col("source") == "archive")).height
    return {
        "league": league, "season": season, "games": len(ids),
        "games_from_archive": from_archive, "games_with_live": len(have_live),
        "team_periods_v3": v3.height, "team_periods_compared": both.height,
        "agree": int(agree.sum()), "agree_share": float(agree.mean()),
        "mean_abs_diff_when_differ": (float((both["points"] - both["points_live"])
                                            .abs().filter(~agree).mean())
                                      if (~agree).any() else 0.0),
    }


def main() -> int:
    committed = seasons.ROOT / "output" / "source_check.csv"
    if "--check" in sys.argv[1:] and not LIVE.is_dir():
        c = pl.read_csv(committed)
        print(f"SOURCE CHECK SKIPPED: no liveData cache at {LIVE.relative_to(seasons.ROOT)} "
              f"(run 07_build_possessions.py to fetch it). Committed result: "
              f"{c.height} league-seasons, agreement {c['agree_share'].min():.2%} to "
              f"{c['agree_share'].max():.2%}")
        return 0
    rows, ok_all = [], True
    for league, season in seasons.SEASONS:
        r = check(league, season)
        ok = (r["games_with_live"] == r["games"]
              and r["team_periods_compared"] == r["team_periods_v3"]
              and r["agree_share"] >= MIN_AGREE)
        ok_all &= ok
        rows.append(r)
        print(f"{'PASS' if ok else 'FAIL'}  {seasons.label(league, season):13s} "
              f"{r['games']:,} games ({r['games_from_archive']:,} from the archive), "
              f"live feed for {r['games_with_live']:,}; window points agree on "
              f"{r['agree']:,} of {r['team_periods_compared']:,} team-periods "
              f"({r['agree_share']:.2%})")
    table = pl.DataFrame(rows)
    if "--check" in sys.argv[1:]:
        same = table.equals(pl.read_csv(committed))
        ok_all &= same
        if not same:
            print("committed output/source_check.csv differs from a rerun")
    else:
        table.write_csv(committed)
    print("SOURCE CHECK " + ("PASSED" if ok_all else "FAILED")
          + f" (each season >= {MIN_AGREE:.1%} agreement with the live feed)")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
