from pydantic import BaseModel


class TeamResponse(BaseModel):
    id: int
    name: str
    abbreviation: str | None
    conference: str | None
    league: str

    model_config = {"from_attributes": True}