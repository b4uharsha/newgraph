"""Integration test fixtures for background jobs."""

from datetime import UTC, datetime

import pytest_asyncio
from graph_olap_schemas import WrapperType
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.infrastructure.tables import instances, mappings, snapshots, users
from control_plane.models import Instance


class TestInstanceFactory:
    """Factory for creating test instances directly in database."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._id_counter = 0

    async def create(
        self,
        *,
        mapping_id: int = 1,
        snapshot_id: int = 1,
        created_by: str = "test-user",
        wrapper_type: WrapperType = WrapperType.RYUGRAPH,
        ttl: str | None = None,
        inactivity_timeout: str | None = None,
        status: str = "starting",
        pod_name: str | None = None,
    ) -> Instance:
        """Create test instance directly in database."""
        self._id_counter += 1
        now = datetime.now(UTC).isoformat()

        result = await self.session.execute(
            insert(instances)
            .values(
                snapshot_id=snapshot_id,
                owner_username=created_by,
                wrapper_type=wrapper_type.value,
                name=f"test-instance-{self._id_counter}",
                description="Test instance",
                status=status,
                pod_name=pod_name,
                pod_ip=None,
                ttl=ttl,
                inactivity_timeout=inactivity_timeout,
                last_activity_at=now if status == "running" else None,
                error_code=None,
                error_message=None,
                created_at=now,
                updated_at=now,
                started_at=None,
            )
            .returning(instances)
        )
        row = result.fetchone()
        await self.session.commit()

        # Fetch the instance as a model
        result = await self.session.execute(select(instances).where(instances.c.id == row.id))
        instance_row = result.fetchone()
        return Instance(**dict(instance_row._mapping))

    async def update(self, instance_id: int, updates: dict) -> None:
        """Update instance fields directly."""
        from sqlalchemy import update

        await self.session.execute(
            update(instances).where(instances.c.id == instance_id).values(**updates)
        )
        await self.session.commit()

    async def get(self, instance_id: int) -> Instance | None:
        """Get instance by ID."""
        result = await self.session.execute(
            select(instances).where(instances.c.id == instance_id)
        )
        row = result.fetchone()
        if not row:
            return None
        return Instance(**dict(row._mapping))

    async def delete(self, instance_id: int) -> None:
        """Delete instance by ID."""
        from sqlalchemy import delete

        await self.session.execute(delete(instances).where(instances.c.id == instance_id))
        await self.session.commit()


class TestMappingFactory:
    """Factory for creating test mappings directly in database."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._id_counter = 0

    async def create(
        self,
        *,
        name: str | None = None,
        created_by: str = "test-user",
        raw_schema: dict | None = None,
        ttl: str | None = None,
    ):
        """Create test mapping directly in database."""
        from control_plane.infrastructure.tables import mapping_versions

        self._id_counter += 1
        now = datetime.now(UTC).isoformat()

        if raw_schema is None:
            raw_schema = {}

        if name is None:
            name = f"test-mapping-{self._id_counter}"

        # Insert mapping with current_version=1
        result = await self.session.execute(
            insert(mappings)
            .values(
                owner_username=created_by,
                name=name,
                description="Test mapping",
                current_version=1,
                ttl=ttl,
                created_at=now,
                updated_at=now,
            )
            .returning(mappings)
        )
        mapping_row = result.fetchone()

        # Insert mapping version
        await self.session.execute(
            insert(mapping_versions).values(
                mapping_id=mapping_row.id,
                version=1,
                node_definitions="[]",  # Empty JSON array
                edge_definitions="[]",  # Empty JSON array
                change_description=None,  # NULL for version 1
                created_by=created_by,
                created_at=now,
            )
        )

        await self.session.commit()

        # Return a simple object with id
        class Mapping:
            def __init__(self, id):
                self.id = id

        return Mapping(mapping_row.id)

    async def update(self, mapping_id: int, updates: dict) -> None:
        """Update mapping fields directly."""
        from sqlalchemy import update

        await self.session.execute(
            update(mappings).where(mappings.c.id == mapping_id).values(**updates)
        )
        await self.session.commit()

    async def get(self, mapping_id: int):
        """Get mapping by ID."""
        result = await self.session.execute(select(mappings).where(mappings.c.id == mapping_id))
        row = result.fetchone()
        if not row:
            return None

        class Mapping:
            def __init__(self, id):
                self.id = id

        return Mapping(row.id)


