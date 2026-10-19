"""Verify the R and Python play-by-play analyses agree.

Same discipline as ../jersey-height-study: two independent implementations of
the same definitions, compared row-by-row, with a non-zero exit on mismatch so
this can gate a commit.

This check is not ceremonial here. The Python implementation originally sorted
events by actionNumber as TEXT ("100" before "2"), scrambling the score
forward-fill and corrupting every window score — the class of bug an
independent second implementation surfaces immediately.

Run:  python python/04_reconcile.py                          NBA 2023-24
      python python/04_reconcile.py --league wnba --season 2025
      python python/04_reconcile.py --all                    every league-season
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

TOL = 1e-9

# (python file, r file, join keys, numeric columns to compare)
TABLES = [
    ("team_period_windows.csv", "team_period_windows_r.csv",
     ["gameId", "period", "location"],
     ["first_fga_sec", "n_fga", "fgm", "fg3m", "points", "opp_points", "net", "efg"]),
    ("two_for_one_summary.csv", "two_for_one_summary_r.csv",
     ["two_for_one"],
     ["team_periods_n", "mean_points", "mean_opp_points", "mean_net",
      "mean_fga", "mean_efg"]),
    ("first_shot_timing.csv", "first_shot_timing_r.csv", ["bucket"], ["n"]),
    ("efg_by_seconds_left.csv", "efg_by_seconds_left_r.csv", ["bucket"], ["n", "efg"]),
]

# Bootstraps use different RNGs per language: compare CI overlap, not equality.
BOOTSTRAPS = [
    ("bootstrap_points_diff.csv", "bootstrap_points_diff_r.csv"),
    ("bootstrap_net_diff.csv", "bootstrap_net_diff_r.csv"),
    ("bootstrap_restricted.csv", "bootstrap_restricted_r.csv"),
    ("bootstrap_net_restricted.csv", "bootstrap_net_restricted_r.csv"),
]


def compare_table(py_name: str, r_name: str, keys: list[str],
                  cols: list[str]) -> tuple[bool, str]:
    py = pl.read_csv(OUT / py_name)
    r = pl.read_csv(OUT / r_name)
    # Booleans serialize as true/TRUE etc. across languages; normalize keys.
    for k in keys:
        if py[k].dtype == pl.Boolean or r[k].dtype == pl.Boolean:
            py = py.with_columns(pl.col(k).cast(pl.Boolean))
            r = r.with_columns(pl.col(k).cast(pl.Boolean))
    merged = py.join(r, on=keys, how="full", suffix="_r", coalesce=True)
    if merged.height != py.height or py.height != r.height:
        return False, f"row counts differ: py={py.height} r={r.height} joined={merged.height}"
    worst = 0.0
    for c in cols:
        d = (merged[c] - merged[f"{c}_r"]).abs().max()
        if d is None:
            return False, f"column {c}: null diff (missing values on one side)"
        worst = max(worst, d)
    ok = worst <= TOL
    return ok, f"{py.height} rows, max abs diff {worst:.2e}"


def compare_bootstrap(py_name: str, r_name: str) -> tuple[bool, str]:
    have_py, have_r = (OUT / py_name).exists(), (OUT / r_name).exists()
    if not have_py and not have_r:
        # both languages skip the restricted sensitivity when a group has
        # 30 or fewer team-periods; agreeing to skip it is still agreement
        return True, "not computed by either (a group has <= 30 team-periods)"
    if have_py != have_r:
        return False, f"only {'python' if have_py else 'R'} wrote it"
    py = pl.read_csv(OUT / py_name).row(0, named=True)
    r = pl.read_csv(OUT / r_name).row(0, named=True)
    overlap = (py["ci_lo"] <= r["ci_hi"]) and (r["ci_lo"] <= py["ci_hi"])
    same_n = (py["n_treated"] == r["n_treated"]) and (py["n_control"] == r["n_control"])
    ok = overlap and same_n
    return ok, (f"py {py['estimate']:+.3f} [{py['ci_lo']:+.3f},{py['ci_hi']:+.3f}] | "
                f"r {r['estimate']:+.3f} [{r['ci_lo']:+.3f},{r['ci_hi']:+.3f}]"
                + ("" if same_n else " | group sizes differ"))


def main() -> int:
    global OUT
    ap = argparse.ArgumentParser()
    seasons.add_args(ap)
    ap.add_argument("--all", action="store_true",
                    help="reconcile every league-season in seasons.SEASONS")
    ap.add_argument("--pooled", action="store_true",
                    help="also compare the pooled per-league bootstraps "
                         "(09_seasons.py vs R/09_pooled.R)")
    args = ap.parse_args()
    targets = seasons.SEASONS if args.all else [(args.league, args.season)]

    all_ok = True
    if args.pooled:
        all_ok &= reconcile_pooled()
        print()
    for league, season in targets:
        OUT = seasons.out_dir(league, season)
        if not (OUT / "team_period_windows.csv").exists():
            # loud, not skipped: --all must cover every season it names
            print(f"FAIL  {seasons.label(league, season)}: no outputs in {OUT}")
            all_ok = False
            continue
        print(f"=== {seasons.label(league, season)}")
        all_ok &= reconcile_one()
        print()

    print("ALL CHECKS PASS" if all_ok else "MISMATCHES FOUND")
    return 0 if all_ok else 1


def reconcile_pooled() -> bool:
    """Pooled window bootstraps: Python vs R, by league and quantity."""
    root = seasons.ROOT / "output"
    py = pl.read_csv(root / "seasons_pooled.csv").filter(
        pl.col("quantity") != "decision_quick_minus_hold")  # python-only layer
    r = pl.read_csv(root / "seasons_pooled_r.csv")
    merged = py.join(r, on=["league", "quantity"], how="full", suffix="_r", coalesce=True)
    print("=== pooled per league (different RNGs; intervals compared for overlap)")
    if merged.height != py.height or py.height != r.height:
        print(f"  FAIL  row counts differ: py={py.height} r={r.height}")
        return False
    ok_all = True
    for row in merged.iter_rows(named=True):
        overlap = row["ci_lo"] <= row["ci_hi_r"] and row["ci_lo_r"] <= row["ci_hi"]
        same_n = (row["n_treated"] == row["n_treated_r"]
                  and row["n_control"] == row["n_control_r"])
        same_est = abs(row["estimate"] - row["estimate_r"]) <= TOL
        ok = overlap and same_n and same_est
        ok_all &= ok
        print(f"  {'PASS' if ok else 'FAIL'}  {row['league']:4s} {row['quantity']:15s} "
              f"py {row['estimate']:+.3f} [{row['ci_lo']:+.3f},{row['ci_hi']:+.3f}] | "
              f"r {row['estimate_r']:+.3f} [{row['ci_lo_r']:+.3f},{row['ci_hi_r']:+.3f}]"
              + ("" if same_n else " | group sizes differ"))
    return ok_all


def reconcile_one() -> bool:
    print(f"Reconciling R and Python implementations (tolerance {TOL:g})\n")
    all_ok = True

    for py_name, r_name, keys, cols in TABLES:
        ok, msg = compare_table(py_name, r_name, keys, cols)
        all_ok &= ok
        print(f"  {'PASS' if ok else 'FAIL'}  {py_name:32s} {msg}")

    print("\nBootstraps (different RNGs; intervals compared for overlap):")
    for py_name, r_name in BOOTSTRAPS:
        ok, msg = compare_bootstrap(py_name, r_name)
        all_ok &= ok
        print(f"  {'PASS' if ok else 'FAIL'}  {py_name:32s} {msg}")
    return all_ok


if __name__ == "__main__":
    sys.exit(main())
