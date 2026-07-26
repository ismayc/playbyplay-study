# Play-by-play study — does the end-of-quarter 2-for-1 pay?

Study addressing `../requirements.md` requirement #5 (*play-by-play and event
data*) and #4 (*models that inform basketball decision-making*).

**The question.** With 30–40 seconds left in a quarter, a team with the ball can
shoot quickly — hoping to get one more possession before the buzzer, two shots for
the opponent's one — or hold for the last shot and deny the opponent any reply.
Coaches genuinely disagree. This measures both sides of the trade on a full season.

---

## 1. What play-by-play data is publicly available?

| Source | Content | Public? | Used |
|---|---|---|---|
| **`PlayByPlayV3`** (stats.nba.com) | Every logged event: period, game clock, action type, player, running score, **shot x/y + distance** | Yes, live | ✅ **primary** |
| `PlayByPlayV2` | Older schema, same events, no shot coordinates | Yes, live | ✗ |
| `ShotChartDetail` | ~102k shots/season with `LOC_X`/`LOC_Y`, zone labels, clock | Yes, live | ✗ (this study needs non-shot events too) |
| `LeagueGameFinder` | Game index by season | Yes, live | ✅ (game IDs) |
| ESPN PBP via `hoopR` (R) | Parallel feed, different event coding | Yes | ✗ |

