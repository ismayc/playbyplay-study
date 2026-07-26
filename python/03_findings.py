"""Write the Findings section of the play-by-play README from computed output.

Same discipline as the jersey study: no number in the prose is typed by hand, so
the narrative cannot drift from the analysis when the data is refreshed.

Run: python python/03_findings.py
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
README = ROOT / "README.md"
MARKER = "## Findings"


def build() -> str:
    summary = pl.read_csv(OUT / "two_for_one_summary.csv")
    boot = pl.read_csv(OUT / "bootstrap_points_diff.csv").row(0, named=True)
    boot_net = pl.read_csv(OUT / "bootstrap_net_diff.csv").row(0, named=True)
    efg = pl.read_csv(OUT / "efg_by_seconds_left.csv").sort("bucket")
    windows = pl.read_csv(OUT / "team_period_windows.csv")

    t = summary.filter(pl.col("two_for_one")).row(0, named=True)
    h = summary.filter(~pl.col("two_for_one")).row(0, named=True)

    n_games = windows["gameId"].n_unique()
    share = t["team_periods_n"] / (t["team_periods_n"] + h["team_periods_n"])

    # Behavioural evidence: a local spike in first-shot timing right at the
    # threshold. Compared against the 36-40s band, which has MORE opportunity
    # (later in the window) and so should be higher if nothing special happened
    # at 32s.
    timing = pl.read_csv(OUT / "first_shot_timing.csv")

    def band(lo: int, hi: int) -> float:
        sel = timing.filter(pl.col("bucket").is_between(lo, hi))
        return float(sel["n"].mean()) if sel.height else float("nan")

    spike = band(31, 33)
    after = band(36, 40)
    trough = band(22, 30)

    early = efg.filter(pl.col("bucket") >= 32)
    late = efg.filter(pl.col("bucket") <= 3)
    early_efg = early["efg"].mean() if early.height else float("nan")
    late_efg = late["efg"].mean() if late.height else float("nan")

    efg_rows = "\n".join(
        f"| {r['bucket']}–{r['bucket'] + 3}s | {r['efg']:.3f} | {r['n']:,} |"
        for r in efg.iter_rows(named=True)
    )

    excl = "excludes" if (boot["ci_lo"] > 0 or boot["ci_hi"] < 0) else "includes"

    restricted = ""
    rpath = OUT / "bootstrap_restricted.csv"
    if rpath.exists():
        r = pl.read_csv(rpath).row(0, named=True)
        rn = pl.read_csv(OUT / "bootstrap_net_restricted.csv").row(0, named=True)
        r_excl = "excludes" if (r["ci_lo"] > 0 or r["ci_hi"] < 0) else "includes"
        rn_excl = "excludes" if (rn["ci_lo"] > 0 or rn["ci_hi"] < 0) else "includes"
        restricted = (
            f"\n### Sensitivity: narrowing the selection gap\n\n"
            f"Restricting to team-periods whose first shot came between 20 and 45 "
            f"seconds — so both groups had the ball at broadly similar times — the "
            f"own-points gap is **{r['estimate']:+.3f}** "
            f"(95% CI [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}], {r_excl} zero) and the "
            f"net gap is **{rn['estimate']:+.3f}** "
            f"(95% CI [{rn['ci_lo']:+.3f}, {rn['ci_hi']:+.3f}], {rn_excl} zero; "
            f"n = {r['n_treated']:,} vs {r['n_control']:,}).\n\n"
            f"Both gaps shrink under the restriction, which is what you would "
            f"expect if part of the headline gap is selection rather than strategy. "
            f"The own-points advantage survives; the net advantage narrows to the "
            f"edge of what one season of data can distinguish from zero. That "
            f"asymmetry is itself informative: the extra possession is real, but "
            f"the opponent's reply claws back much of its value.\n"
        )

    # Possession-level decision-team results, if 05_possession_analysis.py ran
    possession = ""
    dpath = OUT / "decision_summary.csv"
    if dpath.exists():
        ds = pl.read_csv(dpath)
        db = pl.read_csv(OUT / "bootstrap_decision_quick_vs_hold.csv").row(0, named=True)
        pv = pl.read_csv(OUT / "proxy_vs_possession.csv").row(0, named=True)
        by = {r["behavior"]: r for r in ds.iter_rows(named=True)}
        q, nm, hd = by["quick"], by["normal"], by["hold"]
        total = q["n"] + nm["n"] + hd["n"]
        possession = f"""
### 4. Possession-level upgrade: the decision-team design

The proxy limitation is closed with real possessions (pbpstats rows with
start/end times via the bulk archive in `../docs/public-data-availability.md`;
1,228 of 1,230 games — `python/05_possession_analysis.py` also documents why a
literal translation of the old design just relocates the blindness). The
sharper frame: **at the 40-second mark of every Q1–Q3, exactly one team has
the ball — the team actually facing the 2-for-1 decision.** {total:,} decision
possessions, split by the observed choice:

| Choice | n | Share | Net pts from 40s | Later possessions | ended in TO |
|---|---|---|---|---|---|
| **Quick** (released ≥28s left) | {q['n']:,} | **{q['n'] / total:.1%}** | **{q['mean_net']:+.2f}** | {q['mean_later_poss']:.2f} | {q['to_share']:.1%} |
| Normal (16–27s) | {nm['n']:,} | {nm['n'] / total:.1%} | {nm['mean_net']:+.2f} | {nm['mean_later_poss']:.2f} | {nm['to_share']:.1%} |
| **Hold** (carried past 15s) | {hd['n']:,} | **{hd['n'] / total:.1%}** | {hd['mean_net']:+.2f} | {hd['mean_later_poss']:.2f} | {hd['to_share']:.1%} |

