from pydantic import BaseModel
from typing import Generic, TypeVar

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Wrapper for any paginated list endpoint."""
    total: int
    limit: int
    offset: int
    data: list[T]