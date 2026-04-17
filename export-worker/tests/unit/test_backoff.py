"""Tests for the Fibonacci backoff module.

Tests verify:
- Correct delay values at each attempt
- Boundary conditions (attempt 1, high attempts)
- Cumulative time calculations
- Poll estimation for durations
"""

from __future__ import annotations

import pytest

from export_worker.backoff import (
    POLL_DELAYS,
    estimate_polls_for_duration,
    get_cumulative_time,
    get_poll_delay,
)


class TestGetPollDelay:
    """Tests for get_poll_delay function."""

    def test_first_attempt_returns_2_seconds(self) -> None:
        """First poll should be aggressive (2s delay)."""
        assert get_poll_delay(1) == 2

    def test_fibonacci_sequence(self) -> None:
        """Delays follow Fibonacci-like sequence."""
        expected = [2, 3, 5, 8, 13, 21, 34, 55, 89, 90]
        for i, expected_delay in enumerate(expected, start=1):
            assert get_poll_delay(i) == expected_delay

    def test_caps_at_90_seconds(self) -> None:
        """Delay caps at 90s for high attempt numbers."""
        assert get_poll_delay(10) == 90
        assert get_poll_delay(11) == 90
        assert get_poll_delay(100) == 90
        assert get_poll_delay(1000) == 90

    def test_raises_on_zero_attempt(self) -> None:
        """Attempt 0 is invalid."""
        with pytest.raises(ValueError, match="must be >= 1"):
            get_poll_delay(0)

    def test_raises_on_negative_attempt(self) -> None:
        """Negative attempts are invalid."""
        with pytest.raises(ValueError, match="must be >= 1"):
            get_poll_delay(-1)


class TestGetCumulativeTime:
    """Tests for get_cumulative_time function."""

    def test_cumulative_time_after_first_poll(self) -> None:
        """Cumulative time after 1 poll is 2s."""
        assert get_cumulative_time(1) == 2

    def test_cumulative_time_after_five_polls(self) -> None:
        """Cumulative time after 5 polls: 2+3+5+8+13 = 31s."""
        assert get_cumulative_time(5) == 31

    def test_cumulative_time_after_nine_polls(self) -> None:
        """Cumulative time after 9 polls: sum(2,3,5,8,13,21,34,55,89) = 230s."""
        assert get_cumulative_time(9) == 230

    def test_cumulative_time_after_ten_polls(self) -> None:
        """After 10 polls: 230 + 90 = 320s."""
        assert get_cumulative_time(10) == 320

    def test_raises_on_invalid_attempt(self) -> None:
        """Invalid attempt numbers raise ValueError."""
        with pytest.raises(ValueError, match="must be >= 1"):
            get_cumulative_time(0)


class TestEstimatePollsForDuration:
    """Tests for estimate_polls_for_duration function."""

    def test_zero_duration_returns_zero_polls(self) -> None:
        """Zero duration needs no polls."""
        assert estimate_polls_for_duration(0) == 0

    def test_negative_duration_returns_zero_polls(self) -> None:
        """Negative duration needs no polls."""
        assert estimate_polls_for_duration(-10) == 0

    def test_short_export_needs_few_polls(self) -> None:
        """10-second export needs 3 polls (2+3+5 = 10)."""
        polls = estimate_polls_for_duration(10)
        assert polls == 3  # Exactly 10s cumulative after 3 polls

    def test_two_minute_export(self) -> None:
        """2-minute export needs 8 polls."""
        polls = estimate_polls_for_duration(120)
        # After 7 polls: 2+3+5+8+13+21+34 = 86s
        # After 8 polls: 86+55 = 141s >= 120s
        assert polls == 8

    def test_one_hour_export(self) -> None:
        """1-hour export needs many polls at 90s cap."""
        polls = estimate_polls_for_duration(3600)
        # After 10 polls: 2+3+5+8+13+21+34+55+89+90 = 320s
        # Remaining: 3600-320 = 3280s at 90s intervals = ceil(3280/90) = 37 more
        # Total: 10 + 37 = 47 polls
        assert polls == 47


class TestPollDelaysConstant:
    """Tests for POLL_DELAYS constant."""

    def test_sequence_length(self) -> None:
        """Sequence has 10 elements."""
        assert len(POLL_DELAYS) == 10

    def test_sequence_is_sorted(self) -> None:
        """Delays increase monotonically."""
        for i in range(len(POLL_DELAYS) - 1):
            assert POLL_DELAYS[i] <= POLL_DELAYS[i + 1]

    def test_first_delay_is_aggressive(self) -> None:
        """First delay is 2 seconds (aggressive for fast exports)."""
        assert POLL_DELAYS[0] == 2

    def test_last_delay_is_capped(self) -> None:
        """Last delay is 90 seconds (cap)."""
        assert POLL_DELAYS[-1] == 90
