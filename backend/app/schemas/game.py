from pydantic import BaseModel


class GameResponse(BaseModel):
    id: int
    season: int
    week: int | None
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    game_date: str | None
    status: str | None
    venue: str | None