"""Shared test fixtures."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from control_plane.config import Settings
from control_plane.infrastructure.database import reset_engine
from control_plane.infrastructure.tables import metadata
from control_plane.models import User
from control_plane.repositories.config import GlobalConfigRepository
from tests.fakes import FakeClock, FakeK8sClient

# Configure pytest-asyncio
pytest_plugins = ["pytest_asyncio"]

# Session-scoped PostgreSQL container for all tests
_postgres_container: PostgresContainer | None = None


@pytest.fixture(scope="session")
def postgres_container():
    """Session-scoped PostgreSQL container.

    Starts a single PostgreSQL container for the entire test session.
    Much faster than starting a new container per test.
    """
    global _postgres_container
    if _postgres_container is None:
        _postgres_container = PostgresContainer("postgres:15-alpine")
        _postgres_container.start()
    yield _postgres_container
    # Note: Container is stopped when process exits


@pytest.fixture
def settings(postgres_container: PostgresContainer) -> Settings:
    """Test settings with PostgreSQL testcontainer."""
    # Get connection URL and convert to async format
    url = postgres_container.get_connection_url()
    async_url = url.replace("postgresql://", "postgresql+asyncpg://")
    return Settings(
        database_url=async_url,
        debug=True,
        internal_api_key="test-internal-key",
    )


@pytest_asyncio.fixture
async def db_engine(settings: Settings):
    """Create async engine for tests."""
    engine = create_async_engine(
        settings.async_database_url,
        echo=False,
        pool_size=5,
        max_overflow=5,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    yield engine

    # Drop tables to reset state for next test
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    """Create database session for tests."""
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seeded_session(db_session: AsyncSession) -> AsyncSession:
    """Database session with seeded default config."""
    config_repo = GlobalConfigRepository(db_session)
    await config_repo.seed_defaults("system")
    await db_session.commit()
    return db_session


@pytest.fixture
def sample_user() -> User:
    """Sample analyst user for tests."""
    return User(
        username="alice.smith",
        email="alice.smith@example.com",
        display_name="Alice Smith",
        is_active=True,
    )


@pytest.fixture
def admin_user() -> User:
    """Sample admin user for tests."""
    return User(
        username="bob.admin",
        email="bob.admin@example.com",
        display_name="Bob Admin",
        is_active=True,
    )


@pytest.fixture
def ops_user() -> User:
    """Sample ops user for tests."""
    return User(
        username="charlie.ops",
        email="charlie.ops@example.com",
        display_name="Charlie Ops",
        is_active=True,
    )


@pytest.fixture(autouse=True)
def reset_global_engine():
    """Reset global engine state before each test."""
    reset_engine()
    yield
    reset_engine()


@pytest.fixture
def fake_k8s() -> FakeK8sClient:
    """Fake Kubernetes client for unit tests.

    Returns a fresh FakeK8sClient instance with empty state.
    Use this for fast, isolated unit tests of K8s operations.

    Example:
        def test_create_pod(fake_k8s):
            service = K8sService(settings)
            service._core_api = fake_k8s

            pod_name = service.create_pod(...)
            assert pod_name in fake_k8s.pods
    """
    return FakeK8sClient()


@pytest.fixture
def fake_clock() -> FakeClock:
    """Fake clock for testing time-based logic.

    Returns a FakeClock initialized to a fixed time (2024-01-01 12:00 UTC).
    Use this for deterministic testing of TTL expiration and time-based behavior.

    Example:
        def test_ttl_expiration(fake_clock):
            clock = fake_clock
            service = TTLService(clock=clock)

            instance = create_instance(ttl_hours=1)
            clock.advance(hours=2)
            assert service.is_expired(instance)
    """
    return FakeClock(now=datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
