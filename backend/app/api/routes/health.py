from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas import HealthResponse
# The health check gets its own router. This keeps the code code organized as my app grows, as 
# later I will have routers for teams, games, reports, etc.
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
# Dependency injection is used to get a database session. The get_db function is called, which creates a new session 
# and yields it to the health_check function. The session is automatically closed after the function completes.
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check API and database connectivity."""
    try:
        #Simplest database query. This is used to check if the database is reachable and responsive. 
        # If the query executes successfully, it means the database is connected. If it fails, an exception is raised, 
        # and the database is considered to be in a degraded state.
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        database=db_status
    )