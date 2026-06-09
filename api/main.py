from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.deps import get_read_only_connection
from api.routers import games, meta, players, plays, reference, stats

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


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
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(players.router, prefix="/v1")
app.include_router(games.router, prefix="/v1")
app.include_router(plays.router, prefix="/v1")
app.include_router(stats.router, prefix="/v1")
app.include_router(reference.router, prefix="/v1")
app.include_router(meta.router, prefix="/v1")
