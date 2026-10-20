# The 2-for-1 is real, coaches actually do it, and it pays

With thirty-some seconds left in a quarter, a team with the ball faces a
genuine strategic fork: shoot quickly and buy an extra possession before
the buzzer, or hold for the last shot and deny the opponent any reply.
Coaches disagree about this in public. A full season of play-by-play
(all 1,230 games of 2023-24) lets us ask two separable questions: do teams
actually play the 2-for-1, and does it pay? Two more NBA seasons and three
WNBA seasons then test whether the answer holds.

<div class="tiles">
<div class="tile"><div class="label">First shot at 32+ seconds</div>
<div class="value">78%</div>
<div class="sub">Of 7,221 final-minute team-periods in quarters one through three, 2023-24.</div></div>
<div class="tile"><div class="label">Launch-rate spike at 31&ndash;33s</div>
<div class="value">1.37&times;</div>
<div class="sub">201 team-periods per second, versus 147 in the 36&ndash;40 second band.</div></div>
<div class="tile"><div class="label">Own-points edge</div>
<div class="value">+0.78</div>
<div class="sub">Points per team-period over holding; on net points, in the fairest comparison, about +0.2.</div></div>
<div class="tile"><div class="label">Corrected October 19, 2026</div>
<div class="value">15%</div>
<div class="sub">Of 2023-24 windows had wrong points until an independent feed caught an ordering bug.</div></div>
</div>

<div class="eyebrow beat">The fingerprint</div>

## A spike at 31 seconds is a decision, not basketball

The first question has a sharp answer, and it comes from a discontinuity
rather than an average. Of the 7,221 team-periods with a shot in the final
minute of quarters one through three, 78% took their first shot with 32 or
more seconds left. But that share alone is weak evidence, because later in
the window there is simply more time in which to shoot. The strong evidence
is *where* the shots bunch: teams launch at 31–33 seconds at 201
team-periods per second, versus 147 in the 36–40 second band. That is
1.37× the rate, in the band with *fewer* natural shooting opportunities.
Nothing in the flow of a basketball game produces a spike exactly there
except a decision rule.

{{fig:fig1_first_shot_timing|When the first shot of the final minute goes up. This figure is the behavioral fingerprint: the spike at 31–33 seconds is the 2-for-1 threshold made visible, and no smooth basketball process puts it there. The discontinuity, not the 78% share, is the proof that teams deliberately play the 2-for-1.}}

<div class="eyebrow beat">The payoff</div>

## The extra possession is real, and so is the edge

So teams do it. Should they? Counting a team's own points, 2-for-1 windows
produce +0.78 more points per team-period than holds (95% bootstrap CI
[+0.68, +0.88]). The mechanism shows up exactly where it should, as
roughly +0.94 extra field-goal attempts per window. The extra possession is
real, not an accounting trick.

But the case for holding the ball was never about your own points. It is
that holding denies the opponent a reply. So the honest outcome is **net**
points, and the honest comparison controls for the fact that the team with
the ball early is a different kind of team-period. On net points, in the
comparable-sample analysis, the edge shrinks to +0.24 per opportunity
(95% CI [+0.03, +0.44]): the opponent's reply claws back about half of the
gain, but not all of it. Pooled over three NBA seasons that net edge is
+0.22 [+0.10, +0.34], clearly above zero. The decision favors shooting
early: you give up nothing on shot quality, and you keep a real, if
modest, edge after the opponent answers.

{{fig:fig2_efg_by_clock|Shooting efficiency by seconds left on the clock. Necessary because the standard objection to the 2-for-1 is that the early shot is a rushed, bad shot. This figure shows efficiency in the 25–36 second launch window sits at normal levels, so the extra possession is not being bought with junk offense. (The sibling shot-quality study later re-priced this window with a full shot model and confirmed it: about −0.8 points per 100 shots, essentially free.)}}

<div class="eyebrow beat">The scouting report</div>

## Everybody plays it. Sacramento just plays it hardest.

Two natural follow-ups deserve their own figures. First, who actually
hunts the 2-for-1? The behavioral dial is team-controlled, and the league
spread is real but modest: Sacramento leads at 85% of its final-minute
windows, Chicago trails at 73%, and every team sits above 70%. This is a
league-wide habit with team accents, not a strategy some teams run and
others refuse.

