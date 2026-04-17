"""Backwards-compatible re-export from test_data.py.

The shared graph schema has moved to graph_olap.test_data.
This module re-exports everything so existing notebooks that
import from graph_olap.tutorial continue to work unchanged.
"""

from graph_olap.test_data import (  # noqa: F401
    CUSTOMER_NODE,
    EDGE_DEFINITIONS,
    INSTANCE_NAME,
    INSTANCE_TTL,
    MAPPING_NAME,
    NODE_DEFINITIONS,
    SHARES_ACCOUNT_EDGE,
    STARBURST_CATALOG,
    STARBURST_SCHEMA,
    TABLE_PREFIX,
)
