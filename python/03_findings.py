"""Write every analysis number in the play-by-play README from computed output.

Same discipline as the jersey study: no number in the prose is typed by hand,
so the narrative cannot drift from the analysis when the data is refreshed.
Ownership covers the Findings section plus four marked regions elsewhere in
the README (<!-- gen:correction -->, <!-- gen:coverage -->, <!-- gen:proxy -->,
<!-- gen:extension -->).

The generator writes plain text; hover tooltips are re-applied afterwards by
the family glossary tool (../basketball-analysis-tools/glossary.py --sync).

Run:    python python/03_findings.py            rewrite the owned regions
        python python/03_findings.py --check    fail if the committed README
                                                (abbr tags stripped) differs
                                                from what a rewrite would say
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
README = ROOT / "README.md"
MARKER = "## Findings"
ABBR = re.compile(r'<abbr title="[^"]*">([^<]*)</abbr>')

# Tricode -> the short market name used in prose.
TEAM_CITY = {
    "ATL": "Atlanta", "BOS": "Boston", "BKN": "Brooklyn",
    "CHA": "Charlotte", "CHI": "Chicago", "CLE": "Cleveland",
    "DAL": "Dallas", "DEN": "Denver", "DET": "Detroit",
    "GSW": "Golden State", "HOU": "Houston", "IND": "Indiana",
    "LAC": "LA Clippers", "LAL": "LA Lakers", "MEM": "Memphis",
    "MIA": "Miami", "MIL": "Milwaukee", "MIN": "Minnesota",
    "NOP": "New Orleans", "NYK": "New York", "OKC": "Oklahoma City",
    "ORL": "Orlando", "PHI": "Philadelphia", "PHX": "Phoenix",
    "POR": "Portland", "SAC": "Sacramento", "SAS": "San Antonio",
    "TOR": "Toronto", "UTA": "Utah", "WAS": "Washington",
}


def strip_abbr(text: str) -> str:
    return ABBR.sub(r"\1", text)


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

    # Behavioral evidence: a local spike in first-shot timing right at the
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
            f"seconds (so both groups had the ball at broadly similar times), the "
            f"own-points gap is **{r['estimate']:+.3f}** "
            f"(95% CI [{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}], {r_excl} zero) and the "
            f"net gap is **{rn['estimate']:+.3f}** "
            f"(95% CI [{rn['ci_lo']:+.3f}, {rn['ci_hi']:+.3f}], {rn_excl} zero; "
            f"n = {r['n_treated']:,} vs {r['n_control']:,}).\n\n"
            f"Both gaps shrink under the restriction, which is what you would "
            f"expect if part of the headline gap is selection rather than strategy. "
            + ("The own-points advantage survives, and so does the net advantage, "
               f"though at {rn['estimate'] / r['estimate']:.0%} of the own-points "
               "size: the extra possession is real, and the opponent's reply claws "
               "back part of its value.\n"
               if rn_excl == "excludes" else
               "The own-points advantage survives; the net advantage narrows to the "
               "edge of what one season of data can distinguish from zero. That "
               "asymmetry is itself informative: the extra possession is real, but "
               "the opponent's reply claws back much of its value.\n")
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
        rec = (pl.read_csv(OUT / "possession_source_reconciliation.csv")
               .filter((pl.col("league") == "nba") & (pl.col("season") == "2023-24"))
               .row(0, named=True))
        possession = f"""
### 4. Possession-level upgrade: the decision-team design

The proxy limitation is closed with real possessions (pbpstats rows with
start/end times via the bulk archive in `../docs/public-data-availability.md`;
{rec['games_archive']:,} of {rec['games_harvested']:,} games;
`python/05_possession_analysis.py` also documents why a
literal translation of the old design just relocates the blindness). The
sharper frame: **at the 40-second mark of every Q1–Q3, exactly one team has
the ball, the team actually facing the 2-for-1 decision.** {total:,} decision
possessions, split by the observed choice:

