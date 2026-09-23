from pydantic import BaseModel


class GameResponse(BaseModel):
    id: int
    season: int
    week: int | None
    # IDs let the frontend tell home from away and link to the opponent
    # without comparing team names
    home_team_id: int | None
    away_team_id: int | None
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    game_date: str | None
    status: str | None
    venue: str | None