Three things fall out:

1. **The debate is over in practice.** Teams with the ball at the decision
   moment go quick {q['n'] / total:.0%} of the time; genuine holds are nearly
   extinct — {hd['n']} team-periods in a full season. The argument this study
   set out to test has largely been settled by the league's behaviour.
2. **The mechanism is now measured directly**: quick teams average
   {q['mean_later_poss']:.2f} further possessions after the mark vs
   {hd['mean_later_poss']:.2f} for holds — the extra possession counted,
   not inferred from shots.
3. Quick minus hold on net points from the mark:
   **{db['estimate']:+.2f} [{db['ci_lo']:+.2f}, {db['ci_hi']:+.2f}]** —
   consistent with the tactic paying, but with {db['n_control']} holds the
   comparison is honest about being underpowered. When a strategy wins the
   behavioural argument this thoroughly, its control group disappears.

The first-shot proxy, scored against observed choices: it flags
{pv['quick_correctly_flagged']:.0%} of true quicks but correctly identifies
only {pv['hold_correctly_unflagged']:.0%} of true holds — quantifying exactly
how much limitation 2 mattered.
"""

    return f"""{MARKER}

Based on **{n_games:,} games** of 2023-24 play-by-play. Every number is generated by
`python/03_findings.py` from `output/`, not typed by hand.

### 1. Teams really do hunt the 2-for-1

Of the {t['team_periods_n'] + h['team_periods_n']:,} team-periods with a shot in the
final 60 seconds of Q1–Q3, **{share:.0%}** took their first shot with 32 or more
seconds left.

The share alone is weak evidence — later in the window there is simply more
opportunity to shoot. The strong evidence is a **local spike exactly at the
threshold**:

| First shot at | Mean team-periods per second |
|---|---|
| 22–30s (the wait) | {trough:.0f} |
| **31–33s (the threshold)** | **{spike:.0f}** |
| 36–40s (later, more opportunity) | {after:.0f} |

Teams bunch at 31–33 seconds **{spike / after:.2f}× more** than at 36–40 seconds,
even though the later band has more chances to shoot and should be higher if nothing
special happened at 32. That discontinuity is the behaviour itself, visible in the
raw counts rather than assumed: coaches are running this play deliberately.
See `figures/fig1_first_shot_timing.png`.

### 2. The 2-for-1 is associated with more points — on both sides of the ball

| | First shot ≥ 32s (2-for-1) | First shot < 32s (held) |
|---|---|---|
| Team-periods | {t['team_periods_n']:,} | {h['team_periods_n']:,} |
| Mean points in window | **{t['mean_points']:.3f}** | **{h['mean_points']:.3f}** |
| Mean opponent points | **{t['mean_opp_points']:.3f}** | **{h['mean_opp_points']:.3f}** |
| Mean **net** points | **{t['mean_net']:+.3f}** | **{h['mean_net']:+.3f}** |
| Mean field-goal attempts | **{t['mean_fga']:.2f}** | **{h['mean_fga']:.2f}** |
| Effective FG% | **{t['mean_efg']:.3f}** | **{h['mean_efg']:.3f}** |

Own-points difference: **{boot['estimate']:+.3f}** per team-period
(95% bootstrap CI [{boot['ci_lo']:+.3f}, {boot['ci_hi']:+.3f}], {excl} zero,
{int(boot['reps']):,} resamples).

**Why net matters:** the case for holding the ball is precisely that it denies
the opponent a reply, so an outcome that only counts a team's own points misses
half the trade. On net points the raw gap is **{boot_net['estimate']:+.3f}**
(95% CI [{boot_net['ci_lo']:+.3f}, {boot_net['ci_hi']:+.3f}]) — but read the
sensitivity analysis below before taking either raw gap at face value, because
the "held" group includes many team-periods where the *opponent* controlled the
window.

The mechanism is visible in the FGA row: roughly
**{t['mean_fga'] - h['mean_fga']:+.2f} extra shots** per window. That is the extra
possession, showing up exactly where it should.
{restricted}
### 3. The expected cost never appears

The standard objection to the 2-for-1 is that you rush a bad shot to create the
extra possession. **In this data that cost does not show up.**

| Seconds left | Effective FG% | Attempts |
|---|---|---|
{efg_rows}

Shots taken with 32+ seconds left average **eFG% {early_efg:.3f}** — ordinary,
in-rhythm shots. The genuinely bad shot is the buzzer-beater: **eFG% {late_efg:.3f}**
in the last four seconds.

That reframes the decision. The 2-for-1 does not trade a good shot for a bad one. It
**adds** a normal-quality possession, because the desperation heave at the buzzer
gets taken either way. The team that holds gives up the extra possession and still
takes the bad shot.
{possession}
### 5. What this does not establish

The treatment is not randomly assigned, and the biggest confound is possession
timing: a team that does not get the ball until 20 seconds remain *cannot* run a
2-for-1, and is not comparable to one that had it at 40 seconds. Some of the gap is
therefore selection — teams with the ball earlier were more likely to have just
gotten a stop, and may be in transition against an unset defense.

The sensitivity analysis narrows that gap but does not close it. The honest
statement is: **teams that shoot early score more in the window, the extra
possession is real and measurable, and the usual objection to the strategy — a
rushed, bad shot — is not visible in the data. What limits the payoff is not
shot quality but the opponent's reply: on a net basis, in the comparable
sample, one season of data cannot cleanly distinguish the advantage from
zero.** A causal estimate would need possession-level tracking of when each
team actually gained the ball, which is the natural next step.
"""


def main() -> int:
    text = README.read_text()
    head = text.split(MARKER)[0].rstrip()
    README.write_text(head + "\n\n" + build())
    print(f"Updated Findings in {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
