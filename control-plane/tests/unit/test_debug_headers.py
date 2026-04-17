"""Unit tests for the /api/debug/headers endpoint."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from control_plane.routers.health import router


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with the health router."""
    app = FastAPI()
    app.include_router(router)
    return app


client = TestClient(_make_app())


def test_debug_headers_returns_custom_headers():
    """Custom headers sent by the client appear in the response."""
    response = client.get(
        "/api/debug/headers",
        headers={
            "x-username": "alice",
            "x-use-case-id": "uc-42",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["x-username"] == "alice"
    assert body["x-use-case-id"] == "uc-42"


def test_debug_headers_returns_standard_headers():
    """Standard HTTP headers (host, user-agent, etc.) are included."""
    response = client.get("/api/debug/headers")

    assert response.status_code == 200
    body = response.json()
    # TestClient always sends a host header
    assert "host" in body


def test_debug_headers_is_case_insensitive():
    """HTTP headers are case-insensitive; response keys are lowercase."""
    response = client.get(
        "/api/debug/headers",
        headers={"X-Mixed-Case": "value"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["x-mixed-case"] == "value"