| Choice | n | Share | Net pts from 40s | Later possessions | ended in TO |
|---|---|---|---|---|---|
| **Quick** (released ≥28s left) | {q['n']:,} | **{q['n'] / total:.1%}** | **{q['mean_net']:+.2f}** | {q['mean_later_poss']:.2f} | {q['to_share']:.1%} |
| Normal (16–27s) | {nm['n']:,} | {nm['n'] / total:.1%} | {nm['mean_net']:+.2f} | {nm['mean_later_poss']:.2f} | {nm['to_share']:.1%} |
| **Hold** (carried past 15s) | {hd['n']:,} | **{hd['n'] / total:.1%}** | {hd['mean_net']:+.2f} | {hd['mean_later_poss']:.2f} | {hd['to_share']:.1%} |

Three things fall out:

1. **The debate is over in practice.** Teams with the ball at the decision
   moment go quick {q['n'] / total:.0%} of the time; genuine holds are nearly
   extinct: {hd['n']} team-periods in a full season. The argument this study
   set out to test has largely been settled by the league's behavior.
2. **The mechanism is now measured directly**: quick teams average
   {q['mean_later_poss']:.2f} further possessions after the mark vs
   {hd['mean_later_poss']:.2f} for holds (the extra possession counted,
   not inferred from shots; a possession counts if it produced a shot, a
   free-throw trip, or a turnover).
3. Quick minus hold on net points from the mark:
   **{db['estimate']:+.2f} [{db['ci_lo']:+.2f}, {db['ci_hi']:+.2f}]**,
   consistent with the tactic paying, but with {db['n_control']} holds the
   comparison is honest about being underpowered. When a strategy wins the
   behavioral argument this thoroughly, its control group disappears.

The first-shot proxy, scored against observed choices: it flags
{pv['quick_correctly_flagged']:.0%} of true quicks but correctly identifies
only {pv['hold_correctly_unflagged']:.0%} of true holds, quantifying exactly
how much limitation 2 mattered.
"""

    # the closing statement follows the restricted net interval, not a fixed text
    net_settled = False
    if rpath.exists():
        net_settled = rn["ci_lo"] > 0 or rn["ci_hi"] < 0
    pooled_path = OUT / "seasons_pooled.csv"
    pooled_ok = False
    if pooled_path.exists():
        pnr = (pl.read_csv(pooled_path)
               .filter((pl.col("league") == "nba") & (pl.col("quantity") == "net_restricted"))
               .row(0, named=True))
        pooled_ok = pnr["ci_lo"] > 0
    closing = (
        "on a net basis, in the comparable sample, the advantage is smaller but "
        "its interval excludes zero"
        + (", and pooling three NBA seasons (section 6) confirms it.**" if pooled_ok
           else ".**") if net_settled else
        "on a net basis, in the comparable sample, one season of data cannot "
        "cleanly distinguish the advantage from zero.**")

    return f"""{MARKER}

Based on **{n_games:,} games** of 2023-24 play-by-play (sections 1-5; section 6
adds two more NBA seasons and three WNBA seasons). Every number is generated by
`python/03_findings.py` from `output/`, not typed by hand.

### 1. Teams really do hunt the 2-for-1

Of the {t['team_periods_n'] + h['team_periods_n']:,} team-periods with a shot in the
final 60 seconds of Q1–Q3, **{share:.0%}** took their first shot with 32 or more
seconds left.

The share alone is weak evidence. Later in the window there is simply more
opportunity to shoot. The strong evidence is a **local spike exactly at the
threshold**:

| First shot at | Mean team-periods per second |
|---|---|
| 22–30s (the wait) | {trough:.0f} |
| **31–33s (the threshold)** | **{spike:.0f}** |
| 36–40s (later, more opportunity) | {after:.0f} |

Teams bunch at 31–33 seconds **{spike / after:.2f}× more** than at 36–40 seconds,
even though the later band has more chances to shoot and should be higher if nothing
special happened at 32. That discontinuity is the behavior itself, visible in the
raw counts rather than assumed: coaches are running this play deliberately.
See `figures/fig1_first_shot_timing.png`.

