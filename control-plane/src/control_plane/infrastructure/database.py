"""Async database engine and session management using SQLAlchemy Core."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from control_plane.config import Settings, get_settings
from control_plane.infrastructure.tables import metadata

if TYPE_CHECKING:
    pass

# Module-level engine and session factory (initialized on first use)
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine_for_settings(settings: Settings) -> AsyncEngine:
    """Create async engine configured for the given settings.

    PostgreSQL is required - SQLite is not supported.
    """
    url = settings.async_database_url

    # Cloud SQL Proxy on localhost handles its own encryption;
    # disable asyncpg's default SSL attempt to avoid handshake errors.
    connect_args: dict = {}
    if "localhost" in settings.database_url or "127.0.0.1" in settings.database_url:
        connect_args["ssl"] = None

    # PostgreSQL configuration with connection pooling
    return create_async_engine(
        url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle connections after 1 hour
        connect_args=connect_args,
    )


def get_engine() -> AsyncEngine:
    """Get or create the global async engine."""
    global _engine
    if _engine is None:
        _engine = create_engine_for_settings(get_settings())
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the global session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


async def get_async_session(request: "Request") -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides a database session.

    Session is committed by DatabaseCommitMiddleware before response is sent,
    ensuring read-after-write consistency for all mutations.

    Usage in routers:
        @router.get("/items")
        async def get_items(session: AsyncSession = Depends(get_async_session)):
            ...

    Args:
        request: FastAPI Request (injected automatically)

    Yields:
        AsyncSession for database operations
    """
    session_factory = get_session_factory()
    session = session_factory()

    try:
        # Store session in request state for middleware to commit AND close
        if not hasattr(request.state, "_db_sessions"):
            request.state._db_sessions = []
        request.state._db_sessions.append(session)

        yield session
        # Middleware commits AND closes the session before response is sent
        # Don't close here - let middleware handle the full lifecycle
    except Exception:
        await session.rollback()
        await session.close()
        raise


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions outside of FastAPI.

    Usage:
        async with get_session() as session:
            result = await session.execute(text("SELECT 1"))
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_database(engine: AsyncEngine | None = None) -> None:
    """Initialize database by creating all tables.

    Args:
        engine: Optional engine to use. If None, uses global engine.
    """
    target_engine = engine or get_engine()
    async with target_engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


async def drop_database(engine: AsyncEngine | None = None) -> None:
    """Drop all tables. Use with caution!

    Args:
        engine: Optional engine to use. If None, uses global engine.
    """
    target_engine = engine or get_engine()
    async with target_engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)


async def check_database_health(engine: AsyncEngine | None = None) -> bool:
    """Check if database is accessible.

    Args:
        engine: Optional engine to use. If None, uses global engine.

    Returns:
        True if database is healthy, False otherwise.
    """
    target_engine = engine or get_engine()
    try:
        async with target_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def close_engine() -> None:
    """Close the global engine and dispose of connection pool."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def reset_engine() -> None:
    """Reset global engine state. Useful for testing."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


class DatabaseCommitMiddleware(BaseHTTPMiddleware):
    """Middleware that commits and closes database sessions before sending HTTP responses.

    This ensures read-after-write consistency by guaranteeing that all database
    writes are committed BEFORE the client receives the response with resource IDs.

    Without this middleware, the timeline is:
    1. Router creates resource, gets ID
    2. Response with ID is sent to client
    3. Client immediately GETs resource by ID
    4. Database session commits (too late!)
    5. GET fails with NotFoundError

    With this middleware:
    1. Router creates resource, gets ID
    2. Middleware commits session (writes are visible)
    3. Response with ID is sent to client
    4. Client GET succeeds

    The middleware commits AND closes all sessions stored in request.state._db_sessions,
    which are registered by the get_async_session() dependency.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request, commit sessions, then send response."""
        response = await call_next(request)

        # Commit and close all database sessions before sending response
        if hasattr(request.state, "_db_sessions"):
            for session in request.state._db_sessions:
                try:
                    await session.commit()
                except Exception:
                    # Rollback already happened in dependency
                    pass
                finally:
                    # Always close the session to release resources
                    await session.close()

        return response


class DatabaseManager:
    """Manages database lifecycle for application startup/shutdown.

    Usage with FastAPI lifespan:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            db_manager = DatabaseManager(get_settings())
            await db_manager.startup()
            yield
            await db_manager.shutdown()
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._engine: AsyncEngine | None = None

    @property
    def engine(self) -> AsyncEngine:
        """Get the engine, raising if not started."""
        if self._engine is None:
            raise RuntimeError("DatabaseManager not started")
        return self._engine

    async def startup(self) -> None:
        """Initialize database connection on application startup."""
        global _engine, _session_factory

        self._engine = create_engine_for_settings(self._settings)
        _engine = self._engine
        _session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )

        # Create tables if they don't exist
        # In debug mode (E2E tests): auto-create tables
        # In production: tables are managed by Alembic migrations
        if self._settings.debug:
            await init_database(self._engine)
            # Seed default config values
            await self._seed_defaults()

    async def _seed_defaults(self) -> None:
        """Seed default configuration values and system user."""
        from control_plane.repositories.base import utc_now
        from control_plane.repositories.config import GlobalConfigRepository

        async with _session_factory() as session:
            # First create the system user if it doesn't exist (for foreign keys)
            now = utc_now()
            await session.execute(
                text("""
                    INSERT INTO users (username, email, display_name, role, created_at, updated_at, is_active)
                    VALUES (:username, :email, :display_name, :role, :now, :now, :is_active)
                    ON CONFLICT (username) DO NOTHING
                """),
                {
                    "username": "system",
                    "email": "system@internal",
                    "display_name": "System",
                    "role": "ops",
                    "now": now,
                    "is_active": 1,
                },
            )
            await session.commit()

        async with _session_factory() as session:
            repo = GlobalConfigRepository(session)
            await repo.seed_defaults("system")
            await session.commit()

    async def shutdown(self) -> None:
        """Close database connections on application shutdown."""
        global _engine, _session_factory

        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

        _engine = None
        _session_factory = None
