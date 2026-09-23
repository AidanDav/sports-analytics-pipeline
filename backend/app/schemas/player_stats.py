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

class GameStatLineResponse(PlayerStatsResponse):
    """A stat line with the player resolved, for box score views.

    PlayerStatsResponse only carries player_id, which forces the
    frontend into one request per player just to show a name.
    """
    player_name: str
    position: str | None
    team_id: int | None