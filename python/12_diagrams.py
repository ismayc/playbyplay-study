"""Explainer diagrams for the story page, drawn with the family's famdiagram
(../basketball-analysis-tools/famdiagram.py) and saved to figures/<ref>.svg
(plus a <ref>_narrow.svg phone layout). report_builder.py inlines them.

Every number drawn is read from committed files: the analysis scripts'
constants, the output tables, and the committed play-by-play and possession
rows of the two example game-periods (data/raw_pbp/, data/possessions/).

Diagrams:
  dg1_final_minute  the clock marks the study uses (the 60-second window,
                    the 40-second decision mark, the 32-second first-shot
                    threshold) on one real 2-for-1, and how the decision
                    team's choice is sorted into quick, normal, and hold
                    (data/possessions/nba_2023-24.parquet, data/raw_pbp/,
                    output/decision_windows.csv, output/decision_summary.csv)
  dg2_own_to_net    how the own-points headline becomes the fair net
                    comparison: each step and its interval
                    (output/seasons_summary.csv, output/seasons_pooled.csv,
                    output/team_period_windows.csv for the restriction's n)
  dg3_event_order   the October 19, 2026 correction on one real period:
                    action-number order against game-clock order
                    (data/raw_pbp/0022300002.parquet,
                    output/team_period_windows.csv,
                    output/correction_2026-10-19.csv)

Run:     python python/12_diagrams.py
--check: rebuild every SVG in memory and fail if a committed one differs.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
FIG = ROOT / "figures"
RAW = ROOT / "data" / "raw_pbp"
sys.path.insert(0, str(ROOT.parent / "basketball-analysis-tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import famdiagram as fd  # noqa: E402


def _load(rel: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


A02 = _load("python/02_analysis.py", "pbp_02_for_diagrams")
A05 = _load("python/05_possession_analysis.py", "pbp_05_for_diagrams")
WINDOW, THRESH = A02.WINDOW_SEC, A02.TWO_FOR_ONE_SEC
DECISION, QUICK_END, HOLD_END = A05.DECISION_T, A05.QUICK_END, A05.HOLD_END

# Text keys only. dg1's example: the first 2023-24 decision period (by game
# ID) that went quick and got exactly one more possession. dg3's example is
# the game-period named in 02_analysis.prepare_events' comment.
QUICK_EXAMPLE = ("0022300001", 3)
ORDER_EXAMPLE = ("0022300002", 1)
# The sensitivity restriction in 02_analysis.py (first shot between these
# seconds). check_restriction() confirms it reproduces the committed n.
RESTRICT = (20, 45)
WORD = {1: "one", 2: "two", 3: "three"}
QUARTER = {1: "first", 2: "second", 3: "third"}


def wrap(s: str, width: float, size: float) -> list[str]:
    """Greedy word wrap on an estimated glyph width."""
    per = size * 0.55
    out, cur = [], ""
    for w in s.split():
        t = f"{cur} {w}".strip()
        if len(t) * per > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        out.append(cur)
    return out


def para(d: fd.Diagram, x, y, s, width, size, lh=None, **kw) -> float:
    """Wrapped text; returns the baseline of the last line."""
    lh = lh or size * 1.35
    lines = wrap(s, width, size)
    for i, line in enumerate(lines):
        d.text(x, y + i * lh, line, size=size, **kw)
    return y + (len(lines) - 1) * lh


def clock(secs: float) -> str:
    s = int(secs)
    return f"{s // 60}:{s % 60:02d}"


def sgn(v: float, dgt: int = 2) -> str:
    return f"{v:+.{dgt}f}".replace("-", "−")


def events(game: str, period: int) -> pl.DataFrame:
    """One period's V3 rows, typed: secs_left, numeric actionNumber."""
    return A02.prepare_events(pl.read_parquet(RAW / f"{game}.parquet")).filter(
        pl.col("period") == period)


