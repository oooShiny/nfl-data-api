"""Import local historical-data CSV sources (Pro-Football-Reference scrapes) into the bronze layer.

These are static, one-off datasets (1970+) that aren't part of the nflverse
releases and live on an external volume. Import is a no-op if the source
paths aren't mounted, so `nfl run` still works on machines without them.
"""

import re
from pathlib import Path

import polars as pl
from rich.console import Console

from pipeline.config import BRONZE_DIR, EXTERNAL_GAMELOGS_DIR, EXTERNAL_SCORING_DIR

console = Console()

_SCORING_FILENAME_RE = re.compile(r"^(\d{4})-\d+_scoring_.*\.csv$")


def _read_csv(path: Path) -> pl.DataFrame:
    df = pl.read_csv(path)
    if df.columns[0] == "":
        df = df.drop(df.columns[0])
    return df


def import_gamelogs(force: bool = False) -> int:
    """Convert gamelogs_<season>.csv files to bronze parquet, one per season."""
    if not EXTERNAL_GAMELOGS_DIR.exists():
        console.print("  [dim]historical_gamelogs: source not mounted, skipping[/dim]")
        return 0

    dst_dir = BRONZE_DIR / "historical_gamelogs"
    dst_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for src in sorted(EXTERNAL_GAMELOGS_DIR.glob("gamelogs_*.csv")):
        if src.name.startswith("._"):
            continue
        season = src.stem.removeprefix("gamelogs_")
        dst = dst_dir / f"{season}.parquet"
        if not force and dst.exists():
            continue
        df = _read_csv(src)
        df.write_parquet(dst, compression="zstd")
        written += 1

    if written:
        console.print(f"  [green]✓[/green] historical_gamelogs: {written} season files imported")
    return written


def import_scoring(force: bool = False) -> int:
    """Concatenate per-game scoring CSVs into bronze parquet, one per season."""
    if not EXTERNAL_SCORING_DIR.exists():
        console.print("  [dim]historical_scoring: source not mounted, skipping[/dim]")
        return 0

    dst_dir = BRONZE_DIR / "historical_scoring"
    dst_dir.mkdir(parents=True, exist_ok=True)

    by_season: dict[str, list[Path]] = {}
    for src in EXTERNAL_SCORING_DIR.glob("*_scoring_*.csv"):
        if src.name.startswith("._"):
            continue
        m = _SCORING_FILENAME_RE.match(src.name)
        if not m:
            continue
        by_season.setdefault(m.group(1), []).append(src)

    written = 0
    for season, files in sorted(by_season.items()):
        dst = dst_dir / f"{season}.parquet"
        if not force and dst.exists():
            continue
        df = pl.concat([_read_csv(f) for f in sorted(files)], how="vertical_relaxed")
        df.write_parquet(dst, compression="zstd")
        written += 1

    if written:
        console.print(f"  [green]✓[/green] historical_scoring: {written} season files imported")
    return written


def import_local_sources(force: bool = False) -> dict[str, int]:
    console.print("[bold]Importing local historical sources[/bold]")
    results = {
        "historical_gamelogs": import_gamelogs(force=force),
        "historical_scoring": import_scoring(force=force),
    }
    total = sum(results.values())
    if total:
        console.print(f"\n[bold green]Done.[/bold green] {total} season files imported.")
    else:
        console.print("  [dim]nothing to import[/dim]")
    return results
