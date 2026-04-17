"""Repository for instance events (resource monitoring events)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from control_plane.repositories.base import (
    BaseRepository,
    deserialize_json,
    parse_timestamp,
    serialize_json,
    utc_now,
)


@dataclass
class InstanceEvent:
    """Instance event domain model."""

    id: int
    instance_id: int
    event_type: str
    details: dict[str, Any] | None
    created_at: datetime | None


class InstanceEventsRepository(BaseRepository):
    """Repository for instance events."""

    async def create(
        self,
        instance_id: int,
        event_type: str,
        details: dict[str, Any] | None = None,
    ) -> InstanceEvent:
        """Create a new instance event.

        Args:
            instance_id: Instance ID
            event_type: Event type (memory_upgraded, cpu_updated, oom_recovered, resize_failed)
            details: Optional JSON details

        Returns:
            Created event
        """
        now = utc_now()
        sql = """
            INSERT INTO instance_events (instance_id, event_type, details, created_at)
            VALUES (:instance_id, :event_type, :details, :created_at)
            RETURNING id
        """
        event_id = await self._insert_returning_id(
            sql,
            {
                "instance_id": instance_id,
                "event_type": event_type,
                "details": serialize_json(details),
                "created_at": now,
            },
        )

        return InstanceEvent(
            id=event_id,
            instance_id=instance_id,
            event_type=event_type,
            details=details,
            created_at=parse_timestamp(now),
        )

    async def list_by_instance(
        self,
        instance_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[InstanceEvent], int]:
        """List events for an instance.

        Args:
            instance_id: Instance ID
            limit: Max events to return
            offset: Pagination offset

        Returns:
            Tuple of (events, total_count)
        """
        # Get total count
        count_sql = """
            SELECT COUNT(*) FROM instance_events
            WHERE instance_id = :instance_id
        """
        total = await self._fetch_scalar(count_sql, {"instance_id": instance_id}) or 0

        # Get events ordered by most recent first
        sql = """
            SELECT id, instance_id, event_type, details, created_at
            FROM instance_events
            WHERE instance_id = :instance_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        rows = await self._fetch_all(
            sql,
            {
                "instance_id": instance_id,
                "limit": limit,
                "offset": offset,
            },
        )

        events = [
            InstanceEvent(
                id=row.id,
                instance_id=row.instance_id,
                event_type=row.event_type,
                details=deserialize_json(row.details),
                created_at=parse_timestamp(row.created_at),
            )
            for row in rows
        ]

        return events, total
