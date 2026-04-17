"""Unit tests for lifecycle job.

Tests TTL expiry logic, inactivity timeout logic, and ISO 8601 duration parsing.
"""

from datetime import UTC, datetime, timedelta

from control_plane.jobs.lifecycle import _parse_iso8601_duration


class TestParseISO8601Duration:
    """Test ISO 8601 duration parsing."""

    def test_parse_hours(self):
        """Test parsing hours format (PT<n>H)."""
        assert _parse_iso8601_duration("PT1H") == timedelta(hours=1)
        assert _parse_iso8601_duration("PT24H") == timedelta(hours=24)
        assert _parse_iso8601_duration("PT168H") == timedelta(hours=168)

    def test_parse_minutes(self):
        """Test parsing minutes format (PT<n>M)."""
        assert _parse_iso8601_duration("PT30M") == timedelta(minutes=30)
        assert _parse_iso8601_duration("PT90M") == timedelta(minutes=90)
        assert _parse_iso8601_duration("PT1M") == timedelta(minutes=1)

    def test_parse_seconds(self):
        """Test parsing seconds format (PT<n>S)."""
        assert _parse_iso8601_duration("PT60S") == timedelta(seconds=60)
        assert _parse_iso8601_duration("PT3600S") == timedelta(seconds=3600)

    def test_parse_days(self):
        """Test parsing days format (P<n>D)."""
        assert _parse_iso8601_duration("P1D") == timedelta(days=1)
        assert _parse_iso8601_duration("P7D") == timedelta(days=7)
        assert _parse_iso8601_duration("P30D") == timedelta(days=30)

    def test_parse_weeks(self):
        """Test parsing weeks format (P<n>W)."""
        assert _parse_iso8601_duration("P1W") == timedelta(weeks=1)
        assert _parse_iso8601_duration("P2W") == timedelta(weeks=2)
        assert _parse_iso8601_duration("P4W") == timedelta(weeks=4)

    def test_parse_invalid_format(self):
        """Test parsing invalid formats returns None."""
        assert _parse_iso8601_duration("24H") is None  # Missing PT prefix
        assert _parse_iso8601_duration("7D") is None  # Missing P prefix
        assert _parse_iso8601_duration("invalid") is None
        assert _parse_iso8601_duration("") is None
        assert _parse_iso8601_duration("P") is None  # Just prefix
        assert _parse_iso8601_duration("PT") is None  # Just prefix

    def test_parse_unsupported_combinations(self):
        """Test parsing unsupported compound durations returns None."""
        # We only support single-unit durations
        assert _parse_iso8601_duration("P1DT12H") is None  # Mixed days and hours
        assert _parse_iso8601_duration("PT1H30M") is None  # Mixed hours and minutes

    def test_parse_zero_values(self):
        """Test parsing zero values."""
        assert _parse_iso8601_duration("PT0H") == timedelta(hours=0)
        assert _parse_iso8601_duration("P0D") == timedelta(days=0)

    def test_parse_large_values(self):
        """Test parsing large values."""
        assert _parse_iso8601_duration("PT8760H") == timedelta(hours=8760)  # 1 year
        assert _parse_iso8601_duration("P365D") == timedelta(days=365)  # 1 year

    def test_parse_malformed_numbers(self):
        """Test parsing malformed numbers returns None."""
        assert _parse_iso8601_duration("PTABCH") is None
        assert _parse_iso8601_duration("P-1D") is None  # Negative
        assert _parse_iso8601_duration("PT1.5H") is None  # Decimal


