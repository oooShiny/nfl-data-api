"""Infer which team has the ball on each PFR historical play-by-play row.

PFR's pre-1999 play-by-play has no possession column, but its expected-points
columns (exp_pts_before / exp_pts_after) are always from one team's point of
view: the offense, or the kicking team on kickoffs, punts and field goals.
That gives two exact signals:

1. Continuity. Between consecutive plays, exp_pts_before of the next play
   equals exp_pts_after of this one when the same team is "on the clock", and
   is its negative when the ball changed hands (3.05 -> 3.05 vs -0.15 -> 0.15).
   This links plays into chains whose possession is known up to a swap.
2. Scores. On a play where the score changes, exp_pts_after is positive
   (+7, +3) when that team scored and negative (-7 pick-six, -2 safety) when
   the other team did, which pins a chain to a real team.

Neither signal is perfect (PFR writes 0.0 on some penalty and end-of-half
rows, which breaks continuity), so each game is solved as a two-state
sequence (perspective = home or away) with costs, picking the cheapest
path (Viterbi):
  - continuity links between plays (strong),
  - score anchors (very strong),
  - field position: the offense is the team for which exp_pts_before fits
    the distance to the goal line (weak, per play),
  - a second pass adding player consistency: a passer, rusher, receiver,
    punter or kicker stays with one team for the whole game.

Convention for the output posteam, matching nflverse's fact_plays: the
offense on scrimmage plays; the kicking team on punts, field goals and extra
points; the RECEIVING team on kickoffs.
"""

from collections.abc import Callable

import polars as pl

from pipeline.historical_players import name_key

_TOL = 0.015  # PFR rounds expected points to 2 decimals

# Costs (in rough "log-odds" units) for the per-game sequence solve.
_LINK_COST = 6.0       # going against an exact expected-points continuity link
_SCORE_COST = 12.0     # going against a scoring play
_KICK_PRIOR_COST = 2.0  # TD -> try -> kickoff and FG -> kickoff are by the same team
_FIELD_WEIGHT = 1.0    # per point of expected-points misfit
_PLAYER_COST = 3.0     # a player's play assigned to the other team than his majority
_ROSTER_COST = 4.0     # a player's play assigned to the team he isn't on (nflverse rosters)

_OFFENSE_ROLES = {"passer", "rusher", "receiver"}


def _field_position_ep(yardline_100: float, down: int | None) -> float:
    """Rough expected points for the offense at this spot (fit to PFR's values)."""
    ep = 6.2 - 0.07 * yardline_100
    if down:
        ep -= 0.45 * (down - 1)
    return ep


def _viterbi(emit: list[list[float]], trans: list[list[float] | None]) -> list[int]:
    """Cheapest state path. emit[i][s]; trans[i] = [cost_same, cost_switch] from i-1 to i."""
    n = len(emit)
    cost = [emit[0][0], emit[0][1]]
    back: list[list[int]] = []
    for i in range(1, n):
        same, switch = trans[i] or (0.0, 0.0)
        new, bp = [0.0, 0.0], [0, 0]
        for s in (0, 1):
            stay, move = cost[s] + same, cost[1 - s] + switch
            new[s], bp[s] = (stay, s) if stay <= move else (move, 1 - s)
            new[s] += emit[i][s]
        back.append(bp)
        cost = new
    s = 0 if cost[0] <= cost[1] else 1
    path = [s]
    for bp in reversed(back):
        s = bp[s]
        path.append(s)
    return path[::-1]


def _player_roles(r: dict) -> list[str]:
    """Names on this play that belong to the perspective team (offense / kicking team)."""
    names = []
    if r["play_type"] in ("pass", "run", "qb_kneel", "qb_spike"):
        names += [r[c] for c in _OFFENSE_ROLES if r[c]]
    elif r["play_type"] == "punt" and r["punter"]:
        names.append(r["punter"])
    elif r["play_type"] in ("field_goal", "extra_point", "kickoff") and r["kicker"]:
        names.append(r["kicker"])
    return names


