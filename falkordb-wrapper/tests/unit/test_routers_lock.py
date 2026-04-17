"""Unit tests for the lock router.

Tests cover:
- GET /lock endpoint
- Lock status responses in locked/unlocked states

Note: Uses REAL LockService (not mocks) because LockService has no external
dependencies - it's pure in-memory Python. This follows Google testing best
practices: only mock at system boundaries (network, DB, filesystem).
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from wrapper.routers import lock
from wrapper.services.lock import LockService


@pytest.fixture
def app_with_unlocked_service():
    """Create a FastAPI app with REAL lock service in unlocked state.

    LockService starts in unlocked state by default, so no setup needed.
    """
    app = FastAPI()
    app.include_router(lock.router)

    # Use REAL LockService - no mocking needed (pure in-memory, no I/O)
    app.state.lock_service = LockService()
    return app


@pytest.fixture
def app_with_locked_service():
    """Create a FastAPI app with REAL lock service in locked state.

    Acquires the lock using the real service API to set up locked state.
    """
    app = FastAPI()
    app.include_router(lock.router)

    # Use REAL LockService
    lock_service = LockService()

    # Actually acquire the lock (real async operation)
    # Use asyncio.run() since fixture is synchronous
    asyncio.run(
        lock_service.acquire(
            user_id="user-001",
            user_name="testuser",
            algorithm_name="pagerank",
            algorithm_type="cypher",
        )
    )

    app.state.lock_service = lock_service
    return app


class TestGetLockStatus:
    """Tests for GET /lock endpoint."""

    def test_get_lock_status_when_unlocked(self, app_with_unlocked_service):
        """GET /lock returns locked=False when unlocked."""
        client = TestClient(app_with_unlocked_service)

        response = client.get("/lock")

        assert response.status_code == 200
        data = response.json()
        assert "lock" in data
        assert data["lock"]["locked"] is False
        assert data["lock"]["execution_id"] is None
        assert data["lock"]["holder_id"] is None

    def test_get_lock_status_when_locked(self, app_with_locked_service):
        """GET /lock returns full lock info when locked."""
        client = TestClient(app_with_locked_service)

        response = client.get("/lock")

        assert response.status_code == 200
        data = response.json()
        assert "lock" in data
        assert data["lock"]["locked"] is True

    def test_lock_endpoint_returns_holder_info(self, app_with_locked_service):
        """GET /lock returns holder information when locked."""
        client = TestClient(app_with_locked_service)

        response = client.get("/lock")
        data = response.json()

        assert data["lock"]["holder_id"] == "user-001"
        assert data["lock"]["holder_username"] == "testuser"

    def test_lock_endpoint_returns_algorithm_name(self, app_with_locked_service):
        """GET /lock returns algorithm name when locked."""
        client = TestClient(app_with_locked_service)

        response = client.get("/lock")
        data = response.json()

        assert data["lock"]["algorithm_name"] == "pagerank"
        assert data["lock"]["algorithm_type"] == "cypher"

    def test_lock_endpoint_returns_acquired_at(self, app_with_locked_service):
        """GET /lock returns acquired_at timestamp when locked."""
        client = TestClient(app_with_locked_service)

        response = client.get("/lock")
        data = response.json()

        assert data["lock"]["acquired_at"] is not None
        # Should be ISO format with timezone (real timestamp from LockService)
        acquired_at = data["lock"]["acquired_at"]
        assert "T" in acquired_at  # ISO 8601 format has T separator
        assert ":" in acquired_at  # Has time component

    def test_lock_endpoint_returns_execution_id(self, app_with_locked_service):
        """GET /lock returns execution_id when locked."""
        client = TestClient(app_with_locked_service)

        response = client.get("/lock")
        data = response.json()

        # execution_id is auto-generated UUID
        exec_id = data["lock"]["execution_id"]
        assert exec_id is not None
        assert len(exec_id) == 36  # UUID format
        assert exec_id.count("-") == 4  # UUID has 4 dashes


class TestLockEndpointServiceNotInitialized:
    """Tests for when lock service is not initialized."""

    def test_returns_503_when_service_not_initialized(self):
        """GET /lock returns 503 when lock service not in app state."""
        app = FastAPI()
        app.include_router(lock.router)
        # Don't set app.state.lock_service

        client = TestClient(app)
        response = client.get("/lock")

        assert response.status_code == 503
        assert "not initialized" in response.json()["detail"].lower()
