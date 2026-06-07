"""Build the name_resolution lookup table in DuckDB.

Two resolution strategies:
  id_anchor  — play has a gsis_id already; pull canonical name from dim_players
  fuzzy      — no gsis_id; match raw name against dim_players via rapidfuzz

The resulting table maps (raw_name, source) → (resolved_gsis_id, canonical_name,
confidence, method) and is used by views and downstream queries.
"""

from __future__ import annotations

import duckdb
from rapidfuzz import process, fuzz
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

from pipeline.silver.name_normalizer import (
    normalize_for_comparison,
    last_name_key,
    first_initial,
)

console = Console()

# Confidence thresholds
AUTO_ACCEPT  = 0.88   # auto-match, no review needed
REVIEW_FLOOR = 0.72   # flag for manual review; below this = no match


def _build_player_index(con: duckdb.DuckDBPyConnection) -> dict:
    """Build a lookup structure from dim_players for fast candidate generation.

    Returns:
        {
          last_name_key: [(gsis_id, display_name, comparison_key), ...]
        }
    """
    rows = con.execute(
        "SELECT gsis_id, display_name FROM dim_players WHERE display_name IS NOT NULL"
    ).fetchall()

    index: dict[str, list[tuple]] = {}
    for gsis_id, display_name in rows:
        lk = last_name_key(display_name)
        entry = (gsis_id, display_name, normalize_for_comparison(display_name))
        index.setdefault(lk, []).append(entry)

    return index


def _fuzzy_match(
    raw_name: str,
    player_index: dict,
) -> tuple[str | None, str | None, float]:
    """Try to match raw_name to a gsis_id.

    Returns (gsis_id, canonical_name, confidence) or (None, None, 0.0).
    """
    lk = last_name_key(raw_name)
    fi = first_initial(raw_name)
    comp_key = normalize_for_comparison(raw_name)

    if not lk or not comp_key:
        return None, None, 0.0

    # Candidate pool: same last-name bucket, optionally same first initial
    candidates = player_index.get(lk, [])
    if not candidates:
        # Fallback: try without first-initial constraint
        return None, None, 0.0

    # Score each candidate using token_sort_ratio (handles word-order differences)
    best_score = 0.0
    best_entry = None
    for gsis_id, display_name, ckey in candidates:
        # Require matching first initial when we have one
        if fi and ckey and ckey[0] != fi:
            continue
        score = fuzz.token_sort_ratio(comp_key, ckey) / 100.0
        if score > best_score:
            best_score = score
            best_entry = (gsis_id, display_name)

    if best_entry and best_score >= REVIEW_FLOOR:
        return best_entry[0], best_entry[1], best_score

    return None, None, 0.0


