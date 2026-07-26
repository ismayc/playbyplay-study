# One finding, three audiences — the end-of-quarter 2-for-1

Same analysis, three registers. Numbers from `output/` (README Findings holds
the generated originals).

---

## For the coaching staff (one minute, decision-first)

**Should we hunt the 2-for-1?** The data says the case for it is real but
smaller than the box score makes it look.

- Teams already hunt it deliberately — first shots pile up right at the
  31–33 second mark, exactly where the play calls for it.
- Teams that get a shot up with 32+ seconds left score more in the final
  minute — about **+0.6 points** — and the extra shot shows up right where it
  should (+0.9 attempts).
- **The feared cost isn't there.** The early shot is a normal-quality shot
  (~52% eFG). The genuinely bad shot is the buzzer-beater everyone takes
  anyway (35%). You don't trade a good shot for a bad one; you add a normal
  possession.
- **The honest catch:** shooting early gives the opponent the ball back with
  time to answer. Counting both ends, on the fairest comparison we can make,
  the net edge is about **+0.2 points per quarter-end and we can't rule out
  zero** with one season of data. Run it when the possession comes naturally;
  it's not worth forcing.

## For analytics peers

Full 2023-24 pbp (1,230 games, `PlayByPlayV3`). Unit: team-period, final 60s
of Q1–Q3 (Q4 excluded: strategy contamination). Treatment: first FGA ≥ 32s.
Outcomes: own points *and* net points via score deltas (FT-safe). Bootstrap
CIs (4,000 reps). Selection is the elephant: possession timing is not random,
so we report a restricted 20–45s comparison — own-points gap survives
(+0.36 [+0.22, +0.51]), net gap does not (+0.19 [−0.00, +0.38]). Mechanism
checks (eFG by clock, FGA counts) carry the causal-ish story; no causal claim
is made. Implemented in Python and R with a row-level reconciliation gate —
which matters here, because the original single-implementation version had a
text-vs-numeric sort bug that corrupted every window score and shifted the
headline gap from +0.36 to +0.58. Possession-level data (pbpstats) is the
documented upgrade path.

## For the executive summary (three bullets)

- The 2-for-1 adds a real extra possession at no shot-quality cost; the
  opponent's reply claws back much of the value — net edge ~+0.2 points,
  not statistically distinguishable from zero in one season.
- Coaches already run this play on schedule; the data shows the behaviour,
  the payoff, and the honest uncertainty.
- The finding survived a two-language verification gate that caught a
  data-ordering bug which had silently corrupted every score in v1.
