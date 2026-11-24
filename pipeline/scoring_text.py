"""Structured scoring-play fields <-> Pro-Football-Reference style descriptions.

fact_game_scoring has PFR scoring summaries (1970 to part of 2007) and rows
derived from nflverse play-by-play (the rest). Both get the same structured
columns, and one description format, PFR's:

    Jason Elam 43 yard field goal
    Rod Smith 22 yard pass from John Elway (Jason Elam kick)
    Terrell Davis 1 yard rush (pass failed)
    Ty Law 46 yard interception return (Adam Vinatieri kick failed)
    Shaun Gayle defensive fumble recovery in end zone (Kevin Butler kick)
    Safety, Kidd downed ball in end zone

`parse_pfr()` turns a PFR description into fields; `format_scoring()` turns
fields back into the description. For PFR rows the two round-trip; nflverse
rows are built from play-by-play fields and formatted.
"""

import re

# scoring_method values and the PFR phrase each one is written as.
TD_METHOD_PHRASES = {
    "pass": "pass",
    "rush": "rush",
    "interception_return": "interception return",
    "fumble_return": "fumble return",
    "defensive_fumble_return": "defensive fumble return",
    "offensive_fumble_return": "offensive fumble return",
    "special_teams_fumble_return": "special teams fumble return",
    "punt_return": "punt return",
    "kickoff_return": "kickoff return",
    "blocked_punt_return": "blocked punt return",
    "blocked_field_goal_return": "blocked field goal return",
    "field_goal_return": "field goal return",
}
# Touchdowns with no yardage: the ball was recovered or caught in the end zone.
TD_END_ZONE_PHRASES = {
    "fumble_recovery": "fumble recovery in end zone",
    "defensive_fumble_recovery": "defensive fumble recovery in end zone",
    "offensive_fumble_recovery": "offensive fumble recovery in end zone",
    "special_teams_fumble_recovery": "special teams fumble recovery in end zone",
    "blocked_punt_recovery": "blocked punt recovery in end zone",
    "interception": "interception in end zone",
}
_PHRASE_TO_METHOD = {v: k for k, v in {**TD_METHOD_PHRASES, **TD_END_ZONE_PHRASES}.items()}

FIELDS = [
    "scoring_type", "scoring_method", "yards", "scorer", "passer",
    "try_type", "try_result", "try_player", "try_passer", "safety_text",
]

_YARDS_RE = re.compile(
    r"^(?P<scorer>.+?) (?P<yards>-?\d+) yard (?P<phrase>"
    + "|".join(sorted(map(re.escape, TD_METHOD_PHRASES.values()), key=len, reverse=True))
    + r")(?: from (?P<passer>.+?))?(?: \((?P<try>[^()]*)\))?$"
)
_END_ZONE_RE = re.compile(
    r"^(?P<scorer>.+?) (?P<phrase>"
    + "|".join(sorted(map(re.escape, TD_END_ZONE_PHRASES.values()), key=len, reverse=True))
    + r")(?: \((?P<try>[^()]*)\))?$"
)
_FIELD_GOAL_RE = re.compile(r"^(?P<scorer>.+?) (?P<yards>\d+) yard field goal$")
_SAFETY_RE = re.compile(r"^Safety(?:,\s*(?P<text>.*))?$")

_TRY_PATTERNS = [
    (re.compile(r"^(?P<player>.+?) kick$"), "kick", "good"),
    (re.compile(r"^(?P<player>.+?) kick failed$"), "kick", "failed"),
    (re.compile(r"^kick failed$"), "kick", "failed"),
    (re.compile(r"^(?P<player>.+?) pass from (?P<passer>.+)$"), "pass", "good"),
    (re.compile(r"^two point pass successful$"), "pass", "good"),
    (re.compile(r"^pass failed$"), "pass", "failed"),
    (re.compile(r"^(?P<player>.+?) run$"), "run", "good"),
    (re.compile(r"^run failed$"), "run", "failed"),
]


def _empty() -> dict:
    return {f: None for f in FIELDS}


def _parse_try(text: str | None) -> dict | None:
    """Fields for the parenthesised try, or None if it isn't a known form."""
    out = {"try_type": None, "try_result": None, "try_player": None, "try_passer": None}
    if text is None:
        return out
    for regex, try_type, result in _TRY_PATTERNS:
        m = regex.match(text)
        if m:
            g = m.groupdict()
            out.update(try_type=try_type, try_result=result,
                       try_player=g.get("player"), try_passer=g.get("passer"))
            return out
    return None