def _collect_id_anchored(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Collect all (raw_name, source, gsis_id) pairs where the play already has an ID."""
    sources = [
        ("fact_pass_plays",  "passer_player_name",   "passer_player_id"),
        ("fact_pass_plays",  "receiver_player_name",  "receiver_player_id"),
        ("fact_rush_plays",  "rusher_player_name",    "rusher_player_id"),
        ("fact_kick_plays",  "kicker_player_name",    "kicker_player_id"),
        ("fact_kick_plays",  "return_player_name",    "return_player_id"),
    ]
    rows = []
    for table, name_col, id_col in sources:
        result = con.execute(f"""
            SELECT DISTINCT {name_col} AS raw_name,
                            '{table}.{name_col}' AS source,
                            {id_col} AS gsis_id
            FROM {table}
            WHERE {name_col} IS NOT NULL AND {id_col} IS NOT NULL
        """).fetchall()
        rows.extend(result)
    return rows


def _collect_name_only(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Collect (raw_name, source) pairs that have no gsis_id — need fuzzy matching."""
    queries = [
        # ref tables with no or partial IDs
        ("SELECT DISTINCT player_name, 'ref_combine' FROM ref_combine WHERE player_name IS NOT NULL AND player_id IS NULL"),
        ("SELECT DISTINCT player_name, 'ref_contracts' FROM ref_contracts WHERE player_name IS NOT NULL AND player_id IS NULL"),
        ("SELECT DISTINCT player_name, 'ref_draft_picks' FROM ref_draft_picks WHERE player_name IS NOT NULL AND gsis_id IS NULL"),
        ("SELECT DISTINCT pfr_name, 'ref_trades' FROM ref_trades WHERE pfr_name IS NOT NULL"),
        # play table names where ID is null (rare but exists)
        ("SELECT DISTINCT passer_player_name, 'fact_pass_plays.passer_player_name' FROM fact_pass_plays WHERE passer_player_name IS NOT NULL AND passer_player_id IS NULL"),
        ("SELECT DISTINCT receiver_player_name, 'fact_pass_plays.receiver_player_name' FROM fact_pass_plays WHERE receiver_player_name IS NOT NULL AND receiver_player_id IS NULL"),
        ("SELECT DISTINCT rusher_player_name, 'fact_rush_plays.rusher_player_name' FROM fact_rush_plays WHERE rusher_player_name IS NOT NULL AND rusher_player_id IS NULL"),
    ]
    rows = []
    for q in queries:
        rows.extend(con.execute(q).fetchall())
    return rows


def build_name_resolution(con: duckdb.DuckDBPyConnection, rebuild: bool = False) -> None:
    """Populate the name_resolution table."""

    existing = con.execute("SELECT COUNT(*) FROM name_resolution").fetchone()[0]
    if existing > 0 and not rebuild:
        console.print(f"  [dim]name_resolution: {existing:,} rows already present, skipping (use --rebuild to force)[/dim]")
        return

    if rebuild:
        con.execute("DELETE FROM name_resolution")

    console.print("  Building player index from dim_players...")
    player_index = _build_player_index(con)
    total_players = sum(len(v) for v in player_index.values())
    console.print(f"  Player index: {total_players:,} players across {len(player_index):,} last-name buckets")

    # ── Pass 1: ID-anchored rows (fast, exact) ───────────────────────────────
    console.print("  Pass 1: resolving ID-anchored names...")
    id_rows = _collect_id_anchored(con)

    # Look up canonical names from dim_players
    gsis_to_name = dict(
        con.execute("SELECT gsis_id, display_name FROM dim_players WHERE display_name IS NOT NULL").fetchall()
    )

    anchored_records = []
    for raw_name, source, gsis_id in id_rows:
        canonical = gsis_to_name.get(gsis_id, raw_name)
        anchored_records.append((raw_name, source, gsis_id, canonical, 1.0, 'id_anchor'))

    if anchored_records:
        con.executemany(
            "INSERT OR REPLACE INTO name_resolution VALUES (?, ?, ?, ?, ?, ?)",
            anchored_records,
        )
    console.print(f"  [green]✓[/green] ID-anchored: {len(anchored_records):,} name→canonical mappings")

    # ── Pass 2: Fuzzy matching for name-only records ─────────────────────────
    console.print("  Pass 2: fuzzy matching name-only records...")
    name_only_rows = _collect_name_only(con)
    console.print(f"  Found {len(name_only_rows):,} name-only records to match")

    fuzzy_records = []
    no_match = []
    review_needed = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Fuzzy matching...", total=len(name_only_rows))
        for raw_name, source in name_only_rows:
            gsis_id, canonical, confidence = _fuzzy_match(raw_name, player_index)
            progress.advance(task)

            if confidence >= AUTO_ACCEPT:
                fuzzy_records.append((raw_name, source, gsis_id, canonical, confidence, 'fuzzy'))
            elif confidence >= REVIEW_FLOOR:
                review_needed.append((raw_name, source, gsis_id, canonical, confidence, 'fuzzy_review'))
            else:
                no_match.append((raw_name, source))

    if fuzzy_records:
        con.executemany(
            "INSERT OR REPLACE INTO name_resolution VALUES (?, ?, ?, ?, ?, ?)",
            fuzzy_records,
        )
    if review_needed:
        con.executemany(
            "INSERT OR REPLACE INTO name_resolution VALUES (?, ?, ?, ?, ?, ?)",
            review_needed,
        )

    auto_n   = len(fuzzy_records)
    review_n = len(review_needed)
    miss_n   = len(no_match)

    console.print(f"  [green]✓[/green] Fuzzy: {auto_n:,} auto-matched  |  {review_n:,} need review  |  {miss_n:,} no match")

    total = con.execute("SELECT COUNT(*) FROM name_resolution").fetchone()[0]
    console.print(f"  [bold green]✓[/bold green] name_resolution: {total:,} total rows")


def get_review_candidates(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Return rows flagged for manual review, ordered by confidence desc."""
    return con.execute("""
        SELECT raw_name, source, resolved_gsis_id, canonical_name, confidence
        FROM name_resolution
        WHERE method = 'fuzzy_review'
        ORDER BY source, confidence DESC
    """).fetchall()


def accept_match(con: duckdb.DuckDBPyConnection, raw_name: str, source: str, gsis_id: str) -> None:
    """Manually accept a fuzzy_review match, promoting it to 'manual'."""
    canonical = con.execute(
        "SELECT display_name FROM dim_players WHERE gsis_id = ?", [gsis_id]
    ).fetchone()
    if not canonical:
        raise ValueError(f"gsis_id {gsis_id!r} not found in dim_players")
    con.execute("""
        UPDATE name_resolution
        SET resolved_gsis_id = ?, canonical_name = ?, method = 'manual', confidence = 1.0
        WHERE raw_name = ? AND source = ?
    """, [gsis_id, canonical[0], raw_name, source])


def reject_match(con: duckdb.DuckDBPyConnection, raw_name: str, source: str) -> None:
    """Mark a fuzzy_review match as rejected (no match)."""
    con.execute("""
        UPDATE name_resolution
        SET resolved_gsis_id = NULL, canonical_name = NULL, method = 'rejected', confidence = 0.0
        WHERE raw_name = ? AND source = ?
    """, [raw_name, source])
