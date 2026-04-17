"""Fake implementations for testing.

Provides lightweight, in-memory test doubles following Google's testing best practices.
Prefer fakes over mocks for more maintainable and realistic tests.
"""

from .clock import FakeClock
from .k8s_client import FakeK8sClient

__all__ = ["FakeClock", "FakeK8sClient"]
