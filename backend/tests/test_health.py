"""GET /api/v1/health 200. Is kurali yok."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["service"] == "tamlife"
    assert "pin" not in response.text.lower()
    assert "totp" not in response.text.lower()
