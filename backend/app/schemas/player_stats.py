from pydantic import BaseModel


class PlayerStatsResponse(BaseModel):
    id: int
    player_id: int | None
    game_id: int | None
    stat_category: str
    attempts: int | None
    completions: int | None
    yards: float | None
    touchdowns: int | None
    interceptions: int | None
    receptions: int | None
    targets: int | None
    carries: int | None
    fumbles: int | None
    tackles: float | None
    sacks: float | None

    model_config = {"from_attributes": True}