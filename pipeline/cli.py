"""CLI entrypoint: nfl <command>"""

from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="nfl", help="NFL data pipeline: ingest → clean → load")
console = Console()


@app.command()
def ingest(
    tags: Annotated[list[str] | None, typer.Argument(help="Specific release tags to download (default: all)")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Re-download even if up to date")] = False,
    skip_large: Annotated[bool, typer.Option("--skip-large", help="Skip pbp/stats datasets (faster for testing)")] = False,
):
    """Download parquet files from nflverse GitHub releases → bronze layer."""
    from pipeline.bronze.downloader import download_all
    from pipeline.config import RELEASE_TAGS, LARGE_TAGS

    target_tags = list(tags) if tags else RELEASE_TAGS
    if skip_large:
        target_tags = [t for t in target_tags if t not in LARGE_TAGS]

    download_all(target_tags, force=force)


@app.command()
def clean(
    tags: Annotated[list[str] | None, typer.Argument(help="Specific release tags to clean (default: all)")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Re-clean even if silver is newer than bronze")] = False,
):
    """Clean bronze parquet → silver layer (types, nulls, team abbr normalization)."""
    from pipeline.silver.cleaners import clean_all
    from pipeline.config import RELEASE_TAGS

    target_tags = list(tags) if tags else RELEASE_TAGS
    results = clean_all(target_tags, force=force)
    total = sum(results.values())
    changed = {k: v for k, v in results.items() if v > 0}
    if changed:
        for tag, n in changed.items():
            console.print(f"  [green]✓[/green] {tag}: {n} files cleaned")
    console.print(f"\n[bold green]Done.[/bold green] {total} files written to silver.")


@app.command()
def load(
    tables: Annotated[list[str] | None, typer.Argument(help="Specific gold tables to load (default: all)")] = None,
):
    """Load silver parquet → gold DuckDB database."""
    from pipeline.gold.loader import load_all
    load_all(list(tables) if tables else None)


@app.command()
def run(
    tags: Annotated[list[str] | None, typer.Argument(help="Specific release tags (default: all)")] = None,
    force: Annotated[bool, typer.Option("--force", "-f")] = False,
    skip_large: Annotated[bool, typer.Option("--skip-large")] = False,
    rebuild_names: Annotated[bool, typer.Option("--rebuild-names", help="Rebuild name_resolution from scratch")] = False,
):
    """Full pipeline: ingest → clean → load → resolve → enrich."""
    from pipeline.bronze.downloader import download_all
    from pipeline.silver.cleaners import clean_all
    from pipeline.gold.loader import load_all, get_connection, init_schema, apply_name_resolution
    from pipeline.gold.name_resolver import build_name_resolution
    from pipeline.config import RELEASE_TAGS, LARGE_TAGS

    target_tags = list(tags) if tags else RELEASE_TAGS
    if skip_large:
        target_tags = [t for t in target_tags if t not in LARGE_TAGS]

    console.rule("[bold]Step 1: Ingest[/bold]")
    download_all(target_tags, force=force)

    console.rule("[bold]Step 2: Clean[/bold]")
    results = clean_all(target_tags, force=force)
    for tag, n in results.items():
        if n:
            console.print(f"  [green]✓[/green] {tag}: {n} files")

    console.rule("[bold]Step 3: Load[/bold]")
    load_all()

    console.rule("[bold]Step 4: Resolve[/bold]")
    con = get_connection()
    init_schema(con)
    build_name_resolution(con, rebuild=rebuild_names)
    con.close()

    console.rule("[bold]Step 5: Enrich[/bold]")
    con = get_connection()
    apply_name_resolution(con)
    con.close()


@app.command()
def status():
    """Show what data has been downloaded and cleaned."""
    from pipeline.config import BRONZE_DIR, SILVER_DIR, GOLD_DB, RELEASE_TAGS

    table = Table(title="Pipeline Status", show_header=True)
    table.add_column("Dataset", style="bold")
    table.add_column("Bronze files", justify="right")
    table.add_column("Silver files", justify="right")
    table.add_column("Timestamp")

    for tag in RELEASE_TAGS:
        bronze_dir = BRONZE_DIR / tag
        silver_dir = SILVER_DIR / tag
        b_count = len(list(bronze_dir.glob("*.parquet"))) if bronze_dir.exists() else 0
        s_count = len(list(silver_dir.glob("*.parquet"))) if silver_dir.exists() else 0
        stamp_file = bronze_dir / ".timestamp"
        ts = stamp_file.read_text().strip()[:19] if stamp_file.exists() else "—"
        b_str = f"[green]{b_count}[/green]" if b_count else "[dim]0[/dim]"
        s_str = f"[green]{s_count}[/green]" if s_count else "[dim]0[/dim]"
        table.add_row(tag, b_str, s_str, ts)

    console.print(table)

    if GOLD_DB.exists():
        size_mb = GOLD_DB.stat().st_size / 1_000_000
        console.print(f"\n[bold]DuckDB:[/bold] {GOLD_DB} ({size_mb:.1f} MB)")
    else:
        console.print(f"\n[bold]DuckDB:[/bold] not yet created")


@app.command()
def check():
    """Show data quality report: row counts, null rates, and name resolution coverage."""
    import duckdb as _duckdb
    from pipeline.config import GOLD_DB

    if not GOLD_DB.exists():
        console.print("[red]Database not found. Run `nfl load` first.[/red]")
        raise typer.Exit(1)

    con = _duckdb.connect(str(GOLD_DB), read_only=True)

    # ── Row counts ────────────────────────────────────────────────────────────
    count_table = Table(title="Gold Layer Row Counts", show_header=True)
    count_table.add_column("Table", style="bold")
    count_table.add_column("Rows", justify="right")

    gold_tables = [
        "dim_players", "dim_teams", "dim_games",
        "fact_plays", "fact_pass_plays", "fact_rush_plays", "fact_kick_plays",
        "fact_player_game_stats", "fact_weekly_rosters", "fact_rosters",
        "fact_snap_counts", "fact_depth_charts", "fact_injuries",
        "ref_combine", "ref_contracts", "ref_draft_picks", "ref_trades",
        "name_resolution",
    ]
    for t in gold_tables:
        try:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            count_table.add_row(t, f"{n:,}")
        except Exception:
            count_table.add_row(t, "[dim]—[/dim]")
    console.print(count_table)

    # ── Name resolution coverage ──────────────────────────────────────────────
    res_table = Table(title="Name Resolution Coverage", show_header=True)
    res_table.add_column("Table / Column", style="bold")
    res_table.add_column("Resolved", justify="right")
    res_table.add_column("Total", justify="right")
    res_table.add_column("Pct", justify="right")

    id_cols = [
        ("ref_combine",     "player_id"),
        ("ref_contracts",   "player_id"),
        ("ref_draft_picks", "gsis_id"),
        ("ref_trades",      "gsis_id"),
    ]
    for table, col in id_cols:
        try:
            resolved, total = con.execute(
                f"SELECT COUNT({col}), COUNT(*) FROM {table}"
            ).fetchone()
            pct = resolved / total * 100 if total else 0
            color = "green" if pct >= 95 else "yellow" if pct >= 80 else "red"
            res_table.add_row(
                f"{table}.{col}",
                f"{resolved:,}", f"{total:,}",
                f"[{color}]{pct:.1f}%[/{color}]",
            )
        except Exception:
            res_table.add_row(f"{table}.{col}", "—", "—", "—")

    # name_resolution method breakdown
    total_nr = con.execute("SELECT COUNT(*) FROM name_resolution").fetchone()[0]
    for row in con.execute("""
        SELECT method, COUNT(*) AS n
        FROM name_resolution GROUP BY method ORDER BY n DESC
    """).fetchall():
        pct = row[1] / total_nr * 100 if total_nr else 0
        res_table.add_row(f"  name_resolution [{row[0]}]", f"{row[1]:,}", f"{total_nr:,}", f"{pct:.1f}%")

    console.print(res_table)

    # ── Null rates on key fact columns ────────────────────────────────────────
    null_table = Table(title="Key Column Null Rates", show_header=True)
    null_table.add_column("Table.Column", style="bold")
    null_table.add_column("Nulls", justify="right")
    null_table.add_column("Total", justify="right")
    null_table.add_column("Null %", justify="right")

    key_cols = [
        ("fact_plays",            "game_id"),
        ("fact_plays",            "play_id"),
        ("fact_pass_plays",       "passer_player_name"),
        ("fact_rush_plays",       "rusher_player_name"),
        ("fact_player_game_stats","player_id"),
        ("fact_weekly_rosters",   "gsis_id"),
        ("fact_snap_counts",      "pfr_player_id"),
    ]
    for table, col in key_cols:
        try:
            nulls, total = con.execute(
                f"SELECT COUNT(*) - COUNT({col}), COUNT(*) FROM {table}"
            ).fetchone()
            pct = nulls / total * 100 if total else 0
            color = "green" if pct < 1 else "yellow" if pct < 10 else "red"
            null_table.add_row(
                f"{table}.{col}",
                f"{nulls:,}", f"{total:,}",
                f"[{color}]{pct:.1f}%[/{color}]",
            )
        except Exception:
            null_table.add_row(f"{table}.{col}", "—", "—", "—")

    console.print(null_table)
    con.close()


@app.command()
def ui(
    port: Annotated[int, typer.Option("--port", "-p", help="Port to run UI on")] = 4213,
):
    """Open the DuckDB browser UI for the gold database."""
    import time
    import duckdb
    import webbrowser

    if not GOLD_DB.exists():
        console.print("[red]Database not found. Run `nfl load` first.[/red]")
        raise typer.Exit(1)

    from pipeline.config import GOLD_DB
    con = duckdb.connect(str(GOLD_DB))
    con.execute("INSTALL ui")
    con.execute("LOAD ui")
    console.print(f"[bold]DuckDB UI running at[/bold] http://localhost:{port}")
    console.print("Press Ctrl+C to stop.")
    webbrowser.open(f"http://localhost:{port}")
    try:
        con.execute(f"CALL start_ui(open_browser:=false)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\nStopped.")
    finally:
        con.close()


@app.command()
def query(sql: Annotated[str, typer.Argument(help="SQL query to run against the gold database")]):
    """Run a SQL query against the gold DuckDB database."""
    import duckdb
    from pipeline.config import GOLD_DB

    if not GOLD_DB.exists():
        console.print("[red]Database not found. Run `nfl load` first.[/red]")
        raise typer.Exit(1)

    con = duckdb.connect(str(GOLD_DB), read_only=True)
    try:
        result = con.execute(sql).fetchall()
        desc = con.execute(sql).description
        headers = [d[0] for d in desc]
        from rich.table import Table as RichTable
        t = RichTable(*headers)
        for row in result:
            t.add_row(*[str(v) if v is not None else "" for v in row])
        console.print(t)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        con.close()


@app.command()
def resolve(
    rebuild: Annotated[bool, typer.Option("--rebuild", "-r", help="Rebuild from scratch even if table already populated")] = False,
):
    """Build the name_resolution lookup table (ID-anchor + fuzzy matching)."""
    import duckdb as _duckdb
    from pipeline.config import GOLD_DB
    from pipeline.gold.loader import get_connection, init_schema
    from pipeline.gold.name_resolver import build_name_resolution

    if not GOLD_DB.exists():
        console.print("[red]Database not found. Run `nfl load` first.[/red]")
        raise typer.Exit(1)

    con = get_connection()
    init_schema(con)
    console.print("[bold]Building name resolution table[/bold]")
    build_name_resolution(con, rebuild=rebuild)
    con.close()


@app.command()
def enrich():
    """Back-fill player IDs in ref tables using resolved name_resolution data."""
    from pipeline.config import GOLD_DB
    from pipeline.gold.loader import get_connection, init_schema, apply_name_resolution

    if not GOLD_DB.exists():
        console.print("[red]Database not found. Run `nfl load` first.[/red]")
        raise typer.Exit(1)

    con = get_connection()
    init_schema(con)
    console.print("[bold]Applying name resolution to ref tables[/bold]")
    apply_name_resolution(con)
    con.close()


@app.command()
def review(
    source: Annotated[str | None, typer.Option("--source", "-s", help="Filter by source table")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 50,
):
    """Show fuzzy matches that need manual review (confidence between 0.72–0.88)."""
    import duckdb as _duckdb
    from pipeline.config import GOLD_DB
    from rich.table import Table as RichTable

    if not GOLD_DB.exists():
        console.print("[red]Database not found.[/red]")
        raise typer.Exit(1)

    con = _duckdb.connect(str(GOLD_DB), read_only=True)
    source_filter = f"AND source LIKE '%{source}%'" if source else ""
    rows = con.execute(f"""
        SELECT raw_name, source, canonical_name, resolved_gsis_id,
               ROUND(confidence * 100, 1) AS pct
        FROM name_resolution
        WHERE method = 'fuzzy_review'
        {source_filter}
        ORDER BY source, confidence DESC
        LIMIT {limit}
    """).fetchall()
    con.close()

    if not rows:
        console.print("[green]No rows pending review.[/green]")
        return

    t = RichTable("Raw name", "Source", "Suggested match", "gsis_id", "Confidence %")
    for row in rows:
        pct = row[4]
        color = "green" if pct >= 85 else "yellow" if pct >= 78 else "red"
        t.add_row(row[0], row[1], row[2] or "—", row[3] or "—", f"[{color}]{pct}[/{color}]")
    console.print(t)
    console.print(f"\n[dim]{len(rows)} rows shown. Accept with: nfl accept \"<raw_name>\" \"<source>\" \"<gsis_id>\"[/dim]")


@app.command()
def accept(
    raw_name: Annotated[str, typer.Argument()],
    source: Annotated[str, typer.Argument()],
    gsis_id: Annotated[str, typer.Argument()],
):
    """Manually accept a fuzzy_review match."""
    from pipeline.config import GOLD_DB
    from pipeline.gold.loader import get_connection
    from pipeline.gold.name_resolver import accept_match

    con = get_connection()
    try:
        accept_match(con, raw_name, source, gsis_id)
        console.print(f"[green]✓[/green] Accepted: {raw_name!r} → {gsis_id}")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
    finally:
        con.close()


@app.command()
def reject(
    raw_name: Annotated[str, typer.Argument()],
    source: Annotated[str, typer.Argument()],
):
    """Reject a fuzzy_review match (mark as no-match)."""
    from pipeline.config import GOLD_DB
    from pipeline.gold.loader import get_connection
    from pipeline.gold.name_resolver import reject_match

    con = get_connection()
    reject_match(con, raw_name, source)
    console.print(f"[yellow]✗[/yellow] Rejected: {raw_name!r} in {source}")
    con.close()


@app.command(name="ai-review")
def ai_review(
    model:   Annotated[str,        typer.Option("--model",   "-m")] = "google/gemma-4-26b-a4b",
    source:  Annotated[str | None, typer.Option("--source",  "-s", help="Filter by source table")] = None,
    dry_run: Annotated[bool,       typer.Option("--dry-run",       help="Show counts without writing")] = False,
    preview: Annotated[bool,       typer.Option("--preview",       help="Show per-row decisions on a sample, then prompt to apply")] = False,
    sample:  Annotated[int,        typer.Option("--sample",        help="Only review N rows (0 = all)")] = 0,
):
    """Use a local LM Studio model to validate fuzzy name matches."""
    import httpx as _httpx
    from rich.table import Table as RichTable
    from pipeline.config import GOLD_DB
    from pipeline.gold.loader import get_connection
    from pipeline.gold.llm_reviewer import run_llm_review

    if not GOLD_DB.exists():
        console.print("[red]Database not found. Run `nfl load` first.[/red]")
        raise typer.Exit(1)

    try:
        _httpx.get("http://localhost:1234/v1/models", timeout=3).raise_for_status()
    except Exception:
        console.print("[red]LM Studio not reachable at http://localhost:1234[/red]")
        console.print("Start it with: lms server start")
        raise typer.Exit(1)

    con = get_connection()

    # In preview mode, run on 30 rows (split across accept/reject) then prompt
    effective_sample = 30 if preview else sample
    is_dry = dry_run or preview

    if effective_sample > 0:
        console.print(f"[bold]LLM review (sample={effective_sample})[/bold]")
        con.execute(f"""
            UPDATE name_resolution
            SET method = '_review_hold'
            WHERE method = 'fuzzy_review'
              AND (raw_name, source) NOT IN (
                SELECT raw_name, source FROM name_resolution
                WHERE method = 'fuzzy_review'
                {'AND source LIKE ' + repr(f'%{source}%') if source else ''}
                LIMIT {effective_sample}
              )
        """)
    else:
        pending_n = con.execute("SELECT COUNT(*) FROM name_resolution WHERE method='fuzzy_review'").fetchone()[0]
        console.print(f"[bold]LLM review (all {pending_n:,} pending)[/bold]")

    counts, decisions = run_llm_review(con, model=model, dry_run=is_dry, source_filter=source)

    if effective_sample > 0:
        con.execute("UPDATE name_resolution SET method = 'fuzzy_review' WHERE method = '_review_hold'")

    # Show per-row table in preview mode
    if preview and decisions:
        t = RichTable("Verdict", "Raw name", "Suggested match", "Conf%", "Reason", show_lines=False)
        for verdict, raw, canonical, src, conf, reason in decisions:
            color = "green" if verdict == "YES" else ("red" if verdict == "NO" else "yellow")
            icon  = "✓" if verdict == "YES" else ("✗" if verdict == "NO" else "?")
            t.add_row(
                f"[{color}]{icon} {verdict}[/{color}]",
                raw,
                canonical or "—",
                str(conf),
                (reason or "")[:70],
            )
        console.print(t)
        console.print()

    console.print(f"[bold]Results{'  (dry run)' if is_dry else ''}:[/bold]")
    console.print(f"  [green]✓  Accepted:[/green]  {counts['accepted']:,}")
    console.print(f"  [red]✗  Rejected:[/red]  {counts['rejected']:,}")
    console.print(f"  [yellow]?  Uncertain:[/yellow] {counts['uncertain']:,}")

    if preview:
        console.print("\n[dim]This was a sample preview — nothing written yet.[/dim]")
        console.print("[dim]Run `nfl ai-review` (no flags) to process all pending rows.[/dim]")
    elif dry_run:
        console.print("\n[dim]Dry run — no changes written. Re-run without --dry-run to apply.[/dim]")


@app.command()
def report(
    format: Annotated[str, typer.Option("--format", "-f", help="Output format: json or table")] = "table",
    output: Annotated[str | None, typer.Option("--output", "-o", help="Write output to this file path")] = None,
):
    """Generate a data quality and pipeline report: row counts, resolution stats, unmatched players."""
    import json as _json
    from datetime import datetime, timezone
    from pathlib import Path
    import duckdb as _duckdb
    from rich.table import Table as RichTable
    from pipeline.config import GOLD_DB, LAST_RUN_COUNTS_FILE

    if not GOLD_DB.exists():
        console.print("[red]Database not found. Run `nfl load` first.[/red]")
        raise typer.Exit(1)

    con = _duckdb.connect(str(GOLD_DB), read_only=True)

    gold_tables = [
        "dim_players", "dim_teams", "dim_games",
        "fact_plays", "fact_pass_plays", "fact_rush_plays", "fact_kick_plays",
        "fact_player_game_stats", "fact_weekly_rosters", "fact_rosters",
        "fact_snap_counts", "fact_depth_charts", "fact_injuries",
        "ref_combine", "ref_contracts", "ref_draft_picks", "ref_trades",
        "name_resolution",
    ]

    row_counts: dict[str, int | None] = {}
    for t in gold_tables:
        try:
            row_counts[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            row_counts[t] = None

    resolution_methods: dict[str, int] = {}
    for row in con.execute(
        "SELECT method, COUNT(*) FROM name_resolution GROUP BY method ORDER BY method"
    ).fetchall():
        resolution_methods[row[0]] = row[1]

    unmatched = con.execute("""
        SELECT raw_name, source, method
        FROM name_resolution
        WHERE method IN ('rejected', 'llm_rejected')
        ORDER BY source, raw_name
    """).fetchall()
    unmatched_list = [{"raw_name": r[0], "source": r[1], "method": r[2]} for r in unmatched]

    con.close()

    run_at = datetime.now(timezone.utc).isoformat()
    report_data = {
        "run_at": run_at,
        "row_counts": row_counts,
        "resolution_methods": resolution_methods,
        "unmatched_players": unmatched_list,
        "unmatched_count": len(unmatched_list),
    }

    if format == "json":
        out = _json.dumps(report_data, indent=2, default=str)
        if output:
            Path(output).write_text(out)
        else:
            console.print(out)
        # Atomically update last_run_counts.json (CI side effect)
        counts_snapshot = {"run_at": run_at, "row_counts": row_counts, "resolution_methods": resolution_methods}
        tmp = LAST_RUN_COUNTS_FILE.with_suffix(".json.tmp")
        tmp.write_text(_json.dumps(counts_snapshot, indent=2, default=str))
        tmp.rename(LAST_RUN_COUNTS_FILE)
    else:
        count_table = RichTable(title="Gold Layer Row Counts")
        count_table.add_column("Table", style="bold")
        count_table.add_column("Rows", justify="right")
        for t, n in row_counts.items():
            count_table.add_row(t, f"{n:,}" if n is not None else "[dim]—[/dim]")
        console.print(count_table)

        res_table = RichTable(title="Name Resolution Methods")
        res_table.add_column("Method", style="bold")
        res_table.add_column("Count", justify="right")
        for method, count in resolution_methods.items():
            res_table.add_row(method, f"{count:,}")
        console.print(res_table)

        um_table = RichTable(title=f"Unmatched Players ({len(unmatched_list)})")
        um_table.add_column("Raw Name")
        um_table.add_column("Source")
        um_table.add_column("Method")
        for u in unmatched_list[:100]:
            um_table.add_row(u["raw_name"], u["source"], u["method"])
        console.print(um_table)

        if output:
            Path(output).write_text(_json.dumps(report_data, indent=2, default=str))