class TestSnapshotFactory:
    """Factory for creating test snapshots directly in database."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._id_counter = 0

    async def create(
        self,
        *,
        name: str | None = None,
        mapping_id: int,
        created_by: str = "test-user",
        ttl: str | None = None,
    ):
        """Create test snapshot directly in database."""
        self._id_counter += 1
        now = datetime.now(UTC).isoformat()

        if name is None:
            name = f"test-snapshot-{self._id_counter}"

        result = await self.session.execute(
            insert(snapshots)
            .values(
                mapping_id=mapping_id,
                mapping_version=1,
                owner_username=created_by,
                name=name,
                description="Test snapshot",
                gcs_path=f"gs://test-bucket/{name}",
                status="ready",
                ttl=ttl,
                created_at=now,
                updated_at=now,
            )
            .returning(snapshots)
        )
        snapshot_row = result.fetchone()
        await self.session.commit()

        # Return a simple object with id
        class Snapshot:
            def __init__(self, id):
                self.id = id

        return Snapshot(snapshot_row.id)

    async def update(self, snapshot_id: int, updates: dict) -> None:
        """Update snapshot fields directly."""
        from sqlalchemy import update

        await self.session.execute(
            update(snapshots).where(snapshots.c.id == snapshot_id).values(**updates)
        )
        await self.session.commit()

    async def get(self, snapshot_id: int):
        """Get snapshot by ID."""
        result = await self.session.execute(select(snapshots).where(snapshots.c.id == snapshot_id))
        row = result.fetchone()
        if not row:
            return None

        class Snapshot:
            def __init__(self, id, status):
                self.id = id
                self.status = status

        return Snapshot(row.id, row.status)


class TestExportJobFactory:
    """Factory for creating test export jobs directly in database."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._id_counter = 0

    async def create(
        self,
        *,
        snapshot_id: int,
        entity_type: str = "node",
        entity_name: str,
        status: str = "pending",
    ):
        """Create test export job directly in database."""
        from control_plane.infrastructure.tables import export_jobs

        self._id_counter += 1
        now = datetime.now(UTC).isoformat()

        result = await self.session.execute(
            insert(export_jobs)
            .values(
                snapshot_id=snapshot_id,
                job_type=entity_type,
                entity_name=entity_name,
                status=status,
                sql=None,
                column_names=None,
                starburst_catalog=None,
                claimed_by=None,
                claimed_at=None,
                starburst_query_id=None,
                next_uri=None,
                next_poll_at=None,
                poll_count=0,
                gcs_path=f"gs://test-bucket/snapshots/{snapshot_id}/{entity_name}.parquet",
                row_count=None,
                size_bytes=None,
                submitted_at=None,
                completed_at=None,
                error_message=None,
                created_at=now,
                updated_at=now,
            )
            .returning(export_jobs)
        )
        job_row = result.fetchone()
        await self.session.commit()

        class ExportJob:
            def __init__(self, id, status, claimed_at, claimed_by):
                self.id = id
                self.status = status
                self.claimed_at = claimed_at
                self.claimed_by = claimed_by

        return ExportJob(job_row.id, job_row.status, job_row.claimed_at, job_row.claimed_by)

    async def update(self, job_id: int, updates: dict) -> None:
        """Update export job fields directly."""
        from sqlalchemy import update

        from control_plane.infrastructure.tables import export_jobs

        await self.session.execute(
            update(export_jobs).where(export_jobs.c.id == job_id).values(**updates)
        )
        await self.session.commit()

    async def get(self, job_id: int):
        """Get export job by ID."""
        from control_plane.infrastructure.tables import export_jobs

        result = await self.session.execute(select(export_jobs).where(export_jobs.c.id == job_id))
        row = result.fetchone()
        if not row:
            return None

        class ExportJob:
            def __init__(self, id, status, claimed_at, claimed_by):
                self.id = id
                self.status = status
                self.claimed_at = claimed_at
                self.claimed_by = claimed_by

        return ExportJob(row.id, row.status, row.claimed_at, row.claimed_by)


@pytest_asyncio.fixture
async def instance_repo(db_session: AsyncSession) -> TestInstanceFactory:
    """Create instance factory for tests."""
    return TestInstanceFactory(db_session)


@pytest_asyncio.fixture
async def snapshot_repo(db_session: AsyncSession) -> TestSnapshotFactory:
    """Create snapshot factory for tests."""
    return TestSnapshotFactory(db_session)


@pytest_asyncio.fixture
async def mapping_repo(db_session: AsyncSession) -> TestMappingFactory:
    """Create mapping factory for tests."""
    return TestMappingFactory(db_session)


@pytest_asyncio.fixture
async def export_job_repo(db_session: AsyncSession) -> TestExportJobFactory:
    """Create export job factory for tests."""
    return TestExportJobFactory(db_session)


@pytest_asyncio.fixture(autouse=True)
async def setup_test_user(db_session: AsyncSession):
    """Create test user in database for all integration tests."""
    now = datetime.now(UTC).isoformat()

    # Insert test-user if not exists
    await db_session.execute(
        insert(users).values(
            username="test-user",
            email="test@example.com",
            display_name="Test User",
            created_at=now,
            updated_at=now,
            is_active=1,
        )
    )
    await db_session.commit()
