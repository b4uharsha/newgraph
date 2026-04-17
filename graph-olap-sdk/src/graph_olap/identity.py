"""Default identity for SDK requests.

The SDK sends X-Username on every request. This module provides the
default username used when no explicit username is passed to the client.

This default is shared across all consumers: tutorials, E2E tests, UAT,
and reference notebooks. It must be a provisioned user in the control
plane database with analyst-level permissions.

Override at runtime:
    import graph_olap.identity
    graph_olap.identity.DEFAULT_USERNAME = "alice@example.com"

Override via environment:
    export GRAPH_OLAP_USERNAME="ops_dave@e2e.local"
"""

DEFAULT_USERNAME = "analyst_alice@e2e.local"
