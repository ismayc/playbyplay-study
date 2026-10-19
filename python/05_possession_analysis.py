"""Possession-level upgrade of the 2-for-1 analysis: the decision-team design.

The original study proxied possession from shots and compared "first FGA >=32s"
team-periods against the rest — with the stated confound that the control group
mixes teams that CHOSE to hold with teams that never had the ball. Real
possession data (pbpstats rows with start/end times, via the bulk archive in
../docs/public-data-availability.md) allows a cleaner design:

    At the 40-second mark of every Q1-Q3, exactly ONE team has the ball -
    the team facing the actual 2-for-1 decision. Condition on being that
    team, then split by the observed CHOICE:

      quick  - possession released early (ends with >=28s left): went 2-for-1
      normal - possession ends 16-27s left
      hold   - possession carried deep (ends with <=15s left): denied a reply

    Outcome: NET points from the 40s mark to the buzzer, for the decision
    team. Everyone in the comparison had the ball at the same moment, so the
    "never had the ball" contamination is gone by construction. What remains
    (and is stated): the choice itself is not random - defenses, shot-clock
    state, and score context differ.

A first attempt at this upgrade translated the old design literally ("first
possession STARTED in the window >=32s") and its control group turned out to
be teams already holding the ball when the window opened - a new blindness in
place of the old one. The decision-team framing avoids the boundary entirely.

Also computed: how often the original first-shot proxy misread the choice,
and the possession-count mechanism (quick should yield ~1 extra possession).

Two possession sources, selected by --source:
  archive  the shufinskiy/nba_data pbpstats bulk archive (seasons.ARCHIVE);
           NBA 2023-24's published numbers come from this source.
  built    tables built here with the pbpstats library
           (07_build_possessions.py), for every league-season, including the
           two the archive lacks (NBA 2025-26, WNBA 2026).
08_reconcile_possessions.py runs both on the seasons both cover.

Input : seasons.ARCHIVE[...] or data/possessions/<tag>.parquet
        data/raw_pbp/<prefix>*.parquet  (V3 events: scores, team h/v map)
Output: <out>/decision_windows.csv, <out>/decision_summary.csv,
        <out>/bootstrap_decision_quick_vs_hold.csv, <out>/proxy_vs_possession.csv
        where <out> is seasons.out_dir(...) for the archive source and
        seasons.out_dir(...)/built for the built source

Run: python python/05_possession_analysis.py [--league wnba --season 2025]
     [--source built]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seasons  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"

DECISION_T = 40.0   # the ball-holder at this mark faces the 2-for-1 decision
QUICK_END = 28.0    # released by here = went for the 2-for-1
HOLD_END = 15.0     # still holding past here = denied the reply


def mmss(col: str) -> pl.Expr:
    parts = pl.col(col).str.split(":")
    return (parts.list.get(0).cast(pl.Float64) * 60
            + parts.list.get(1).cast(pl.Float64))


def load_possessions(league: str = "nba", season: str = "2023-24",
                     source: str = "archive") -> pl.DataFrame:
    """One row per possession: game_id, PERIOD, start_secs, end_secs,
    offense (tricode), TURNOVERS, and `used` (the possession produced a
    field-goal attempt, a free-throw trip, or a turnover), from either source.

    `used` is what makes the later-possessions count comparable across
    sources: the two draw end-of-period boundaries differently (pbpstats keeps
    a final possession in which nothing happens before the buzzer, and the
    archive drops it), but both record every possession that used the ball."""
    if source == "built":
        built = pl.read_parquet(seasons.possessions_file(league, season))
        tricode = team_tricodes(league, season)
        out = built.join(tricode, left_on=["game_id", "offense_team_id"],
                         right_on=["gameId", "teamId"], how="left")
        assert out["offense"].null_count() == 0, "offense team id without a tricode"
        return (out.with_columns(used=(pl.col("FGA") > 0) | (pl.col("FTA") > 0)
                                 | (pl.col("TURNOVERS") > 0))
                .drop("offense_team_id"))

    bulk = seasons.ARCHIVE.get((league, season))
    if bulk is None:
        raise SystemExit(f"the archive has no {seasons.label(league, season)}; "
                         f"use --source built")
    raw = pl.read_csv(bulk, infer_schema_length=10000)
    # possession-level stats repeat on every event row of a possession
    poss = (raw.unique(subset=["GAMEID", "PERIOD", "STARTTIME", "ENDTIME", "OPPONENT"])
            .with_columns(
                start_secs=mmss("STARTTIME"),
                end_secs=mmss("ENDTIME"),
                game_id=pl.col("GAMEID").cast(pl.Int64),
                used=((pl.col("FG2A") + pl.col("FG3A")) > 0) | (pl.col("TURNOVERS") > 0)
                     | (pl.col("SHOOTINGFOULSDRAWN") > 0)
                     | (pl.col("NONSHOOTINGFOULSTHATRESULTEDINFTS") > 0),
            ))
    teams = poss.group_by("game_id").agg(tricodes=pl.col("OPPONENT").unique().sort())
    assert (teams["tricodes"].list.len() == 2).all()
    return (poss.join(teams, on="game_id")
            .with_columns(
                offense=pl.when(pl.col("tricodes").list.get(0) == pl.col("OPPONENT"))
                .then(pl.col("tricodes").list.get(1))
                .otherwise(pl.col("tricodes").list.get(0)))
            .drop("tricodes"))


def team_tricodes(league: str, season: str) -> pl.DataFrame:
    """gameId + teamId -> tricode (as `offense`), from the V3 events."""
    return (pl.scan_parquet(seasons.raw_files(league, season))
            .filter(pl.col("teamTricode") != "")
            .select(gameId=pl.col("gameId").cast(pl.Int64),
                    teamId=pl.col("teamId").cast(pl.Int64),
                    offense=pl.col("teamTricode"))
            .unique().collect())


def v3_events(league: str = "nba", season: str = "2023-24") -> pl.DataFrame:
    """V3 events in game-clock order with forward-filled scores (both 02 fixes
    apply: numeric actionNumber, and clock order so late-inserted events do
    not carry a later score into the 40-second mark)."""
    files = seasons.raw_files(league, season)
    mins = pl.col("clock").str.extract(r"PT(\d+)M", 1).cast(pl.Float64)
    secs = pl.col("clock").str.extract(r"M([\d.]+)S", 1).cast(pl.Float64)
    df = (pl.scan_parquet(files)
          .select("gameId", "actionNumber", "clock", "period",
                  "scoreHome", "scoreAway", "teamTricode", "location")
          .with_columns(
              period=pl.col("period").cast(pl.Int32),
              actionNumber=pl.col("actionNumber").cast(pl.Int64),
              secs_left=mins * 60 + secs,
              score_h=pl.when(pl.col("scoreHome") == "").then(None)
              .otherwise(pl.col("scoreHome")).cast(pl.Float64, strict=False),
              score_a=pl.when(pl.col("scoreAway") == "").then(None)
              .otherwise(pl.col("scoreAway")).cast(pl.Float64, strict=False),
          )
          .sort(["gameId", "period", "secs_left", "actionNumber"],
                descending=[False, False, True, False], nulls_last=True)
          .with_columns(
              score_h=pl.col("score_h").fill_null(strategy="forward").over("gameId"),
              score_a=pl.col("score_a").fill_null(strategy="forward").over("gameId"),
          )
          .with_columns(score_h=pl.col("score_h").fill_null(0.0),
                        score_a=pl.col("score_a").fill_null(0.0))
          .filter(pl.col("secs_left").is_not_null())
          .collect())
    return df


def main() -> int:
    global OUT
    ap = argparse.ArgumentParser()
    seasons.add_args(ap)
    ap.add_argument("--source", choices=["archive", "built"], default="archive")
    args = ap.parse_args()
    lg, ssn = args.league, args.season
    windows_dir = seasons.out_dir(lg, ssn)
    OUT = windows_dir / "built" if args.source == "built" else windows_dir
    OUT.mkdir(parents=True, exist_ok=True)

    poss = load_possessions(lg, ssn, args.source)
    n_games = len(seasons.raw_files(lg, ssn))
    print(f"{poss.height:,} possessions, {poss['game_id'].n_unique()} of {n_games:,} "
          f"games ({seasons.label(lg, ssn)}, {args.source} source)")

    # ---- decision team: possession active at the 40s mark ------------------
    decision = (poss.filter(pl.col("PERIOD").is_in([1, 2, 3])
                            & (pl.col("start_secs") >= DECISION_T)
                            & (pl.col("end_secs") < DECISION_T))
                .with_columns(
                    behavior=pl.when(pl.col("end_secs") >= QUICK_END).then(pl.lit("quick"))
                    .when(pl.col("end_secs") <= HOLD_END).then(pl.lit("hold"))
                    .otherwise(pl.lit("normal"))))
    # exactly one decision team per period (a few periods have none, e.g.
    # possession boundaries exactly at the mark)
    per_period = decision.group_by("game_id", "PERIOD").len()
    print(f"decision possessions: {decision.height:,} "
          f"({per_period.filter(pl.col('len') > 1).height} periods with >1 - dropped)")
    good = per_period.filter(pl.col("len") == 1).select("game_id", "PERIOD")
    decision = decision.join(good, on=["game_id", "PERIOD"], how="inner")

    # mechanism: possessions the decision team starts AFTER the mark and
    # uses (a shot, a free-throw trip, or a turnover; see load_possessions)
    later = (poss.filter(pl.col("PERIOD").is_in([1, 2, 3])
                         & (pl.col("start_secs") < DECISION_T)
                         & pl.col("used"))
             .group_by("game_id", "PERIOD", "offense")
             .agg(n_later_poss=pl.len()))
    decision = decision.join(
        later, on=["game_id", "PERIOD", "offense"], how="left"
    ).with_columns(pl.col("n_later_poss").fill_null(0))

    # ---- outcome: net points from the mark, via V3 scores ------------------
    events = v3_events(lg, ssn)
    per = events.filter(pl.col("period").is_in([1, 2, 3]))
    start = (per.filter(pl.col("secs_left") > DECISION_T)
             .group_by("gameId", "period")
             .agg(h0=pl.col("score_h").last(), a0=pl.col("score_a").last()))
    end = (per.group_by("gameId", "period")
           .agg(h1=pl.col("score_h").last(), a1=pl.col("score_a").last()))
    marks = (start.join(end, on=["gameId", "period"])
             .with_columns(h_net=(pl.col("h1") - pl.col("h0")) - (pl.col("a1") - pl.col("a0")))
             .with_columns(gameId=pl.col("gameId").cast(pl.Int64)))

    side_map = (pl.scan_parquet(seasons.raw_files(lg, ssn))
                .filter(pl.col("location").is_in(["h", "v"]) & (pl.col("teamTricode") != ""))
                .select("gameId", "teamTricode", "location").unique().collect()
                .with_columns(gameId=pl.col("gameId").cast(pl.Int64)))

    merged = (decision
              .join(side_map, left_on=["game_id", "offense"],
                    right_on=["gameId", "teamTricode"], how="inner")
              .join(marks, left_on=["game_id", "PERIOD"],
                    right_on=["gameId", "period"], how="inner")
              .with_columns(net=pl.when(pl.col("location") == "h")
                            .then(pl.col("h_net")).otherwise(-pl.col("h_net")))
              # joins return rows in run-dependent order and the bootstrap
              # draws by position; sort so every run reproduces (see 02)
              .sort(["game_id", "PERIOD"]))
    print(f"{merged.height:,} decision team-periods with outcomes")
    merged.select("game_id", "PERIOD", "offense", "behavior", "start_secs",
                  "end_secs", "n_later_poss", "net").write_csv(OUT / "decision_windows.csv")

    summary = (merged.group_by("behavior")
               .agg(n=pl.len(),
                    mean_net=pl.col("net").mean(),
                    mean_later_poss=pl.col("n_later_poss").mean(),
                    mean_release=pl.col("end_secs").mean(),
                    # a possession can END early involuntarily; the share that
                    # ended in a turnover separates choice from accident
                    to_share=(pl.col("TURNOVERS") > 0).mean())
               .sort("mean_release", descending=True))
    summary.write_csv(OUT / "decision_summary.csv")
    print(summary)

    def boot(a: np.ndarray, b: np.ndarray, seed: int) -> dict:
        rng = np.random.default_rng(seed)
        boots = np.array([rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean()
                          for _ in range(4000)])
        lo, hi = np.quantile(boots, [0.025, 0.975])
        return {"estimate": float(a.mean() - b.mean()), "ci_lo": float(lo),
                "ci_hi": float(hi), "reps": 4000, "n_treated": len(a), "n_control": len(b)}

    q = merged.filter(pl.col("behavior") == "quick")["net"].to_numpy()
    h = merged.filter(pl.col("behavior") == "hold")["net"].to_numpy()
    res = boot(q, h, seed=21)
    print(f"\nquick minus hold, net from {DECISION_T:.0f}s: {res['estimate']:+.3f} "
          f"[{res['ci_lo']:+.3f}, {res['ci_hi']:+.3f}] "
          f"(n={res['n_treated']:,} vs {res['n_control']:,})")
    pl.DataFrame([{"quantity": "decision_quick_minus_hold_net", **res}]
                 ).write_csv(OUT / "bootstrap_decision_quick_vs_hold.csv")

    # ---- how often did the first-shot proxy misread the choice? ------------
    windows = (pl.read_csv(windows_dir / "team_period_windows.csv")
               .with_columns(gameId=pl.col("gameId").cast(pl.Int64)))
    pv = (merged.join(windows, left_on=["game_id", "PERIOD", "location"],
                      right_on=["gameId", "period", "location"], how="inner")
          .with_columns(proxy_said_quick=pl.col("two_for_one")))
    agree_quick = pv.filter(pl.col("behavior") == "quick")["proxy_said_quick"].mean()
    agree_hold = (~pv.filter(pl.col("behavior") == "hold")["proxy_said_quick"]).mean()
    pl.DataFrame([{
        "quantity": "proxy_vs_observed_choice",
        "quick_correctly_flagged": float(agree_quick),
        "hold_correctly_unflagged": float(agree_hold),
        "n_quick": pv.filter(pl.col("behavior") == "quick").height,
        "n_hold": pv.filter(pl.col("behavior") == "hold").height,
    }]).write_csv(OUT / "proxy_vs_possession.csv")
    print(f"first-shot proxy vs observed choice: flags {agree_quick:.0%} of true "
          f"quicks, correctly ignores {agree_hold:.0%} of true holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
