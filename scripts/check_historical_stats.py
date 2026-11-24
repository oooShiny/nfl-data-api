"""Compare season stats derived from pre-1999 play-by-play with PFR's official tables.

Needs PFR's season pages, fetched with scripts/scrape-pfr-season-stats.mjs
into data/scraped/pfr_season_stats/<season>/, and a loaded database
(fact_historical_player_season_stats, fact_historical_team_season_stats).

    uv run python scripts/check_historical_stats.py [--detail]

Regular season only (PFR's season pages are regular season). For each
season and stat:
  - teams: teams whose derived total equals PFR's exactly, and the largest
    difference
  - players: players (matched on PFR id -> gsis_id) whose derived total is
    exact / within 2% (min 10 yards), and the league total both ways
--detail lists the largest player differences.
"""

import sys
from pathlib import Path

import duckdb
import polars as pl

ROOT = Path(__file__).resolve().parent.parent
DB = Path(sys.argv[sys.argv.index("--db") + 1]) if "--db" in sys.argv else ROOT / "data" / "nfl.duckdb"
SCRAPED = ROOT / "data" / "scraped" / "pfr_season_stats"

# PFR full team names that dim_teams spells differently (its names are current).
TEAM_NAMES = {
    "Tennessee Oilers": "TEN", "Houston Oilers": "HOU", "Washington Redskins": "WSH",
    "Baltimore Colts": "BAL", "Los Angeles Rams": "LA", "St. Louis Rams": "STL",
    "Boston Patriots": "NE", "Phoenix Cardinals": "PHX", "St. Louis Cardinals": "SLC",
    "Los Angeles Raiders": "RAI", "Oakland Raiders": "OAK", "San Diego Chargers": "SD",
}

TEAM_STATS = [  # (ours, PFR's)
    ("attempts", "pass_att"), ("completions", "pass_cmp"), ("net_passing_yards", "pass_yds"),
    ("passing_tds", "pass_td"), ("passing_interceptions", "pass_int"),
    ("carries", "rush_att"), ("rushing_yards", "rush_yds"), ("rushing_tds", "rush_td"),
]
PLAYER_STATS = {  # page: [(ours, PFR's)]
    "passing": [("attempts", "pass_att"), ("completions", "pass_cmp"), ("passing_yards", "pass_yds"),
                ("passing_tds", "pass_td"), ("passing_interceptions", "pass_int"), ("sacks_suffered", "pass_sacked")],
    "rushing": [("carries", "rush_att"), ("rushing_yards", "rush_yds"), ("rushing_tds", "rush_td")],
    "receiving": [("receptions", "rec"), ("receiving_yards", "rec_yds"), ("receiving_tds", "rec_td")],
}


def _num(col: str) -> pl.Expr:
    return pl.col(col).cast(pl.Int64, strict=False).fill_null(0)


def _pfr_players(path: Path, stats: list[tuple[str, str]]) -> pl.DataFrame:
    df = pl.read_csv(path, infer_schema_length=0).filter(pl.col("player_href").is_not_null())
    df = df.with_columns(pfr_id=pl.col("player_href").str.extract(r"/players/./([^.]+(?:\.\d+)?)\.htm"),
                         multi=pl.col("team_name_abbr").str.ends_with("TM").fill_null(False))
    # Traded players have a combined "2TM" row plus one per team: keep the combined one.
    df = df.filter(pl.col("multi") | ~pl.col("multi").any().over("pfr_id"))
    return df.select("pfr_id", pl.col("name_display").alias("name"),
                     *[_num(p).alias(o) for o, p in stats])


def main() -> int:
    detail = "--detail" in sys.argv
    con = duckdb.connect(str(DB), read_only=True)
    names = dict(con.execute("SELECT team_name, team_abbr FROM dim_teams").fetchall()) | TEAM_NAMES
    pfr_to_gsis = dict(con.execute(
        "SELECT pfr_id, gsis_id FROM dim_players WHERE pfr_id IS NOT NULL AND gsis_id IS NOT NULL").fetchall())

    seasons = sorted((int(p.name) for p in SCRAPED.iterdir() if p.is_dir() and p.name.isdigit()), reverse=True)
    for season in seasons:
        d = SCRAPED / str(season)
        print(f"\n{season}")
        if (d / "team_stats.csv").exists():
            pfr = pl.read_csv(d / "team_stats.csv", infer_schema_length=0).with_columns(
                team=pl.col("team").replace_strict(names, default=None))
            ours = con.execute("SELECT * FROM fact_historical_team_season_stats "
                               "WHERE season = ? AND season_type = 'REG'", [season]).pl()
            j = ours.join(pfr.select("team", *[_num(p).alias("pfr_" + o) for o, p in TEAM_STATS]),
                          on="team", how="full", coalesce=True)
            print(f"  teams: {j['games'].is_not_null().sum()} derived, "
                  f"{j['pfr_attempts'].is_not_null().sum()} on PFR")
            for o, _ in TEAM_STATS:
                diff = (j[o].fill_null(0) - j["pfr_" + o].fill_null(0)).abs()
                print(f"    {o:<18} exact {int((diff == 0).sum()):>2}/{len(j)}  max diff {diff.max()}")
        for page, stats in PLAYER_STATS.items():
            if not (d / f"{page}.csv").exists():
                continue
            pfr = _pfr_players(d / f"{page}.csv", stats).with_columns(
                player_id=pl.col("pfr_id").replace_strict(pfr_to_gsis, default=None))
            cols = ", ".join(f"sum({o}) AS {o}" for o, _ in stats)
            ours = con.execute(f"SELECT player_id, {cols} FROM fact_historical_player_season_stats "
                               f"WHERE season = ? AND season_type = 'REG' AND player_id IS NOT NULL "
                               f"GROUP BY 1", [season]).pl()
            main_stat = stats[0][0] if page != "passing" else "attempts"
            pfr = pfr.filter(pl.col(main_stat) > 0)
            j = pfr.join(ours, on="player_id", how="left", suffix="_ours")
            unmatched = int(j["player_id"].is_null().sum())
            print(f"  {page}: {len(pfr)} PFR players, {unmatched} without a gsis_id via pfr_id")
            j = j.filter(pl.col("player_id").is_not_null())
            for o, _ in stats:
                a, b = j[o], j[o + "_ours"].fill_null(0)
                diff = (a - b).abs()
                close = diff <= (a.abs() * 0.02).clip(lower_bound=2 if "yards" not in o else 10)
                print(f"    {o:<16} exact {(diff == 0).mean():>6.1%}  close {close.mean():>6.1%}  "
                      f"total PFR {int(a.sum()):>7,} ours {int(b.sum()):>7,}")
            if detail:
                key = [o for o, _ in stats if "yards" in o][0]
                worst = j.with_columns(d=(pl.col(key) - pl.col(key + "_ours").fill_null(0)).abs()) \
                    .sort("d", descending=True).head(8)
                for r in worst.iter_rows(named=True):
                    print(f"      {r['name']:<24} {key} PFR {r[key]} ours {r[key + '_ours']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
