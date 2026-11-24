import pytest

from pipeline.scoring_text import format_scoring, parse_pfr


@pytest.mark.parametrize("text, expected", [
    ("Jason Elam 43 yard field goal ", {"scoring_type": "field_goal", "scorer": "Jason Elam", "yards": 43}),
    ("Rod Smith 22 yard pass from John Elway (Jason Elam kick)",
     {"scoring_method": "pass", "scorer": "Rod Smith", "passer": "John Elway", "yards": 22,
      "try_type": "kick", "try_result": "good", "try_player": "Jason Elam"}),
    ("Mark van Eeghen 1 yard rush (Uwe von Schamann kick failed)",
     {"scorer": "Mark van Eeghen", "try_type": "kick", "try_result": "failed", "try_player": "Uwe von Schamann"}),
    ("Marion Barber III 1 yard pass from Tony Romo", {"scorer": "Marion Barber III", "try_type": None}),
    ("Duce Staley 20 yard rush (Donovan McNabb run)",
     {"scoring_method": "rush", "try_type": "run", "try_result": "good", "try_player": "Donovan McNabb"}),
    ("Keith Poole 20 yard pass from Billy Joe Tolliver (Cam Cleeland pass from Billy Joe Tolliver)",
     {"passer": "Billy Joe Tolliver", "try_type": "pass", "try_player": "Cam Cleeland",
      "try_passer": "Billy Joe Tolliver"}),
    ("Kordell Stewart 45 yard rush (two point pass successful)",
     {"try_type": "pass", "try_result": "good", "try_player": None}),
    ("Terry Fair 35 yard defensive fumble return (pass failed)",
     {"scoring_method": "defensive_fumble_return", "try_type": "pass", "try_result": "failed"}),
    ("Shaun Gayle defensive fumble recovery in end zone (kick failed)",
     {"scoring_method": "defensive_fumble_recovery", "yards": None, "try_result": "failed", "try_player": None}),
    ("Ray McElroy 42 yard blocked field goal return", {"scoring_method": "blocked_field_goal_return"}),
    ("Safety, Kidd downed ball in end zone ", {"scoring_type": "safety", "safety_text": "Kidd downed ball in end zone"}),
    ("Safety, ", {"scoring_type": "safety", "safety_text": None}),
    ("Charle Young 32 yard pass from Dave Krieg (kick failed, Steve Largent XP)", {"scoring_type": None}),
])
def test_parse_pfr(text, expected):
    out = parse_pfr(text)
    for key, value in expected.items():
        assert out[key] == value, key


@pytest.mark.parametrize("text", [
    "Jason Elam 43 yard field goal",
    "Rod Smith 22 yard pass from John Elway (Jason Elam kick)",
    "Mark van Eeghen 1 yard rush (Uwe von Schamann kick failed)",
    "Terry Fair 35 yard defensive fumble return (pass failed)",
    "Shaun Gayle defensive fumble recovery in end zone (kick failed)",
    "Kordell Stewart 45 yard rush (two point pass successful)",
    "Safety, Kidd downed ball in end zone",
])
def test_format_round_trips(text):
    assert format_scoring(parse_pfr(text)) == text


def test_format_incomplete_fields_returns_none():
    assert format_scoring({"scoring_type": "touchdown", "scoring_method": "pass", "scorer": "X", "yards": 3}) is None
    assert format_scoring({"scoring_type": None}) is None