### 2. The 2-for-1 is associated with more points, on both sides of the ball

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
(95% CI [{boot_net['ci_lo']:+.3f}, {boot_net['ci_hi']:+.3f}]). But read the
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

Shots taken with 32+ seconds left average **eFG% {early_efg:.3f}**: ordinary,
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
therefore selection: teams with the ball earlier were more likely to have just
gotten a stop, and may be in transition against an unset defense.

The sensitivity analysis narrows that gap but does not close it. The honest
statement is: **teams that shoot early score more in the window, the extra
possession is real and measurable, and the usual objection to the strategy (a
rushed, bad shot) is not visible in the data. What limits the payoff is not
shot quality but the opponent's reply: {closing} Section 4's decision-team
design removes the "never had the ball" confound but not the choice itself,
which is still made by teams, not assigned.
{seasons_section()}"""


def _ci(est: float, lo: float, hi: float, digits: int = 2) -> str:
    return f"{est:+.{digits}f} [{lo:+.{digits}f}, {hi:+.{digits}f}]"


def _excl(lo: float, hi: float) -> bool:
    return lo > 0 or hi < 0


def seasons_section() -> str:
    """Section 6, from 09_seasons.py, 08_reconcile_possessions.py and
    10_check_sources.py outputs."""
    spath = OUT / "seasons_summary.csv"
    if not spath.exists():
        return ""
    s = pl.read_csv(spath)
    pooled = pl.read_csv(OUT / "seasons_pooled.csv")
    src = pl.read_csv(OUT / "source_check.csv")
    rec = pl.read_csv(OUT / "possession_source_reconciliation.csv")

    def pool(league: str, q: str) -> dict:
        return pooled.filter((pl.col("league") == league)
                             & (pl.col("quantity") == q)).row(0, named=True)

    rows = []
    for r in s.iter_rows(named=True):
        restricted = (_ci(r["net_gap_restricted"], r["net_gap_restricted_lo"],
                          r["net_gap_restricted_hi"])
                      if r["net_gap_restricted"] is not None else "not computed")
        rows.append(
            f"| {r['league'].upper()} {r['season']} | {r['games']:,} | "
            f"{r['proxy_2for1_share']:.1%} | {r['spike_ratio']:.2f} | "
            f"{r['quick_share']:.1%} | {r['hold_n']} | {restricted} | "
            f"{_ci(r['quick_minus_hold'], r['quick_minus_hold_lo'], r['quick_minus_hold_hi'])} |")
    table = "\n".join(rows)

    prow = []
    for lg in ("nba", "wnba"):
        cells = []
        for q in ("own", "net", "net_restricted", "decision_quick_minus_hold"):
            p = pool(lg, q)
            cells.append(_ci(p["estimate"], p["ci_lo"], p["ci_hi"]))
        prow.append(f"| {pool(lg, 'own')['seasons']} | " + " | ".join(cells) + " |")
    ptable = "\n".join(prow)

    nba, wnba = s.filter(pl.col("league") == "nba"), s.filter(pl.col("league") == "wnba")
    first, last = nba.row(0, named=True), nba.row(-1, named=True)
    qmin, qmax = nba["quick_share"].min(), nba["quick_share"].max()
    rising = bool((nba["quick_share"].diff().drop_nulls() > 0).all())
    holds = ", ".join(str(h) for h in nba["hold_n"])
    spike_falling = bool((nba["spike_ratio"].diff().drop_nulls() < 0).all())
    nr, nd = pool("nba", "net_restricted"), pool("nba", "decision_quick_minus_hold")
    wr, wd = pool("wnba", "net_restricted"), pool("wnba", "decision_quick_minus_hold")
    w_spike_max = wnba["spike_ratio"].max()
    w_holds = ", ".join(str(h) for h in wnba["hold_n"])
    w_hold_share = float(wnba["hold_n"].sum() / wnba["decision_periods"].sum())
    n_hold_share = float(nba["hold_n"].sum() / nba["decision_periods"].sum())

    archive_games = int(src["games_from_archive"].sum())
    ac = pl.read_csv(OUT / "archive_check.csv")
    ac_tp, ac_diff = int(ac["team_periods"].sum()), int(ac["team_periods_differ"].sum())
    ac_text = (f"all {ac_tp:,} team-periods matched" if ac_diff == 0 else
               f"{ac_diff:,} of {ac_tp:,} team-periods differed")
    agree_lo, agree_hi = src["agree_share"].min(), src["agree_share"].max()
    rmin = rec["behavior_agree"].min()
    agree_text = ("agrees on every decision period both sources classify"
                  if rmin == 1.0 else f"agrees on at least {rmin:.1%} of decision periods")

    nba_trend = (
        f"**The quick rate is not still rising** ({qmin:.1%} to {qmax:.1%} across "
        f"the three seasons), and **holds are not going extinct**: {holds} "
        f"in {first['season']}, {nba.row(1, named=True)['season']} and "
        f"{last['season']}." if not rising else
        f"The quick rate rose every season ({qmin:.1%} to {qmax:.1%}); holds "
        f"ran {holds}.")
    spike = (
        f" The bunching at the 32-second threshold is fading: the 31-33s spike "
        f"fell from {first['spike_ratio']:.2f}× to {last['spike_ratio']:.2f}× the "
        f"36-40s rate." if spike_falling else
        f" The 31-33s spike ran {first['spike_ratio']:.2f}× to "
        f"{last['spike_ratio']:.2f}× the 36-40s rate.")
    nba_net = (
        f"Pooled over three seasons, the restricted-sample net gap is "
        f"**{_ci(nr['estimate'], nr['ci_lo'], nr['ci_hi'], 3)}**, which "
        + ("excludes zero: the question one season left open is settled in the "
           "2-for-1's favor." if nr["ci_lo"] > 0 else
           "still includes zero."))
    wnba_designs = (
        f"**The two designs disagree in the WNBA.** The decision-team comparison "
        f"says going quick pays ({_ci(wd['estimate'], wd['ci_lo'], wd['ci_hi'])} "
        f"net points, n = {wd['n_control']} holds pooled), but the shot-timing "
        f"comparison restricted to first shots at 20-45s finds "
        f"{_ci(wr['estimate'], wr['ci_lo'], wr['ci_hi'])}. The decision-team "
        f"design is the more direct of the two (it conditions on who had the "
        f"ball at the mark), so it carries the conclusion, with the disagreement "
        f"stated." if _excl(wd["ci_lo"], wd["ci_hi"]) != _excl(wr["ci_lo"], wr["ci_hi"])
        else
        f"Both WNBA designs point the same way: decision-team "
        f"{_ci(wd['estimate'], wd['ci_lo'], wd['ci_hi'])}, restricted shot-timing "
        f"{_ci(wr['estimate'], wr['ci_lo'], wr['ci_hi'])}.")

    return f"""