# ---------------------------------------------------------------- dg1
def final_minute(narrow: bool) -> fd.Diagram:
    game, period = QUICK_EXAMPLE
    dw = pl.read_csv(OUT / "decision_windows.csv")
    dec = dw.filter((pl.col("game_id") == int(game)) & (pl.col("PERIOD") == period)).row(0, named=True)
    assert dec["behavior"] == "quick" and dec["n_later_poss"] == 1, dec
    ev = events(game, period)
    tri = (ev.filter(pl.col("teamTricode") != "")
             .select("teamId", "teamTricode", "location").unique())
    team_of = {int(r["teamId"]): r["teamTricode"] for r in tri.iter_rows(named=True)}
    side_of = {r["teamTricode"]: r["location"] for r in tri.iter_rows(named=True)}
    home = next(t for t, s in side_of.items() if s == "h")
    away = next(t for t, s in side_of.items() if s == "v")
    poss = (pl.read_parquet(ROOT / "data" / "possessions" / "nba_2023-24.parquet")
              .filter((pl.col("game_id") == int(game)) & (pl.col("PERIOD") == period)
                      & (pl.col("start_secs") > pl.col("end_secs"))
                      & (pl.col("end_secs") < WINDOW))
              .sort("start_secs", descending=True))
    segs = []
    for r in poss.iter_rows(named=True):
        team = team_of[r["offense_team_id"]]
        col = "score_h" if side_of[team] == "h" else "score_a"
        inside = ev.filter((pl.col("secs_left") <= r["start_secs"])
                           & (pl.col("secs_left") > r["end_secs"] - 1e-9))
        before = ev.filter(pl.col("secs_left") > r["start_secs"])
        pts = (inside[col].max() or 0) - (before[col].max() if before.height else 0)
        if r["TURNOVERS"]:
            what = "turnover"
        elif pts:
            what = f"{int(pts)} pts"
        else:
            what = "miss"
        segs.append({"team": team, "start": min(r["start_secs"], WINDOW),
                     "end": r["end_secs"], "what": what})
    # the decision possession in the drawing is the one in the committed table
    d0 = next(s for s in segs if s["start"] >= DECISION > s["end"])
    assert d0["team"] == dec["offense"] and d0["end"] == dec["end_secs"], (d0, dec)
    dteam = dec["offense"]
    opp = home if dteam == away else away
    after = [s for s in segs if s["start"] <= d0["end"]]
    n_own = 1 + sum(s["team"] == dteam for s in after)
    n_opp = sum(s["team"] == opp for s in after)

    summ = {r["behavior"]: r for r in pl.read_csv(OUT / "decision_summary.csv").iter_rows(named=True)}
    total = sum(r["n"] for r in summ.values())

    W = 360 if narrow else 760
    fs, small, head = (13, 12, 17) if narrow else (15, 14, 20)
    pad = 12
    ax0, ax1 = (pad + 6, W - pad - 6) if narrow else (pad + 20, W - pad - 20)
    aw = ax1 - ax0

    def x(s: float) -> float:
        return ax0 + (WINDOW - s) / WINDOW * aw

    d = fd.Diagram(W, 10, "The final minute of a quarter: the clock marks the study uses, "
                   "one real 2-for-1, and how the team with the ball is sorted")
    y = 28
    d.text(pad, y, "1. The marks on the clock", size=head, display=True, weight="600")
    y += 18
    y = para(d, pad, y, f"Seconds left in quarters one to three, from {int(WINDOW)} down "
             "to the buzzer", W - 2 * pad, small, fill="ink2") + 30
    q = "Q" + str(period)
    lab = f"One real 2-for-1: {away} at {home}, {q}, 2023-24"
    d.text(pad, y, lab, size=fs, fill="ink", weight="700")
    y += 28
    # mark labels in two rows so neighbors never collide
    row_hi, row_lo = y, y + small * 1.5 + 2
    marks = [(WINDOW, "window opens", row_lo, "start", "ink3"),
             (DECISION, "decision mark", row_hi, "end", "ink"),
             (THRESH, "2-for-1 threshold", row_lo, "start", "nba"),
             (0.0, "buzzer", row_hi, "end", "ink3")]
    if narrow:
        marks = [(WINDOW, "opens", row_lo, "start", "ink3"),
                 (DECISION, "decision", row_hi, "end", "ink"),
                 (THRESH, "threshold", row_lo, "start", "nba"),
                 (0.0, "buzzer", row_hi, "end", "ink3")]
    for s, lab, ly, anc, col in marks:
        dx = 4 if anc == "start" else -4
        d.text(x(s) + dx, ly, f"{lab}, {int(s)} s", size=small, fill=col, anchor=anc,
               weight="700" if col in ("ink", "nba") else None)
    lane_y = row_lo + 14
    lh = 34
    axis_y = lane_y + lh + (small * 2.6 + 18 if narrow else 6)
    for s, *_ in marks:
        col = "nba" if s == THRESH else ("ink" if s == DECISION else "ink3")
        for ya, yb in ((row_lo + 6 if s in (WINDOW, THRESH) else row_hi + 6, lane_y),
                       (lane_y + lh if not narrow else axis_y - 4, axis_y)):
            d.line(x(s), ya, x(s), yb, stroke=col, sw=1.5 if col != "ink3" else 1,
                   dash="4 3")
    for k, s in enumerate(segs):
        x0, x1 = x(s["start"]), x(s["end"])
        mine = s["team"] == dteam
        d.rect(x0, lane_y, x1 - x0, lh, fill="nba" if mine else "ink3",
               opacity=0.9 if mine else 0.45, rx=3)
        d.line(x0, lane_y, x0, lane_y + lh, stroke="surface", sw=2)
        txt = f"{s['team']} {s['what']}"
        if not narrow:
            d.text((x0 + x1) / 2, lane_y + lh * 0.66, txt, size=small,
                   fill="surface" if mine else "ink", anchor="middle", weight="600")
        else:
            ty = lane_y + lh + 16 + (k % 2) * (small * 1.3)
            d.text((x0 + x1) / 2, ty, txt, size=small, fill="nba" if mine else "ink2",
                   anchor="middle", weight="600")
    d.line(ax0, axis_y, ax1, axis_y, stroke="rule", sw=1)
    y = axis_y + 26
    y = para(d, pad, y, f"{dteam} had the ball at the decision mark and shot with "
             f"{int(d0['end'])} seconds left, so it got the ball back: "
             f"{WORD[n_own]} {dteam} possessions to {opp}'s {WORD[n_opp]}.",
             W - 2 * pad, fs, fill="ink2") + 44

    d.text(pad, y, "2. Sorting the team with the ball at the mark", size=head, display=True,
           weight="600")
    y += 18
    y = para(d, pad, y, "by when its possession ends", W - 2 * pad, small, fill="ink2") + 18
    zones = [("quick", "Quick", DECISION, QUICK_END, "nba", 0.9),
             ("normal", "Normal", QUICK_END, HOLD_END, "ink3", 0.45),
             ("hold", "Hold", HOLD_END, 0.0, "c4", 0.55)]
    zh = 30
    for key, lab, s0, s1, col, op in zones:
        d.rect(x(s0), y, x(s1) - x(s0), zh, fill=col, opacity=op, rx=3)
        d.line(x(s0), y, x(s0), y + zh, stroke="surface", sw=2)
        d.text((x(s0) + x(s1)) / 2, y + zh * 0.68, lab, size=fs,
               fill="surface" if key == "quick" else "ink", anchor="middle", weight="700")
    for s in (DECISION, QUICK_END, HOLD_END, 0.0):
        d.text(x(s), y + zh + 18, f"{int(s)} s", size=small, fill="ink2", anchor="middle")
    y += zh + 48
    d.text(pad, y, f"NBA 2023-24, {total:,} decisions:", size=small, fill="ink2")
    y += small * 1.6
    for key, lab, *_ in zones:
        r = summ[key]
        share = r["n"] / total
        line1 = f"{lab}: {r['n']:,} ({share:.1%})"
        line2 = f"{r['mean_later_poss']:.2f} more possessions after it, on average"
        if narrow:
            d.text(pad, y, line1, size=fs, fill="ink", weight="700")
            y = para(d, pad, y + fs * 1.35, line2, W - 2 * pad, small, fill="ink2") + fs * 1.7
        else:
            d.text(pad, y, line1, size=fs, fill="ink", weight="700")
            d.text(pad + 230, y, line2, size=fs, fill="ink2")
            y += fs * 1.8
    d.h = y + 2
    return d


