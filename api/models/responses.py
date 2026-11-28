from __future__ import annotations

from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    total: int
    limit: int
    offset: int


class Player(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    gsis_id: str
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    position: str | None = None
    position_group: str | None = None
    birth_date: date | None = None
    height: int | None = None
    weight: int | None = None
    college: str | None = None
    draft_year: int | None = None
    draft_round: int | None = None
    draft_pick: int | None = None
    draft_club: str | None = None
    status: str | None = None
    years_exp: int | None = None
    rookie_year: int | None = None


class Game(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    game_id: str
    season: int | None = None
    week: int | None = None
    game_type: str | None = None
    gameday: date | None = None
    gametime: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    overtime: bool | None = None
    stadium: str | None = None
    roof: str | None = None
    surface: str | None = None
    temp: float | None = None
    wind: float | None = None
    spread_line: float | None = None
    total_line: float | None = None
    div_game: bool | None = None
    home_coach: str | None = None
    away_coach: str | None = None
    humidity: int | None = None
    attendance: int | None = None
    boxscore_url: str | None = None


class PlayerGameStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    player_id: str | None = None
    player_name: str | None = None
    recent_team: str | None = None
    season: int | None = None
    week: int | None = None
    season_type: str | None = None
    completions: int | None = None
    attempts: int | None = None
    passing_yards: int | None = None
    passing_tds: int | None = None
    interceptions: int | None = None
    passing_epa: float | None = None
    carries: int | None = None
    rushing_yards: int | None = None
    rushing_tds: int | None = None
    rushing_epa: float | None = None
    receptions: int | None = None
    targets: int | None = None
    receiving_yards: int | None = None
    receiving_tds: int | None = None
    receiving_epa: float | None = None
    target_share: float | None = None
    fantasy_points: float | None = None
    fantasy_points_ppr: float | None = None


class CombineResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    season: int | None = None
    player_name: str | None = None
    player_id: str | None = None
    pos: str | None = None
    school: str | None = None
    ht: str | None = None
    wt: int | None = None
    forty: float | None = None
    bench: int | None = None
    vertical: float | None = None
    broad_jump: int | None = None
    cone: float | None = None
    shuttle: float | None = None
    draft_year: int | None = None
    draft_round: int | None = None
    draft_ovr: int | None = None


class DraftPick(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    season: int | None = None
    round: int | None = None
    pick: int | None = None
    team: str | None = None
    player_name: str | None = None
    gsis_id: str | None = None
    pfr_player_id: str | None = None
    position: str | None = None
    college: str | None = None


class Contract(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    player_name: str | None = None
    player_id: str | None = None
    team: str | None = None
    position: str | None = None
    year_signed: int | None = None
    years: int | None = None
    value: int | None = None
    apy: int | None = None
    guaranteed: int | None = None
    apy_cap_pct: float | None = None
