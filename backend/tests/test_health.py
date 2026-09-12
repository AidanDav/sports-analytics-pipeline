import pytest


@pytest.mark.asyncio
async def test_health_returns_healthy(client):
    """Health endpoint should return healthy when DB is connected."""
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"