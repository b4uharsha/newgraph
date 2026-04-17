"""Shared test data schema — Customer + SHARES_ACCOUNT graph definition.

Single source of truth for the graph schema used across tutorials,
E2E tests, UAT validation, and test fixtures. Centralised here so
every consumer gets the same schema without repeating SQL definitions.

These are DATA CONSTANTS, not helper functions. The notebook/test is
responsible for calling client.mappings.create(), client.instances.list(),
etc. This module just provides the arguments.

The SQL references target our GKE London dev environment. The HSBC
handoff build (make repo / make hsbc) replaces them via
tools/render-notebooks.py (ADR-121).
"""

from graph_olap.models.mapping import (
    EdgeDefinition,
    NodeDefinition,
    PropertyDefinition,
)

# ---------------------------------------------------------------------------
# Starburst catalog/schema (ADR-121)
# These values target our GKE London dev environment. The HSBC handoff
# build (make repo / make hsbc) replaces them via tools/render-notebooks.py.
# ---------------------------------------------------------------------------
STARBURST_CATALOG: str = "hsbc-244552-hkibishk-dev"
STARBURST_SCHEMA: str = "hk_ibis_wsdv_app_view_dev"
TABLE_PREFIX: str = f"{STARBURST_CATALOG}.{STARBURST_SCHEMA}"

# ---------------------------------------------------------------------------
# Naming conventions
# ---------------------------------------------------------------------------
MAPPING_NAME: str = "tutorial-customer-graph"
INSTANCE_NAME: str = "tutorial-instance"
INSTANCE_TTL: str = "PT1H"

# ---------------------------------------------------------------------------
# Node definitions
# ---------------------------------------------------------------------------
CUSTOMER_NODE = NodeDefinition(
    label="Customer",
    sql="""SELECT DISTINCT CAST(psdo_cust_id AS VARCHAR) AS id, MIN(bk_sectr) AS bk_sectr, COUNT(DISTINCT psdo_acno) AS account_count, MIN(acct_stus) AS acct_stus FROM "hsbc-244552-hkibishk-dev"."hk_ibis_wsdv_app_view_dev".bis_acct_dh WHERE image_dt >= DATE '2020-01-01' GROUP BY psdo_cust_id""",
    primary_key={"name": "id", "type": "STRING"},
    properties=[
        PropertyDefinition(name="bk_sectr", type="STRING"),
        PropertyDefinition(name="account_count", type="INT64"),
        PropertyDefinition(name="acct_stus", type="STRING"),
    ],
)

NODE_DEFINITIONS = [CUSTOMER_NODE]

# ---------------------------------------------------------------------------
# Edge definitions
# ---------------------------------------------------------------------------
SHARES_ACCOUNT_EDGE = EdgeDefinition(
    type="SHARES_ACCOUNT",
    from_node="Customer",
    to_node="Customer",
    sql="""SELECT DISTINCT CAST(a.psdo_cust_id AS VARCHAR) AS from_id, CAST(b.psdo_cust_id AS VARCHAR) AS to_id FROM "hsbc-244552-hkibishk-dev"."hk_ibis_wsdv_app_view_dev".bis_acct_dh a JOIN "hsbc-244552-hkibishk-dev"."hk_ibis_wsdv_app_view_dev".bis_acct_dh b ON a.psdo_acno = b.psdo_acno AND a.psdo_cust_id < b.psdo_cust_id AND a.image_dt >= DATE '2020-01-01' AND b.image_dt >= DATE '2020-01-01'""",
    from_key="from_id",
    to_key="to_id",
)

EDGE_DEFINITIONS = [SHARES_ACCOUNT_EDGE]
