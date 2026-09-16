from pydantic import BaseModel


class ReportResponse(BaseModel):
    id: int
    report_type: str
    title: str
    content: str | None = None
    status: str
    season: int | None
    week: int | None

    model_config = {"from_attributes": True}