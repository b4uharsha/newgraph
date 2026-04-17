"""Base repository with common database operations and utilities."""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession


def utc_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse ISO 8601 timestamp string to datetime."""
    if value is None:
        return None
    # Handle both Z suffix and +00:00 offset
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def serialize_json(data: dict[str, Any] | list[Any] | None) -> str | None:
    """Serialize Python object to JSON string for TEXT column."""
    if data is None:
        return None
    return json.dumps(data)


def deserialize_json(value: str | None) -> dict[str, Any] | list[Any] | None:
    """Deserialize JSON string from TEXT column."""
    if value is None:
        return None
    return json.loads(value)


def row_to_dict(row: Row) -> dict[str, Any]:
    """Convert SQLAlchemy Row to dictionary."""
    return dict(row._mapping)


class BaseRepository:
    """Base repository with common database patterns.

    All repositories inherit from this class to get:
    - Session management
    - Common query execution methods
    - Utility functions for timestamps and JSON
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository with a database session.

        Args:
            session: SQLAlchemy async session for database operations.
        """
        self._session = session

    async def _execute(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """Execute raw SQL and return result.

        Args:
            sql: SQL query string with named parameters (e.g., :param_name)
            params: Dictionary of parameter values

        Returns:
            SQLAlchemy Result object
        """
        return await self._session.execute(text(sql), params or {})

    async def _fetch_one(self, sql: str, params: dict[str, Any] | None = None) -> Row | None:
        """Execute SQL and return single row or None.

        Args:
            sql: SQL query string
            params: Dictionary of parameter values

        Returns:
            Single Row or None if no results
        """
        result = await self._execute(sql, params)
        return result.fetchone()

    async def _fetch_all(self, sql: str, params: dict[str, Any] | None = None) -> list[Row]:
        """Execute SQL and return all rows.

        Args:
            sql: SQL query string
            params: Dictionary of parameter values

        Returns:
            List of Row objects
        """
        result = await self._execute(sql, params)
        return list(result.fetchall())

    async def _fetch_scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """Execute SQL and return scalar value.

        Args:
            sql: SQL query string returning single value
            params: Dictionary of parameter values

        Returns:
            Scalar value from first column of first row
        """
        result = await self._execute(sql, params)
        row = result.fetchone()
        return row[0] if row else None

    async def _insert_returning_id(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute INSERT with RETURNING clause and return the auto-generated ID.

        The SQL must include 'RETURNING id' at the end for PostgreSQL.

        Args:
            sql: INSERT SQL statement with RETURNING id clause
            params: Dictionary of parameter values

        Returns:
            Auto-generated integer ID
        """
        result = await self._execute(sql, params)
        row = result.fetchone()
        return row[0] if row else 0