def _infer_game(rows: list[dict], home: str, away: str,
                roster_side: Callable[[str], int | None] = lambda name: None) -> list[str | None]:
    """Perspective team (offense / kicking team) for each play of one game; state 0 = home.

    roster_side(name) is 0 (home) or 1 (away) when the name is on exactly one
    of the two teams' rosters, else None.
    """
    n = len(rows)
    emit = [[0.0, 0.0] for _ in range(n)]
    trans: list[list[float] | None] = [None] * n
    informative = [False] * n

    prev_h = prev_a = 0
    for i, r in enumerate(rows):
        if i > 0:
            p = rows[i - 1]
            a, b = p["exp_pts_after"], r["exp_pts_before"]
            if a is not None and b is not None and not (abs(a) < _TOL and abs(b) < _TOL):
                if abs(b - a) <= _TOL:
                    trans[i] = [0.0, _LINK_COST]
                elif abs(b + a) <= _TOL:
                    trans[i] = [_LINK_COST, 0.0]
            if trans[i] is None and (
                (p["play_type"] == "extra_point" or p["two_point_attempt"] or p["touchdown"])
                and r["play_type"] in ("extra_point", "kickoff") or r["two_point_attempt"]
            ):
                trans[i] = [0.0, _KICK_PRIOR_COST]

        # Score anchor.
        h = prev_h if r["home_score"] is None else r["home_score"]
        a_ = prev_a if r["away_score"] is None else r["away_score"]
        if h != prev_h or a_ != prev_a:
            scorer_home = (h - prev_h) > (a_ - prev_a)
            after = r["exp_pts_after"]
            persp_home = None
            if r["play_type"] == "extra_point" or r["two_point_attempt"]:
                persp_home = scorer_home
            elif after is not None and abs(after) >= 1.5:
                persp_home = scorer_home if after > 0 else not scorer_home
            if persp_home is not None:
                emit[i][1 if persp_home else 0] += _SCORE_COST
                informative[i] = True
        prev_h, prev_a = h, a_

        # Field position.
        side, yl, before = r["yardline_side"], r["yardline"], r["exp_pts_before"]
        if side in (home, away) and yl is not None and before is not None and r["down"]:
            yl100_home = 100 - yl if side == home else yl
            emit[i][0] += _FIELD_WEIGHT * abs(before - _field_position_ep(yl100_home, r["down"]))
            emit[i][1] += _FIELD_WEIGHT * abs(before - _field_position_ep(100 - yl100_home, r["down"]))
            informative[i] = True

        # Rosters: the only evidence in the few games where PFR has no
        # expected points.
        for name in _player_roles(r):
            side_ = roster_side(name)
            if side_ is not None:
                emit[i][1 - side_] += _ROSTER_COST
                informative[i] = True

    path = _viterbi(emit, trans)

    # Second pass: player consistency.
    votes: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        for name in _player_roles(r):
            votes.setdefault(name, [0, 0])[path[i]] += 1
    team_of = {}
    for name, (h_votes, a_votes) in votes.items():
        total = h_votes + a_votes
        if total >= 3 and max(h_votes, a_votes) / total >= 0.7:
            team_of[name] = 0 if h_votes > a_votes else 1
    for i, r in enumerate(rows):
        for name in _player_roles(r):
            if name in team_of:
                emit[i][1 - team_of[name]] += _PLAYER_COST
                informative[i] = True
    path = _viterbi(emit, trans)

    # A play is only assigned if something ties it to a team: its own evidence
    # or a continuity link to a neighbour.
    linked = [informative[i] or (trans[i] is not None) or (i + 1 < n and trans[i + 1] is not None)
              for i in range(n)]
    return [(home if path[i] == 0 else away) if linked[i] and rows[i]["play_type"] is not None else None
            for i in range(n)]


def _roster_lookup(rosters: pl.DataFrame | None) -> dict[tuple, set]:
    teams: dict[tuple, set] = {}
    if rosters is None:
        return teams
    for season, team, name in rosters.select("season", "team", "player_name").iter_rows():
        if name:
            teams.setdefault((season, name_key(name)), set()).add(team)
    return teams


