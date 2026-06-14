from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.deps import get_read_only_connection
from api.routers import admin, advanced, games, meta, players, plays, reference, stats

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = get_read_only_connection()
    yield
    app.state.db.close()


app = FastAPI(
    title="NFL Data API",
    version="1.0.0",
    description=(
        "Public read-only access to the nflverse gold layer — play-by-play, "
        "player stats, games, rosters, contracts, combine, and draft data."
    ),
    lifespan=lifespan,
    docs_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    html = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Docs",
    ).body.decode()
    theme = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600;700'
        '&family=Barlow+Semi+Condensed:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600'
        '&display=swap" rel="stylesheet">'
        '<link rel="stylesheet" href="/static/swagger-broadcast.css">'
    )
    return HTMLResponse(html.replace("</head>", theme + "</head>"))

app.include_router(players.router, prefix="/v1")
app.include_router(games.router, prefix="/v1")
app.include_router(plays.router, prefix="/v1")
app.include_router(stats.router, prefix="/v1")
app.include_router(advanced.router, prefix="/v1")
app.include_router(reference.router, prefix="/v1")
app.include_router(meta.router, prefix="/v1")
app.include_router(admin.router, prefix="/v1")
