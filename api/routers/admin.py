import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from api.deps import get_read_only_connection
from pipeline.config import GOLD_DB, LAST_RUN_COUNTS_FILE

router = APIRouter(tags=["admin"])

ADMIN_TOKEN = os.environ.get("ADMIN_REFRESH_TOKEN")
RELEASE_BASE_URL = "https://github.com/oooShiny/nfl-data-api/releases/download/latest-data"


def _download(url: str, dest: Path) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                f.write(chunk)


@router.post("/admin/refresh")
def refresh(request: Request, x_admin_token: str | None = Header(default=None)):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    db_tmp = GOLD_DB.with_suffix(".duckdb.new")
    counts_tmp = LAST_RUN_COUNTS_FILE.with_suffix(".json.new")

    try:
        _download(f"{RELEASE_BASE_URL}/nfl.duckdb", db_tmp)
        _download(f"{RELEASE_BASE_URL}/last_run_counts.json", counts_tmp)
    except Exception as e:
        db_tmp.unlink(missing_ok=True)
        counts_tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=f"Download failed: {e}")

    if db_tmp.stat().st_size < 1_000_000:
        db_tmp.unlink(missing_ok=True)
        counts_tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail="Downloaded database looks too small")

    old_db = request.app.state.db
    if old_db is not None:
        old_db.close()

    db_tmp.replace(GOLD_DB)
    counts_tmp.replace(LAST_RUN_COUNTS_FILE)

    request.app.state.db = get_read_only_connection()

    return {"status": "ok", "size": GOLD_DB.stat().st_size}
