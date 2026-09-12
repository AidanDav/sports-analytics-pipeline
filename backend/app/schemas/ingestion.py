from pydantic import BaseModel


class IngestionRunResponse(BaseModel):
    status: str
    rows_created: int
    rows_updated: int
    error: str | None