# ---------------------------------------------------------------- dg2
def check_restriction(row: dict) -> None:
    """RESTRICT must reproduce the committed restricted-sample n."""
    tp = pl.read_csv(OUT / "team_period_windows.csv")
    nar = tp.filter(pl.col("first_fga_sec").is_between(*RESTRICT))
    br = pl.read_csv(OUT / "bootstrap_net_restricted.csv").row(0, named=True)
    assert nar.filter(pl.col("two_for_one")).height == br["n_treated"], "RESTRICT drifted"
    assert nar.filter(~pl.col("two_for_one")).height == br["n_control"], "RESTRICT drifted"


def own_to_net(narrow: bool) -> fd.Diagram:
    ss = pl.read_csv(OUT / "seasons_summary.csv").filter(
        (pl.col("league") == "nba") & (pl.col("season") == "2023-24")).row(0, named=True)
    check_restriction(ss)
    pooled = pl.read_csv(OUT / "seasons_pooled.csv").filter(
        (pl.col("league") == "nba") & (pl.col("quantity") == "net_restricted")).row(0, named=True)
    lo_, hi_ = RESTRICT
    steps = [
        ("Own points, every team-period", "NBA 2023-24",
         ss["own_gap"], ss["own_gap_lo"], ss["own_gap_hi"], None),
        ("Own points, comparable team-periods", "NBA 2023-24",
         ss["own_gap_restricted"], ss["own_gap_restricted_lo"], ss["own_gap_restricted_hi"],
         f"Keep only team-periods whose first shot came {lo_} to {hi_} seconds out, "
         "so both groups had the ball at similar times"),
        ("Net points, comparable team-periods", "NBA 2023-24",
         ss["net_gap_restricted"], ss["net_gap_restricted_lo"], ss["net_gap_restricted_hi"],
         "Subtract what the opponent scored in the same window"),
        ("Net points, comparable team-periods", pooled["seasons"],
         pooled["estimate"], pooled["ci_lo"], pooled["ci_hi"],
         "Pool three NBA seasons"),
    ]
    W = 360 if narrow else 760
    fs, small = (13, 12) if narrow else (15, 14)
    pad = 12
    d = fd.Diagram(W, 10, "From the own-points headline to the fair net comparison")
    lab_w = W - 2 * pad if narrow else 300
    px0 = pad + 8 if narrow else pad + lab_w + 30
    px1 = W - pad - 8
    vmax = max(s[4] for s in steps)
    vmin = min(0.0, min(s[3] for s in steps))
    span = (vmax - vmin) * 1.08

    def vx(v: float) -> float:
        return px0 + (v - vmin) / span * (px1 - px0)

    y = 22
    d.text(pad, y, "Points per team-period gained by shooting early, with 95% intervals",
           size=small, fill="ink2") if not narrow else para(
        d, pad, y, "Points per team-period gained by shooting early, with 95% intervals",
        W - 2 * pad, small, fill="ink2")
    y += (small * 1.35 if narrow else 0) + 26
    top_y = y
    rows_y = []
    for k, (lab, sub, est, lo, hi, why) in enumerate(steps):
        if why:
            ay0 = y - 4
            yw = para(d, pad + 26, y + 10, why, (W - 2 * pad - 30) if narrow else lab_w - 10,
                      small, fill="ink3", italic=True)
            d.line(pad + 10, ay0, pad + 10, yw + 10, stroke="ink3", sw=1.5, arrow=True)
            y = yw + 30
        last = k == len(steps) - 1
        col = "nba"
        if narrow:
            d.text(pad, y, lab, size=fs, fill="ink", weight="700")
            d.text(pad, y + fs * 1.35, sub, size=small, fill="ink2")
            py = y + fs * 1.35 + 36
        else:
            d.text(pad, y, lab, size=fs, fill="ink", weight="700")
            d.text(pad, y + fs * 1.35, sub, size=small, fill="ink2")
            py = y + 4
        d.line(vx(lo), py, vx(hi), py, stroke="nba", sw=3)
        d.line(vx(lo), py - 7, vx(lo), py + 7, stroke="nba", sw=2)
        d.line(vx(hi), py - 7, vx(hi), py + 7, stroke="nba", sw=2)
        d.circle(vx(est), py, 7 if last else 6, fill=col)
        d.text(vx(est), py - 13, f"{sgn(est)} [{sgn(lo)}, {sgn(hi)}]", size=small,
               fill="ink", anchor="middle", weight="700" if last else None)
        rows_y.append(py)
        y = py + (36 if narrow else 40)
    # zero line
    if narrow:   # labels sit above each row here, so mark zero row by row
        for py in rows_y:
            d.line(vx(0), py - 10, vx(0), py + 10, stroke="ink2", sw=1, dash="3 3")
        d.text(vx(0), rows_y[-1] + 32, "dashed: 0, no edge", size=small, fill="ink2")
    else:
        d.line(vx(0), top_y - 18, vx(0), rows_y[-1] + 16, stroke="ink2", sw=1, dash="3 3")
        d.text(vx(0), rows_y[-1] + 32, "0, no edge", size=small, fill="ink2",
               anchor="middle")
    d.h = rows_y[-1] + 44
    return d