### 6. Three seasons, two leagues

The study now covers NBA {nba.row(0, named=True)['season']} to {last['season']} and
WNBA {wnba.row(0, named=True)['season']} to {wnba.row(-1, named=True)['season']},
every regular-season game, with the same definitions. The WNBA plays 10-minute
quarters but the same 24-second shot clock, so the 60-second window and
32-second threshold carry over unchanged. Possessions for every season come
from the pbpstats library (`python/07_build_possessions.py`), checked against
the bulk archive on the seasons it covers (`python/08_reconcile_possessions.py`:
the quick/normal/hold call {agree_text}).

| League-season | Games | First shot ≥ 32s | 31-33s spike | Quick share | Holds | Restricted net gap [95% CI] | Quick minus hold, net [95% CI] |
|---|---|---|---|---|---|---|---|
{table}

Pooled within each league (bootstrap 95% CIs; the R implementation reproduces
the window estimates, `python/04_reconcile.py --pooled`):

| Seasons | Own-points gap | Net gap | Restricted net gap | Quick minus hold, net |
|---|---|---|---|---|
{ptable}

1. **NBA.** {nba_trend}{spike}
2. **NBA, the open question from one season.** {nba_net} Quick minus hold
   on the decision-team design pools to
   **{_ci(nd['estimate'], nd['ci_lo'], nd['ci_hi'])}** net points over
   {nd['n_control']} holds.
