"""Match player names in pre-1999 play-by-play to gsis_ids.

PFR's play-by-play gives names only ("John Elway"). nflverse rosters
(fact_rosters, in dim_games' team codes before 1999) list every player on
every team back to 1920 with a gsis_id,
so a name can be matched against the rosters of the two teams in the game.
In order, a name gets an id from the first of these that finds exactly one
player:

1. the same name on either team's roster that season
2. the same name on any roster that season (players missing from a team's
   roster, e.g. after a mid-season move)
3. the same last name and first initial on either team's roster
   ("Chuck Evans" for "Charles Evans", "Cam Cleeland" for "Cameron Cleeland")

A name that matches more than one player at a step is left without an id
rather than guessed.
"""

import re
import unicodedata
from collections import defaultdict

import polars as pl

# Player-role columns of fact_historical_plays; each has a matching <col>_id.
NAME_COLUMNS = [
    "passer", "rusher", "receiver", "interceptor", "sacker", "kicker", "punter", "returner",
    "tackler_1", "tackler_2", "forced_fumble_player", "fumble_recovery_player", "penalized_player",
]

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

def _tokens(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[.,']", " ", s)
    toks = s.split()
    while len(toks) > 2 and toks[-1] in _SUFFIXES:
        toks.pop()
    # Leading initials -> one token: "n d kalu" -> "nd kalu".
    i = 0
    while i < len(toks) - 1 and len(toks[i]) == 1:
        i += 1
    if i > 1:
        toks = ["".join(toks[:i])] + toks[i:]
    # Drop middle initials: "mike d jones" -> "mike jones".
    if len(toks) > 2:
        toks = [toks[0]] + [t for t in toks[1:-1] if len(t) > 1] + [toks[-1]]
    return toks


def name_key(name: str) -> str:
    return " ".join(_tokens(name))


def initial_key(name: str) -> str | None:
    toks = _tokens(name)
    if len(toks) < 2:
        return None
    return f"{toks[0][0]} {toks[-1]}"


def match_player_ids(names: pl.DataFrame, rosters: pl.DataFrame) -> pl.DataFrame:
    """names: season, home_team, away_team, name. rosters: season, team, player_name, player_id.

    Returns names with a player_id column (null when no unique match).
    """
    by_team: dict[tuple, set] = defaultdict(set)
    by_season: dict[tuple, set] = defaultdict(set)
    by_initial: dict[tuple, set] = defaultdict(set)
    for season, team, player_name, pid in rosters.select("season", "team", "player_name", "player_id").iter_rows():
        if player_name is None or pid is None:
            continue
        k = name_key(player_name)
        by_team[(season, team, k)].add(pid)
        by_season[(season, k)].add(pid)
        ik = initial_key(player_name)
        if ik:
            by_initial[(season, team, ik)].add(pid)

    def lookup(season, home, away, name):
        if name is None:
            return None
        teams = (home, away)  # fact_rosters uses dim_games codes before 1999
        k = name_key(name)
        ids = set().union(*(by_team.get((season, t, k), set()) for t in teams))
        if not ids:
            ids = by_season.get((season, k), set())
        if not ids:
            ik = initial_key(name)
            if ik:
                ids = set().union(*(by_initial.get((season, t, ik), set()) for t in teams))
        return next(iter(ids)) if len(ids) == 1 else None

    ids = [lookup(*r) for r in names.select("season", "home_team", "away_team", "name").iter_rows()]
    return names.with_columns(pl.Series("player_id", ids, dtype=pl.Utf8))