{{fig:fig3_team_2for1|Every team's 2-for-1 rate, sorted, with the league line marked. The scouting read: the spread from Sacramento (85%) to Chicago (73%) is about 12 points, so opponent tendency is worth knowing but nobody truly abstains. Hover a team for its window count and points outcomes.}}

<div class="eyebrow beat">Context check</div>

## The clock decides, not the quarter

Second, does the quarter matter? Almost not at all. The 2-for-1 rate is
78.4% in the first quarter, 78.0% in the second, and 76.8% in the third.
The payoff ordering also holds in every quarter: taking the 2-for-1 wins
each one on own points and on net. That flatness is itself informative.
The decision is driven by the clock, not the scoreboard or the stage of
the game, at least through three quarters (the fourth is excluded by
design, because endgame strategy changes everything).

{{fig:fig4_quarter_2for1|Own points per window by quarter, 2-for-1 versus hold. Necessary because "does context change the answer?" is the first question a coach asks: the bars barely move across quarters, so the recommendation survives without a quarter-by-quarter carve-out.}}

<div class="eyebrow beat">Three seasons</div>

## The habit has stopped spreading, and the holdouts came back

One season could not say whether the 2-for-1 was still taking over. Three
can. Looking only at the team that has the ball at the 40-second mark, the
share that goes quick sits at 84.5%, 82.4% and 83.0% across 2023-24 to
2025-26: flat, not rising. Holding for the last shot, nearly extinct at 24
team-periods in 2023-24, ran 50 and 48 in the next two seasons. The
bunching at the 32-second threshold also softened, from 1.37× to 1.19× the
rate in the 36–40 second band. The play is standard, but the league has not
finished converging on it.

{{fig:fig5_quick_share_by_season|Share of 2-for-1 decisions that went quick, by league-season, with the number of holds on each bar. Necessary because "everyone already does it" was a one-season claim: the NBA bars are flat, the holds doubled after 2023-24, and the WNBA bars sit lower.}}

<div class="eyebrow beat">The WNBA</div>

## The WNBA plays it less, and less on schedule

The WNBA plays 10-minute quarters with the same 24-second shot clock, so
the same 60-second window and 32-second threshold apply. WNBA teams with
the ball at the mark go quick 76% to 78% of the time, below the NBA's
rate, and they do not time the first shot to the threshold at all: the
31–33 second band never reaches even the rate of the 36–40 second band.
The hope for the replication was a larger group of teams that hold, which
would make the comparison better powered. Holds are about twice as
common as in the NBA, but that is still only 16 to 19 a season.

Does it pay there? The possession-level comparison says yes: quick minus
hold pools to +0.71 net points over 2024-2026 (95% CI [+0.25, +1.18]). The
shot-timing comparison restricted to first shots at 20–45 seconds does
not: −0.13 [−0.36, +0.11]. The possession design is the more direct of the
two, because it compares only teams that had the ball at the mark, so it
carries the conclusion, but the disagreement is real and worth stating.

{{fig:fig6_restricted_net_by_season|The restricted net-points gap with its 95% interval for every league-season and pooled by league. Necessary because the one-season question was whether this interval clears zero: pooled, the NBA's does, and the WNBA's does not on this design.}}

<div class="eyebrow beat">The correction</div>

## These numbers were wrong twice. Each time, a check caught it.

The first version of this analysis silently sorted play-by-play event
numbers as text, putting "100" before "2". The family's rule that every
analysis is implemented twice, in R and Python, caught that. But a second
implementation cannot catch a mistake both implementations share, and
there was one. Both ordered events by action number, and the league's feed
inserts late events with a high action number but an early clock. Those
strays carried the end-of-quarter score back to the start of the final
minute, which zeroed or shrank the window points of 15% of 2023-24
team-periods and understated every estimate. An independent feed caught
it: the NBA's own liveData play-by-play disagreed with the old window
points, and agrees with the corrected ones on 100.0% of team-periods.
A second pass the same day, prompted by the
[Elam Ending study](https://github.com/ismayc/elam-ending-study)'s own check
against that feed, fixed how scores are read: Instant Replay rows carried
stale scores, and free throws at one clock reading could arrive out of
order. It changed 28 more team-periods across all six league-seasons.
Every season in this study is now checked against that second feed, and
the README's correction note lists each published number next to its
corrected value.
