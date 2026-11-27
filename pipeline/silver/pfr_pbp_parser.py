"""Parse Pro-Football-Reference play-by-play `detail` text (pre-1999 games).

PFR's historical play-by-play has no structured columns for who did what,
only a prose description per play, e.g.

    "Jamal Anderson middle for 3 yards (tackle by Sean Gilbert)"
    "Kerry Collins pass complete to Mark Carrier for 22 yards"

`parse_detail()` derives a play_type plus per-role player names from that
text with a set of ordered regexes. Ported from the nfldata.org legacy
Patriots parser (ne_legacy_parser.py / enrich-legacy-pbp.py).

Deliberately conservative: rare phrasings (multi-clause fumble/interception
combos, blocked punts, penalty-interrupted fragments) fall through to
play_type 'other' with no players, rather than being guessed at. Player
names are free text, not gsis_ids.
"""

import re

NAME = r"[A-Z][\w'.\-]*(?:\s+(?:van|von|der|den|de|la|St\.|of)\s+[A-Z][\w'.\-]*|\s+[A-Z][\w'.\-]*)*"
YARDS = r"for (?:(?P<y>-?\d+) yards?|no gain)"

NO_PLAY_RE = re.compile(r"\(no play\)\s*$|play nullified", re.IGNORECASE)
PENALTY_ONLY_RE = re.compile(r"^Penalty on ")
TWO_PT_RE = re.compile(r"^Two Point Attempt:\s*")
SPIKE_RE = re.compile(rf"^(?P<p>{NAME}) spiked the ball")
KNEEL_RE = re.compile(rf"^(?P<p>{NAME}) kneels for (?P<y>-?\d+) yards")
SCRAMBLE_RE = re.compile(rf"^(?P<p>{NAME}) scrambles(?:\s+[a-z][a-z' ]*?)? {YARDS}(?P<td>, touchdown)?")
# Split sacks name two defenders ("sacked by A and B for 8 yards"); sacker is the first.
SACK_RE = re.compile(
    rf"^(?P<p>{NAME}) sacked(?: by (?P<sacker>{NAME})(?: and {NAME})?)?(?: for (?P<y>-?\d+) yards?)?"
)
INT_RE = re.compile(
    rf"^(?P<passer>{NAME}) pass (?:incomplete )?(?:intended for (?P<receiver>{NAME}) )?"
    rf"is intercepted by (?P<interceptor>{NAME})"
)
# An interception where the defender fumbles on the return:
# "X pass intended for Y. Z fumbles is intercepted by Z ..." (the same Z
# twice, which also pins down where Y ends when it has initials).
INT_FUMBLE_RE = re.compile(
    rf"^(?P<passer>{NAME}) pass(?: intended for (?P<receiver>.+?))?\. (?P<interceptor>{NAME}) fumbles "
    rf"is intercepted by (?P=interceptor)\b"
)
# A botched snap, officially a rush by the player who fumbled (0 yards here;
# PFR's text rarely says where the ball was recovered relative to the snap).
ABORTED_RE = re.compile(rf"^(?P<p>{NAME}) (?:aborted snap|fumbles(?: \(aborted\))?, recovered by)")
PASS_COMPLETE_RE = re.compile(
    rf"^(?P<passer>{NAME}) pass complete to (?P<receiver>{NAME}) {YARDS}(?P<td>, touchdown)?"
)
PASS_INCOMPLETE_RE = re.compile(rf"^(?P<passer>{NAME}) pass incomplete(?: intended for (?P<receiver>{NAME}))?")
RUSH_RE = re.compile(rf"^(?P<p>{NAME})\s*(?:[a-z][a-z' ]*?\s)?{YARDS}(?P<td>, touchdown)?")
KICKOFF_RE = re.compile(
    rf"^(?P<p>{NAME}) kicks (?:off|onside) (?P<y>\d+) yards?(?:, returned by (?P<returner>{NAME}) for)?"
)
PUNT_RE = re.compile(rf"^(?P<p>{NAME}) punts (?P<y>\d+) yards?(?:, returned by (?P<returner>{NAME}) for)?")
FIELD_GOAL_RE = re.compile(
    rf"^(?P<p>{NAME}) (?P<y>\d+) yard field goal (?P<result>good|no good)(?: blocked by (?P<blocker>{NAME}))?"
)
EXTRA_POINT_RE = re.compile(rf"^(?P<p>{NAME}) kicks extra point (?P<result>good|no good)")

TACKLE_RE = re.compile(rf"\(tackle by (?P<t1>{NAME})(?: and (?P<t2>{NAME}))?\)")
FUMBLE_FORCED_RE = re.compile(rf"fumbles?\s*\(forced by (?P<forcer>{NAME})\)")
FUMBLE_RECOVERED_RE = re.compile(rf"recovered by (?P<recoverer>{NAME})")

# Ordered: earlier patterns win (e.g. scramble/kneel before the generic rush).
_CLASSIFIERS = [
    ("spike", SPIKE_RE),
    ("kneel", KNEEL_RE),
    ("scramble", SCRAMBLE_RE),
    ("int", INT_FUMBLE_RE),
    ("int", INT_RE),
    ("sack", SACK_RE),
    ("pass_complete", PASS_COMPLETE_RE),
    ("pass_incomplete", PASS_INCOMPLETE_RE),
    ("kickoff", KICKOFF_RE),
    ("aborted", ABORTED_RE),
    ("punt", PUNT_RE),
    ("field_goal", FIELD_GOAL_RE),
    ("extra_point", EXTRA_POINT_RE),
    ("rush", RUSH_RE),
]

# Pass-type patterns come first; any other text with " pass " in it is a
# pass we couldn't parse, checked before the kicking and rushing patterns.
_FIRST_NON_PASS = next(i for i, (c, _) in enumerate(_CLASSIFIERS) if c == "kickoff")

