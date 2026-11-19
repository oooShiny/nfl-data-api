import json

import duckdb
import pytest
from typer.testing import CliRunner

from pipeline.audit import load_previous_counts, run_audit
from pipeline.cli import app


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "nfl.duckdb"
    c = duckdb.connect(str(path))
    c.execute("""CREATE TABLE dim_games (game_id VARCHAR, season INT, week INT, game_type VARCHAR,
                 gameday DATE, home_team VARCHAR, away_team VARCHAR, result INT, old_game_id VARCHAR, espn VARCHAR)""")
    c.execute("""INSERT INTO dim_games VALUES
        ('2025_01_DAL_PHI', 2025, 1, 'REG', DATE '2025-09-04', 'PHI', 'DAL', 4, '2025090400', '401'),
        ('2025_02_KC_PHI',  2025, 2, 'REG', DATE '2025-09-14', 'PHI', 'KC', 3, '2025091400', '402'),
        ('2025_03_PHI_LA',  2025, 3, 'REG', DATE '2025-09-21', 'LA', 'PHI', 7, '2025092100', '403'),
        ('2025_04_PHI_TB',  2025, 4, 'REG', DATE '2025-09-28', 'TB', 'PHI', NULL, '2025092800', '404')""")
    c.execute("CREATE TABLE fact_plays (game_id VARCHAR, play_id INT, season INT, week INT)")
    c.execute("""INSERT INTO fact_plays VALUES ('2025_01_DAL_PHI', 1, 2025, 1), ('2025_02_KC_PHI', 1, 2025, 2),
                 ('2025_03_PHI_LA', 1, 2025, 3)""")
    c.execute("CREATE TABLE fact_player_game_stats (game_id VARCHAR, player_id VARCHAR, season INT, week INT)")
    c.execute("INSERT INTO fact_player_game_stats VALUES ('2025_01_DAL_PHI', 'p', 2025, 1)")  # stale: weeks 2-3 missing
    c.execute("CREATE TABLE ref_officials (game_id VARCHAR, season INT)")
    c.execute("INSERT INTO ref_officials VALUES ('2025090400', 2025), ('2025091400', 2025)")
    c.execute("CREATE TABLE ref_contracts (player_id VARCHAR, year_signed INT)")
    c.execute("INSERT INTO ref_contracts VALUES ('a', 2020), ('b', 2023), ('c', 2025)")
    c.close()
    return path


def _checks(findings):
    return {(f.severity, f.table, f.check) for f in findings}


def test_audit_flags_staleness_gaps_and_drops(db):
    con = duckdb.connect(str(db), read_only=True)
    findings = run_audit(con, previous_counts={"fact_plays": 100, "dim_games": 4, "fact_snap_counts": 50})
    checks = _checks(findings)
    assert ("error", "fact_plays", "row_drop") in checks             # 3 rows vs 100 last run
    assert ("error", "fact_snap_counts", "missing_table") in checks  # existed last run
    assert ("warning", "fact_player_game_stats", "stale_week") in checks
    assert ("warning", "ref_contracts", "season_gap") in checks      # 2021, 2022, 2024
    # The latest played game (week 3) is within the publishing grace period, but week 2 is not.
    missing = [f for f in findings if f.table == "fact_player_game_stats" and f.check == "missing_games"]
    assert missing and "2025_02_KC_PHI" in missing[0].message and "2025_03_PHI_LA" not in missing[0].message
    # Officials use the NFL game key, which matches old_game_id: no orphan warning.
    assert not any(f.table == "ref_officials" for f in findings)
    # Unplayed week 4 is not expected anywhere.
    assert not any("2025_04" in f.message for f in findings)
    con.close()


def test_audit_cli_strict_exit_code_and_json(db, tmp_path):
    prev = tmp_path / "prev.json"
    prev.write_text(json.dumps({"row_counts": {"fact_plays": 100}}))
    out = tmp_path / "findings.json"
    runner = CliRunner()

    result = runner.invoke(app, ["audit", "--db", str(db), "--previous", str(prev), "--json", str(out), "--strict"])
    assert result.exit_code == 1
    assert any(f["check"] == "row_drop" for f in json.loads(out.read_text()))

    # Without a previous run there are only warnings, so --strict passes.
    assert runner.invoke(app, ["audit", "--db", str(db), "--strict"]).exit_code == 0


def test_load_previous_counts_tolerates_missing_or_bad_files(tmp_path):
    assert load_previous_counts(None) == {}
    assert load_previous_counts(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert load_previous_counts(bad) == {}