3. **WNBA.** Teams go quick less often than in the NBA
   ({wnba['quick_share'].min():.1%} to {wnba['quick_share'].max():.1%}) and do not
   bunch at the threshold at all (the 31-33s spike never exceeds
   {w_spike_max:.2f}× the 36-40s rate). Holds are
   {'more common' if w_hold_share > n_hold_share else 'no more common'}
   ({w_hold_share:.1%} of decisions vs {n_hold_share:.1%} in the NBA) but still
   rare ({w_holds} a season), so the WNBA does not supply the large hold group
   the replication hoped for.
4. {wnba_designs}

**Data sources for the added seasons.** stats.nba.com began timing out
partway through the NBA 2024-25 harvest, so {archive_games:,} games came from
the V3 archive instead (`python/01b_import_v3_archive.py`; on the
{int(ac['games_compared'].sum()):,} games both sources had, {ac_text} in the window table). Every
season's window points were then checked against an independent feed, the
NBA's liveData play-by-play: they agree on {agree_lo:.2%} to {agree_hi:.2%} of
team-periods (`python/10_check_sources.py`).
"""


def correction_note() -> str:
    """The 2026-10-19 correction, from 11_correction.py's table."""
    path = OUT / "correction_2026-10-19.csv"
    if not path.exists():
        return ""
    c = {r["quantity"]: r for r in pl.read_csv(path).iter_rows(named=True)}

    def pair(q: str, digits: int = 3) -> str:
        o, n = c[q], (c[q + "_lo"], c[q + "_hi"])
        return (f"{o['published']:+.{digits}f} [{n[0]['published']:+.{digits}f}, "
                f"{n[1]['published']:+.{digits}f}] → **{o['corrected']:+.{digits}f} "
                f"[{n[0]['corrected']:+.{digits}f}, {n[1]['corrected']:+.{digits}f}]**")

    changed = int(c["team_periods_points_changed"]["corrected"])
    total = int(c["team_periods"]["corrected"])
    changed2 = int(c["second_pass_points_changed"]["corrected"])
    total2 = int(c["second_pass_team_periods"]["corrected"])
    heads = ["own_gap", "net_gap", "net_gap_restricted", "quick_minus_hold"]
    direction = ("Every estimate moved in the 2-for-1's favor." if
                 all(c[q]["change"] > 0 for q in heads) else
                 "The estimates moved in both directions.")
    rl, rh = c["net_gap_restricted_lo"], c["net_gap_restricted_hi"]
    was_excl = _excl(rl["published"], rh["published"])
    now_excl = _excl(rl["corrected"], rh["corrected"])
    if now_excl and not was_excl:
        zero = ("The restricted net gap's interval now excludes zero, which reverses "
                "the earlier conclusion that one season could not distinguish it "
                "from zero.")
    elif was_excl and not now_excl:
        zero = ("The restricted net gap's interval now includes zero, which reverses "
                "the earlier conclusion that it excluded zero.")
    else:
        zero = "No interval changed sides of zero."
    return f"""
> **Correction, October 19, 2026.** The 2023-24 window points were computed
> with events in action-number order. The feed inserts late events with a high
> action number but an early clock, and those carried the period-end score back
> to the start of the window, so {changed:,} of {total:,} team-periods
> ({changed / total:.0%}) had wrong window points. An independent feed (the
> NBA's liveData play-by-play) exposed it; events are now in game-clock order,
> and every season is checked against that feed. {direction}
> Published → corrected (95% CI):
>
> - Own-points gap: {pair('own_gap')}
> - Net-points gap: {pair('net_gap')}
> - Restricted net gap: {pair('net_gap_restricted')}
> - Quick minus hold (decision team): {pair('quick_minus_hold', 2)}
>
> {zero} The
> same change sorts each table before bootstrapping, since the published
> intervals came from a row order that changed between runs.
>
> A second pass the same day fixed how scores are read from the feed: only
> made shots and free throws set the score, each only for the scoring team,
> and the score never falls (Instant Replay rows carried stale scores, and
> free throws at one clock reading could arrive out of order). It changed
> {changed2} of {total2:,} team-periods across all six league-seasons
> ({changed2 / total2:.2%}); the figures above include it. Full table:
> `output/correction_2026-10-19.csv`.
"""


