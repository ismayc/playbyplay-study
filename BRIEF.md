# One finding, three audiences: the end-of-quarter 2-for-1

Same analysis, three registers. Numbers from `output/` (README Findings holds
the generated originals). Corrected October 19, 2026: see the correction note
at the top of the README.

---

## For the coaching staff (one minute, decision-first)

**Should we hunt the 2-for-1?** Yes. The case for it is real, it holds up
across three NBA seasons, and the feared cost isn't there.

- Teams already hunt it deliberately: first shots pile up right at the
  31–33 second mark, exactly where the play calls for it.
- Teams that get a shot up with 32+ seconds left score more in the final
  minute (about **+0.8 points**), and the extra shot shows up right where it
  should (+0.9 attempts).
- **The feared cost isn't there.** The early shot is a normal-quality shot
  (~55% eFG). The genuinely bad shot is the buzzer-beater everyone takes
  anyway (35%). You don't trade a good shot for a bad one; you add a normal
  possession.
- **Counting both ends:** shooting early gives the opponent the ball back
  with time to answer, which claws back part of the gain. On the fairest
  comparison we can make, the net edge is about **+0.2 points per
  quarter-end**, and over three seasons it is clearly above zero
  (+0.23 [+0.10, +0.35]).
- **From real possession data:** the team that has the ball at the 40-second
  mark goes quick **84% of the time**; holding for the last shot is rare
  (24 times in 2023-24) but not disappearing (50 and 48 in the next two
  seasons). The quick group really does get the extra possession (1.1 vs 0.2
  later possessions).
- **WNBA:** the same play pays there too on possession data
  (+0.71 [+0.25, +1.18] net points pooled over 2024-2026), but WNBA teams go
  quick less often (76% to 78%) and don't time their first shot to the
  32-second mark the way NBA teams do.

## For analytics peers

Full regular-season pbp for NBA 2023-24 (1,230 games, `PlayByPlayV3`), then
NBA 2024-25 and 2025-26 and WNBA 2024-2026 under the same definitions. Unit:
team-period, final 60s of Q1–Q3 (Q4 excluded: strategy contamination).
Treatment: first FGA ≥ 32s. Outcomes: own points *and* net points via score
deltas (FT-safe), with events in game-clock order. Bootstrap CIs (4,000 reps).
Selection is the elephant: possession timing is not random, so we report a
restricted 20–45s comparison. In 2023-24 both gaps survive it, own points
+0.50 [+0.36, +0.64] and net +0.24 [+0.03, +0.44]; pooled over three NBA
seasons the restricted net gap is +0.23 [+0.10, +0.35]. A possession-level
rebuild (pbpstats rows, built for every season and checked against the bulk
archive) conditions on the team holding the ball at the 40s mark and splits
by observed choice: quick 84.5% / normal 14.9% / hold 0.7% in 2023-24; quick
minus hold net from the mark +0.92 [+0.35, +1.51], underpowered because holds
are rare; the first-shot proxy flags 82% of true quicks but only half of true
holds. In the WNBA the two designs disagree: the possession design pools to
+0.71 [+0.25, +1.18], the restricted shot-timing comparison to
−0.13 [−0.36, +0.11]. Implemented in Python and R with a row-level
reconciliation gate, plus a check of every season's window points against
the NBA's liveData feed. That feed check is what caught the second ordering
bug: both implementations sorted events by action number, which let
late-inserted events zero 15% of the 2023-24 windows. A two-implementation
gate cannot see an error both implementations share.

## For the executive summary (three bullets)

- The 2-for-1 adds a real extra possession at no shot-quality cost; the
  opponent's reply claws back part of the value, and the net edge
  (~+0.2 points per quarter-end) holds up over three NBA seasons.
- Coaches already run this play on schedule; the WNBA runs it less often and
  less precisely, and it pays there too.
- The published numbers were corrected on October 19, 2026, after an
  independent data feed exposed an event-ordering bug that understated the
  2-for-1's value.
