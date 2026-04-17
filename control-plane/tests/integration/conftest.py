"""Integration test fixtures.

Provisions test users in the database for each test. The identity middleware
(ADR-104) reads roles from the DB, so users must exist before API calls.
"""

import pytest
from fastapi.testclient import TestClient


# All test users and their roles. The first ops user is created via the
# unauthenticated bootstrap endpoint; the rest are created by that ops user.
_TEST_USERS = [
    # (username, email, display_name, role)
    # First entry MUST be ops — used for bootstrap.
    ("charlie.ops", "charlie.ops@test.local", "Charlie Ops", "ops"),
    ("bob.admin", "bob.admin@test.local", "Bob Admin", "admin"),
    ("alice.smith", "alice.smith@test.local", "Alice Smith", "analyst"),
    ("test.user", "test.user@test.local", "Test User", "analyst"),
    ("other.user", "other.user@test.local", "Other User", "analyst"),
    ("ops.user", "ops.user@test.local", "Ops User", "ops"),
    ("analyst.user", "analyst.user@test.local", "Analyst User", "analyst"),
    ("admin.user", "admin.user@test.local", "Admin User", "admin"),
]


def seed_test_users(client: TestClient) -> None:
    """Provision all standard test users in the database.

    Call this once per test (after table creation) to populate the users
    table so that the identity middleware can resolve usernames to roles.

    Flow:
    1. Bootstrap the first ops user (no auth required, empty DB).
    2. Use that ops user to create the remaining users via POST /api/users.
    """
    bootstrap_user = _TEST_USERS[0]
    resp = client.post(
        "/api/users/bootstrap",
        json={
            "username": bootstrap_user[0],
            "email": bootstrap_user[1],
            "display_name": bootstrap_user[2],
            "role": bootstrap_user[3],
        },
    )
    assert resp.status_code == 201, f"Bootstrap failed: {resp.text}"

    ops_headers = {"X-Username": bootstrap_user[0]}

    for username, email, display_name, role in _TEST_USERS[1:]:
        resp = client.post(
            "/api/users",
            json={
                "username": username,
                "email": email,
                "display_name": display_name,
                "role": role,
            },
            headers=ops_headers,
        )
        assert resp.status_code == 201, f"Create user {username} failed: {resp.text}"