# Same play_type vocabulary as nflfastR's fact_plays (sacks are pass plays,
# kneels are qb_kneel, scrambles are runs).
PLAY_TYPE_BY_CATEGORY = {
    "pass_complete": "pass",
    "pass_incomplete": "pass",
    "pass_unmatched": "pass",
    "int": "pass",
    "sack": "pass",
    "rush": "run",
    "scramble": "run",
    "aborted": "run",
    "kneel": "qb_kneel",
    "spike": "qb_spike",
    "kickoff": "kickoff",
    "punt": "punt",
    "field_goal": "field_goal",
    "extra_point": "extra_point",
    "penalty_only": "no_play",
    "no_play": "no_play",
}

# Which regex group fills which output column, per category.
ROLE_FOR_CATEGORY = {
    "pass_complete": {"passer": "passer", "receiver": "receiver"},
    "pass_incomplete": {"passer": "passer", "receiver": "receiver"},
    "int": {"passer": "passer", "receiver": "receiver", "interceptor": "interceptor"},
    "sack": {"p": "passer", "sacker": "sacker"},
    "rush": {"p": "rusher"},
    "scramble": {"p": "rusher"},
    "aborted": {"p": "rusher"},
    "kneel": {"p": "rusher"},
    "spike": {"p": "passer"},
    "kickoff": {"p": "kicker", "returner": "returner"},
    "punt": {"p": "punter", "returner": "returner"},
    "field_goal": {"p": "kicker"},
    "extra_point": {"p": "kicker"},
}

# Categories whose `y` group is yards gained by the offense.
_YARDS_GAINED_CATEGORIES = {"pass_complete", "rush", "scramble", "kneel", "sack", "aborted"}

PLAYER_COLUMNS = [
    "passer", "rusher", "receiver", "interceptor", "sacker",
    "kicker", "punter", "returner",
    "tackler_1", "tackler_2", "forced_fumble_player", "fumble_recovery_player",
    "penalized_player",
]
OUTPUT_COLUMNS = ["play_type", "two_point_attempt", "yards_gained", "touchdown", *PLAYER_COLUMNS]


def classify(detail: str) -> tuple[str, dict]:
    """Return (category, regex groups) for one play's detail text."""
    if NO_PLAY_RE.search(detail):
        return "no_play", {}
    if PENALTY_ONLY_RE.match(detail):
        return "penalty_only", {}
    for category, regex in _CLASSIFIERS[:_FIRST_NON_PASS]:
        m = regex.match(detail)
        if m:
            return category, m.groupdict()
    if " pass " in detail.lower() and "interference" not in detail.lower():
        return "pass_unmatched", {}
    for category, regex in _CLASSIFIERS[_FIRST_NON_PASS:]:
        m = regex.match(detail)
        if m:
            return category, m.groupdict()
    return "other", {}


# NAME allows periods (initials: "J.J. Stokes"), so it can run on into the
# next sentence: "sacked by Clyde Simmons. John Elway fumbles". A ". " after
# two lowercase letters ends a sentence, not an initial or "Jr.".
_RUN_ON_RE = re.compile(r"(?<=[a-z]{2})\. [A-Z].*$")


def clean_name(name: str | None) -> str | None:
    """Strip whitespace, a run-on next sentence, and a trailing sentence
    period NAME can swallow."""
    if not name:
        return None
    name = _RUN_ON_RE.sub("", name.strip())
    if name.endswith(".") and not re.search(r"\b[A-Z]\.$", name):
        name = name[:-1]
    return name or None


def _penalized_player(detail: str) -> str | None:
    m = PENALTY_ONLY_RE.match(detail)
    if not m:
        return None
    who = re.split(r"[:,]", detail[m.end():], maxsplit=1)[0].strip()
    if re.fullmatch(r"[A-Z]{2,4}", who):  # a team code, not a person
        return None
    return clean_name(who)


def parse_detail(detail: str | None) -> dict:
    """Derive play_type, yards, touchdown, and player roles from detail text."""
    out: dict = {c: None for c in OUTPUT_COLUMNS}
    out["two_point_attempt"] = False
    out["touchdown"] = False
    if not detail:
        return out

    text = detail
    m = TWO_PT_RE.match(text)
    if m:
        out["two_point_attempt"] = True
        text = text[m.end():]

    category, info = classify(text)
    if category == "other" and re.match(r"^\S.* (won|wins) the coin toss", text):
        out["play_type"] = None  # coin toss / administrative row, not a play
    else:
        out["play_type"] = PLAY_TYPE_BY_CATEGORY.get(category, "other")

    for group, column in ROLE_FOR_CATEGORY.get(category, {}).items():
        out[column] = clean_name(info.get(group))

    if category in _YARDS_GAINED_CATEGORIES:
        y = info.get("y")
        out["yards_gained"] = int(y) if y else 0
        if category == "sack" and out["yards_gained"] > 0:
            out["yards_gained"] = -out["yards_gained"]

    if category not in ("no_play", "penalty_only") and not out["two_point_attempt"]:
        out["touchdown"] = "touchdown" in text.lower()

    if category == "penalty_only":
        out["penalized_player"] = _penalized_player(text)

    t = TACKLE_RE.search(text)
    if t:
        out["tackler_1"], out["tackler_2"] = clean_name(t.group("t1")), clean_name(t.group("t2"))
    f = FUMBLE_FORCED_RE.search(text)
    if f:
        out["forced_fumble_player"] = clean_name(f.group("forcer"))
    r = FUMBLE_RECOVERED_RE.search(text)
    if r:
        out["fumble_recovery_player"] = clean_name(r.group("recoverer"))
    return out
