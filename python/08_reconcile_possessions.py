"""Check the pbpstats-library possessions against the bulk archive.

07_build_possessions.py builds every season itself because the archive lacks
NBA 2025-26 and WNBA 2026. Those two seasons are trusted only because this
check passes on every season both sources cover: 05_possession_analysis.py
is run on each source, and the decision windows it writes are compared
period by period.

Gates, per league-season the archive has:
  1. the built table covers every harvested game;
  2. on game-periods both sources classify, the decision team (offense at the
     40-second mark) is the same in at least 99.5% of them;
  3. on those, the quick/normal/hold call is the same in at least 99%;
  4. the quick-minus-hold net estimate differs by less than 0.05 points and
     the two bootstrap intervals overlap.
Games rebuilt with the starter check off (lenient_starters) are reported
separately, so a problem confined to them cannot hide in the totals.

Reported, not gated: agreement on 05's "later possessions" count. The two
sources draw the final possession of a period differently (the archive
leaves out some last possessions that pbpstats keeps, including some that
end in a buzzer heave), and the archive's rule cannot be recovered from its
published rows, so the count differs by about 0.07 possessions per decision
(NBA 2023-24: 267 of 3,683 decision periods, always pbpstats +1). The
cross-season comparison uses the built source for every season, so it
compares like with like.

Prerequisite: 05_possession_analysis.py run with --source archive and
--source built for each season below.

Run: python python/08_reconcile_possessions.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seasons  # noqa: E402

OFFENSE_MIN = 0.995
BEHAVIOR_MIN = 0.99
ESTIMATE_TOL = 0.05


def reconcile(league: str, season: str) -> tuple[bool, dict]:
    out = seasons.out_dir(league, season)
    arch = pl.read_csv(out / "decision_windows.csv")
    built = pl.read_csv(out / "built" / "decision_windows.csv")
    poss = pl.read_parquet(seasons.possessions_file(league, season))
    n_raw = len(seasons.raw_files(league, season))
    lenient = set(poss.filter(pl.col("lenient_starters"))["game_id"].unique().to_list())

    keys = ["game_id", "PERIOD"]
    both = arch.join(built, on=keys, how="inner", suffix="_b")
    same_off = (both["offense"] == both["offense_b"])
    same_beh = (both["behavior"] == both["behavior_b"])
    in_len = both["game_id"].is_in(list(lenient))

    ba = pl.read_csv(out / "bootstrap_decision_quick_vs_hold.csv").row(0, named=True)
    bb = pl.read_csv(out / "built" / "bootstrap_decision_quick_vs_hold.csv").row(0, named=True)

    row = {
        "league": league, "season": season,
        "games_harvested": n_raw,
        "games_built": poss["game_id"].n_unique(),
        "games_archive": arch["game_id"].n_unique(),
        "lenient_games": len(lenient),
        "periods_archive": arch.height, "periods_built": built.height,
        "periods_both": both.height,
        "offense_agree": float(same_off.mean()),
        "behavior_agree": float(same_beh.mean()),
        "behavior_agree_lenient": (float(same_beh.filter(in_len).mean())
                                   if in_len.any() else None),
        "lenient_periods": int(in_len.sum()),
        "later_poss_agree": float((both["n_later_poss"] == both["n_later_poss_b"]).mean()),
        "later_poss_mean_archive": float(both["n_later_poss"].mean()),
        "later_poss_mean_built": float(both["n_later_poss_b"].mean()),
        "estimate_archive": ba["estimate"], "estimate_built": bb["estimate"],
        "ci_archive": f"[{ba['ci_lo']:+.3f}, {ba['ci_hi']:+.3f}]",
        "ci_built": f"[{bb['ci_lo']:+.3f}, {bb['ci_hi']:+.3f}]",
    }
    gates = {
        "built covers every harvested game": row["games_built"] == n_raw,
        f"decision team agrees >= {OFFENSE_MIN:.1%}": row["offense_agree"] >= OFFENSE_MIN,
        f"quick/normal/hold agrees >= {BEHAVIOR_MIN:.0%}": row["behavior_agree"] >= BEHAVIOR_MIN,
        f"estimates within {ESTIMATE_TOL}":
            abs(row["estimate_archive"] - row["estimate_built"]) < ESTIMATE_TOL,
        "intervals overlap": ba["ci_lo"] <= bb["ci_hi"] and bb["ci_lo"] <= ba["ci_hi"],
    }
    return all(gates.values()), {**row, "gates": gates}


def main() -> int:
    targets = [ls for ls in seasons.SEASONS if ls in seasons.ARCHIVE]
    rows, all_ok = [], True
    for league, season in targets:
        ok, r = reconcile(league, season)
        all_ok &= ok
        print(f"=== {seasons.label(league, season)}: {'PASS' if ok else 'FAIL'}")
        print(f"  games: harvested {r['games_harvested']:,}, built {r['games_built']:,} "
              f"({r['lenient_games']} lenient), archive {r['games_archive']:,}")
        print(f"  decision periods: archive {r['periods_archive']:,}, built "
              f"{r['periods_built']:,}, both {r['periods_both']:,}")
        print(f"  agreement: decision team {r['offense_agree']:.2%}, "
              f"quick/normal/hold {r['behavior_agree']:.2%}"
              + (f" (lenient games: {r['behavior_agree_lenient']:.2%} of "
                 f"{r['lenient_periods']} periods)" if r['lenient_periods'] else ""))
        print(f"  quick minus hold: archive {r['estimate_archive']:+.3f} {r['ci_archive']}, "
              f"built {r['estimate_built']:+.3f} {r['ci_built']}")
        print(f"  (reported, not gated) later possessions agree on "
              f"{r['later_poss_agree']:.1%}; mean archive {r['later_poss_mean_archive']:.2f}, "
              f"built {r['later_poss_mean_built']:.2f}")
        for name, passed in r["gates"].items():
            print(f"    {'PASS' if passed else 'FAIL'}  {name}")
        rows.append({k: v for k, v in r.items() if k != "gates"})

    out = seasons.ROOT / "output" / "possession_source_reconciliation.csv"
    pl.DataFrame(rows).write_csv(out)
    print(f"\nwrote {out.relative_to(seasons.ROOT)}")
    print("POSSESSION SOURCES " + ("RECONCILE" if all_ok else "DISAGREE"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
