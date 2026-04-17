"""Fake clock for testing time-based logic.

Provides controllable time injection for deterministic testing of TTL expiration,
reconciliation loops, and other time-dependent behavior.
"""

from datetime import UTC, datetime, timedelta


class FakeClock:
    """Controllable clock for testing.

    Allows tests to control time progression and verify time-based behavior
    without waiting for real time to pass.

    Example:
        clock = FakeClock(now=datetime(2024, 1, 1, 12, 0, tzinfo=UTC))
        ttl_service = TTLService(clock=clock)

        # Create instance with 1-hour TTL
        instance = create_instance(ttl_hours=1)

        # Advance time by 30 minutes
        clock.advance(minutes=30)
        assert not ttl_service.is_expired(instance)

        # Advance time by another 31 minutes
        clock.advance(minutes=31)
        assert ttl_service.is_expired(instance)
    """

    def __init__(self, now: datetime | None = None):
        """Initialize clock with specific time.

        Args:
            now: Starting time (defaults to current UTC time)
        """
        self._now = now or datetime.now(UTC)

    def now(self) -> datetime:
        """Get current time.

        Returns:
            Current datetime in UTC
        """
        return self._now

    def advance(
        self,
        *,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
    ):
        """Advance clock by specified duration.

        Args:
            days: Days to advance
            hours: Hours to advance
            minutes: Minutes to advance
            seconds: Seconds to advance
        """
        delta = timedelta(
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
        )
        self._now += delta

    def set(self, time: datetime):
        """Set clock to specific time.

        Args:
            time: New current time
        """
        self._now = time

    def reset(self, time: datetime | None = None):
        """Reset clock to initial or specified time.

        Args:
            time: Time to reset to (defaults to current UTC time)
        """
        self._now = time or datetime.now(UTC)
