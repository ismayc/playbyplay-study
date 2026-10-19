"""The 2026-10-19 correction to the NBA 2023-24 results: published vs corrected.

Until 2026-10-19 the score forward-fill ran in actionNumber order. The feed
inserts late events with a high actionNumber but an early clock, and those
strays carried the period-end score back to the 60-second (and 40-second)
mark, which zeroed or shrank the window points of about 15% of team-periods.
10_check_sources.py found it: the NBA liveData feed agreed with the old
window points on 84.9% of team-periods, and on 99.93% after the fix (events
in game-clock order). The same commit also sorted the window tables before
bootstrapping (the published intervals had come from a run-dependent row
order) and changed 05's "later possessions" to count possessions that used
the ball.

This writes every published headline quantity next to its corrected value.
The published values are read from the last commit before the fix, so the
table stays reproducible after later commits; 03_findings.py renders the
README's correction note from it.

Output: output/correction_2026-10-19.csv
Run:    python python/11_correction.py          build
        python python/11_correction.py --check  fail if the table is stale
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
TABLE = OUT / "correction_2026-10-19.csv"
PUBLISHED_COMMIT = "9456968"   # last commit before the fix (2026-10-19)


def published(name: str) -> pl.DataFrame:
    blob = subprocess.run(["git", "-C", str(ROOT), "show",
                           f"{PUBLISHED_COMMIT}:output/{name}"],
                          capture_output=True, check=True).stdout
    return pl.read_csv(io.BytesIO(blob))


def current(name: str) -> pl.DataFrame:
    return pl.read_csv(OUT / name)


def rows() -> list[dict]:
    out = []

    def add(quantity: str, old: float, new: float) -> None:
        out.append({"quantity": quantity, "published": float(old),
                    "corrected": float(new), "change": float(new - old)})

    for name, label in [("bootstrap_points_diff.csv", "own_gap"),
                        ("bootstrap_net_diff.csv", "net_gap"),
                        ("bootstrap_restricted.csv", "own_gap_restricted"),
                        ("bootstrap_net_restricted.csv", "net_gap_restricted"),
                        ("bootstrap_decision_quick_vs_hold.csv", "quick_minus_hold")]:
        o, n = published(name).row(0, named=True), current(name).row(0, named=True)
        for col, suffix in [("estimate", ""), ("ci_lo", "_lo"), ("ci_hi", "_hi")]:
            add(label + suffix, o[col], n[col])

    for flag, label in [(True, "two_for_one"), (False, "held")]:
        o = published("two_for_one_summary.csv").filter(pl.col("two_for_one") == flag).row(0, named=True)
        n = current("two_for_one_summary.csv").filter(pl.col("two_for_one") == flag).row(0, named=True)
        for col in ["mean_points", "mean_opp_points", "mean_net"]:
            add(f"{label}_{col}", o[col], n[col])

    for behavior in ["quick", "normal", "hold"]:
        o = published("decision_summary.csv").filter(pl.col("behavior") == behavior).row(0, named=True)
        n = current("decision_summary.csv").filter(pl.col("behavior") == behavior).row(0, named=True)
        add(f"{behavior}_mean_net", o["mean_net"], n["mean_net"])
        add(f"{behavior}_later_poss", o["mean_later_poss"], n["mean_later_poss"])

    old_w, new_w = published("team_period_windows.csv"), current("team_period_windows.csv")
    k = ["gameId", "period", "location"]
    j = old_w.join(new_w, on=k, suffix="_new")
    add("team_periods", j.height, j.height)
    add("team_periods_points_changed", 0,
        int((j["points"] != j["points_new"]).sum()))
    return out


def main(argv: list[str]) -> int:
    table = pl.DataFrame(rows())
    if "--check" in argv:
        committed = pl.read_csv(TABLE)
        ok = (committed["quantity"].to_list() == table["quantity"].to_list()
              and float((committed["corrected"] - table["corrected"]).abs().max()) < 1e-12
              and float((committed["published"] - table["published"]).abs().max()) < 1e-12)
        print("CORRECTION TABLE CHECK " + ("PASSED" if ok else "FAILED")
              + f" ({table.height} quantities, published values from {PUBLISHED_COMMIT})")
        return 0 if ok else 1
    table.write_csv(TABLE)
    with pl.Config(tbl_rows=-1, float_precision=3):
        print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
