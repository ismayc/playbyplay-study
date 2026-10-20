# Play-by-play study: does the end-of-quarter 2-for-1 pay?

A full-season play-by-play study in the [basketball-data-science](https://github.com/ismayc/basketball-data-science)
family: event data turned into a basketball decision.

**The question.** With 30–40 seconds left in a quarter, a team with the ball can
shoot quickly (hoping to get one more possession before the buzzer, two shots for
the opponent's one) or hold for the last shot and deny the opponent any reply.
Coaches genuinely disagree. This measures both sides of the trade on a full season,
then repeats it on two more NBA seasons and three WNBA seasons.
<!-- gen:correction -->
> **Correction, October 19, 2026.** The 2023-24 window points were computed
> with events in action-number order. The feed inserts late events with a high
> action number but an early clock, and those carried the period-end score back
> to the start of the window, so 1,089 of 7,221 team-periods
> (15%) had wrong window points. An independent feed (the
> NBA's liveData play-by-play) exposed it; events are now in game-clock order,
> and every season is checked against that feed. Every estimate moved in the <abbr title="Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.">2-for-1</abbr>'s favor.
> Published → corrected (95% <abbr title="Confidence interval.">CI</abbr>):
>
> - Own-points gap: +0.579 [+0.476, +0.680] → **+0.778 [+0.680, +0.876]**
> - Net-points gap: +0.679 [+0.541, +0.818] → **+0.828 [+0.672, +0.980]**
> - Restricted net gap: +0.188 [-0.002, +0.378] → **+0.235 [+0.029, +0.441]**
> - Quick minus hold (decision team): +0.69 [+0.23, +1.20] → **+0.92 [+0.35, +1.51]**
>
> The restricted net gap's interval now excludes zero, which reverses the earlier conclusion that one season could not distinguish it from zero. The
> same change sorts each table before bootstrapping, since the published
> intervals came from a row order that changed between runs.
>
> A second pass the same day fixed how scores are read from the feed: only
> made shots and free throws set the score, each only for the scoring team,
> and the score never falls (Instant Replay rows carried stale scores, and
> free throws at one clock reading could arrive out of order). It changed
> 28 of 26,523 team-periods across all six league-seasons
> (0.11%); the figures above include it. Full table:
> `output/correction_2026-10-19.csv`.
<!-- /gen:correction -->

---

<!-- terms -->
> **Terms used in this analysis.** Dotted-underlined terms anywhere below repeat these definitions on hover ([full glossary](https://github.com/ismayc/basketball-data-science/blob/main/docs/glossary.md)).
>
> - **FGA**: Field-goal attempts.
> - **eFG%**: Effective field-goal percentage: field-goal percentage with made threes counted 1.5x, putting twos and threes on one points scale.
> - **2-for-1**: Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.
> - **CI**: Confidence interval.
<!-- /terms -->

## 1. What play-by-play data is publicly available?

| Source | Content | Public? | Used |
|---|---|---|---|
| **`PlayByPlayV3`** (stats.nba.com) | Every logged event: period, game clock, action type, player, running score, **shot x/y + distance** | Yes, live | ✅ **primary** |
| `PlayByPlayV2` | Older schema, same events, no shot coordinates | Yes, live | ✗ |
| `ShotChartDetail` | ~102k shots/season with `LOC_X`/`LOC_Y`, zone labels, clock | Yes, live | ✗ (this study needs non-shot events too) |
| `LeagueGameFinder` | Game index by season | Yes, live | ✅ (game IDs) |
| `nbastatsv3_*` archives ([shufinskiy/nba_data](https://github.com/shufinskiy/nba_data)) | The same `PlayByPlayV3` rows, one file per league-season | Yes | ✅ games the API timed out on, checked against the harvest |
| `pbpstats_*` archives (same repository) | Possession rows with start/end times | Yes | ✅ check on the possession layer |
| NBA liveData play-by-play (via [`pbpstats`](https://github.com/dblackrun/pbpstats)) | A separate feed of the same games, running score on every action | Yes, live | ✅ possessions for every season; independent check on window points |
| ESPN PBP via `hoopR` (R) | Parallel feed, different event coding | Yes | ✗ |

All are reached through the [`nba_api`](https://github.com/swar/nba_api) Python
package, which is an unofficial but well-maintained wrapper over the same public
`stats.nba.com` endpoints the league's own site calls.

<!-- gen:coverage -->
**Coverage:** every regular-season game of six league-seasons, 4,546
games in all: NBA 2023-24 (1,230); NBA 2024-25 (1,230); NBA 2025-26 (1,230); WNBA 2024 (240); WNBA 2025 (286); WNBA 2026 (330). Sections 1-5 of the findings are NBA 2023-24
(1,230 games); section 6 compares all six.
<!-- /gen:coverage -->

Worth noting for the tracking question: `PlayByPlayV3` carries `xLegacy`/`yLegacy`
court coordinates on shot events. That is genuine spatial data, live and current,
unlike raw tracking, which is only available as a frozen 2015-16 archive (see
[tracking-study](https://github.com/ismayc/tracking-study)).

---

## 2. Pipeline

```
python/seasons.py                 the six league-seasons and where each one's files live
python/01_harvest_pbp.py          stats.nba.com -> data/raw_pbp/<game_id>.parquet  (resumable)
python/01b_import_v3_archive.py   V3 archive -> data/raw_pbp/ for games the API timed out on
python/02_analysis.py             -> output/ (NBA 2023-24) or output/seasons/<tag>/
R/02_analysis.R                   independent R/tidyverse implementation -> *_r.csv
python/04_reconcile.py            compares the two row-by-row (--all, --pooled)
python/07_build_possessions.py    pbpstats possessions -> data/possessions/<tag>.parquet
python/05_possession_analysis.py  decision-team design (--source archive | built)
python/06_team_quarter.py         teams and quarters
python/08_reconcile_possessions.py  built possessions vs the archive
python/10_check_sources.py        window points vs the NBA liveData feed, every season
python/09_seasons.py, R/09_pooled.R  cross-season table and pooled estimates
python/11_correction.py           2026-10-19 correction: published vs corrected
python/03_findings.py             -> writes the Findings section of this README
```

```bash
pip install -r requirements.txt
Rscript -e 'install.packages(c("tidyverse","nanoparquet"))'
python python/01_harvest_pbp.py --season 2023-24          # ~20 min, rate-limited
python python/01_harvest_pbp.py --league wnba --season 2025
python python/02_analysis.py [--league wnba --season 2025]
Rscript R/02_analysis.R [wnba 2025]
python python/04_reconcile.py --all   # exits non-zero if the two disagree
python python/03_findings.py
```

The reconciliation is not ceremonial. The Python implementation originally
sorted events by `actionNumber` **as text** (`"100"` before `"2"`), which
scrambled the score forward-fill and corrupted every window score. The bug was
caught in review by re-deriving the table with a numeric sort; the independent
R implementation now guards that class of error permanently, the same
discipline as [jersey-height-study](https://github.com/ismayc/jersey-height-study).

A second-implementation check cannot catch an error both implementations
share, though. Both ordered events by `actionNumber`, and both were wrong in
the same way (see the correction at the top). An independent *feed*, the NBA's
liveData play-by-play, found it; `python/10_check_sources.py` now runs that
comparison on every season.

One parquet per game, so an interrupted harvest resumes and the analysis never
re-hits the network.

---

## 3. Method and every judgment call

| Decision | Value | Why |
|---|---|---|
| Periods | **1–3 only** | Q4 is contaminated by score-margin strategy, intentional fouling, and clock-stopping that have nothing to do with <abbr title="Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.">2-for-1</abbr> |
| Window | **final 60 seconds** | Wide enough to contain the whole decision, narrow enough that the rest of the quarter does not dilute it |
| Treatment | **first <abbr title="Field-goal attempts.">FGA</abbr> at ≥ 32s** | Conventional threshold: enough for a 24-second opponent possession plus a final possession of your own |
| Outcome | **score delta**, not summed shot values | Free throws in this feed carry an *empty* `shotResult`, so summing shot values would silently drop every and-1 and shooting foul. Score deltas capture all scoring |
| Second outcome | **net points** (own minus opponent, same window) | Holding for the last shot is valuable *because it denies the opponent a reply*: an own-points outcome misses the entire cost side of the trade. Both outcomes are reported |
| Score handling | forward-fill across the game, **in game-clock order** | Scores are only stamped on scoring events; the fill runs across the whole game, not within period, because periods start from the running total. Events are ordered by the clock (action number only breaks ties), because the feed inserts late events with a high action number but an early clock |
| Uncertainty | **bootstrap**, not a t-test | Points in a 60-second window are a small, lumpy, non-normal count (0, 2, 3, 5…) |
| Unit of analysis | team-period | One row per team per period, not per game |

### The confound this design cannot remove

**A team can only run a <abbr title="Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.">2-for-1</abbr> if it happens to have the ball early in the window.**
Which teams have the ball at 40 seconds is not random. They likely just got a stop,
and may be attacking an unset defense.

This is stated up front rather than buried, a restricted-sample sensitivity analysis
is reported alongside the headline, and the write-up does not claim a causal effect.

---

## 4. Limitations

1. **Observational, not causal.** See above. The treatment is chosen by teams, not
   assigned.
2. **Possession is inferred from shots, not tracked**, in the original design.
   Now addressed: Finding 4 redoes the analysis on real possession rows and
   quantifies exactly how often this proxy misread the choice (<!-- gen:proxy -->it flags 82% of
   true quick attempts, but only 50% of true holds<!-- /gen:proxy -->).
3. **Recent seasons only.** Three NBA seasons (2023-24 to 2025-26) and three
   WNBA seasons (2024 to 2026). No test across older eras or rule changes, and
   the WNBA's hold group stays small even pooled.
4. **No score-margin control.** A team down 20 behaves differently from a tied team.
   Not conditioned on.
5. **<abbr title="Effective field-goal percentage: field-goal percentage with made threes counted 1.5x, putting twos and threes on one points scale.">eFG%</abbr> ignores free throws.** The shot-quality comparison uses field goals only,
   so it understates the value of drawing a shooting foul on a drive.
6. **Team quality is not controlled.** Good offenses both score more and are more
   likely to have the ball, which inflates the raw gap.

---

## Extension: teams and quarters

<!-- gen:extension -->
`python/06_team_quarter.py` (gated, wired into `run_checks.sh`) joins the
committed window table back to team identities and asks who hunts the
<abbr title="Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.">2-for-1</abbr> (Sacramento 85% to Chicago 73%; league 77.7%)
and whether the quarter matters (it barely does: 78.4% / 78.0% / 76.8%
across Q1-Q3, with the payoff ordering intact in each). Outputs:
`output/team_2for1.csv`, `output/quarter_2for1.csv`.
<!-- /gen:extension -->

## Findings

Based on **1,230 games** of 2023-24 play-by-play (sections 1-5; section 6
adds two more NBA seasons and three WNBA seasons). Every number is generated by
`python/03_findings.py` from `output/`, not typed by hand.

### 1. Teams really do hunt the 2-for-1

Of the 7,221 team-periods with a shot in the
final 60 seconds of Q1–Q3, **78%** took their first shot with 32 or more
seconds left.

The share alone is weak evidence. Later in the window there is simply more
opportunity to shoot. The strong evidence is a **local spike exactly at the
threshold**:

| First shot at | Mean team-periods per second |
|---|---|
| 22–30s (the wait) | 68 |
| **31–33s (the threshold)** | **201** |
| 36–40s (later, more opportunity) | 147 |

Teams bunch at 31–33 seconds **1.37× more** than at 36–40 seconds,
even though the later band has more chances to shoot and should be higher if nothing
special happened at 32. That discontinuity is the behavior itself, visible in the
raw counts rather than assumed: coaches are running this play deliberately.
See `figures/fig1_first_shot_timing.png`.

### 2. The 2-for-1 is associated with more points, on both sides of the ball

| | First shot ≥ 32s (<abbr title="Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.">2-for-1</abbr>) | First shot < 32s (held) |
|---|---|---|
| Team-periods | 5,614 | 1,607 |
| Mean points in window | **2.886** | **2.108** |
| Mean opponent points | **2.682** | **2.732** |
| Mean **net** points | **+0.204** | **-0.624** |
| Mean field-goal attempts | **2.47** | **1.52** |
| Effective FG% | **0.506** | **0.436** |

Own-points difference: **+0.778** per team-period
(95% bootstrap <abbr title="Confidence interval.">CI</abbr> [+0.680, +0.876], excludes zero,
4,000 resamples).

**Why net matters:** the case for holding the ball is precisely that it denies
the opponent a reply, so an outcome that only counts a team's own points misses
half the trade. On net points the raw gap is **+0.828**
(95% <abbr title="Confidence interval.">CI</abbr> [+0.672, +0.980]). But read the
sensitivity analysis below before taking either raw gap at face value, because
the "held" group includes many team-periods where the *opponent* controlled the
window.

The mechanism is visible in the <abbr title="Field-goal attempts.">FGA</abbr> row: roughly
**+0.94 extra shots** per window. That is the extra
possession, showing up exactly where it should.

### Sensitivity: narrowing the selection gap

Restricting to team-periods whose first shot came between 20 and 45 seconds (so both groups had the ball at broadly similar times), the own-points gap is **+0.495** (95% <abbr title="Confidence interval.">CI</abbr> [+0.359, +0.636], excludes zero) and the net gap is **+0.235** (95% <abbr title="Confidence interval.">CI</abbr> [+0.029, +0.441], excludes zero; n = 2,199 vs 842).

Both gaps shrink under the restriction, which is what you would expect if part of the headline gap is selection rather than strategy. The own-points advantage survives, and so does the net advantage, though at 48% of the own-points size: the extra possession is real, and the opponent's reply claws back part of its value.

### 3. The expected cost never appears

The standard objection to the <abbr title="Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.">2-for-1</abbr> is that you rush a bad shot to create the
extra possession. **In this data that cost does not show up.**

| Seconds left | Effective FG% | Attempts |
|---|---|---|
| 0–3s | 0.347 | 3,818 |
| 4–7s | 0.495 | 953 |
| 8–11s | 0.522 | 689 |
| 12–15s | 0.535 | 570 |
| 16–19s | 0.542 | 492 |
| 20–23s | 0.556 | 506 |
| 24–27s | 0.539 | 747 |
| 28–31s | 0.520 | 1,331 |
| 32–35s | 0.520 | 1,394 |
| 36–39s | 0.571 | 943 |
| 40–43s | 0.532 | 850 |
| 44–47s | 0.542 | 947 |
| 48–51s | 0.569 | 920 |
| 52–55s | 0.559 | 904 |
| 56–59s | 0.562 | 931 |

Shots taken with 32+ seconds left average **<abbr title="Effective field-goal percentage: field-goal percentage with made threes counted 1.5x, putting twos and threes on one points scale.">eFG%</abbr> 0.551**: ordinary,
in-rhythm shots. The genuinely bad shot is the buzzer-beater: **<abbr title="Effective field-goal percentage: field-goal percentage with made threes counted 1.5x, putting twos and threes on one points scale.">eFG%</abbr> 0.347**
in the last four seconds.

That reframes the decision. The <abbr title="Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.">2-for-1</abbr> does not trade a good shot for a bad one. It
**adds** a normal-quality possession, because the desperation heave at the buzzer
gets taken either way. The team that holds gives up the extra possession and still
takes the bad shot.

### 4. Possession-level upgrade: the decision-team design

The proxy limitation is closed with real possessions (pbpstats rows with
start/end times via the bulk archive in `../docs/public-data-availability.md`;
1,228 of 1,230 games;
`python/05_possession_analysis.py` also documents why a
literal translation of the old design just relocates the blindness). The
sharper frame: **at the 40-second mark of every Q1–Q3, exactly one team has
the ball, the team actually facing the <abbr title="Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.">2-for-1</abbr> decision.** 3,683 decision
possessions, split by the observed choice:

| Choice | n | Share | Net pts from 40s | Later possessions | ended in TO |
|---|---|---|---|---|---|
| **Quick** (released ≥28s left) | 3,112 | **84.5%** | **+0.58** | 1.06 | 11.8% |
| Normal (16–27s) | 547 | 14.9% | -0.03 | 0.65 | 9.1% |
| **Hold** (carried past 15s) | 24 | **0.7%** | -0.33 | 0.17 | 8.3% |

Three things fall out:

1. **The debate is over in practice.** Teams with the ball at the decision
   moment go quick 84% of the time; genuine holds are nearly
   extinct: 24 team-periods in a full season. The argument this study
   set out to test has largely been settled by the league's behavior.
2. **The mechanism is now measured directly**: quick teams average
   1.06 further possessions after the mark vs
   0.17 for holds (the extra possession counted,
   not inferred from shots; a possession counts if it produced a shot, a
   free-throw trip, or a turnover).
3. Quick minus hold on net points from the mark:
   **+0.92 [+0.35, +1.51]**,
   consistent with the tactic paying, but with 24 holds the
   comparison is honest about being underpowered. When a strategy wins the
   behavioral argument this thoroughly, its control group disappears.

The first-shot proxy, scored against observed choices: it flags
82% of true quicks but correctly identifies
only 50% of true holds, quantifying exactly
how much limitation 2 mattered.

### 5. What this does not establish

The treatment is not randomly assigned, and the biggest confound is possession
timing: a team that does not get the ball until 20 seconds remain *cannot* run a
<abbr title="Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.">2-for-1</abbr>, and is not comparable to one that had it at 40 seconds. Some of the gap is
therefore selection: teams with the ball earlier were more likely to have just
gotten a stop, and may be in transition against an unset defense.

The sensitivity analysis narrows that gap but does not close it. The honest
statement is: **teams that shoot early score more in the window, the extra
possession is real and measurable, and the usual objection to the strategy (a
rushed, bad shot) is not visible in the data. What limits the payoff is not
shot quality but the opponent's reply: on a net basis, in the comparable sample, the advantage is smaller but its interval excludes zero, and pooling three NBA seasons (section 6) confirms it.** Section 4's decision-team
design removes the "never had the ball" confound but not the choice itself,
which is still made by teams, not assigned.

### 6. Three seasons, two leagues

The study now covers NBA 2023-24 to 2025-26 and
WNBA 2024 to 2026,
every regular-season game, with the same definitions. The WNBA plays 10-minute
quarters but the same 24-second shot clock, so the 60-second window and
32-second threshold carry over unchanged. Possessions for every season come
from the pbpstats library (`python/07_build_possessions.py`), checked against
the bulk archive on the seasons it covers (`python/08_reconcile_possessions.py`:
the quick/normal/hold call agrees on at least 100.0% of decision periods).

| League-season | Games | First shot ≥ 32s | 31-33s spike | Quick share | Holds | Restricted net gap [95% <abbr title="Confidence interval.">CI</abbr>] | Quick minus hold, net [95% <abbr title="Confidence interval.">CI</abbr>] |
|---|---|---|---|---|---|---|---|
| NBA 2023-24 | 1,230 | 77.7% | 1.37 | 84.5% | 24 | +0.24 [+0.03, +0.44] | +0.92 [+0.37, +1.54] |
| NBA 2024-25 | 1,230 | 78.5% | 1.27 | 82.4% | 50 | +0.13 [-0.08, +0.33] | +0.77 [+0.32, +1.23] |
| NBA 2025-26 | 1,230 | 78.0% | 1.19 | 83.0% | 48 | +0.30 [+0.09, +0.52] | +0.42 [-0.12, +0.96] |
| WNBA 2024 | 240 | 74.8% | 0.79 | 76.4% | 16 | +0.47 [+0.01, +0.92] | +1.25 [+0.51, +2.00] |
| WNBA 2025 | 286 | 72.0% | 0.65 | 78.3% | 16 | -0.32 [-0.70, +0.07] | +0.62 [-0.36, +1.54] |
| WNBA 2026 | 330 | 73.8% | 0.86 | 76.4% | 19 | -0.36 [-0.73, +0.04] | +0.32 [-0.35, +1.00] |

Pooled within each league (bootstrap 95% CIs; the R implementation reproduces
the window estimates, `python/04_reconcile.py --pooled`):

| Seasons | Own-points gap | Net gap | Restricted net gap | Quick minus hold, net |
|---|---|---|---|---|
| NBA 2023-24 to 2025-26 | +0.75 [+0.70, +0.81] | +0.81 [+0.72, +0.90] | +0.22 [+0.10, +0.34] | +0.65 [+0.33, +0.95] |
| WNBA 2024 to 2026 | +0.54 [+0.43, +0.65] | +0.56 [+0.40, +0.72] | -0.13 [-0.36, +0.11] | +0.71 [+0.25, +1.18] |

1. **NBA.** **The quick rate is not still rising** (82.4% to 84.5% across the three seasons), and **holds are not going extinct**: 24, 50, 48 in 2023-24, 2024-25 and 2025-26. The bunching at the 32-second threshold is fading: the 31-33s spike fell from 1.37× to 1.19× the 36-40s rate.
2. **NBA, the open question from one season.** Pooled over three seasons, the restricted-sample net gap is **+0.223 [+0.100, +0.344]**, which excludes zero: the question one season left open is settled in the <abbr title="Shooting early with 25-36 seconds left in a period so your team gets two possessions to the opponent's one before the buzzer.">2-for-1</abbr>'s favor. Quick minus hold
   on the decision-team design pools to
   **+0.65 [+0.33, +0.95]** net points over
   122 holds.
3. **WNBA.** Teams go quick less often than in the NBA
   (76.4% to 78.3%) and do not
   bunch at the threshold at all (the 31-33s spike never exceeds
   0.86× the 36-40s rate). Holds are
   more common
   (2.0% of decisions vs 1.1% in the NBA) but still
   rare (16, 16, 19 a season), so the WNBA does not supply the large hold group
   the replication hoped for.
4. **The two designs disagree in the WNBA.** The decision-team comparison says going quick pays (+0.71 [+0.25, +1.18] net points, n = 51 holds pooled), but the shot-timing comparison restricted to first shots at 20-45s finds -0.13 [-0.36, +0.11]. The decision-team design is the more direct of the two (it conditions on who had the ball at the mark), so it carries the conclusion, with the disagreement stated.

**Data sources for the added seasons.** stats.nba.com began timing out
partway through the NBA 2024-25 harvest, so 2,327 games came from
the V3 archive instead (`python/01b_import_v3_archive.py`; on the
601 games both sources had, all 3,508 team-periods matched in the window table). Every
season's window points were then checked against an independent feed, the
NBA's liveData play-by-play: they agree on 99.93% to 100.00% of
team-periods (`python/10_check_sources.py`).
