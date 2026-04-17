"""Adaptive polling backoff using Fibonacci-like sequence.

This module provides the delay calculation for the Export Poller's
self-scheduling poll chain. The delays start aggressive (2s) and
gradually increase to a cap (90s), optimizing for:
- Fast detection of quick exports (2-5 second latency)
- Reduced polling for long exports (90s max interval)
- Cost efficiency (fewer Cloud Function invocations)

See ADR-025 for architecture rationale.
"""

from __future__ import annotations

# Fibonacci-like sequence with cap at 90s
# Total time to reach cap: ~3m 50s after 9 polls
POLL_DELAYS: tuple[int, ...] = (2, 3, 5, 8, 13, 21, 34, 55, 89, 90)


def get_poll_delay(attempt: int) -> int:
    """Get delay in seconds for next poll attempt.

    Uses Fibonacci-like backoff: aggressive early, then settles to 90s cap.
    This optimizes for fast detection of quick exports while minimizing
    polling overhead for long-running exports.

    Args:
        attempt: Poll attempt number (1-indexed).
            - attempt=1 is the first poll after submission
            - attempt=10+ are all at the 90s cap

    Returns:
        Delay in seconds before next poll.

    Examples:
        >>> get_poll_delay(1)  # First poll
        2
        >>> get_poll_delay(5)  # Fifth poll
        13
        >>> get_poll_delay(100)  # Capped at 90s
        90

    Cumulative times:
        attempt=1:  2s   (cumulative:  2s)
        attempt=2:  3s   (cumulative:  5s)
        attempt=3:  5s   (cumulative: 10s)
        attempt=4:  8s   (cumulative: 18s)
        attempt=5: 13s   (cumulative: 31s)
        attempt=6: 21s   (cumulative: 52s)
        attempt=7: 34s   (cumulative: 1m 26s)
        attempt=8: 55s   (cumulative: 2m 21s)
        attempt=9: 89s   (cumulative: 3m 50s)
        attempt=10+: 90s (capped)
    """
    if attempt < 1:
        raise ValueError(f"Attempt must be >= 1, got {attempt}")
    index = min(attempt - 1, len(POLL_DELAYS) - 1)
    return POLL_DELAYS[index]


def estimate_polls_for_duration(duration_seconds: int) -> int:
    """Estimate number of polls needed for a given export duration.

    Useful for capacity planning and cost estimation.

    Args:
        duration_seconds: Expected export duration in seconds.

    Returns:
        Estimated number of poll invocations.

    Examples:
        >>> estimate_polls_for_duration(10)   # 10-second export
        3
        >>> estimate_polls_for_duration(120)  # 2-minute export
        8
        >>> estimate_polls_for_duration(3600) # 1-hour export
        47
    """
    if duration_seconds <= 0:
        return 0

    cumulative = 0
    polls = 0

    # Go through the Fibonacci sequence
    for delay in POLL_DELAYS:
        cumulative += delay
        polls += 1
        if cumulative >= duration_seconds:
            return polls

    # If we've exhausted the sequence and still haven't reached duration,
    # continue at the capped rate (90s)
    remaining = duration_seconds - cumulative
    polls += (remaining + POLL_DELAYS[-1] - 1) // POLL_DELAYS[-1]

    return polls


def get_cumulative_time(attempt: int) -> int:
    """Get cumulative time in seconds after N poll attempts.

    Args:
        attempt: Poll attempt number (1-indexed).

    Returns:
        Total seconds elapsed after completing this many polls.

    Examples:
        >>> get_cumulative_time(1)
        2
        >>> get_cumulative_time(5)
        31
        >>> get_cumulative_time(10)
        320
    """
    if attempt < 1:
        raise ValueError(f"Attempt must be >= 1, got {attempt}")

    total = 0
    for i in range(1, attempt + 1):
        total += get_poll_delay(i)
    return total
