from pydantic import BaseModel


class PlayerResponse(BaseModel):
    id: int
    first_name: str | None
    last_name: str
    position: str | None
    number: int | None
    team_id: int | None
    team_name: str | None
    league: str

    model_config = {"from_attributes": True}