# ---------------------------------------------------------------- dg3
def short(r: dict) -> str | None:
    t, a = r["teamTricode"], r["actionType"].strip()
    if a == "Made Shot":
        return f"{t} makes a {int(float(r['shotValue']))}"
    if a == "Missed Shot":
        return f"{t} misses"
    if a == "Rebound":
        return f"{t} rebound"
    if a == "Turnover":
        return f"{t} turnover"
    if a == "Free Throw":
        return f"{t} free throw"
    if a == "period":
        return "end of period"
    return None


def window_points(rows: pl.DataFrame) -> dict:
    """Each side's window points by 02_analysis.window_points' rule (score at
    the last event with more than WINDOW seconds left, to the score at the
    last event), on rows already in the order being tested."""
    secs = rows["secs_left"].to_list()
    o = max(i for i, s in enumerate(secs) if s > WINDOW)
    c = rows.height - 1
    return {"open": o, "close": c,
            "h": rows["score_h"][c] - rows["score_h"][o],
            "v": rows["score_a"][c] - rows["score_a"][o]}


def event_order(narrow: bool) -> fd.Diagram:
    game, period = ORDER_EXAMPLE
    raw = (pl.read_parquet(RAW / f"{game}.parquet")
             .with_columns(sh0=A02.stamp("h", "scoreHome"), sa0=A02.stamp("v", "scoreAway")))
    typed = A02.prepare_events(raw)          # clock order, corrected scores
    # the published build: the same stamps, filled across the game in
    # action-number order
    by_action = (typed.sort(["period", "actionNumber"])
                      .with_columns(score_h=pl.col("sh0").fill_null(0.0).cum_max(),
                                    score_a=pl.col("sa0").fill_null(0.0).cum_max()))
    panels_rows = {}
    for name, frame in (("action", by_action), ("clock", typed)):
        rows = frame.filter(pl.col("period") == period).with_row_index("i")
        panels_rows[name] = (rows, window_points(rows))
    arow, ainfo = panels_rows["action"]
    crow, cinfo = panels_rows["clock"]
    tp = pl.read_csv(OUT / "team_period_windows.csv", schema_overrides={"gameId": pl.Utf8})
    mine = tp.filter((pl.col("gameId") == game) & (pl.col("period") == period))
    committed = {r["location"]: r["points"] for r in mine.iter_rows(named=True)}
    assert committed == {"h": cinfo["h"], "v": cinfo["v"]}, (committed, cinfo)
    sides = (crow.filter(pl.col("teamTricode") != "")
                 .select("location", "teamTricode").unique())
    side = {r["location"]: r["teamTricode"] for r in sides.iter_rows(named=True)}
    home, away = side["h"], side["v"]
    scorer = "v" if cinfo["v"] else "h"
    steam = side[scorer]
    end_an = crow.filter(pl.col("actionType") == "period")["actionNumber"].max()
    strays = set(crow.filter((pl.col("actionNumber") > end_an)
                             & (pl.col("secs_left") > WINDOW))["actionNumber"].to_list())
    corr = {r["quantity"]: r for r in
            pl.read_csv(OUT / "correction_2026-10-19.csv").iter_rows(named=True)}
    n_ch = int(corr["team_periods_points_changed"]["corrected"])
    n_tp = int(corr["team_periods"]["corrected"])

    def pick(rows: pl.DataFrame, info: dict) -> list[dict | None]:
        """Rows worth showing: the strays, the rows where the window opens
        and closes, and the made shots inside it; None marks a gap."""
        recs = [r for r in rows.iter_rows(named=True) if short(r)]
        keep = []
        for r in recs:
            made = r["actionType"].strip() == "Made Shot" and r["secs_left"] <= WINDOW
            if (r["actionNumber"] in strays or made
                    or r["i"] in (info["open"], info["close"])
                    or r["actionNumber"] == end_an):
                keep.append(r)
        out, prev = [], None
        pos = {r["i"]: k for k, r in enumerate(recs)}
        for r in keep:
            if prev is not None and pos[r["i"]] - pos[prev] > 1:
                out.append(None)
            out.append(r)
            prev = r["i"]
        return out

    W = 360 if narrow else 760
    fs, small, head = (13, 12, 17) if narrow else (15, 14, 19)
    pad = 12
    d = fd.Diagram(W, 10, "How event order changed one period's window points")
    y = 26
    # Teams and season, not the raw game ID, which means nothing to a reader.
    start = 2000 + int(str(game).zfill(10)[3:5])   # 00223... is the 2023-24 season
    y = para(d, pad, y, f"{away} at {home}, {start}-{(start + 1) % 100:02d}, "
             f"{QUARTER[period]} quarter. "
             f"Score shown {home}–{away}.", W - 2 * pad, small, fill="ink2") + 24
    colw = (W - 2 * pad) if narrow else (W - 3 * pad) / 2
    panels = [("Action-number order (published)", arow, ainfo, "c8"),
              ("Game-clock order (corrected)", crow, cinfo, "c3")]
    bottoms = []
    y0 = y
    for k, (title, rows, info, col) in enumerate(panels):
        px = pad if narrow else pad + k * (colw + pad)
        py = y if narrow else y0
        shown = pick(rows, info)
        rh = fs * 1.75
        ph = 44 + len(shown) * rh + 74
        d.rect(px, py, colw, ph, fill="surface2", stroke="rule", rx=8)
        d.text(px + 12, py + 26, title, size=fs, fill="ink", weight="700")
        ry = py + 54
        for r in shown:
            if r is None:
                d.text(px + 16, ry, "…", size=fs, fill="ink3")
                ry += rh * 0.8
                continue
            is_open, is_close = r["i"] == info["open"], r["i"] == info["close"]
            stray = r["actionNumber"] in strays
            if is_open or is_close:
                d.rect(px + 6, ry - fs - 2, colw - 12, rh, fill=col, opacity=0.18, rx=4)
            d.text(px + 12, ry, f"#{r['actionNumber']}", size=small, fill="ink3")
            d.text(px + (54 if narrow else 62), ry, clock(r["secs_left"]), size=small,
                   fill="c8" if stray else "ink2", weight="700" if stray else None)
            d.text(px + (96 if narrow else 108), ry, short(r), size=small, fill="ink")
            d.text(px + colw - 12, ry, f"{int(r['score_h'])}–{int(r['score_a'])}",
                   size=small, fill="ink", anchor="end",
                   weight="700" if (is_open or is_close) else None)
            ry += rh
        tag_y = ry + 6
        opens_closes = ("window opens and closes here" if info["open"] == info["close"]
                        else "shaded: where the window opens and closes")
        d.text(px + 12, tag_y, opens_closes, size=small, fill="ink2", italic=True)
        pts = info[scorer]
        d.text(px + 12, tag_y + 30, f"{steam} points in the final minute:", size=fs, fill="ink")
        d.text(px + colw - 12, tag_y + 30, f"{int(pts)}", size=fs + 6, fill=col,
               anchor="end", weight="700")
        bottoms.append(py + ph)
        if narrow:
            y = py + ph + 16
    y = max(bottoms) + 30
    late = crow.filter(pl.col("actionNumber").is_in(list(strays)))["secs_left"].max()
    y = para(d, pad, y, f"{WORD[len(strays)].capitalize()} plays logged late, at "
             f"{clock(late)} left, carried high action numbers, so in action order they came after the "
             "end of the period and took its score back to the start of the window. "
             f"The same thing zeroed or shrank {n_ch:,} of {n_tp:,} team-periods in "
             f"2023-24 ({n_ch / n_tp:.0%}).", W - 2 * pad, small, fill="ink2")
    d.h = y + 14
    return d


DIAGRAMS = {"dg1_final_minute": final_minute, "dg2_own_to_net": own_to_net,
            "dg3_event_order": event_order}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        fails = []
        with tempfile.TemporaryDirectory() as tmp:
            for ref, fn in DIAGRAMS.items():
                for p in fd.save(Path(tmp), ref, fn(False), fn(True)):
                    old = FIG / p.name
                    if not old.exists() or old.read_text() != p.read_text():
                        fails.append(p.name)
        for f in fails:
            print("FAIL", f, "differs from a fresh build")
        print("DIAGRAMS", "FAILED" if fails else
              f"PASSED: {len(DIAGRAMS)} diagrams rebuild identically")
        return 1 if fails else 0
    for ref, fn in DIAGRAMS.items():
        for p in fd.save(FIG, ref, fn(False), fn(True)):
            print("wrote", p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
