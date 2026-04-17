# =============================================================================
# SNAPSHOT TESTS DISABLED
# These tests are commented out as snapshot functionality has been disabled.
# All tests in this file relate to snapshot finalization during export reconciliation.
# =============================================================================

# """Integration tests for export reconciliation job with real database."""
#
# from datetime import UTC, datetime, timedelta
#
# import pytest
#
# from control_plane.jobs.export_reconciliation import run_export_reconciliation_job
#
#
# @pytest.mark.asyncio
# @pytest.mark.integration
# class TestExportReconciliationIntegration:
#     """Integration tests for export reconciliation job."""
#
#     async def test_resets_stale_claimed_jobs(self, db_session, mapping_repo, snapshot_repo, export_job_repo):
#         """Test stale claimed jobs (>10 min) are reset to pending."""
#         # Create mapping and snapshot
#         mapping = await mapping_repo.create(name="test-mapping", created_by="test-user")
#         snapshot = await snapshot_repo.create(
#             name="test-snapshot",
#             mapping_id=mapping.id,
#             created_by="test-user",
#         )
#
#         # Create export job claimed 15 minutes ago
#         job = await export_job_repo.create(
#             snapshot_id=snapshot.id,
#             entity_type="node",
#             entity_name="Person",
#         )
#         stale_time = datetime.now(UTC) - timedelta(minutes=15)
#         await export_job_repo.update(
#             job.id,
#             {
#                 "status": "claimed",
#                 "claimed_at": stale_time.isoformat(),
#                 "claimed_by": "worker-1",
#             },
#         )
#
#         # Run export reconciliation job with test session
#         await run_export_reconciliation_job(session=db_session)
#
#         # Verify job reset to pending
#         updated_job = await export_job_repo.get(job.id)
#         assert updated_job.status == "pending"
#         assert updated_job.claimed_at is None
#         assert updated_job.claimed_by is None
#
#     async def test_ignores_recent_claimed_jobs(self, db_session, mapping_repo, snapshot_repo, export_job_repo):
#         """Test recent claimed jobs (<10 min) are not reset."""
#         # Create mapping and snapshot
#         mapping = await mapping_repo.create(name="test-mapping", created_by="test-user")
#         snapshot = await snapshot_repo.create(
#             name="test-snapshot",
#             mapping_id=mapping.id,
#             created_by="test-user",
#         )
#
#         # Create export job claimed 5 minutes ago
#         job = await export_job_repo.create(
#             snapshot_id=snapshot.id,
#             entity_type="node",
#             entity_name="Person",
#         )
#         recent_time = datetime.now(UTC) - timedelta(minutes=5)
#         await export_job_repo.update(
#             job.id,
#             {
#                 "status": "claimed",
#                 "claimed_at": recent_time.isoformat(),
#                 "claimed_by": "worker-1",
#             },
#         )
#
#         # Run export reconciliation job with test session
#         await run_export_reconciliation_job(session=db_session)
#
#         # Verify job still claimed
#         updated_job = await export_job_repo.get(job.id)
#         assert updated_job.status == "claimed"
#         assert updated_job.claimed_by == "worker-1"
#
#     async def test_finalizes_snapshot_when_all_jobs_completed(
#         self, db_session, mapping_repo, snapshot_repo, export_job_repo
#     ):
#         """Test snapshot marked ready when all export jobs completed."""
#         # Create mapping and snapshot
#         mapping = await mapping_repo.create(name="test-mapping", created_by="test-user")
#         snapshot = await snapshot_repo.create(
#             name="test-snapshot",
#             mapping_id=mapping.id,
#             created_by="test-user",
#         )
#
#         # Set snapshot to CREATING status
#         await snapshot_repo.update(snapshot.id, {"status": "creating"})
#
#         # Create 3 export jobs, all completed
#         for i in range(3):
#             job = await export_job_repo.create(
#                 snapshot_id=snapshot.id,
#                 entity_type="node",
#                 entity_name=f"Entity{i}",
#             )
#             await export_job_repo.update(job.id, {"status": "completed"})
#
#         # Run export reconciliation job with test session
#         await run_export_reconciliation_job(session=db_session)
#
#         # Verify snapshot finalized
#         updated_snapshot = await snapshot_repo.get(snapshot.id)
#         assert updated_snapshot.status == "ready"
#
#     async def test_does_not_finalize_snapshot_with_pending_jobs(
#         self, db_session, mapping_repo, snapshot_repo, export_job_repo
#     ):
#         """Test snapshot not finalized when jobs still pending/claimed."""
#         # Create mapping and snapshot
#         mapping = await mapping_repo.create(name="test-mapping", created_by="test-user")
#         snapshot = await snapshot_repo.create(
#             name="test-snapshot",
#             mapping_id=mapping.id,
#             created_by="test-user",
#         )
#
#         # Set snapshot to CREATING status
#         await snapshot_repo.update(snapshot.id, {"status": "creating"})
#
#         # Create mix of jobs: 2 completed, 1 pending
#         for i in range(2):
#             job = await export_job_repo.create(
#                 snapshot_id=snapshot.id,
#                 entity_type="node",
#                 entity_name=f"Entity{i}",
#             )
#             await export_job_repo.update(job.id, {"status": "completed"})
#
#         # Create pending job (default status)
#         await export_job_repo.create(
#             snapshot_id=snapshot.id,
#             entity_type="node",
#             entity_name="EntityPending",
#         )
#
#         # Run export reconciliation job with test session
#         await run_export_reconciliation_job(session=db_session)
#
#         # Verify snapshot still creating
#         updated_snapshot = await snapshot_repo.get(snapshot.id)
#         assert updated_snapshot.status == "creating"
#
#     async def test_handles_multiple_snapshots(
#         self, db_session, mapping_repo, snapshot_repo, export_job_repo
#     ):
#         """Test reconciliation handles multiple snapshots correctly."""
#         # Create mapping
#         mapping = await mapping_repo.create(name="test-mapping", created_by="test-user")
#
#         # Create 2 snapshots
#         snapshot1 = await snapshot_repo.create(
#             name="snapshot-1",
#             mapping_id=mapping.id,
#             created_by="test-user",
#         )
#         snapshot2 = await snapshot_repo.create(
#             name="snapshot-2",
#             mapping_id=mapping.id,
#             created_by="test-user",
#         )
#
#         # Both CREATING
#         await snapshot_repo.update(snapshot1.id, {"status": "creating"})
#         await snapshot_repo.update(snapshot2.id, {"status": "creating"})
#
#         # Snapshot 1: All jobs completed
#         for i in range(3):
#             job = await export_job_repo.create(
#                 snapshot_id=snapshot1.id,
#                 entity_type="node",
#                 entity_name=f"S1_Entity{i}",
#             )
#             await export_job_repo.update(job.id, {"status": "completed"})
#
#         # Snapshot 2: Has pending job
#         await export_job_repo.create(
#             snapshot_id=snapshot2.id,
#             entity_type="node",
#             entity_name="S2_Entity",
#         )
#         # Leave as PENDING (default status)
#
#         # Run export reconciliation job with test session
#         await run_export_reconciliation_job(session=db_session)
#
#         # Verify only snapshot1 finalized
#         updated_snapshot1 = await snapshot_repo.get(snapshot1.id)
#         updated_snapshot2 = await snapshot_repo.get(snapshot2.id)
#
#         assert updated_snapshot1.status == "ready"
#         assert updated_snapshot2.status == "creating"
#
#     async def test_idempotency_already_finalized_snapshot(
#         self, db_session, mapping_repo, snapshot_repo, export_job_repo
#     ):
#         """Test reconciliation is idempotent (doesn't fail on already-ready snapshots)."""
#         # Create mapping and snapshot
#         mapping = await mapping_repo.create(name="test-mapping", created_by="test-user")
#         snapshot = await snapshot_repo.create(
#             name="test-snapshot",
#             mapping_id=mapping.id,
#             created_by="test-user",
#         )
#
#         # Snapshot already READY (default status in factory)
#         # Create completed export jobs
#         for i in range(3):
#             job = await export_job_repo.create(
#                 snapshot_id=snapshot.id,
#                 entity_type="node",
#                 entity_name=f"Entity{i}",
#             )
#             await export_job_repo.update(job.id, {"status": "completed"})
#
#         # Run export reconciliation job with test session
#         await run_export_reconciliation_job(session=db_session)
#
#         # Verify snapshot still ready (idempotent)
#         updated_snapshot = await snapshot_repo.get(snapshot.id)
#         assert updated_snapshot.status == "ready"
