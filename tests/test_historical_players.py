import polars as pl

from pipeline.historical_players import initial_key, match_player_ids, name_key


def test_name_key():
    assert name_key("N.D. Kalu") == name_key("N. D. Kalu") == "nd kalu"
    assert name_key("Mike D. Jones") == "mike jones"
    assert name_key("Ken Griffey Jr.") == "ken griffey"
    assert name_key("J.J. Stokes") == "jj stokes"
    assert initial_key("Chuck Evans") == initial_key("Charles Evans") == "c evans"


def test_match_player_ids():
    rosters = pl.DataFrame([
        dict(season=1998, team="DEN", player_name="John Elway", player_id="00-E"),
        dict(season=1998, team="MIN", player_name="Chuck Evans", player_id="00-C"),
        dict(season=1998, team="LA", player_name="Mike A. Jones", player_id="00-J1"),
        dict(season=1998, team="LA", player_name="Mike D. Jones", player_id="00-J2"),
        dict(season=1998, team="LAC", player_name="Ryan Leaf", player_id="00-L"),
        dict(season=1998, team="NYJ", player_name="Traded Guy", player_id="00-T"),
        dict(season=1998, team="NYJ", player_name="John Smith", player_id="00-S1"),
        dict(season=1998, team="BUF", player_name="John Smith", player_id="00-S2"),
    ])
    names = pl.DataFrame([
        dict(season=1998, home_team="DEN", away_team="SD", name="John Elway"),
        dict(season=1998, home_team="DEN", away_team="SD", name="Ryan Leaf"),      # SD -> LAC on rosters
        dict(season=1998, home_team="STL", away_team="MIN", name="Charles Evans"),  # first initial + last name
        dict(season=1998, home_team="STL", away_team="MIN", name="Mike Jones"),     # two on the Rams: no id
        dict(season=1998, home_team="DEN", away_team="SD", name="Traded Guy"),      # any roster that season
        dict(season=1998, home_team="DEN", away_team="SD", name="John Smith"),      # two elsewhere: no id
        dict(season=1998, home_team="DEN", away_team="SD", name=None),
    ])
    assert match_player_ids(names, rosters)["player_id"].to_list() == [
        "00-E", "00-L", "00-C", None, "00-T", None, None]
