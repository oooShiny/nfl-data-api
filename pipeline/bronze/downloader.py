"""Download parquet files from nflverse GitHub releases into the bronze layer."""

import json
import subprocess
from pathlib import Path

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn

from pipeline.config import BRONZE_DIR, NFLVERSE_REPO, RELEASE_TAGS

console = Console()


def _gh_api(path: str) -> dict | list:
    result = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def list_release_assets(tag: str) -> list[dict]:
    """Return list of parquet assets for a release tag: [{name, url, size}]."""
    data = _gh_api(f"repos/{NFLVERSE_REPO}/releases/tags/{tag}")
    return [
        {"name": a["name"], "url": a["browser_download_url"], "size": a["size"]}
        for a in data.get("assets", [])
        if a["name"].endswith(".parquet")
    ]


def get_release_timestamp(tag: str) -> str | None:
    """Return the timestamp string from a release's timestamp.json asset, or None."""
    data = _gh_api(f"repos/{NFLVERSE_REPO}/releases/tags/{tag}")
    for asset in data.get("assets", []):
        if asset["name"] == "timestamp.json":
            try:
                resp = httpx.get(asset["browser_download_url"], follow_redirects=True, timeout=10)
                resp.raise_for_status()
                return resp.json().get("timestamp")
            except Exception:
                return None
    return None


def _stamp_path(tag_dir: Path) -> Path:
    return tag_dir / ".timestamp"


def _is_stale(tag_dir: Path, remote_ts: str | None) -> bool:
    stamp = _stamp_path(tag_dir)
    if not stamp.exists():
        return True
    if remote_ts is None:
        return False
    return stamp.read_text().strip() != remote_ts.strip()


def download_file(url: str, dest: Path, client: httpx.Client) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url, follow_redirects=True) as resp:
        resp.raise_for_status()
        with dest.open("wb") as f:
            for chunk in resp.iter_bytes(chunk_size=65536):
                f.write(chunk)


def download_release(tag: str, force: bool = False) -> int:
    """Download all parquet assets for a release. Returns count of files downloaded."""
    tag_dir = BRONZE_DIR / tag
    tag_dir.mkdir(parents=True, exist_ok=True)

    remote_ts = get_release_timestamp(tag)
    if not force and not _is_stale(tag_dir, remote_ts):
        console.print(f"  [dim]{tag}: up to date, skipping[/dim]")
        return 0

    assets = list_release_assets(tag)
    if not assets:
        console.print(f"  [yellow]{tag}: no parquet assets found[/yellow]")
        return 0

    downloaded = 0
    with httpx.Client(timeout=300) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[bold]{tag}[/bold] {{task.description}}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
            transient=True,
        ) as progress:
            for asset in assets:
                dest = tag_dir / asset["name"]
                task = progress.add_task(asset["name"], total=asset["size"])
                download_file(asset["url"], dest, client)
                progress.update(task, completed=asset["size"])
                downloaded += 1

    if remote_ts:
        _stamp_path(tag_dir).write_text(remote_ts)

    console.print(f"  [green]✓[/green] {tag}: {downloaded} files downloaded")
    return downloaded


def download_all(tags: list[str] | None = None, force: bool = False) -> dict[str, int]:
    """Download all releases. Returns {tag: file_count} for downloaded tags."""
    tags = tags or RELEASE_TAGS
    results = {}
    console.print(f"[bold]Downloading {len(tags)} releases from nflverse[/bold]")
    for tag in tags:
        results[tag] = download_release(tag, force=force)
    total = sum(results.values())
    console.print(f"\n[bold green]Done.[/bold green] {total} files downloaded across {len(tags)} releases.")
    return results