def parse_pfr(description: str | None) -> dict:
    """Structured fields from a PFR scoring description.

    Unrecognised text gives scoring_type None (the description is kept as-is).
    """
    out = _empty()
    if not description:
        return out
    text = description.strip()

    m = _SAFETY_RE.match(text)
    if m:
        out.update(scoring_type="safety", scoring_method="safety", safety_text=m.group("text") or None)
        return out
    m = _FIELD_GOAL_RE.match(text)
    if m:
        out.update(scoring_type="field_goal", scoring_method="field_goal",
                   scorer=m.group("scorer"), yards=int(m.group("yards")))
        return out
    m = _YARDS_RE.match(text) or _END_ZONE_RE.match(text)
    if m:
        g = m.groupdict()
        tried = _parse_try(g.get("try"))
        if tried is not None:
            out.update(scoring_type="touchdown", scoring_method=_PHRASE_TO_METHOD[g["phrase"]],
                       scorer=g["scorer"], passer=g.get("passer"),
                       yards=int(g["yards"]) if g.get("yards") else None, **tried)
    return out


def _format_try(f: dict) -> str:
    t, ok, player, passer = f.get("try_type"), f.get("try_result") == "good", f.get("try_player"), f.get("try_passer")
    if t == "kick":
        if ok:
            return f" ({player} kick)" if player else ""
        return f" ({player} kick failed)" if player else " (kick failed)"
    if t == "pass":
        if ok:
            return f" ({player} pass from {passer})" if player and passer else " (two point pass successful)"
        return " (pass failed)"
    if t == "run":
        if ok:
            return f" ({player} run)" if player else ""
        return " (run failed)"
    return ""


def format_scoring(f: dict) -> str | None:
    """PFR-style description from structured fields, or None if they're incomplete."""
    kind = f.get("scoring_type")
    if kind == "safety":
        return f"Safety, {f['safety_text']}" if f.get("safety_text") else "Safety"
    if kind == "field_goal":
        if not f.get("scorer") or f.get("yards") is None:
            return None
        return f"{f['scorer']} {f['yards']} yard field goal"
    if kind == "touchdown":
        method, scorer = f.get("scoring_method"), f.get("scorer")
        if not scorer:
            return None
        if method in TD_END_ZONE_PHRASES:
            return f"{scorer} {TD_END_ZONE_PHRASES[method]}{_format_try(f)}"
        if method not in TD_METHOD_PHRASES or f.get("yards") is None:
            return None
        if method == "pass" and not f.get("passer"):
            return None
        passer = f" from {f['passer']}" if method == "pass" else ""
        return f"{scorer} {f['yards']} yard {TD_METHOD_PHRASES[method]}{passer}{_format_try(f)}"
    return None


# ── nflverse play-by-play -> structured fields ───────────────────────────────

NFLVERSE_FIELDS = [
    "scoring_type", "scoring_method", "yards", "scorer", "scorer_id", "passer", "passer_id",
    "try_type", "try_result", "try_player", "try_player_id", "try_passer", "try_passer_id",
]


def _flag(v) -> bool:
    return bool(v) and v == v  # not None, not 0, not NaN


def _int(v) -> int | None:
    return None if v is None or v != v else int(v)


_TD_YARDS_RE = re.compile(r"for (-?\d+) yards?,? TOUCHDOWN", re.IGNORECASE)


def _text_yards(p: dict) -> int | None:
    """Yardage of the touchdown run/return from the play text ("for 61 yards, TOUCHDOWN")."""
    found = _TD_YARDS_RE.findall(p.get("desc") or "")
    return int(found[-1]) if found else None


def _td_method(p: dict) -> tuple[str | None, int | None]:
    """(scoring_method, yards) for an nflverse touchdown play."""
    play_type = p.get("play_type")
    offense_scored = p.get("td_team") is not None and p.get("td_team") == p.get("posteam")

    def ret_yards(*cols):
        # Return yardage fields are sometimes 0 on return TDs; the text has it.
        for c in cols:
            if _int(p.get(c)):
                return _int(p.get(c))
        return _text_yards(p)

    if _flag(p.get("pass_touchdown")):
        return "pass", _int(p.get("yards_gained"))
    if _flag(p.get("rush_touchdown")):
        return "rush", _int(p.get("yards_gained"))
    if play_type == "kickoff":  # posteam is the receiving team
        if offense_scored:
            return "kickoff_return", ret_yards("return_yards")
        yards = ret_yards("fumble_recovery_1_yards")  # kicking team recovered (onside / muff)
        return ("special_teams_fumble_return", yards) if yards else ("special_teams_fumble_recovery", None)
    if play_type == "punt" and not offense_scored:
        if _flag(p.get("punt_blocked")):
            yards = ret_yards("return_yards", "fumble_recovery_1_yards")
            return ("blocked_punt_return", yards) if yards else ("blocked_punt_recovery", None)
        if not _flag(p.get("fumble")):
            return "punt_return", ret_yards("return_yards")
    if p.get("field_goal_result") in ("blocked", "missed") and not offense_scored:
        method = "blocked_field_goal_return" if p["field_goal_result"] == "blocked" else "field_goal_return"
        return method, ret_yards("return_yards", "fumble_recovery_1_yards")
    if _flag(p.get("interception")) and not offense_scored:
        yards = ret_yards("return_yards")
        return ("interception_return", yards) if yards else ("interception", None)
    if _flag(p.get("fumble")):
        yards = ret_yards("fumble_recovery_1_yards")
        side = "offensive" if offense_scored else "defensive"
        return (f"{side}_fumble_return", yards) if yards else (f"{side}_fumble_recovery", None)
    return None, None


