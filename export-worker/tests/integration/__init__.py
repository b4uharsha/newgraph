"""Integration tests for Export Worker (ADR-025).

Tests component interactions with mocked external services:
- Full export flow (claim → submit → poll → complete)
- Error handling and recovery
- Graceful shutdown
- Cancellation detection

Per testing.strategy.md:
- Integration tests use mocked external services (Starburst, GCS, Control Plane)
- Test component interactions
- Test error handling and retry logic
"""
