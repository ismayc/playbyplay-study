"""The 2-for-1 across seasons and leagues: NBA 2023-24 to 2025-26, WNBA 2024-2026.

Reads each league-season's outputs (02_analysis.py and, with --source built,
05_possession_analysis.py) and writes one comparison table plus pooled
estimates. Every season's possession layer uses the pbpstats-library tables
(07_build_possessions.py), including the seasons the bulk archive also
covers, so the trend compares like with like; 08_reconcile_possessions.py is
what licenses that.

The questions the 2023-24 study could not answer from one season:
  * is the quick rate still rising, and are holds now fully extinct?
  * does the bunching at the 32-second threshold sharpen?
  * the restricted-sample net gap's interval sat at zero on one season; does
    pooling seasons resolve it?
  * does the WNBA hunt the 2-for-1 at NBA rates, or does a real hold group
    still exist there?

Pooling concatenates each league's team-periods (or decision possessions)
across its three seasons and bootstraps the same difference as 02/05, with
fixed seeds. R/09_pooled.R repeats the window bootstraps independently;
04_reconcile.py --pooled compares the two.

Outputs: output/seasons_summary.csv   one row per league-season
         output/seasons_pooled.csv    pooled estimates per league
         figures/fig5_quick_share_by_season.html
         figures/fig6_restricted_net_by_season.html

Run: python python/09_seasons.py           build
     python python/09_seasons.py --check   fail if the committed tables differ
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seasons  # noqa: E402

ROOT = seasons.ROOT
OUT = ROOT / "output"
FIG = ROOT / "figures"
TOL = 1e-12

POOLED_SEEDS = {"own": 3101, "net": 3102, "own_restricted": 3103,
                "net_restricted": 3104, "decision": 3105}


def boot_diff(a: np.ndarray, b: np.ndarray, seed: int, reps: int = 4000) -> dict:
    """Same resampling as 02_analysis.py's boot_diff and 05's boot."""
    rng = np.random.default_rng(seed)
    boots = np.array([rng.choice(a, len(a), replace=True).mean()
                      - rng.choice(b, len(b), replace=True).mean()
                      for _ in range(reps)])
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {"estimate": float(a.mean() - b.mean()), "ci_lo": float(lo),
            "ci_hi": float(hi), "reps": reps, "n_treated": len(a), "n_control": len(b)}


def ci_cols(prefix: str, row: dict | None) -> dict:
    if row is None:
        return {f"{prefix}": None, f"{prefix}_lo": None, f"{prefix}_hi": None}
    return {f"{prefix}": row["estimate"], f"{prefix}_lo": row["ci_lo"],
            f"{prefix}_hi": row["ci_hi"]}


def read_row(path: Path) -> dict | None:
    return pl.read_csv(path).row(0, named=True) if path.exists() else None


def season_row(league: str, season: str) -> dict:
    out = seasons.out_dir(league, season)
    windows = pl.read_csv(out / "team_period_windows.csv")
    timing = pl.read_csv(out / "first_shot_timing.csv")
    efg = pl.read_csv(out / "efg_by_seconds_left.csv")

    def band(lo: int, hi: int) -> float:
        sel = timing.filter(pl.col("bucket").is_between(lo, hi))
        return float(sel["n"].mean()) if sel.height else float("nan")

    ds = pl.read_csv(out / "built" / "decision_summary.csv")
    by = {r["behavior"]: r for r in ds.iter_rows(named=True)}
    total = sum(r["n"] for r in by.values())
    pv = read_row(out / "built" / "proxy_vs_possession.csv")

    return {
        "league": league, "season": season,
        "games": windows["gameId"].n_unique(),
        "team_periods": windows.height,
        "proxy_2for1_share": float(windows["two_for_one"].mean()),
        "spike_31_33": band(31, 33), "band_36_40": band(36, 40),
        "spike_ratio": band(31, 33) / band(36, 40),
        **ci_cols("own_gap", read_row(out / "bootstrap_points_diff.csv")),
        **ci_cols("net_gap", read_row(out / "bootstrap_net_diff.csv")),
        **ci_cols("own_gap_restricted", read_row(out / "bootstrap_restricted.csv")),
        **ci_cols("net_gap_restricted", read_row(out / "bootstrap_net_restricted.csv")),
        "efg_32_plus": float(efg.filter(pl.col("bucket") >= 32)["efg"].mean()),
        "efg_last_4s": float(efg.filter(pl.col("bucket") <= 3)["efg"].mean()),
        "decision_periods": total,
        "quick_n": by["quick"]["n"], "normal_n": by["normal"]["n"],
        "hold_n": by["hold"]["n"],
        "quick_share": by["quick"]["n"] / total,
        "hold_share": by["hold"]["n"] / total,
        "quick_later_poss": by["quick"]["mean_later_poss"],
        "hold_later_poss": by["hold"]["mean_later_poss"],
        **ci_cols("quick_minus_hold",
                  read_row(out / "built" / "bootstrap_decision_quick_vs_hold.csv")),
        "proxy_flags_quick": pv["quick_correctly_flagged"],
        "proxy_ignores_hold": pv["hold_correctly_unflagged"],
    }


def pooled_rows(league: str) -> list[dict]:
    targets = [ls for ls in seasons.SEASONS if ls[0] == league]
    windows = pl.concat([pl.read_csv(seasons.out_dir(*ls) / "team_period_windows.csv")
                         .with_columns(season=pl.lit(ls[1])) for ls in targets],
                        how="vertical_relaxed").sort(["season", "gameId", "period", "location"])
    decision = pl.concat([pl.read_csv(seasons.out_dir(*ls) / "built" / "decision_windows.csv")
                          .with_columns(season=pl.lit(ls[1])) for ls in targets],
                         how="vertical_relaxed").sort(["season", "game_id", "PERIOD"])
    narrow = windows.filter(pl.col("first_fga_sec").is_between(20, 45))
    label = f"{league.upper()} {targets[0][1]} to {targets[-1][1]}"

    def split(frame: pl.DataFrame, col: str) -> tuple[np.ndarray, np.ndarray]:
        return (frame.filter(pl.col("two_for_one"))[col].to_numpy(),
                frame.filter(~pl.col("two_for_one"))[col].to_numpy())

    rows = []
    for name, frame, col in [("own", windows, "points"), ("net", windows, "net"),
                             ("own_restricted", narrow, "points"),
                             ("net_restricted", narrow, "net")]:
        a, b = split(frame, col)
        rows.append({"league": league, "seasons": label, "quantity": name,
                     **boot_diff(a, b, POOLED_SEEDS[name])})
    q = decision.filter(pl.col("behavior") == "quick")["net"].to_numpy()
    h = decision.filter(pl.col("behavior") == "hold")["net"].to_numpy()
    rows.append({"league": league, "seasons": label, "quantity": "decision_quick_minus_hold",
                 **boot_diff(q, h, POOLED_SEEDS["decision"])})
    return rows


def build() -> tuple[pl.DataFrame, pl.DataFrame]:
    summary = pl.DataFrame([season_row(*ls) for ls in seasons.SEASONS])
    pooled = pl.DataFrame([r for lg in ("nba", "wnba") for r in pooled_rows(lg)])
    return summary, pooled


def figures(summary: pl.DataFrame, pooled: pl.DataFrame) -> None:
    import plotly.graph_objects as go

    # One panel, no subplots: the family's famplot renderer has no subplot
    # branch, and an unsupported layout renders as zeros without an error.
    # One trace per league, each a single color: famplot ignores per-bar
    # color arrays (verified 2026-10-19: every bar rendered in one blue), so
    # the league split has to come from separate, named traces.
    fig = go.Figure()
    for league, color in (("nba", "#1E3A5F"), ("wnba", "#C8102E")):
        part = summary.filter(pl.col("league") == league)
        fig.add_trace(go.Bar(
            name=league.upper(),
            x=[seasons.label(league, s) for s in part["season"]], y=part["quick_share"],
            marker=dict(color=color, line=dict(color="white", width=1)),
            text=[f"{h} holds" for h in part["hold_n"]], textposition="outside",
            customdata=part.select("hold_n", "decision_periods").rows(),
            hovertemplate=("%{x}: %{y:.1%} quick<br>%{customdata[0]} holds of "
                           "%{customdata[1]:,} decisions<extra></extra>")))
    fig.update_layout(template="plotly_white", showlegend=True, height=400,
                      barmode="stack",   # distinct categories: keeps bars centered
                      legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom"),
                      yaxis=dict(tickformat=".0%", range=[0, 1],
                                 title="share of decisions that went quick"),
                      title="Who still holds? The 2-for-1 decision by league-season")
    fig.write_html(FIG / "fig5_quick_share_by_season.html", include_plotlyjs="cdn")

    # The season labels: the fig5 rewrite (per-league traces) dropped the list
    # this loop read, so a full run died here while --check, which skips the
    # figures, kept passing.
    labels = [seasons.label(r["league"], r["season"]) for r in summary.iter_rows(named=True)]
    rows = [(lab, r["net_gap_restricted"], r["net_gap_restricted_lo"],
             r["net_gap_restricted_hi"])
            for lab, r in zip(labels, summary.iter_rows(named=True))
            if r["net_gap_restricted"] is not None]
    for r in pooled.filter(pl.col("quantity") == "net_restricted").iter_rows(named=True):
        rows.append((f"{r['seasons']} pooled", r["estimate"], r["ci_lo"], r["ci_hi"]))
    fig = go.Figure(go.Scatter(
        x=[r[1] for r in rows], y=[r[0] for r in rows], mode="markers",
        marker=dict(size=9, color="#1E3A5F"),
        error_x=dict(type="data", symmetric=False,
                     array=[r[3] - r[1] for r in rows],
                     arrayminus=[r[1] - r[2] for r in rows]),
        hovertemplate="%{y}: %{x:+.3f}<extra></extra>"))
    fig.add_vline(x=0, line_dash="dot", line_color="#767b88")
    fig.update_layout(template="plotly_white", height=60 + 42 * len(rows),
                      title="Net-points gap, first shot 20-45s, by season and pooled (95% CI)",
                      xaxis_title="2-for-1 minus hold, net points per window",
                      yaxis=dict(autorange="reversed"))
    fig.write_html(FIG / "fig6_restricted_net_by_season.html", include_plotlyjs="cdn")


def max_diff(a: pl.DataFrame, b: pl.DataFrame) -> float:
    worst = 0.0
    for c in a.columns:
        if a[c].dtype.is_numeric():
            d = (a[c].cast(pl.Float64) - b[c].cast(pl.Float64)).abs().max()
            if d is not None:
                worst = max(worst, float(d))
        elif not a[c].equals(b[c]):
            return float("inf")
    return worst


def main(argv: list[str]) -> int:
    summary, pooled = build()
    if "--check" in argv:
        drift = max(max_diff(summary, pl.read_csv(OUT / "seasons_summary.csv")),
                    max_diff(pooled, pl.read_csv(OUT / "seasons_pooled.csv")))
        ok = drift <= TOL
        print("SEASONS CHECK " + ("PASSED" if ok else "FAILED")
              + f" ({summary.height} league-seasons, {pooled.height} pooled estimates "
                f"reproduce; max drift {drift:.2e})")
        return 0 if ok else 1
    summary.write_csv(OUT / "seasons_summary.csv")
    pooled.write_csv(OUT / "seasons_pooled.csv")
    with pl.Config(tbl_rows=-1, tbl_cols=-1, tbl_width_chars=200):
        print(summary.select("league", "season", "games", "proxy_2for1_share", "spike_ratio",
                             "quick_share", "hold_n", "net_gap_restricted",
                             "net_gap_restricted_lo", "quick_minus_hold"))
        print(pooled)
    figures(summary, pooled)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
