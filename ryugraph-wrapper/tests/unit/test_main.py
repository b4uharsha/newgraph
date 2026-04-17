"""Unit tests for the main FastAPI application module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wrapper.exceptions import (
    AlgorithmNotFoundError,
    QueryTimeoutError,
    ResourceLockedError,
    WrapperError,
)


@pytest.fixture
def mock_lifespan() -> MagicMock:
    """Create a mock lifespan context manager."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_lifespan_func(app: FastAPI):  # type: ignore[no-untyped-def]
        yield

    return mock_lifespan_func


class TestCreateApp:
    """Tests for the create_app factory function."""

    @pytest.mark.unit
    def test_create_app_returns_fastapi_instance(self, mock_lifespan: MagicMock) -> None:
        """create_app returns a FastAPI instance."""
        with patch("wrapper.main.lifespan", mock_lifespan):
            from wrapper.main import create_app

            app = create_app()
            assert isinstance(app, FastAPI)
            assert app.title == "Ryugraph Wrapper API"

    @pytest.mark.unit
    def test_app_has_required_routes(self, mock_lifespan: MagicMock) -> None:
        """App has all required routes registered."""
        with patch("wrapper.main.lifespan", mock_lifespan):
            from wrapper.main import create_app

            app = create_app()
            routes = [r.path for r in app.routes]

            # Check key endpoints exist
            assert "/" in routes
            assert "/health" in routes
            assert "/ready" in routes
            assert "/query" in routes
            assert "/schema" in routes
            assert "/lock" in routes
            assert "/docs" in routes
            assert "/openapi.json" in routes


class TestExceptionHandlers:
    """Tests for application exception handlers."""

    @pytest.fixture
    def app(self, mock_lifespan: MagicMock) -> FastAPI:
        """Create app for testing exception handlers."""
        with patch("wrapper.main.lifespan", mock_lifespan):
            from wrapper.main import create_app

            return create_app()

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    @pytest.mark.unit
    def test_wrapper_error_handler(self, app: FastAPI, client: TestClient) -> None:
        """WrapperError is handled with custom response."""

        @app.get("/test-wrapper-error")
        async def raise_wrapper_error() -> None:
            raise WrapperError("Test error message", details={"key": "value"})

        response = client.get("/test-wrapper-error")
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "WRAPPER_ERROR"
        assert "Test error message" in data["error"]["message"]

    @pytest.mark.unit
    def test_algorithm_not_found_handler(self, app: FastAPI, client: TestClient) -> None:
        """AlgorithmNotFoundError returns 404."""

        @app.get("/test-algo-not-found")
        async def raise_algo_not_found() -> None:
            raise AlgorithmNotFoundError("my_algorithm")

        response = client.get("/test-algo-not-found")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "ALGORITHM_NOT_FOUND"
        assert "my_algorithm" in data["error"]["message"]

    @pytest.mark.unit
    def test_query_timeout_handler(self, app: FastAPI, client: TestClient) -> None:
        """QueryTimeoutError returns 408."""

        @app.get("/test-query-timeout")
        async def raise_query_timeout() -> None:
            raise QueryTimeoutError(timeout_ms=5000, elapsed_ms=5100)

        response = client.get("/test-query-timeout")
        assert response.status_code == 408
        data = response.json()
        assert data["error"]["code"] == "QUERY_TIMEOUT"
        assert data["error"]["details"]["timeout_ms"] == 5000
        assert data["error"]["details"]["elapsed_ms"] == 5100

    @pytest.mark.unit
    def test_resource_locked_handler(self, app: FastAPI, client: TestClient) -> None:
        """ResourceLockedError returns 409."""

        @app.get("/test-resource-locked")
        async def raise_resource_locked() -> None:
            raise ResourceLockedError(
                holder_id="user-123",
                holder_username="testuser",
                algorithm_name="pagerank",
                acquired_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            )

        response = client.get("/test-resource-locked")
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "RESOURCE_LOCKED"
        assert data["error"]["details"]["holder_username"] == "testuser"
        assert data["error"]["details"]["algorithm_name"] == "pagerank"

    @pytest.mark.unit
    def test_validation_error_handler(self, app: FastAPI, client: TestClient) -> None:
        """Validation errors return 422 with details."""
        from pydantic import BaseModel

        # Create a test endpoint that requires validation
        class TestModel(BaseModel):
            name: str
            value: int

        @app.post("/test-validation")
        async def test_validation(data: TestModel) -> dict[str, str]:
            return {"status": "ok"}

        # Send invalid data to trigger validation error
        response = client.post("/test-validation", json={"invalid": "data"})
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "errors" in data["error"]["details"]


class TestRootEndpoint:
    """Tests for the root endpoint."""

    @pytest.fixture
    def client(self, mock_lifespan: MagicMock) -> TestClient:
        """Create test client."""
        with patch("wrapper.main.lifespan", mock_lifespan):
            from wrapper.main import create_app

            app = create_app()
            return TestClient(app, raise_server_exceptions=False)

    @pytest.mark.unit
    def test_root_returns_api_info(self, client: TestClient) -> None:
        """Root endpoint returns API information."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Ryugraph Wrapper API"
        assert data["version"] == "1.0.0"
        assert data["docs"] == "/docs"
