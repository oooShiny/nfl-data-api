"""Compare season stats derived from pre-1999 play-by-play with PFR's official tables.

Needs PFR's season pages, fetched with scripts/scrape-pfr-season-stats.mjs
into data/scraped/pfr_season_stats/<season>/, and a loaded database
(fact_historical_player_season_stats, fact_historical_team_season_stats).

    uv run python scripts/check_historical_stats.py [--detail]

Regular season only (PFR's season pages are regular season). For each
season and stat:
  - teams: teams whose derived total equals PFR's exactly, and the largest
    difference
  - players: players (matched on PFR id -> gsis_id, else on name) whose derived total is
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
    ("fumbles_lost", "fumbles_lost"),  # summed from the player lines
]
# page: [(ours, PFR's)]; ours is a column, or "alias=SQL expression" when PFR's
# stat is a sum of ours.
PLAYER_STATS = {
    "passing": [("attempts", "pass_att"), ("completions", "pass_cmp"), ("passing_yards", "pass_yds"),
                ("passing_tds", "pass_td"), ("passing_interceptions", "pass_int"), ("sacks_suffered", "pass_sacked")],
    "rushing": [("carries", "rush_att"), ("rushing_yards", "rush_yds"), ("rushing_tds", "rush_td"),
                ("fumbles", "fumbles")],  # all of the player's fumbles, not only on runs
    "receiving": [("receptions", "rec"), ("receiving_yards", "rec_yds"), ("receiving_tds", "rec_td")],
    "defense": [("def_interceptions", "def_int"), ("def_interception_yards", "def_int_yds"),
                ("def_interception_tds", "def_int_td"), ("def_sacks", "sacks"),
                ("def_fumbles_forced", "fumbles_forced"),
                ("fumble_recoveries=fumble_recovery_own + fumble_recovery_opp", "fumbles_rec"),
                ("fumble_recovery_tds", "fumbles_rec_td")],
    "kicking": [("fg_made", "fgm"), ("fg_att", "fga"), ("fg_long", "fg_long"),
                ("fg_made_0_19", "fgm1"), ("fg_att_0_19=fg_made_0_19 + fg_missed_0_19", "fga1"),
                ("fg_made_20_29", "fgm2"), ("fg_att_20_29=fg_made_20_29 + fg_missed_20_29", "fga2"),
                ("fg_made_30_39", "fgm3"), ("fg_att_30_39=fg_made_30_39 + fg_missed_30_39", "fga3"),
                ("fg_made_40_49", "fgm4"), ("fg_att_40_49=fg_made_40_49 + fg_missed_40_49", "fga4"),
                ("fg_made_50_=fg_made_50_59 + fg_made_60_", "fgm5"),
                ("fg_att_50_=fg_made_50_59 + fg_made_60_ + fg_missed_50_59 + fg_missed_60_", "fga5"),
                ("pat_made", "xpm"), ("pat_att", "xpa")],
    "punting": [("punts", "punt"), ("punt_yards", "punt_yds"), ("punt_long", "punt_long"),
                ("punts_blocked", "punt_blocked")],
    "returns": [("kickoff_returns", "kick_ret"), ("kickoff_return_yards", "kick_ret_yds"),
                ("kickoff_return_tds", "kick_ret_td"), ("punt_returns", "punt_ret"),
                ("punt_return_yards", "punt_ret_yds"), ("punt_return_tds", "punt_ret_td")],
}



def _num(col: str) -> pl.Expr:
    return pl.col(col).cast(pl.Float64, strict=False).fill_null(0)


def _alias(ours: str) -> str:
    return ours.split("=")[0]


def _sql(ours: str) -> str:
    name, _, expr = ours.partition("=")
    agg = "max" if name.endswith("_long") else "sum"
    return f"{agg}({expr or name}) AS {name}"


def _pfr_players(path: Path, stats: list[tuple[str, str]]) -> pl.DataFrame:
    df = pl.read_csv(path, infer_schema_length=0).filter(pl.col("player_href").is_not_null())
    df = df.with_columns(pfr_id=pl.col("player_href").str.extract(r"/players/./([^.]+(?:\.\d+)?)\.htm"),
                         multi=pl.col("team_name_abbr").str.ends_with("TM").fill_null(False))
    # Traded players have a combined "2TM" row plus one per team: keep the combined one.
    df = df.filter(pl.col("multi") | ~pl.col("multi").any().over("pfr_id"))
    return df.select("pfr_id", pl.col("name_display").alias("name"),
                     *[_num(p).alias(_alias(o)) for o, p in stats])


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
            ours = con.execute("""SELECT t.*, f.fumbles_lost FROM fact_historical_team_season_stats t
                LEFT JOIN (SELECT team, sum(fumbles_lost) AS fumbles_lost FROM fact_historical_player_season_stats
                           WHERE season = $1 AND season_type = 'REG' GROUP BY 1) f USING (team)
                WHERE season = $1 AND season_type = 'REG'""", [season]).pl()
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
            cols = ", ".join(_sql(o) for o, _ in stats)
            stat_names = [_alias(o) for o, _ in stats]
            ours = con.execute(f"SELECT player_id, {cols} FROM fact_historical_player_season_stats "
                               f"WHERE season = ? AND season_type = 'REG' AND player_id IS NOT NULL "
                               f"GROUP BY 1", [season]).pl()
            # Players with any of the page's stats (passing: an attempt).
            main = [pl.col("attempts")] if page == "passing" else [pl.col(n) for n in stat_names]
            pfr = pfr.filter(pl.any_horizontal([c != 0 for c in main]))
            # Older players can have a placeholder id in fact_rosters (hist_...)
            # that dim_players doesn't share; match those on name, when the name
            # is one player on both sides (two James Stewarts in 1995).
            by_name = con.execute(f"SELECT player_name AS name, {cols} FROM fact_historical_player_season_stats "
                                  f"WHERE season = ? AND season_type = 'REG' GROUP BY 1 "
                                  f"HAVING count(DISTINCT player_id) <= 1", [season]).pl()
            by_name = by_name.filter(~pl.col("name").is_in(
                pfr.filter(pl.col("name").is_duplicated())["name"].implode()))
            j = pfr.join(ours, on="player_id", how="left", suffix="_ours")
            id_hit = j[stat_names[0] + "_ours"].is_not_null()
            j = pl.concat([
                j.filter(id_hit),
                j.filter(~id_hit).select(pfr.columns).join(by_name, on="name", how="left", suffix="_ours"),
            ], how="diagonal_relaxed")
            unmatched = int(j[stat_names[0] + "_ours"].is_null().sum())
            print(f"  {page}: {len(pfr)} PFR players, {unmatched} with no derived row (by id or name)")
            for o in stat_names:
                a, b = j[o], j[o + "_ours"].cast(pl.Float64).fill_null(0)
                diff = (a - b).abs()
                close = diff <= (a.abs() * 0.02).clip(lower_bound=2 if "yards" not in o else 10)
                print(f"    {o:<22} exact {(diff == 0).mean():>6.1%}  close {close.mean():>6.1%}  "
                      f"total PFR {a.sum():>9,.0f} ours {b.sum():>9,.0f}")
            if detail:
                key = next((o for o in stat_names if "yards" in o), stat_names[0])
                worst = j.with_columns(d=(pl.col(key) - pl.col(key + "_ours").fill_null(0)).abs()) \
                    .sort("d", descending=True).head(8)
                for r in worst.iter_rows(named=True):
                    print(f"      {r['name']:<24} {key} PFR {r[key]} ours {r[key + '_ours']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