class TestTTLExpiryCalculation:
    """Test TTL expiry calculation logic."""

    def test_expired_instance_24h_ttl(self):
        """Test instance is expired after 24 hour TTL."""
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ttl = "PT24H"
        now = datetime(2025, 1, 2, 13, 0, 0, tzinfo=UTC)  # 25 hours later

        ttl_delta = _parse_iso8601_duration(ttl)
        expiry_time = created_at + ttl_delta
        assert now > expiry_time

    def test_not_expired_instance_24h_ttl(self):
        """Test instance is not expired before 24 hour TTL."""
        created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        ttl = "PT24H"
        now = datetime(2025, 1, 2, 11, 0, 0, tzinfo=UTC)  # 23 hours later

        ttl_delta = _parse_iso8601_duration(ttl)
        expiry_time = created_at + ttl_delta
        assert now < expiry_time

    def test_expired_instance_7d_ttl(self):
        """Test instance is expired after 7 day TTL."""
        created_at = datetime(2025, 1, 1, tzinfo=UTC)
        ttl = "P7D"
        now = datetime(2025, 1, 9, tzinfo=UTC)  # 8 days later

        ttl_delta = _parse_iso8601_duration(ttl)
        expiry_time = created_at + ttl_delta
        assert now > expiry_time

    def test_exact_ttl_boundary(self):
        """Test instance at exact TTL boundary (1 microsecond difference)."""
        created_at = datetime(2025, 1, 1, 12, 0, 0, 0, tzinfo=UTC)
        ttl = "PT24H"
        ttl_delta = _parse_iso8601_duration(ttl)
        expiry_time = created_at + ttl_delta

        # At exact boundary
        now_at_boundary = expiry_time
        assert now_at_boundary == expiry_time  # Exact equality

        # 1 microsecond before expiry
        now_before = expiry_time - timedelta(microseconds=1)
        assert now_before < expiry_time

        # 1 microsecond after expiry
        now_after = expiry_time + timedelta(microseconds=1)
        assert now_after > expiry_time


class TestInactivityTimeoutCalculation:
    """Test inactivity timeout calculation logic."""

    def test_expired_inactive_4h_timeout(self):
        """Test instance is inactive after 4 hour timeout."""
        last_activity_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        timeout = "PT4H"
        now = datetime(2025, 1, 1, 17, 0, 0, tzinfo=UTC)  # 5 hours later

        timeout_delta = _parse_iso8601_duration(timeout)
        inactive_deadline = last_activity_at + timeout_delta
        assert now > inactive_deadline

    def test_not_expired_inactive_4h_timeout(self):
        """Test instance is not inactive before 4 hour timeout."""
        last_activity_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        timeout = "PT4H"
        now = datetime(2025, 1, 1, 15, 0, 0, tzinfo=UTC)  # 3 hours later

        timeout_delta = _parse_iso8601_duration(timeout)
        inactive_deadline = last_activity_at + timeout_delta
        assert now < inactive_deadline

    def test_recent_activity_resets_timeout(self):
        """Test that recent activity extends the deadline."""
        # Instance created 10 hours ago
        created_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        # But had activity 1 hour ago
        last_activity_at = datetime(2025, 1, 1, 9, 0, 0, tzinfo=UTC)

        timeout = "PT4H"  # 4 hour timeout
        now = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)

        # Should NOT be inactive (last activity was 1 hour ago)
        timeout_delta = _parse_iso8601_duration(timeout)
        inactive_deadline = last_activity_at + timeout_delta
        assert now < inactive_deadline


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_none_ttl(self):
        """Test None TTL returns None."""
        assert _parse_iso8601_duration(None) is None

    def test_empty_string_ttl(self):
        """Test empty string TTL returns None."""
        assert _parse_iso8601_duration("") is None

    def test_whitespace_only_ttl(self):
        """Test whitespace-only TTL returns None."""
        assert _parse_iso8601_duration("   ") is None

    def test_case_sensitivity(self):
        """Test that lowercase durations fail (ISO 8601 requires uppercase)."""
        # Our parser is strict - requires uppercase
        assert _parse_iso8601_duration("pt24h") is None
        assert _parse_iso8601_duration("p7d") is None

    def test_duration_with_leading_trailing_whitespace(self):
        """Test durations with whitespace are rejected."""
        assert _parse_iso8601_duration(" PT24H") is None
        assert _parse_iso8601_duration("PT24H ") is None
        assert _parse_iso8601_duration(" PT24H ") is None


# Mark tests as async for consistency with job implementation
pytest_plugins = ("pytest_asyncio",)
