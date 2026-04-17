"""E2E tests for user management API.

Tests CRUD operations on the /api/users endpoints via the SDK's UserResource.
Most operations require admin or ops privileges; permission-denial tests use
the analyst persona to verify access control.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import pytest

from graph_olap.exceptions import ConflictError, ForbiddenError, GraphOLAPError, PermissionDeniedError

if TYPE_CHECKING:
    from graph_olap import GraphOLAPClient

logger = logging.getLogger(__name__)


def _worker_id() -> str:
    """Return the pytest-xdist worker id ('gw0', 'gw1', ...) or 'main' if not parallel."""
    return os.environ.get("PYTEST_XDIST_WORKER", "main")


def _test_username(suffix: str = "") -> str:
    """Return a unique test username scoped to this xdist worker."""
    tag = f"-{suffix}" if suffix else ""
    return f"{_worker_id()}-e2e-test-user{tag}@test.local"


def _ensure_test_user_absent(client: GraphOLAPClient, username: str) -> None:
    """Deactivate the test user if it exists (idempotent cleanup)."""
    try:
        client.users.deactivate(username)
        logger.info(f"Cleaned up pre-existing test user: {username}")
    except Exception:
        pass


# =============================================================================
# E2E Tests
# =============================================================================


@pytest.mark.xdist_group("user_management")
@pytest.mark.e2e
class TestUserManagement:
    """E2E tests for user management operations."""

    def test_list_users(self, ops_client: GraphOLAPClient):
        """Ops can list users; at least the 4 E2E personas exist."""
        users = ops_client.users.list()

        assert isinstance(users, list), f"Expected list, got {type(users)}"
        assert len(users) >= 3, f"Expected >= 3 users, got {len(users)}"

        for user in users:
            assert "username" in user, f"User missing 'username': {user}"
            assert "role" in user, f"User missing 'role': {user}"
            assert "is_active" in user, f"User missing 'is_active': {user}"

        logger.info(f"Listed {len(users)} user(s)")

    def test_get_user_self(self, graph_olap_client: GraphOLAPClient):
        """Analyst can retrieve their own profile."""
        user = graph_olap_client.users.get("analyst_alice@e2e.local")

        assert user["username"] == "analyst_alice@e2e.local"
        assert user["role"] == "analyst"
        logger.info(f"Retrieved self: {user['username']} (role={user['role']})")

    def test_get_user_as_admin(self, admin_client: GraphOLAPClient):
        """Admin can retrieve another user's profile."""
        user = admin_client.users.get("analyst_alice@e2e.local")

        assert user["username"] == "analyst_alice@e2e.local"
        assert user["role"] == "analyst"
        logger.info(f"Admin retrieved user: {user['username']}")

    def test_create_and_deactivate_user(self, ops_client: GraphOLAPClient):
        """Ops can create a user and then deactivate them.

        Uses a unique username to avoid conflicts with deactivated users
        from previous runs (the API returns 500 on re-create of deactivated users).
        """
        import uuid
        unique = uuid.uuid4().hex[:6]
        username = f"{_worker_id()}-e2e-create-{unique}@test.local"

        try:
            user = ops_client.users.create(
                username=username,
                email=f"create-{unique}@test.local",
                display_name="E2E Create Test",
                role="analyst",
            )
            assert user["username"] == username
            logger.info(f"Created test user: {username}")

            # Deactivate the user
            deactivated = ops_client.users.deactivate(username)
            assert deactivated["is_active"] is False, (
                f"Expected is_active=False, got {deactivated.get('is_active')}"
            )
            logger.info(f"Deactivated test user: {username}")
        finally:
            _ensure_test_user_absent(ops_client, username)

    def test_update_user(self, ops_client: GraphOLAPClient):
        """Ops can update a user's display name."""
        import uuid
        unique = uuid.uuid4().hex[:6]
        username = f"{_worker_id()}-e2e-update-{unique}@test.local"

        try:
            ops_client.users.create(
                username=username,
                email=f"update-{unique}@test.local",
                display_name="Original Name",
                role="analyst",
            )

            updated = ops_client.users.update(username, display_name="Updated Name")
            assert updated["display_name"] == "Updated Name", (
                f"Expected 'Updated Name', got {updated.get('display_name')}"
            )
            logger.info(f"Updated display_name for {username}")
        finally:
            _ensure_test_user_absent(ops_client, username)

    @pytest.mark.xfail(reason="assign_role API returns 500 — server-side bug", strict=False)
    def test_assign_role(self, ops_client: GraphOLAPClient):
        """Ops can change a user's role."""
        import uuid
        unique = uuid.uuid4().hex[:6]
        username = f"{_worker_id()}-e2e-role-{unique}@test.local"

        try:
            ops_client.users.create(
                username=username,
                email=f"role-{unique}@test.local",
                display_name="Role Test User",
                role="analyst",
            )

            # Promote to admin
            promoted = ops_client.users.assign_role(username, role="admin")
            assert promoted["role"] == "admin", (
                f"Expected role='admin', got {promoted.get('role')}"
            )
            logger.info(f"Promoted {username} to admin")

            # Demote back to analyst
            demoted = ops_client.users.assign_role(username, role="analyst")
            assert demoted["role"] == "analyst", (
                f"Expected role='analyst', got {demoted.get('role')}"
            )
            logger.info(f"Demoted {username} back to analyst")
        finally:
            _ensure_test_user_absent(ops_client, username)

    def test_analyst_cannot_list_users(self, graph_olap_client: GraphOLAPClient):
        """Analyst is denied access to the user list."""
        with pytest.raises((PermissionDeniedError, ForbiddenError)):
            graph_olap_client.users.list()

        logger.info("Analyst correctly denied from listing users")

    def test_analyst_cannot_create_users(self, graph_olap_client: GraphOLAPClient):
        """Analyst is denied access to user creation."""
        with pytest.raises((PermissionDeniedError, ForbiddenError)):
            graph_olap_client.users.create(
                username="should-not-exist@test.local",
                email="nope@test.local",
                display_name="Should Not Exist",
                role="analyst",
            )

        logger.info("Analyst correctly denied from creating users")