def build_regions() -> dict[str, str]:
    """Owned regions outside the Findings section, keyed by marker name.

    Same discipline as build(): prose is fixed here, every number is computed.
    """
    windows = pl.read_csv(OUT / "team_period_windows.csv")
    n_games = windows["gameId"].n_unique()

    team = pl.read_csv(OUT / "team_2for1.csv").sort("rate", descending=True)
    top = team.row(0, named=True)
    bot = team.row(-1, named=True)
    league = team["tfo"].sum() / team["windows"].sum()
    top_city = TEAM_CITY.get(top["teamTricode"], top["teamTricode"])
    bot_city = TEAM_CITY.get(bot["teamTricode"], bot["teamTricode"])

    quarter = pl.read_csv(OUT / "quarter_2for1.csv").sort("period")
    q_rates = " / ".join(f"{r:.1%}" for r in quarter["rate"])
    ordering_holds = all(
        r["own_tfo"] > r["own_hold"] and r["net_tfo"] > r["net_hold"]
        for r in quarter.iter_rows(named=True))
    ordering = ("with the payoff ordering intact in each" if ordering_holds
                else "though the payoff ordering flips in at least one")

    pv = pl.read_csv(OUT / "proxy_vs_possession.csv").row(0, named=True)

    s = pl.read_csv(OUT / "seasons_summary.csv")
    listed = "; ".join(f"{r['league'].upper()} {r['season']} ({r['games']:,})"
                       for r in s.iter_rows(named=True))
    coverage = f"""
**Coverage:** every regular-season game of six league-seasons, {int(s['games'].sum()):,}
games in all: {listed}. Sections 1-5 of the findings are NBA 2023-24
({n_games:,} games); section 6 compares all six.
"""

    proxy = (f"it flags {pv['quick_correctly_flagged']:.0%} of\n"
             f"   true quick attempts, but only "
             f"{pv['hold_correctly_unflagged']:.0%} of true holds")

    extension = f"""
`python/06_team_quarter.py` (gated, wired into `run_checks.sh`) joins the
committed window table back to team identities and asks who hunts the
2-for-1 ({top_city} {top['rate']:.0%} to {bot_city} {bot['rate']:.0%}; league {league:.1%})
and whether the quarter matters (it barely does: {q_rates}
across Q1-Q3, {ordering}). Outputs:
`output/team_2for1.csv`, `output/quarter_2for1.csv`.
"""
    return {"coverage": coverage, "proxy": proxy, "extension": extension,
            "correction": correction_note()}


def regenerate(text: str) -> str:
    """The whole README with every owned region rebuilt from output/."""
    for name, body in build_regions().items():
        pattern = re.compile(
            rf"<!-- gen:{name} -->.*?<!-- /gen:{name} -->", re.S)
        if not pattern.search(text):
            raise SystemExit(f"README.md is missing the gen:{name} markers")
        text = pattern.sub(
            lambda _m: f"<!-- gen:{name} -->{body}<!-- /gen:{name} -->",
            text, count=1)
    head = text.split(MARKER)[0].rstrip()
    return head + "\n\n" + build()


def main(argv: list[str]) -> int:
    current = README.read_text()
    if "--check" in argv:
        plain = strip_abbr(current)
        if plain != regenerate(plain):
            print("Committed README analysis numbers differ from what "
                  "output/ supports. Fix: python python/03_findings.py, "
                  "then glossary.py --sync.")
            print("PLAYBYPLAY FINDINGS CHECK FAILED")
            return 1
        print("PLAYBYPLAY FINDINGS CHECK PASSED (coverage, proxy, "
              "extension, and Findings all regenerate from output/)")
        return 0
    README.write_text(regenerate(current))
    print(f"Updated generated regions + Findings in {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
