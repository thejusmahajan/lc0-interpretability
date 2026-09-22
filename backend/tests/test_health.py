from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

def test_health_endpoint():
    """
    Ensure the health endpoint returns a 200 OK and valid JSON.
    """
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
