"""
Tests for /api/training/trends endpoint.
Verifies that trends data incorporates live SRS and training stats.
"""
from fastapi.testclient import TestClient
from backend.app import app

def test_get_trends_endpoint_returns_live_stats():
    client = TestClient(app)
    response = client.get("/api/training/trends")
    assert response.status_code == 200
    data = response.json()
    assert "srs_stats" in data
    assert "sac_stats" in data
    assert "intuition_stats" in data
    assert "accuracy" in data["srs_stats"]
