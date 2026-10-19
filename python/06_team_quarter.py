"""Who hunts the 2-for-1, and does the quarter matter?

Two follow-ups to the core windows analysis, both running off the same
committed team-period table (output/team_period_windows.csv) joined back
to team identities from the raw play-by-play:

  1. TEAM PROPENSITY: each team's share of final-minute windows where its
     first shot came with 32+ seconds left. This is a behavioral dial the
     team controls, so a league-wide table of it is a coaching-tendency
     scout in miniature.
  2. QUARTER EFFECTS: the same rate split by quarter (Q1/Q2/Q3; Q4 is
     excluded from the study by design because endgame strategy changes
     everything), plus the own- and net-points outcomes per quarter.

Gates: the join must cover every window with exactly the league-season's
team count (seasons.N_TEAMS: 30 NBA, 12-15 WNBA); totals and the league-wide
2-for-1 rate must reproduce the committed table.

Run:  python python/06_team_quarter.py           full build (NBA 2023-24)
      python python/06_team_quarter.py --check   offline gate replay
      python python/06_team_quarter.py --league wnba --season 2025 [--check]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seasons  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
FIG = ROOT / "figures"
LEAGUE, SEASON = seasons.ORIGINAL


def game_team_map() -> pl.DataFrame:
    """gameId + location (h/v) -> teamTricode, from the raw events."""
    df = pl.scan_parquet(seasons.raw_files(LEAGUE, SEASON)).select(
        "gameId", "teamTricode", "location").filter(
        pl.col("teamTricode") != "").unique().collect()
    return df.with_columns(pl.col("gameId").cast(pl.Int64))


def build() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    n_teams = seasons.N_TEAMS[(LEAGUE, SEASON)]
    windows = pl.read_csv(OUT / "team_period_windows.csv")
    joined = windows.join(game_team_map(), on=["gameId", "location"],
                          how="left")

    team = (joined.group_by("teamTricode")
            .agg(windows=pl.len(),
                 tfo=pl.col("two_for_one").sum(),
                 rate=pl.col("two_for_one").mean(),
                 own_pts=pl.col("points").mean(),
                 net_pts=pl.col("net").mean())
            .sort("rate", descending=True))

    quarter = (joined.group_by("period")
               .agg(windows=pl.len(),
                    rate=pl.col("two_for_one").mean(),
                    own_tfo=pl.col("points").filter(
                        pl.col("two_for_one")).mean(),
                    own_hold=pl.col("points").filter(
                        ~pl.col("two_for_one")).mean(),
                    net_tfo=pl.col("net").filter(
                        pl.col("two_for_one")).mean(),
                    net_hold=pl.col("net").filter(
                        ~pl.col("two_for_one")).mean())
               .sort("period"))

    checks = pl.DataFrame([
        {"check": "every window joined to a team (nulls)",
         "value": float(joined["teamTricode"].is_null().sum()),
         "threshold": 0.0},
        {"check": f"exactly {n_teams} teams",
         "value": float(abs(team.height - n_teams)), "threshold": 0.0},
        {"check": "team windows sum to the committed window count",
         "value": float(abs(int(team["windows"].sum()) - windows.height)),
         "threshold": 0.0},
        {"check": "league 2-for-1 rate reproduces committed table "
                  "(abs diff)",
         "value": float(abs(float(team["tfo"].sum()) / windows.height
                            - float(windows["two_for_one"].mean()))),
         "threshold": 1e-12},
    ]).with_columns(passed=pl.col("value") <= pl.col("threshold"))
    return team, quarter, checks


def figures(team: pl.DataFrame, quarter: pl.DataFrame) -> None:
    import plotly.graph_objects as go

    fig = go.Figure(go.Bar(
        x=team["rate"], y=team["teamTricode"], orientation="h",
        marker=dict(color="#1E3A5F", line=dict(color="white", width=1)),
        customdata=[[int(w), round(o, 2), round(n, 2)] for w, o, n in
                    team.select("windows", "own_pts", "net_pts").rows()],
        hovertemplate=("%{y}: %{x:.0%} of %{customdata[0]} windows"
                       "<br>own pts/window %{customdata[1]:.2f} · net "
                       "%{customdata[2]:+.2f}<extra></extra>")))
    league = float(team["tfo"].sum()) / float(team["windows"].sum())
    fig.add_vline(x=league, line_dash="dot", line_color="#767b88",
                  annotation_text=f"league {league:.0%}",
                  annotation_position="bottom right")
    fig.update_layout(
        title="Who hunts the 2-for-1: share of final-minute windows with a "
              "32+ second first shot, "
              + (SEASON if LEAGUE == "nba" else seasons.label(LEAGUE, SEASON)),
        xaxis_title="2-for-1 rate", yaxis_title="",
        xaxis_tickformat=".0%", height=640,
        template="plotly_white",
        yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
        margin=dict(l=60, r=40, t=70, b=50))
    fig.write_html(FIG / "fig3_team_2for1.html", include_plotlyjs="cdn")

    labels = [f"Q{q}" for q in quarter["period"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="2-for-1 taken", y=labels, x=quarter["own_tfo"],
        orientation="h",
        marker=dict(color="#1E3A5F", line=dict(color="white", width=1)),
        customdata=[[round(r, 3), round(n, 2)] for r, n in
                    quarter.select("rate", "net_tfo").rows()],
        hovertemplate=("%{y} 2-for-1: %{x:.2f} own pts/window"
                       "<br>net %{customdata[1]:+.2f} · taken in "
                       "%{customdata[0]:.0%} of windows<extra></extra>")))
    fig.add_trace(go.Bar(
        name="held", y=labels, x=quarter["own_hold"],
        orientation="h",
        marker=dict(color="#9AAFC9", line=dict(color="white", width=1)),
        customdata=[[round(n, 2)] for n in quarter["net_hold"]],
        hovertemplate=("%{y} held: %{x:.2f} own pts/window"
                       "<br>net %{customdata[0]:+.2f}<extra></extra>")))
    fig.update_layout(
        title="Does the quarter matter? Own points per window, 2-for-1 vs "
              "hold, by quarter",
        xaxis_title="own points per window", barmode="group", height=340,
        template="plotly_white",
        yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"))
    fig.write_html(FIG / "fig4_quarter_2for1.html", include_plotlyjs="cdn")


def main(argv: list[str]) -> int:
    global OUT, FIG, LEAGUE, SEASON
    ap = argparse.ArgumentParser()
    seasons.add_args(ap)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    LEAGUE, SEASON = args.league, args.season
    OUT = seasons.out_dir(LEAGUE, SEASON)
    FIG = seasons.fig_dir(LEAGUE, SEASON)
    FIG.mkdir(parents=True, exist_ok=True)
    team, quarter, checks = build()

    if args.check:
        committed = pl.read_csv(OUT / "team_2for1.csv")
        drift = (team.sort("teamTricode")["rate"]
                 - committed.sort("teamTricode")["rate"]).abs().max()
        ok = bool(checks["passed"].all()) and float(drift) < 1e-12
        print("TEAM/QUARTER CHECK " + ("PASSED" if ok else "FAILED")
              + f" ({checks.height} gates; committed team rates reproduce, "
                f"max drift {float(drift):.2e})")
        return 0 if ok else 1

    team.write_csv(OUT / "team_2for1.csv")
    quarter.write_csv(OUT / "quarter_2for1.csv")
    checks.write_csv(OUT / "team_quarter_validation.csv")
    with pl.Config(tbl_rows=-1):
        print(team.head(6))
        print(team.tail(3))
        print(quarter)
        print(checks)
    figures(team, quarter)
    ok = bool(checks["passed"].all())
    print("TEAM/QUARTER VALIDATION " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
