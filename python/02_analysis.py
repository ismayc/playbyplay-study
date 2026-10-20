"""Does the end-of-quarter "2-for-1" actually pay?

The question
------------
With roughly 30-40 seconds left in a quarter, a team holding the ball can either
shoot quickly — hoping to get one more possession before the buzzer, two shots for
the opponent's one — or hold for the last shot and deny the opponent any reply.

The trade is real and coaches disagree about it: the extra possession is worth
something, but the shot you rush to create it is worse than the one you'd otherwise
take. This measures both sides.

Method
------
* Periods 1-3 only. Q4 is excluded: end-of-game play is contaminated by score-margin
  strategy, intentional fouling, and clock-stopping that have nothing to do with 2-for-1.
* Window: the final 60 seconds of the period.
* Treatment: a team's FIRST field-goal attempt in the window comes with >= 32 seconds
  remaining. 32s is the conventional threshold — enough for a 24-second opponent
  possession plus a final possession of your own.
* Outcome: points the team scores in the window, measured from the SCORE DELTA
  (score at period end minus score at the 60-second mark). Score deltas rather than
  summed shot values, because free throws in this feed carry an empty `shotResult`
  and would otherwise be silently dropped.

Causal caution
--------------
This is observational and the treatment is not randomly assigned. A team can only
run a 2-for-1 if it happens to hold the ball early in the window, and *which* teams
hold the ball then is not random. Section "Findings" reports the association and
does not claim a causal effect. The mechanism checks (shot quality, shot count) are
what carry the argument.

The WNBA runs the same design unchanged: four 10-minute quarters, but the same
24-second shot clock, so the 60-second window and 32-second threshold transfer.

Inputs : data/raw_pbp/<league-season prefix>*.parquet   (from 01_harvest_pbp.py)
Outputs: output/*.csv, figures/*.png + *.html for NBA 2023-24;
         output/seasons/<tag>/ (figures in its gitignored figures/) for every other
         league-season (see seasons.py)

Run: python python/02_analysis.py [--league wnba --season 2025]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seasons  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
FIG = ROOT / "figures"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"

WINDOW_SEC = 60.0
TWO_FOR_ONE_SEC = 32.0


def base_layout(title: str, subtitle: str, x_title: str, y_title: str) -> go.Layout:
    return go.Layout(
        title=dict(text=f"<b>{title}</b><br><span style='font-size:12px;color:{INK2}'>"
                        f"{subtitle}</span>",
                   font=dict(size=17, color=INK), x=0, xanchor="left"),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif",
                  size=12, color=INK2),
        xaxis=dict(title=dict(text=x_title, font=dict(color=INK2, size=12)),
                   showgrid=True, gridcolor=GRID, gridwidth=0.5, zeroline=False,
                   linecolor=AXIS, tickfont=dict(color=MUTED, size=11)),
        yaxis=dict(title=dict(text=y_title, font=dict(color=INK2, size=12)),
                   showgrid=True, gridcolor=GRID, gridwidth=0.5, zeroline=False,
                   linecolor=AXIS, tickfont=dict(color=MUTED, size=11)),
        showlegend=False, margin=dict(l=80, r=140, t=85, b=55),
        width=900, height=500,
    )


def save(fig: go.Figure, stem: str) -> None:
    fig.write_image(FIG / f"{stem}.png", scale=2)
    fig.write_html(FIG / f"{stem}.html", include_plotlyjs="cdn")


def load_events(league: str = "nba", season: str = "2023-24") -> pl.DataFrame:
    # diagonal: the feed adds or drops columns between seasons; every column
    # this script reads is present in all of them
    df = pl.concat([pl.read_parquet(f) for f in seasons.raw_files(league, season)],
                   how="diagonal")
    return prepare_events(df)


def prepare_events(df: pl.DataFrame) -> pl.DataFrame:
    """Raw V3 rows (all text) -> typed, ordered events with running scores.
    Separate from load_events so 01b_import_v3_archive.py can run the same
    preparation on archive rows."""
    # "PT11M42.00S" -> 702.0 seconds remaining in the period.
    mins = pl.col("clock").str.extract(r"PT(\d+)M", 1).cast(pl.Float64)
    secs = pl.col("clock").str.extract(r"M([\d.]+)S", 1).cast(pl.Float64)

    df = df.with_columns(
        period=pl.col("period").cast(pl.Int32),
        # The feed delivers every column as text. actionNumber MUST be cast
        # before sorting: lexicographic order puts "100" before "2", which
        # scrambles the score forward-fill and corrupts every window score.
        # (Caught in review by re-deriving the table with a numeric sort.)
        actionNumber=pl.col("actionNumber").cast(pl.Int64),
        secs_left=(mins * 60 + secs),
        is_fga=(pl.col("isFieldGoal") == "1"),
        made=(pl.col("shotResult") == "Made"),
        shot_value=pl.col("shotValue").cast(pl.Float64, strict=False),
        score_h=stamp("h", "scoreHome"),
        score_a=stamp("v", "scoreAway"),
    # GAME-CLOCK order, actionNumber only to break ties. The feed inserts late
    # events (logged after the fact) with a high actionNumber but an early
    # clock: in 0022300002 events 244-246 sit in period 1 at 5:05 left, after
    # the period-end event. Ordered by actionNumber, those strays became "the
    # last event with more than 60s left", carried the period-END score, and
    # zeroed the window: 15% of 2023-24 team-periods (1,105 of 7,380) had
    # wrong window points until 2026-10-19, when the NBA liveData feed
    # disagreed (10_check_sources.py). Clock order agrees on 99.93%.
    ).sort(["gameId", "period", "secs_left", "actionNumber"],
           descending=[False, False, True, False], nulls_last=True)

    # The running score, carried across the whole game (periods start from the
    # running total) in clock order, as a per-team running maximum of the
    # stamps stamp() keeps. A plain forward fill of every stamp left a wrong
    # score somewhere in about 6% of games (second 2026-10-19 correction,
    # found by elam-ending-study's endgame check against liveData): Instant
    # Replay rows carry a stale stamp (window "points" of -18 in 0022500232
    # Q3), free throws at one clock reading can sort out of order, and a
    # free-throw row can carry the other team's next score.
    df = df.with_columns(
        score_h=pl.col("score_h").fill_null(0.0).cum_max().over("gameId"),
        score_a=pl.col("score_a").fill_null(0.0).cum_max().over("gameId"),
    )
    return df.filter(pl.col("secs_left").is_not_null())


def stamp(side: str, column: str) -> pl.Expr:
    """A score stamp only where the row is a made shot or free throw by that
    side (location "h" or "v"); null elsewhere."""
    scoring = (pl.col("actionType").str.strip_chars().is_in(["Made Shot", "Free Throw"])
               & (pl.col("location") == side) & (pl.col(column) != ""))
    return pl.when(scoring).then(pl.col(column)).cast(pl.Float64, strict=False)


def window_points(df: pl.DataFrame) -> pl.DataFrame:
    """Points scored by each side during the final WINDOW_SEC of periods 1-3."""
    per = df.filter(pl.col("period").is_in([1, 2, 3]))

    # Score at the moment the window opens: last event with > WINDOW_SEC remaining.
    start = (per.filter(pl.col("secs_left") > WINDOW_SEC)
             .group_by(["gameId", "period"])
             .agg(pl.col("score_h").last().alias("h0"),
                  pl.col("score_a").last().alias("a0")))

    end = (per.group_by(["gameId", "period"])
           .agg(pl.col("score_h").last().alias("h1"),
                pl.col("score_a").last().alias("a1")))

    joined = start.join(end, on=["gameId", "period"], how="inner")
    return (joined
            .with_columns(h=pl.col("h1") - pl.col("h0"), v=pl.col("a1") - pl.col("a0"))
            .unpivot(index=["gameId", "period"], on=["h", "v"],
                     variable_name="location", value_name="points"))


def window_shots(df: pl.DataFrame) -> pl.DataFrame:
    """Shot behavior by each side inside the window."""
    shots = df.filter(
        pl.col("period").is_in([1, 2, 3])
        & (pl.col("secs_left") <= WINDOW_SEC)
        & pl.col("is_fga")
        & pl.col("location").is_in(["h", "v"])
    )
    return (shots.group_by(["gameId", "period", "location"])
            .agg(first_fga_sec=pl.col("secs_left").max(),
                 n_fga=pl.len(),
                 fgm=pl.col("made").sum(),
                 fg3m=(pl.col("made") & (pl.col("shot_value") == 3)).sum()))


def team_period_table(df: pl.DataFrame) -> pl.DataFrame:
    """Per team-period window outcomes: the table every finding is built on."""
    shots = window_shots(df)
    pts = window_points(df)
    team_periods = (shots.join(pts, on=["gameId", "period", "location"], how="inner")
                    .with_columns(
                        two_for_one=pl.col("first_fga_sec") >= TWO_FOR_ONE_SEC,
                        efg=(pl.col("fgm") + 0.5 * pl.col("fg3m")) / pl.col("n_fga"),
                    ))
    # The tactic's real payoff is NET: holding for the last shot is valuable
    # precisely because it denies the opponent a reply, so an outcome that only
    # counts a team's own points misses half the trade. Attach what the opponent
    # scored in the same window (pts covers both sides of every period, so this
    # join is complete even when the opponent never attempted a shot).
    opp = (pts.with_columns(
               location=pl.when(pl.col("location") == "h")
                          .then(pl.lit("v")).otherwise(pl.lit("h")))
           .rename({"points": "opp_points"}))
    team_periods = (team_periods
                    .join(opp, on=["gameId", "period", "location"], how="left")
                    .with_columns(net=pl.col("points") - pl.col("opp_points")))
    assert team_periods["opp_points"].null_count() == 0, "opponent points join incomplete"
    # polars group_by and join return rows in a different order on every run,
    # and the bootstraps below draw from rows by position, so an unsorted
    # table moved every published interval by up to 0.009 from run to run
    # (found 2026-10-19). Sorting on the keys makes each run reproduce.
    return team_periods.sort(["gameId", "period", "location"])


def main() -> int:
    global OUT, FIG
    ap = argparse.ArgumentParser()
    seasons.add_args(ap)
    args = ap.parse_args()
    OUT = seasons.out_dir(args.league, args.season)
    FIG = seasons.fig_dir(args.league, args.season)
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)

    df = load_events(args.league, args.season)
    n_games = df["gameId"].n_unique()
    print(f"Loaded {df.height:,} events from {n_games:,} games "
          f"({seasons.label(args.league, args.season)})")

    team_periods = team_period_table(df)
    team_periods.write_csv(OUT / "team_period_windows.csv")
    print(f"{team_periods.height:,} team-periods with at least one shot in the "
          f"final {WINDOW_SEC:.0f}s of Q1-Q3")

    # ---- 1. Do teams actually run it? Distribution of first-shot timing --------
    hist = (team_periods
            .with_columns(bucket=pl.col("first_fga_sec").floor().cast(pl.Int32))
            .group_by("bucket").agg(n=pl.len()).sort("bucket"))
    hist.write_csv(OUT / "first_shot_timing.csv")

    # ---- 2. The trade-off ------------------------------------------------------
    summary = (team_periods.group_by("two_for_one")
               .agg(team_periods_n=pl.len(),
                    mean_points=pl.col("points").mean(),
                    mean_opp_points=pl.col("opp_points").mean(),
                    mean_net=pl.col("net").mean(),
                    mean_fga=pl.col("n_fga").mean().alias("mean_fga"),
                    mean_efg=(pl.col("fgm").sum() + 0.5 * pl.col("fg3m").sum())
                              / pl.col("n_fga").sum())
               .sort("two_for_one", descending=True))
    summary.write_csv(OUT / "two_for_one_summary.csv")

    print("\n--- Outcome by whether the first shot came at 32s or later ---")
    for row in summary.iter_rows(named=True):
        label = "2-for-1 attempt" if row["two_for_one"] else "held for last shot"
        print(f"  {label:22s} n={row['team_periods_n']:6,}  "
              f"points={row['mean_points']:.3f}  "
              f"FGA={row['mean_fga']:.2f}  eFG%={row['mean_efg']:.3f}")

    # Bootstrap rather than a t-test: points in a 60-second window are a small,
    # lumpy, non-normal count (0, 2, 3, 5...). Both outcomes are bootstrapped:
    # `points` (own scoring — the mechanism) and `net` (own minus opponent — the
    # payoff, since holding is valuable precisely because it denies a reply).
    def boot_diff(frame: pl.DataFrame, outcome: str, seed: int) -> dict:
        a = frame.filter(pl.col("two_for_one"))[outcome].to_numpy()
        b = frame.filter(~pl.col("two_for_one"))[outcome].to_numpy()
        rng = np.random.default_rng(seed)
        boots = np.array([
            rng.choice(a, len(a), replace=True).mean()
            - rng.choice(b, len(b), replace=True).mean()
            for _ in range(4000)
        ])
        lo, hi = np.quantile(boots, [0.025, 0.975])
        return {"estimate": float(a.mean() - b.mean()), "ci_lo": float(lo),
                "ci_hi": float(hi), "reps": len(boots),
                "n_treated": len(a), "n_control": len(b)}

    full_pts = boot_diff(team_periods, "points", seed=2026)
    full_net = boot_diff(team_periods, "net", seed=2027)
    print(f"\n  Own-points gap (2-for-1 minus hold): {full_pts['estimate']:+.3f} "
          f"[{full_pts['ci_lo']:+.3f}, {full_pts['ci_hi']:+.3f}]")
    print(f"  Net-points gap                     : {full_net['estimate']:+.3f} "
          f"[{full_net['ci_lo']:+.3f}, {full_net['ci_hi']:+.3f}]")
    pl.DataFrame([{"quantity": "points_diff_2for1_minus_hold", **full_pts}]
                 ).write_csv(OUT / "bootstrap_points_diff.csv")
    pl.DataFrame([{"quantity": "net_diff_2for1_minus_hold", **full_net}]
                 ).write_csv(OUT / "bootstrap_net_diff.csv")

    # ---- 2b. Sensitivity: narrow the selection gap -----------------------------
    # The headline comparison is confounded by *when a team got the ball*. A team
    # that never touches it until 20s left cannot run a 2-for-1, and is a different
    # kind of team-period. Restricting to first shots between 20 and 45 seconds
    # compares teams that all had the ball at broadly similar times, which shrinks
    # (does not remove) the selection gap.
    narrow = team_periods.filter(pl.col("first_fga_sec").is_between(20, 45))
    if narrow.filter(pl.col("two_for_one")).height > 30 and \
       narrow.filter(~pl.col("two_for_one")).height > 30:
        r_pts = boot_diff(narrow, "points", seed=7)
        r_net = boot_diff(narrow, "net", seed=8)
        print(f"\n--- Sensitivity: first shot restricted to 20-45s "
              f"(n={r_pts['n_treated']:,} vs {r_pts['n_control']:,}) ---")
        print(f"  Own-points gap: {r_pts['estimate']:+.3f} "
              f"[{r_pts['ci_lo']:+.3f}, {r_pts['ci_hi']:+.3f}]")
        print(f"  Net-points gap: {r_net['estimate']:+.3f} "
              f"[{r_net['ci_lo']:+.3f}, {r_net['ci_hi']:+.3f}]")
        pl.DataFrame([{"quantity": "points_diff_restricted_20_45s", **r_pts}]
                     ).write_csv(OUT / "bootstrap_restricted.csv")
        pl.DataFrame([{"quantity": "net_diff_restricted_20_45s", **r_net}]
                     ).write_csv(OUT / "bootstrap_net_restricted.csv")

    # ---- 3. Mechanism: how good is the shot at each point on the clock? --------
    all_shots = df.filter(
        pl.col("period").is_in([1, 2, 3]) & (pl.col("secs_left") <= WINDOW_SEC)
        & pl.col("is_fga"))
    by_sec = (all_shots
              .with_columns(bucket=(pl.col("secs_left") / 4).floor().cast(pl.Int32) * 4)
              .group_by("bucket")
              .agg(n=pl.len(),
                   efg=(pl.col("made").sum()
                        + 0.5 * (pl.col("made") & (pl.col("shot_value") == 3)).sum())
                       / pl.len())
              # Drop the boundary bucket: the window filter is `<= 60`, so bucket 60
              # can only hold shots at exactly 60.0s and its "60-63s" label would lie.
              .filter((pl.col("n") >= 100) & (pl.col("bucket") < WINDOW_SEC))
              .sort("bucket"))
    by_sec.write_csv(OUT / "efg_by_seconds_left.csv")

    print("\n--- Shot quality by time left on the game clock (all Q1-Q3 window shots) ---")
    for row in by_sec.iter_rows(named=True):
        print(f"  {row['bucket']:2d}-{row['bucket']+3:2d}s left: "
              f"eFG% {row['efg']:.3f}  (n={row['n']:,})")

    # ---- figures ---------------------------------------------------------------
    fig = go.Figure(layout=base_layout(
        "Teams really do hunt the 2-for-1",
        f"When a team takes its first shot in the last 60s of Q1-Q3 "
        f"({n_games:,} games, "
        + (args.season if args.league == "nba" else seasons.label(args.league, args.season))
        + ")",
        "Seconds left when the first shot went up", "Team-periods"))
    fig.add_trace(go.Bar(marker_line=dict(color='white', width=1), x=hist["bucket"].to_list(), y=hist["n"].to_list(),
                         marker=dict(color=BLUE, line=dict(width=0)),
                         hovertemplate="%{x}s left: %{y:,} team-periods<extra></extra>"))
    fig.add_vline(x=TWO_FOR_ONE_SEC, line=dict(color=ORANGE, width=1.5, dash="dot"))
    fig.add_annotation(x=TWO_FOR_ONE_SEC, y=1, yref="paper", yanchor="bottom",
                       xanchor="left", xshift=6,
                       text="32s: conventional 2-for-1 threshold",
                       showarrow=False, font=dict(color=ORANGE, size=12))
    save(fig, "fig1_first_shot_timing")

    # Title states what the data shows. An earlier draft asserted that the rushed
    # 2-for-1 shot is a worse shot; the data says the opposite, and the expensive
    # shot is the buzzer-beater everyone takes anyway.
    fig = go.Figure(layout=base_layout(
        "The bad shot is the buzzer-beater, not the early one",
        "Effective FG% by game clock, all field-goal attempts in the last 60s of Q1-Q3",
        "Seconds left (4-second bins)", "Effective FG%"))
    fig.add_trace(go.Scatter(x=by_sec["bucket"].to_list(), y=by_sec["efg"].to_list(),
                             mode="lines+markers",
                             line=dict(color=BLUE, width=2),
                             marker=dict(size=8, color=BLUE),
                             hovertemplate="%{x}s left: eFG% %{y:.3f}<extra></extra>"))
    fig.add_vline(x=TWO_FOR_ONE_SEC, line=dict(color=ORANGE, width=1.5, dash="dot"))
    fig.update_yaxes(tickformat=".0%")
    save(fig, "fig2_efg_by_clock")

    print(f"\nWrote {OUT} and {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
