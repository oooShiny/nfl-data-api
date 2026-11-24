import polars as pl

from pipeline.silver.pfr_possession import _number_drives, infer_possession


def _play(seq, play_type, before, after, h, a, side=None, yl=None, down=None, **kw):
    row = dict(game_id="1998_01_NE_DEN", play_seq=seq, quarter=1, home_team="DEN", away_team="NE", play_type=play_type,
               exp_pts_before=before, exp_pts_after=after, home_score=h, away_score=a,
               yardline_side=side, yardline=yl, down=down, two_point_attempt=False, touchdown=False,
               passer=None, rusher=None, receiver=None, punter=None, kicker=None)
    row.update(kw)
    return row


def test_infer_possession_from_expected_points():
    # Mirrors the start of 1998_01_NE_DEN: NE kicks off, DEN drives for a FG,
    # DEN kicks off, NE drives, misses a FG, DEN takes over.
    df = pl.DataFrame([
        _play(1, "kickoff", 0.0, -0.04, 0, 0, "NE", 30, kicker="Adam Vinatieri"),
        _play(2, "pass", 0.04, 3.05, 0, 0, "DEN", 18, 1, passer="John Elway"),
        _play(3, "pass", 3.05, 3.18, 0, 0, "NE", 38, 1, passer="John Elway"),
        _play(4, "field_goal", 1.07, 3.0, 3, 0, "NE", 34, 4, kicker="Jason Elam"),
        _play(5, "kickoff", 0.0, -3.45, 3, 0, "DEN", 30, kicker="Jason Elam"),
        _play(6, "pass", 3.45, 2.9, 3, 0, "DEN", 32, 1, passer="Drew Bledsoe"),
        # PFR writes 0.0 on some rows, breaking continuity; field position decides.
        _play(7, "no_play", 2.9, 0.0, 3, 0, "DEN", 27, 2),
        _play(8, "run", 4.31, 3.88, 3, 0, "DEN", 19, 1, rusher="Sedrick Shaw"),
        _play(9, "field_goal", 1.99, -0.94, 3, 0, "DEN", 22, 4, kicker="Adam Vinatieri"),
        _play(10, "pass", 0.94, 0.8, 3, 0, "DEN", 30, 1, passer="John Elway"),
    ])
    out = infer_possession(df)
    assert out["posteam"].to_list() == ["DEN", "DEN", "DEN", "DEN", "NE", "NE", "NE", "NE", "NE", "DEN"]
    assert out["defteam"].to_list()[:2] == ["NE", "NE"]
    # yardline_100 from the offense's view: DEN at its own 18 is 82 from the goal.
    assert out["yardline_100"].to_list()[1:4] == [82, 38, 34]
    # A drive per possession; each kickoff starts the receiving team's drive.
    assert out["drive"].to_list() == [1, 1, 1, 1, 2, 2, 2, 2, 2, 3]


def test_score_anchor_overrides_field_position():
    # A pick-six: exp_pts_after is -7 from the offense's (DEN's) view, and NE
    # scores, so the play belongs to DEN even though field position is ambiguous.
    df = pl.DataFrame([
        _play(1, "pass", 2.0, -7.0, 0, 6, "DEN", 50, 1),
        _play(2, "extra_point", 0.0, 0.0, 0, 7),
    ])
    out = infer_possession(df)
    assert out["posteam"].to_list() == ["DEN", "NE"]


def test_drives_break_at_half_and_carry_over_unassigned_plays():
    rows = [
        # (quarter, posteam, play_type)
        (1, None, None),           # coin toss: takes the first drive
        (1, "DEN", "kickoff"),
        (1, "DEN", "run"),
        (1, None, "no_play"),      # timeout: same drive
        (2, "DEN", "pass"),        # quarter change within a half: same drive
        (2, "DEN", "extra_point"),
        (2, "NE", "kickoff"),
        (2, "NE", "run"),
        (3, "NE", "run"),          # second half: new drive, same team
        (5, "NE", "pass"),         # overtime: new drive
    ]
    df = pl.DataFrame([dict(game_id="g", play_seq=i, quarter=q, posteam=t, play_type=pt)
                       for i, (q, t, pt) in enumerate(rows, 1)])
    assert _number_drives(df)["drive"].to_list() == [1, 1, 1, 1, 1, 1, 2, 2, 3, 4]