def nflverse_scoring_fields(row: dict, names: dict) -> dict:
    """Structured fields for one derived scoring event.

    `row` has the scoring play's nflverse columns plus its try play's, prefixed
    try_. `names` maps (gsis_id, season) and gsis_id -> full name, so
    "15-P.Mahomes" style abbreviations become "Patrick Mahomes" where the ID
    is known (see the loader for where the names come from).
    """
    season = row.get("season")

    def person(pid, fallback):
        if not pid:
            return fallback, None
        return names.get((pid, season)) or names.get(pid) or fallback, pid

    out = {f: None for f in NFLVERSE_FIELDS}
    pts = row.get("event_pts")
    if row.get("field_goal_result") == "made":  # play_type is NULL on some penalty plays
        out["scoring_type"] = out["scoring_method"] = "field_goal"
        out["yards"] = _int(row.get("kick_distance"))
        out["scorer"], out["scorer_id"] = person(row.get("kicker_player_id"), row.get("kicker_player_name"))
        return out
    if pts == 2 and _flag(row.get("defensive_two_point_conv")):
        out["scoring_type"] = out["scoring_method"] = "defensive_two_point"
        return out
    if pts == 2:
        out["scoring_type"] = out["scoring_method"] = "safety"
        out["scorer"], out["scorer_id"] = person(row.get("safety_player_id"), row.get("safety_player_name"))
        return out
    if not row.get("td_team") and not _flag(row.get("pass_touchdown")) and not _flag(row.get("rush_touchdown")):
        return out

    out["scoring_type"] = "touchdown"
    out["scoring_method"], out["yards"] = _td_method(row)
    out["scorer"], out["scorer_id"] = person(row.get("td_player_id"), row.get("td_player_name"))
    if out["scoring_method"] == "pass":
        out["passer"], out["passer_id"] = person(row.get("passer_player_id"), row.get("passer_player_name"))

    xp, two = row.get("try_extra_point_result"), row.get("try_two_point_conv_result")
    if xp:
        out["try_type"], out["try_result"] = "kick", "good" if xp == "good" else "failed"
        out["try_player"], out["try_player_id"] = person(row.get("try_kicker_player_id"),
                                                         row.get("try_kicker_player_name"))
    elif two:
        out["try_result"] = "good" if two == "success" else "failed"
        try_text = (row.get("try_desc") or "").lower()
        if row.get("try_play_type") == "pass" or (row.get("try_play_type") != "run" and " pass" in try_text):
            out["try_type"] = "pass"
            if out["try_result"] == "good":
                out["try_player"], out["try_player_id"] = person(row.get("try_receiver_player_id"),
                                                                 row.get("try_receiver_player_name"))
                out["try_passer"], out["try_passer_id"] = person(row.get("try_passer_player_id"),
                                                                 row.get("try_passer_player_name"))
        else:
            out["try_type"] = "run"
            if out["try_result"] == "good":
                out["try_player"], out["try_player_id"] = person(row.get("try_rusher_player_id"),
                                                                 row.get("try_rusher_player_name"))
    elif row.get("try_pts") == 1:
        # A try that scored but isn't flagged as one (e.g. re-kicked after a penalty).
        out["try_type"], out["try_result"] = "kick", "good"
        out["try_player"], out["try_player_id"] = person(row.get("try_kicker_player_id"),
                                                         row.get("try_kicker_player_name"))
    elif row.get("try_pts") == 2:
        try_text = (row.get("try_desc") or "").lower()
        out["try_type"], out["try_result"] = ("pass" if " pass" in try_text else "run"), "good"
    return out