def infer_possession(df: pl.DataFrame, rosters: pl.DataFrame | None = None) -> pl.DataFrame:
    """Add posteam, defteam, yardline_100 and drive to cleaned historical play-by-play.

    rosters (season, team, player_name; dim_games team codes) adds roster
    evidence for the players on each play.
    """
    df = df.sort("game_id", "play_seq")
    on_roster = _roster_lookup(rosters)
    cols = ["exp_pts_before", "exp_pts_after", "home_score", "away_score", "yardline_side", "yardline",
            "down", "play_type", "two_point_attempt", "touchdown", "passer", "rusher", "receiver",
            "punter", "kicker"]
    perspective: list[str | None] = []
    for (_game_id,), g in df.group_by(["game_id"], maintain_order=True):
        season = g["season"][0] if "season" in g.columns else None
        home, away = g["home_team"][0], g["away_team"][0]

        def roster_side(name, season=season, home=home, away=away):
            teams = on_roster.get((season, name_key(name)), set())
            if (home in teams) == (away in teams):
                return None
            return 0 if home in teams else 1

        perspective += _infer_game(g.select(cols).to_dicts(), home, away, roster_side)
    df = df.with_columns(pl.Series("_ep_team", perspective, dtype=pl.Utf8))
    other = pl.when(pl.col("_ep_team") == pl.col("home_team")).then(pl.col("away_team")).otherwise(pl.col("home_team"))
    # Kickoffs are from the kicking team's view; nflverse's posteam is the receiver.
    posteam = pl.when(pl.col("_ep_team").is_null()).then(None) \
        .when(pl.col("play_type") == "kickoff").then(other).otherwise(pl.col("_ep_team"))
    df = df.with_columns(posteam.alias("posteam"))
    df = df.with_columns(
        pl.when(pl.col("posteam").is_null()).then(None)
        .when(pl.col("posteam") == pl.col("home_team")).then(pl.col("away_team"))
        .otherwise(pl.col("home_team")).alias("defteam"),
    )
    # Distance to the opponent's goal line, from the offense's view.
    on_field = ((pl.col("yardline_side") == pl.col("home_team"))
                | (pl.col("yardline_side") == pl.col("away_team"))).fill_null(False)
    df = df.with_columns(
        pl.when(pl.col("posteam").is_null() | pl.col("yardline").is_null() | ~on_field).then(None)
        .when(pl.col("yardline_side") == pl.col("posteam")).then(100 - pl.col("yardline"))
        .otherwise(pl.col("yardline")).cast(pl.Int16).alias("yardline_100"),
    )
    return _number_drives(df.drop("_ep_team"))


def _number_drives(df: pl.DataFrame) -> pl.DataFrame:
    """Add drive, numbered from 1 within each game.

    A drive starts on a kickoff, when posteam changes, and at the start of the
    second half and of overtime. Kickoffs belong to the receiving team's drive,
    and tries to the scoring team's, as in nflverse. Plays with no posteam
    (timeouts, end of quarter) take the drive in progress.
    """
    half = pl.when(pl.col("quarter") <= 2).then(1).when(pl.col("quarter") <= 4).then(2).otherwise(pl.col("quarter"))
    has = pl.col("posteam").is_not_null()
    df = df.with_columns(_half=half)
    # Previous assigned play's team and half, carried forward over unassigned plays.
    df = df.with_columns(
        _prev_team=pl.when(has).then(pl.col("posteam")).forward_fill().shift(1).over("game_id"),
        _prev_half=pl.when(has).then(pl.col("_half")).forward_fill().shift(1).over("game_id"),
    )
    starts = has & (
        pl.col("_prev_team").is_null()
        | (pl.col("posteam") != pl.col("_prev_team"))
        | (pl.col("_half") != pl.col("_prev_half"))
        | (pl.col("play_type") == "kickoff")
    )
    df = df.with_columns(_start=starts.cast(pl.Int16))
    drive = pl.col("_start").cum_sum().over("game_id")
    df = df.with_columns(pl.when(drive > 0).then(drive).otherwise(None).cast(pl.Int16).alias("drive"))
    df = df.with_columns(pl.col("drive").backward_fill().over("game_id"))
    return df.drop("_half", "_prev_team", "_prev_half", "_start")
