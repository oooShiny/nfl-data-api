"""PFR gamelog cleaning: week and game type fixes for odd seasons."""
import polars as pl

from pipeline.config import BRONZE_DIR
from pipeline.silver.cleaners import clean_dataset


def test_1982_last_regular_week_is_not_wild_card():
    # Strike season: the source puts Jan 2-3, 1983 (regular season) in week 17
    # with the Wild Card round (Jan 8-9).
    df = clean_dataset("historical_gamelogs", BRONZE_DIR / "historical_gamelogs" / "1982.parquet")
    counts = dict(df.group_by("game_type").len().iter_rows())
    assert counts == {"REG": 126, "WC": 8, "DIV": 4, "CON": 2, "SB": 1}
    wk17 = df.filter(pl.col("week") == 17)
    assert set(wk17.filter(pl.col("game_type") == "REG")["gameday"].cast(str)) == {"1983-01-02", "1983-01-03"}
    assert "1982_17_ATL_NO" in wk17["game_id"].to_list()  # game_ids keep the source week