All are reached through the [`nba_api`](https://github.com/swar/nba_api) Python
package, which is an unofficial but well-maintained wrapper over the same public
`stats.nba.com` endpoints the league's own site calls.

**Coverage:** the full 2023-24 regular season — **1,230 games**, ~500 events each.

Worth noting for the tracking question: `PlayByPlayV3` carries `xLegacy`/`yLegacy`
court coordinates on shot events. That is genuine spatial data, live and current —
unlike raw tracking, which is only available as a frozen 2015-16 archive (see
`../tracking-study`).

---

## 2. Pipeline

```
python/01_harvest_pbp.py   stats.nba.com -> data/raw_pbp/<game_id>.parquet  (resumable)
python/02_analysis.py      -> output/*.csv, figures/*.png + *.html
R/02_analysis.R            independent R/tidyverse implementation -> output/*_r.csv
python/04_reconcile.py     compares the two row-by-row, non-zero exit on mismatch
python/03_findings.py      -> writes the Findings section of this README
```

```bash
pip install nba_api polars plotly kaleido numpy pyarrow
Rscript -e 'install.packages(c("tidyverse","nanoparquet"))'
python python/01_harvest_pbp.py --season 2023-24   # ~20 min, rate-limited
python python/02_analysis.py
Rscript R/02_analysis.R
python python/04_reconcile.py   # exits non-zero if the two disagree
python python/03_findings.py
```

The reconciliation is not ceremonial. The Python implementation originally
sorted events by `actionNumber` **as text** — `"100"` before `"2"` — which
scrambled the score forward-fill and corrupted every window score. The bug was
caught in review by re-deriving the table with a numeric sort; the independent
R implementation now guards that class of error permanently, the same
discipline as `../jersey-height-study`.

One parquet per game, so an interrupted harvest resumes and the analysis never
re-hits the network.

---

## 3. Method and every judgment call

| Decision | Value | Why |
|---|---|---|
| Periods | **1–3 only** | Q4 is contaminated by score-margin strategy, intentional fouling, and clock-stopping that have nothing to do with 2-for-1 |
| Window | **final 60 seconds** | Wide enough to contain the whole decision, narrow enough that the rest of the quarter does not dilute it |
| Treatment | **first FGA at ≥ 32s** | Conventional threshold: enough for a 24-second opponent possession plus a final possession of your own |
| Outcome | **score delta**, not summed shot values | Free throws in this feed carry an *empty* `shotResult`, so summing shot values would silently drop every and-1 and shooting foul. Score deltas capture all scoring |
| Second outcome | **net points** (own minus opponent, same window) | Holding for the last shot is valuable *because it denies the opponent a reply* — an own-points outcome misses the entire cost side of the trade. Both outcomes are reported |
| Score handling | forward-fill across the game | Scores are only stamped on scoring events; the fill runs across the whole game, not within period, because periods start from the running total |
| Uncertainty | **bootstrap**, not a t-test | Points in a 60-second window are a small, lumpy, non-normal count (0, 2, 3, 5…) |
| Unit of analysis | team-period | One row per team per period, not per game |

### The confound this design cannot remove

**A team can only run a 2-for-1 if it happens to have the ball early in the window.**
Which teams have the ball at 40 seconds is not random — they likely just got a stop,
and may be attacking an unset defense.

This is stated up front rather than buried, a restricted-sample sensitivity analysis
is reported alongside the headline, and the write-up does not claim a causal effect.

---

## 4. Limitations

1. **Observational, not causal.** See above. The treatment is chosen by teams, not
   assigned.
2. **Possession is inferred from shots, not tracked** — in the original design.
   Now addressed: Finding 4 redoes the analysis on real possession rows and
   quantifies exactly how often this proxy misread the choice (it flags 82% of
   true quick attempts, but only half of true holds).
3. **One season.** 2023-24 only. No test of whether the pattern holds across eras or
   rule changes.
4. **No score-margin control.** A team down 20 behaves differently from a tied team.
   Not conditioned on.
5. **eFG% ignores free throws.** The shot-quality comparison uses field goals only,
   so it understates the value of drawing a shooting foul on a drive.
6. **Team quality is not controlled.** Good offenses both score more and are more
   likely to have the ball, which inflates the raw gap.

---

## Findings

Based on **1,230 games** of 2023-24 play-by-play. Every number is generated by
`python/03_findings.py` from `output/`, not typed by hand.

### 1. Teams really do hunt the 2-for-1

Of the 7,221 team-periods with a shot in the
final 60 seconds of Q1–Q3, **78%** took their first shot with 32 or more
seconds left.

The share alone is weak evidence — later in the window there is simply more
opportunity to shoot. The strong evidence is a **local spike exactly at the
threshold**:

| First shot at | Mean team-periods per second |
|---|---|
| 22–30s (the wait) | 68 |
| **31–33s (the threshold)** | **201** |
| 36–40s (later, more opportunity) | 147 |

Teams bunch at 31–33 seconds **1.37× more** than at 36–40 seconds,
even though the later band has more chances to shoot and should be higher if nothing
special happened at 32. That discontinuity is the behaviour itself, visible in the
raw counts rather than assumed: coaches are running this play deliberately.
See `figures/fig1_first_shot_timing.png`.

### 2. The 2-for-1 is associated with more points — on both sides of the ball

| | First shot ≥ 32s (2-for-1) | First shot < 32s (held) |
|---|---|---|
| Team-periods | 5,614 | 1,607 |
| Mean points in window | **2.347** | **1.767** |
| Mean opponent points | **2.183** | **2.283** |
| Mean **net** points | **+0.163** | **-0.516** |
| Mean field-goal attempts | **2.47** | **1.52** |
| Effective FG% | **0.506** | **0.436** |

Own-points difference: **+0.579** per team-period
(95% bootstrap CI [+0.475, +0.679], excludes zero,
4,000 resamples).

**Why net matters:** the case for holding the ball is precisely that it denies
the opponent a reply, so an outcome that only counts a team's own points misses
half the trade. On net points the raw gap is **+0.679**
(95% CI [+0.544, +0.816]) — but read the
sensitivity analysis below before taking either raw gap at face value, because
the "held" group includes many team-periods where the *opponent* controlled the
window.

The mechanism is visible in the FGA row: roughly
**+0.94 extra shots** per window. That is the extra
possession, showing up exactly where it should.

### Sensitivity: narrowing the selection gap

Restricting to team-periods whose first shot came between 20 and 45 seconds — so both groups had the ball at broadly similar times — the own-points gap is **+0.364** (95% CI [+0.216, +0.512], excludes zero) and the net gap is **+0.188** (95% CI [-0.002, +0.375], includes zero; n = 2,199 vs 842).

Both gaps shrink under the restriction, which is what you would expect if part of the headline gap is selection rather than strategy. The own-points advantage survives; the net advantage narrows to the edge of what one season of data can distinguish from zero. That asymmetry is itself informative: the extra possession is real, but the opponent's reply claws back much of its value.

### 3. The expected cost never appears

The standard objection to the 2-for-1 is that you rush a bad shot to create the
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

Shots taken with 32+ seconds left average **eFG% 0.551** — ordinary,
in-rhythm shots. The genuinely bad shot is the buzzer-beater: **eFG% 0.347**
in the last four seconds.

That reframes the decision. The 2-for-1 does not trade a good shot for a bad one. It
**adds** a normal-quality possession, because the desperation heave at the buzzer
gets taken either way. The team that holds gives up the extra possession and still
takes the bad shot.

### 4. Possession-level upgrade: the decision-team design

The proxy limitation is closed with real possessions (pbpstats rows with
start/end times via the bulk archive in `../docs/public-data-availability.md`;
1,228 of 1,230 games — `python/05_possession_analysis.py` also documents why a
literal translation of the old design just relocates the blindness). The
sharper frame: **at the 40-second mark of every Q1–Q3, exactly one team has
the ball — the team actually facing the 2-for-1 decision.** 3,683 decision
possessions, split by the observed choice:

| Choice | n | Share | Net pts from 40s | Later possessions | ended in TO |
|---|---|---|---|---|---|
| **Quick** (released ≥28s left) | 3,112 | **84.5%** | **+0.48** | 1.09 | 11.8% |
| Normal (16–27s) | 547 | 14.9% | +0.01 | 0.71 | 9.1% |
| **Hold** (carried past 15s) | 24 | **0.7%** | -0.21 | 0.21 | 8.3% |

Three things fall out:

1. **The debate is over in practice.** Teams with the ball at the decision
   moment go quick 84% of the time; genuine holds are nearly
   extinct — 24 team-periods in a full season. The argument this study
   set out to test has largely been settled by the league's behaviour.
2. **The mechanism is now measured directly**: quick teams average
   1.09 further possessions after the mark vs
   0.21 for holds — the extra possession counted,
   not inferred from shots.
3. Quick minus hold on net points from the mark:
   **+0.69 [+0.23, +1.20]** —
   consistent with the tactic paying, but with 24 holds the
   comparison is honest about being underpowered. When a strategy wins the
   behavioural argument this thoroughly, its control group disappears.

The first-shot proxy, scored against observed choices: it flags
82% of true quicks but correctly identifies
only 50% of true holds — quantifying exactly
how much limitation 2 mattered.

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
