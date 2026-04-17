"""Shared persona definitions for notebook setup and E2E testing.

Single source of truth for the four test personas used across tutorials,
reference notebooks, UAT, and E2E tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class PersonaConfig:
    """Configuration for a test persona.

    Each persona is identified by username (ADR-104/105). The env_var
    points to the environment variable containing the username for that
    persona.

    Attributes:
        name: Short identifier (e.g. ``"analyst_alice"``).
        role: Expected role in the database (e.g. ``"analyst"``).
        display_name: Human-readable label (e.g. ``"Alice (Analyst)"``).
        env_var: Environment variable containing the username.
    """

    name: str
    role: str
    display_name: str
    env_var: str

    # -- derived helpers used by testing.py ------------------------------------

    @property
    def expected_role(self) -> str:
        """Alias for :attr:`role` (backward compat with E2E tests)."""
        return self.role

    @property
    def description(self) -> str:
        """Auto-generated description from role and name."""
        role_label = self.role.capitalize()
        # e.g. "Analyst user Alice - standard analyst permissions"
        #       "Admin user Carol - elevated admin permissions"
        first_name = self.display_name.split(" ")[0]
        if self.role == "ops":
            return f"Ops user {first_name} - operations and monitoring permissions"
        if self.role == "admin":
            return f"Admin user {first_name} - elevated {role_label.lower()} permissions"
        return f"{role_label} user {first_name} - standard {role_label.lower()} permissions"


class Persona(Enum):
    """Pre-defined personas for all notebook and test contexts.

    Each persona maps to a username environment variable (ADR-104/105).
    The user must be provisioned in the database with the appropriate role.

    Naming pattern: <ROLE>_<NAME> for consistency.

    IMPORTANT: There is NO default persona. Every test must explicitly
    specify which user is acting. This prevents confusion and ensures
    tests are self-documenting about who is performing each action.

    This is the SINGLE SOURCE OF TRUTH for test personas.
    """

    ANALYST_ALICE = PersonaConfig(
        name="analyst_alice",
        role="analyst",
        display_name="Alice (Analyst)",
        env_var="GRAPH_OLAP_USERNAME_ANALYST_ALICE",
    )
    ANALYST_BOB = PersonaConfig(
        name="analyst_bob",
        role="analyst",
        display_name="Bob (Analyst)",
        env_var="GRAPH_OLAP_USERNAME_ANALYST_BOB",
    )
    ADMIN_CAROL = PersonaConfig(
        name="admin_carol",
        role="admin",
        display_name="Carol (Admin)",
        env_var="GRAPH_OLAP_USERNAME_ADMIN_CAROL",
    )
    OPS_DAVE = PersonaConfig(
        name="ops_dave",
        role="ops",
        display_name="Dave (Ops)",
        env_var="GRAPH_OLAP_USERNAME_OPS_DAVE",
    )


# Backward compatibility alias for E2E tests
TestPersona = Persona
