"""Unit tests for ExportJobRepository."""

import pytest
import pytest_asyncio

from control_plane.models import ExportJobStatus
from control_plane.repositories.export_jobs import ExportJobRepository
from control_plane.repositories.mappings import MappingRepository
from control_plane.repositories.snapshots import SnapshotRepository
from control_plane.repositories.users import UserRepository
from tests.fixtures.data import create_test_user, create_test_node_definitions, create_test_edge_definitions


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create a test user for FK constraints."""
    repo = UserRepository(db_session)
    user = await repo.create(create_test_user("export.test.user"))
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def test_mapping(db_session, test_user):
    """Create a test mapping for FK constraints."""
    repo = MappingRepository(db_session)
    mapping = await repo.create(
        owner_username=test_user.username,
        name="Export Test Mapping",
        description="Mapping for export job tests",
        node_definitions=create_test_node_definitions(2),
        edge_definitions=create_test_edge_definitions(1),
    )
    await db_session.commit()
    return mapping


@pytest_asyncio.fixture
async def test_snapshots(db_session, test_mapping):
    """Create test snapshots for export job tests."""
    repo = SnapshotRepository(db_session)
    snapshot1 = await repo.create(
        mapping_id=test_mapping.id,
        mapping_version=1,
        owner_username=test_mapping.owner_username,
        name="Test Snapshot 1",
        description="First test snapshot",
        gcs_path="gs://bucket/test1/",
    )
    snapshot2 = await repo.create(
        mapping_id=test_mapping.id,
        mapping_version=1,
        owner_username=test_mapping.owner_username,
        name="Test Snapshot 2",
        description="Second test snapshot",
        gcs_path="gs://bucket/test2/",
    )
    await db_session.commit()
    return [snapshot1, snapshot2]


class TestExportJobRepositoryCreate:
    """Tests for creating export jobs."""

    @pytest.mark.asyncio
    async def test_create_export_job(self, db_session, test_snapshots):
        """Test creating a new export job."""
        repo = ExportJobRepository(db_session)

        job = await repo.create(
            snapshot_id=test_snapshots[0].id,
            job_type="node",
            entity_name="Person",
            gcs_path="gs://bucket/person.parquet",
            sql_query="SELECT * FROM person",
            column_names=["id", "name", "age"],
            starburst_catalog="catalog",
        )

        assert job.id is not None
        assert job.snapshot_id == test_snapshots[0].id
        assert job.job_type == "node"
        assert job.entity_name == "Person"
        assert job.status == ExportJobStatus.PENDING
        assert job.gcs_path == "gs://bucket/person.parquet"
        assert job.sql == "SELECT * FROM person"
        assert job.column_names == ["id", "name", "age"]
        assert job.starburst_catalog == "catalog"
        assert job.poll_count == 0

    @pytest.mark.asyncio
    async def test_create_export_job_minimal(self, db_session, test_snapshots):
        """Test creating job with minimal fields."""
        repo = ExportJobRepository(db_session)

        job = await repo.create(
            snapshot_id=test_snapshots[0].id,
            job_type="edge",
            entity_name="KNOWS",
            gcs_path="gs://bucket/knows.parquet",
        )

        assert job.sql is None
        assert job.column_names is None
        assert job.starburst_catalog is None
        assert job.status == ExportJobStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_batch(self, db_session, test_snapshots):
        """Test creating multiple jobs at once."""
        repo = ExportJobRepository(db_session)

        jobs_data = [
            {
                "job_type": "node",
                "entity_name": "Person",
                "gcs_path": "gs://bucket/person.parquet",
                "sql": "SELECT * FROM person",
                "column_names": ["id", "name"],
            },
            {
                "job_type": "node",
                "entity_name": "Company",
                "gcs_path": "gs://bucket/company.parquet",
            },
            {
                "job_type": "edge",
                "entity_name": "WORKS_AT",
                "gcs_path": "gs://bucket/works_at.parquet",
            },
        ]

        jobs = await repo.create_batch(snapshot_id=test_snapshots[0].id, jobs=jobs_data)

        assert len(jobs) == 3
        assert all(j.snapshot_id == test_snapshots[0].id for j in jobs)
        assert all(j.status == ExportJobStatus.PENDING for j in jobs)
        assert jobs[0].entity_name == "Person"
        assert jobs[1].entity_name == "Company"
        assert jobs[2].entity_name == "WORKS_AT"


class TestExportJobRepositoryGet:
    """Tests for retrieving export jobs."""

    @pytest.mark.asyncio
    async def test_get_by_id(self, db_session, test_snapshots):
        """Test getting job by ID."""
        repo = ExportJobRepository(db_session)

        created = await repo.create(
            snapshot_id=test_snapshots[0].id,
            job_type="node",
            entity_name="Person",
            gcs_path="gs://bucket/person.parquet",
        )

        # Retrieve it
        job = await repo.get_by_id(created.id)

        assert job is not None
        assert job.id == created.id
        assert job.entity_name == "Person"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session):
        """Test getting non-existent job."""
        repo = ExportJobRepository(db_session)

        job = await repo.get_by_id(99999)

        assert job is None

    @pytest.mark.asyncio
    async def test_list_by_snapshot(self, db_session, test_snapshots):
        """Test listing jobs for a snapshot."""
        repo = ExportJobRepository(db_session)

        await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        await repo.create(snapshot_id=test_snapshots[0].id, job_type="edge", entity_name="KNOWS", gcs_path="gs://b/k")
        await repo.create(snapshot_id=test_snapshots[1].id, job_type="node", entity_name="Company", gcs_path="gs://b/c")

        # List for snapshot 1
        jobs = await repo.list_by_snapshot(test_snapshots[0].id)

        assert len(jobs) == 2
        assert all(j.snapshot_id == test_snapshots[0].id for j in jobs)
        # Should be ordered by job_type, entity_name
        assert jobs[0].entity_name == "KNOWS"  # edge comes first
        assert jobs[1].entity_name == "Person"  # then node

    @pytest.mark.asyncio
    async def test_list_pending(self, db_session, test_snapshots):
        """Test listing pending jobs."""
        repo = ExportJobRepository(db_session)

        job1 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        job2 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Company", gcs_path="gs://b/c")

        # Mark one as submitted
        await repo.mark_submitted(job1.id, "query-123", "http://starburst/next")

        # List pending
        pending = await repo.list_pending(limit=10)

        assert len(pending) == 1
        assert pending[0].id == job2.id
        assert pending[0].status == ExportJobStatus.PENDING

    @pytest.mark.asyncio
    async def test_list_submitted(self, db_session, test_snapshots):
        """Test listing submitted jobs."""
        repo = ExportJobRepository(db_session)

        job1 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        job2 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Company", gcs_path="gs://b/c")

        # Mark one as submitted
        await repo.mark_submitted(job1.id, "query-123", "http://starburst/next")

        # List submitted
        submitted = await repo.list_submitted(limit=10)

        assert len(submitted) == 1
        assert submitted[0].id == job1.id
        assert submitted[0].status == ExportJobStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_list_all(self, db_session, test_snapshots):
        """Test listing all jobs."""
        repo = ExportJobRepository(db_session)

        await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Company", gcs_path="gs://b/c")
        await repo.create(snapshot_id=test_snapshots[1].id, job_type="edge", entity_name="KNOWS", gcs_path="gs://b/k")

        # List all
        jobs = await repo.list_all()

        assert len(jobs) == 3


class TestExportJobRepositoryStatusUpdates:
    """Tests for updating job status."""

    @pytest.mark.asyncio
    async def test_mark_submitted(self, db_session, test_snapshots):
        """Test marking job as submitted."""
        repo = ExportJobRepository(db_session)

        job = await repo.create(
            snapshot_id=test_snapshots[0].id,
            job_type="node",
            entity_name="Person",
            gcs_path="gs://bucket/person.parquet",
        )

        # Mark as submitted
        updated = await repo.mark_submitted(
            job_id=job.id,
            starburst_query_id="query-123",
            next_uri="http://starburst/status",
            next_poll_at="2024-01-01T12:00:00Z",
        )

        assert updated is not None
        assert updated.status == ExportJobStatus.SUBMITTED
        assert updated.starburst_query_id == "query-123"
        assert updated.next_uri == "http://starburst/status"
        assert updated.submitted_at is not None
        assert updated.poll_count == 0

    @pytest.mark.asyncio
    async def test_mark_running_alias(self, db_session, test_snapshots):
        """Test mark_running is an alias for mark_submitted."""
        repo = ExportJobRepository(db_session)

        job = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")

        # Use mark_running (backward compatibility)
        updated = await repo.mark_running(
            job_id=job.id,
            starburst_query_id="query-123",
            next_uri="http://starburst/status",
        )

        assert updated is not None
        assert updated.status == ExportJobStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_update_next_uri(self, db_session, test_snapshots):
        """Test updating polling URI."""
        repo = ExportJobRepository(db_session)

        job = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        await repo.mark_submitted(job.id, "query-123", "http://starburst/uri1")

        # Update next URI
        await repo.update_next_uri(
            job_id=job.id,
            next_uri="http://starburst/uri2",
            next_poll_at="2024-01-01T12:05:00Z",
            poll_count=1,
        )

        # Verify update
        updated = await repo.get_by_id(job.id)
        assert updated.next_uri == "http://starburst/uri2"
        assert updated.poll_count == 1

    @pytest.mark.asyncio
    async def test_update_next_uri_minimal(self, db_session, test_snapshots):
        """Test updating just URI without poll time or count."""
        repo = ExportJobRepository(db_session)

        job = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        await repo.mark_submitted(job.id, "query-123", "http://starburst/uri1")

        # Update only URI
        await repo.update_next_uri(job_id=job.id, next_uri="http://starburst/uri2")

        # Verify update
        updated = await repo.get_by_id(job.id)
        assert updated.next_uri == "http://starburst/uri2"

    @pytest.mark.asyncio
    async def test_mark_completed(self, db_session, test_snapshots):
        """Test marking job as completed."""
        repo = ExportJobRepository(db_session)

        job = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        await repo.mark_submitted(job.id, "query-123", "http://starburst/status")

        # Mark as completed
        updated = await repo.mark_completed(
            job_id=job.id,
            row_count=1000,
            size_bytes=1024 * 1024 * 5,  # 5 MB
        )

        assert updated is not None
        assert updated.status == ExportJobStatus.COMPLETED
        assert updated.row_count == 1000
        assert updated.size_bytes == 1024 * 1024 * 5
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_mark_failed(self, db_session, test_snapshots):
        """Test marking job as failed."""
        repo = ExportJobRepository(db_session)

        job = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")

        # Mark as failed
        updated = await repo.mark_failed(
            job_id=job.id,
            error_message="Starburst query failed: timeout",
        )

        assert updated is not None
        assert updated.status == ExportJobStatus.FAILED
        assert updated.error_message == "Starburst query failed: timeout"
        assert updated.completed_at is not None

    @pytest.mark.asyncio
    async def test_reset_to_pending(self, db_session, test_snapshots):
        """Test resetting job back to pending."""
        repo = ExportJobRepository(db_session)

        job = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")

        # Claim the job first
        claimed = await repo.claim_pending_jobs(worker_id="worker-1", limit=1)
        assert len(claimed) == 1
        assert claimed[0].status == ExportJobStatus.CLAIMED

        # Reset back to pending
        updated = await repo.reset_to_pending(job.id)

        assert updated is not None
        assert updated.status == ExportJobStatus.PENDING
        assert updated.claimed_by is None
        assert updated.claimed_at is None


class TestExportJobRepositoryQueries:
    """Tests for complex query operations."""

    @pytest.mark.asyncio
    async def test_get_snapshot_progress(self, db_session, test_snapshots):
        """Test getting aggregated progress for a snapshot."""
        repo = ExportJobRepository(db_session)

        # Create jobs with different statuses
        job1 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        job2 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Company", gcs_path="gs://b/c")
        job3 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="edge", entity_name="KNOWS", gcs_path="gs://b/k")

        # Update statuses
        await repo.mark_submitted(job1.id, "query-1", "http://sb/1")
        await repo.mark_completed(job2.id, 100, 1024)

        # Get progress
        progress = await repo.get_snapshot_progress(test_snapshots[0].id)

        assert progress["jobs_total"] == 3
        assert progress["jobs_pending"] == 1
        assert progress["jobs_submitted"] == 1
        assert progress["jobs_completed"] == 1
        assert progress["jobs_failed"] == 0

    @pytest.mark.asyncio
    async def test_all_completed(self, db_session, test_snapshots):
        """Test checking if all jobs are completed."""
        repo = ExportJobRepository(db_session)

        job1 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        job2 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Company", gcs_path="gs://b/c")

        # Not all completed yet
        assert not await repo.all_completed(test_snapshots[0].id)

        # Mark both as completed
        await repo.mark_completed(job1.id, 100, 1024)
        await repo.mark_completed(job2.id, 200, 2048)

        # Now all completed
        assert await repo.all_completed(test_snapshots[0].id)

    @pytest.mark.asyncio
    async def test_any_failed(self, db_session, test_snapshots):
        """Test checking if any jobs have failed."""
        repo = ExportJobRepository(db_session)

        job1 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        job2 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Company", gcs_path="gs://b/c")

        # No failures yet
        assert not await repo.any_failed(test_snapshots[0].id)

        # Mark one as failed
        await repo.mark_failed(job1.id, "Test error")

        # Now has failures
        assert await repo.any_failed(test_snapshots[0].id)


class TestExportJobRepositoryClaiming:
    """Tests for job claiming and polling."""

    @pytest.mark.asyncio
    async def test_claim_pending_jobs(self, db_session, test_snapshots):
        """Test claiming pending jobs for a worker."""
        repo = ExportJobRepository(db_session)

        # Create pending jobs
        await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Company", gcs_path="gs://b/c")
        await repo.create(snapshot_id=test_snapshots[0].id, job_type="edge", entity_name="KNOWS", gcs_path="gs://b/k")

        # Claim 2 jobs
        claimed = await repo.claim_pending_jobs(worker_id="worker-1", limit=2)

        assert len(claimed) == 2
        assert all(j.status == ExportJobStatus.CLAIMED for j in claimed)
        assert all(j.claimed_by == "worker-1" for j in claimed)
        assert all(j.claimed_at is not None for j in claimed)

    @pytest.mark.asyncio
    async def test_claim_pending_jobs_no_double_claim(self, db_session, test_snapshots):
        """Test that claimed jobs are not claimed again."""
        repo = ExportJobRepository(db_session)

        await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")

        # First worker claims
        claimed1 = await repo.claim_pending_jobs(worker_id="worker-1", limit=10)
        assert len(claimed1) == 1

        # Second worker tries to claim (should get nothing)
        claimed2 = await repo.claim_pending_jobs(worker_id="worker-2", limit=10)
        assert len(claimed2) == 0

    @pytest.mark.asyncio
    async def test_get_pollable_jobs(self, db_session, test_snapshots):
        """Test getting jobs ready for polling."""
        repo = ExportJobRepository(db_session)

        job1 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")
        job2 = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Company", gcs_path="gs://b/c")

        # Mark as submitted with different poll times
        await repo.mark_submitted(job1.id, "query-1", "http://sb/1", "2024-01-01T12:00:00Z")
        await repo.mark_submitted(job2.id, "query-2", "http://sb/2", "2024-01-01T13:00:00Z")

        # Get pollable jobs (current_time before both)
        pollable = await repo.get_pollable_jobs(limit=10, current_time="2024-01-01T11:00:00Z")
        assert len(pollable) == 0

        # Get pollable jobs (current_time after first)
        pollable = await repo.get_pollable_jobs(limit=10, current_time="2024-01-01T12:30:00Z")
        assert len(pollable) == 1
        assert pollable[0].id == job1.id

        # Get pollable jobs (current_time after both)
        pollable = await repo.get_pollable_jobs(limit=10, current_time="2024-01-01T14:00:00Z")
        assert len(pollable) == 2

    @pytest.mark.asyncio
    async def test_get_pollable_jobs_null_poll_time(self, db_session, test_snapshots):
        """Test that jobs with NULL next_poll_at are pollable immediately."""
        repo = ExportJobRepository(db_session)

        job = await repo.create(snapshot_id=test_snapshots[0].id, job_type="node", entity_name="Person", gcs_path="gs://b/p")

        # Mark as submitted without next_poll_at
        await repo.mark_submitted(job.id, "query-1", "http://sb/1", next_poll_at=None)

        # Should be pollable immediately
        pollable = await repo.get_pollable_jobs(limit=10)
        assert len(pollable) == 1
        assert pollable[0].id == job.id
