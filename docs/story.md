# The 2-for-1 is real, coaches actually do it, and the payoff is smaller than it looks

With thirty-some seconds left in a quarter, a team with the ball faces a
genuine strategic fork: shoot quickly and buy an extra possession before
the buzzer, or hold for the last shot and deny the opponent any reply.
Coaches disagree about this in public. A full season of play-by-play
(all 1,230 games of 2023-24) lets us ask two separable questions: do teams
actually play the 2-for-1, and does it pay?

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

So teams do it. Should they? Counting a team's own points, 2-for-1 windows
produce +0.58 more points per team-period than holds (95% bootstrap CI
[+0.48, +0.68]). The mechanism shows up exactly where it should, as
roughly +0.94 extra field-goal attempts per window. The extra possession is
real, not an accounting trick.

But the case for holding the ball was never about your own points. It is
that holding denies the opponent a reply. So the honest outcome is **net**
points, and the honest comparison controls for the fact that better teams
choose the 2-for-1 more often. On net points, in the comparable-sample
analysis, the edge shrinks to roughly +0.2 per opportunity and is not
statistically distinguishable from zero. The decision still favors
shooting early: you give up nothing, and the shot-quality cost is
negligible. But the breathless version of the 2-for-1 case does not
survive its own accounting.

{{fig:fig2_efg_by_clock|Shooting efficiency by seconds left on the clock. Necessary because the standard objection to the 2-for-1 is that the early shot is a rushed, bad shot. This figure shows efficiency in the 25–36 second launch window sits at normal levels, so the extra possession is not being bought with junk offense. (The sibling shot-quality study later re-priced this window with a full shot model and confirmed it: about −0.8 points per 100 shots, essentially free.)}}

One methodological note belongs in the story rather than a footnote,
because it explains why these numbers can be trusted: the first version of
this analysis silently sorted play-by-play event numbers as text ("100"
before "2"), which corrupted every scoreboard-dependent number downstream.
The bug was caught by this family's standing rule that every analysis is
implemented twice, in R and Python, and reconciled to numeric tolerance
before findings are written. The gap between the naive and corrected
numbers (+0.36 → +0.58) is a permanent reminder of what the reconcile gate
is for.
