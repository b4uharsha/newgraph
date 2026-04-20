---
title: "Jupyter SDK Deployment Design"
scope: hsbc
---

<!-- Verified against SDK code on 2026-04-20 -->

# Jupyter SDK Deployment Design

## Overview

This document covers packaging and distribution of the Graph OLAP Python SDK for use from HSBC-managed Jupyter notebooks on Dataproc. Analysts `pip install` the SDK inside their Dataproc notebook and connect to the control-plane running on HSBC GKE via the Azure AD proxy. The SDK is the sole user interface; there is no separate web UI.

For SDK architecture and implementation, see [jupyter-sdk.design.md](-/jupyter-sdk.design.md).

## Prerequisites

- [jupyter-sdk.design.md](-/jupyter-sdk.design.md) - SDK architecture and implementation
- [requirements.md](--/foundation/requirements.md) - SDK requirements

---

## Package Configuration

```toml
# pyproject.toml
[project]
name = "graph-olap-sdk"
version = "1.0.0"
description = "Python SDK for Graph OLAP Platform"
requires-python = ">=3.10"

dependencies = [
    "httpx>=0.28.1",
    "pydantic>=2.12.5",
    "tenacity>=9.1.2",
]

[project.optional-dependencies]
# DataFrame support
dataframe = ["polars>=1.36.1", "pandas>=2.3.3"]

# Basic visualization
viz = [
    "pyvis>=0.3.2",
    "plotly>=6.5.0",
    "networkx>=3.6.1",
]

# Interactive Jupyter features
interactive = [
    "itables>=2.6.2",
    "ipywidgets>=8.1.8",
]

# Everything for analysts
all = [
    "graph-olap-sdk[dataframe,viz,interactive]",
]

# Development
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
    "mypy>=1.19.1",
    "ruff>=0.14.10",
]
```

---

## Distribution via HSBC Nexus

The SDK is published as a Python wheel to the HSBC internal Nexus PyPI repository. Analysts install it with `pip` inside their Dataproc notebooks:

```bash
# Minimal (control plane only)
pip install graph-olap-sdk

# For analysts (recommended)
pip install graph-olap-sdk[all]
```

If the notebook environment is not already configured to use Nexus as its index, analysts can specify it explicitly:

```bash
pip install --index-url https://nexus.hsbc/repository/pypi/simple graph-olap-sdk[all]
```

Check with your Dataproc administrator for the exact Nexus URL and any required authentication.

---

## Zero-Config Jupyter Integration

The SDK provides a "magic" import that auto-configures everything:

```python
# notebook.py - Zero-config Jupyter setup
import os

def init(username: str | None = None, api_url: str | None = None):
    """
    Initialize Graph OLAP SDK for Jupyter notebooks.

    Auto-discovers configuration from environment variables:
    - GRAPH_OLAP_USERNAME: Username for the X-Username header
    - GRAPH_OLAP_API_URL: Control plane URL (HSBC Azure AD proxy endpoint, required)
    - GRAPH_OLAP_USE_CASE_ID: Use case ID for X-Use-Case-Id (ADR-102, optional)
    - GRAPH_OLAP_PROXY: HTTP proxy URL (optional)
    - GRAPH_OLAP_SSL_VERIFY: Verify SSL certs (optional; "false" to disable)

    There is NO api_key / Bearer auth mode (ADR-104/105/137). Production auth is
    terminated upstream by the HSBC Azure AD proxy; the SDK only attaches
    identity headers.

    Also configures:
    - itables for automatic interactive DataFrames
    - Polars as default DataFrame backend
    - Rich output for all result types
    """
    username = username or os.environ.get("GRAPH_OLAP_USERNAME")
    api_url = api_url or os.environ.get("GRAPH_OLAP_API_URL")

    if not api_url:
        raise RuntimeError(
            "GRAPH_OLAP_API_URL not set. Either pass api_url=... "
            "or set the environment variable."
        )
    if not username:
        raise RuntimeError(
            "GRAPH_OLAP_USERNAME not set. Pass username=... or set the env var."
        )

    # Configure itables for automatic interactive display
    try:
        import itables
        itables.init_notebook_mode(all_interactive=True)
    except ImportError:
        pass

    from graph_olap import GraphOLAPClient
    return GraphOLAPClient(username=username, api_url=api_url)


def connect(**kwargs):
    """Shorthand for init() - returns ready-to-use client."""
    return init(**kwargs)
```

**Analyst Usage (2 lines to get started):**

```python
from graph_olap import notebook
client = notebook.connect()  # Auto-discovers from environment

# Start working immediately
result = client.quick_start(mapping_id=1)
result.show()
```

---

## IPython Magic Commands

For power users, the SDK provides IPython magic commands:

```python
# _jupyter/magic.py
from IPython.core.magic import register_line_magic, register_cell_magic

@register_line_magic
def graph_query(line):
    """
    Execute a Cypher query inline.

    Usage:
        %graph_query MATCH (n) RETURN n LIMIT 10
    """
    from graph_olap import _current_connection
    if _current_connection is None:
        print("Not connected. Run: from graph_olap import notebook; notebook.connect()")
        return
    result = _current_connection.query(line)
    return result.show()

@register_cell_magic
def cypher(line, cell):
    """
    Execute multi-line Cypher query.

    Usage:
        %%cypher
        MATCH (c:Customer)-[p:PURCHASED]->(pr:Product)
        WHERE c.city = 'London'
        RETURN c.name, pr.name, p.amount
        ORDER BY p.amount DESC
        LIMIT 100
    """
    from graph_olap import _current_connection
    if _current_connection is None:
        print("Not connected. Run: from graph_olap import notebook; notebook.connect()")
        return
    result = _current_connection.query(cell)
    return result.show()

def load_ipython_extension(ipython):
    ipython.register_magic_function(graph_query, 'line')
    ipython.register_magic_function(cypher, 'cell')
```

**Usage:**

```python
# Load magic commands
%load_ext graph_olap

# Quick inline query
%graph_query MATCH (n:Customer) RETURN count(n)

# Multi-line query
%%cypher
MATCH (c:Customer)-[p:PURCHASED]->(pr:Product)
WHERE c.city = 'London'
RETURN c.name, pr.name, p.amount
ORDER BY p.amount DESC
LIMIT 100
```

---

## Deployment Process (HSBC Dataproc)

### 1. Publish the SDK Wheel to Nexus

The SDK build pipeline produces a Python wheel, which is uploaded to the HSBC Nexus PyPI repository. Refer to the HSBC Nexus upload procedure for the authoritative steps.

### 2. Install in a Dataproc Notebook

Inside a Dataproc notebook cell:

```python
!pip install graph-olap-sdk[all]
```

### 3. Configure Environment

Set the environment variables for the Azure-AD-proxied control-plane endpoint. These are typically injected by the Dataproc cluster configuration. Per ADR-104/105 the SDK has **no** API-key / Bearer-token authentication mode: production auth is terminated upstream by the HSBC Azure AD proxy, which then forwards the caller identity to the control-plane via the `X-Username` header. The SDK simply attaches `X-Username` on every request.

- `GRAPH_OLAP_API_URL` - Azure AD proxy URL for the control-plane on HSBC GKE
- `GRAPH_OLAP_USERNAME` - Identity attached to every request via `X-Username` (set by the notebook bootstrap or auth-proxy; see `graph_olap.config.Config`)

### 4. Verify

```python
from graph_olap import notebook
client = notebook.connect()  # Should work automatically

# Test call
client.mappings.list()
```

---

## Notebook Styling (CSS Distribution)

**Reference:** [ADR-091: SDK Embedded CSS Distribution](--/process/adr/ux/adr-091-sdk-embedded-css.md)

The SDK embeds the notebook CSS design system for zero-config styling when rendering results in Jupyter output cells.

### CSS Access Function

```python
# styles/__init__.py

from importlib import resources

def get_notebook_css() -> str:
    """Load the notebook CSS from package resources."""
    return resources.files(__package__).joinpath("notebook.css").read_text()
```

### Usage

The SDK applies the CSS automatically on import when running inside a Jupyter kernel, via `IPython.display.HTML`. Analysts can also load it manually:

```python
from IPython.display import HTML
from graph_olap.styles import get_notebook_css

HTML(f"<style>{get_notebook_css()}</style>")
```

### Verification

```python
# Verify CSS is accessible from installed package
from graph_olap.styles import get_notebook_css

css = get_notebook_css()
print(f"CSS loaded: {len(css)} characters")
assert ".nb-callout" in css
assert ".nb-card" in css
```

---

## Environment Variables

Recognised by `graph_olap.config.Config.from_env()` — see `packages/graph-olap-sdk/src/graph_olap/config.py`. There is **no** `GRAPH_OLAP_API_KEY` / Bearer-token mode (ADR-104/105): identity is carried via `X-Username` only.

| Variable | Required | Description |
|----------|----------|-------------|
| `GRAPH_OLAP_API_URL` | Yes | Control plane API URL (Azure AD proxy) |
| `GRAPH_OLAP_USERNAME` | Yes | Identity attached to every request via `X-Username` (ADR-104/105) |
| `GRAPH_OLAP_USE_CASE_ID` | No | Value of the `X-Use-Case-Id` header (ADR-102) |
| `GRAPH_OLAP_PROXY` | No | HTTP(S) proxy URL (falls back to `https_proxy`) |
| `GRAPH_OLAP_SSL_VERIFY` | No | Set to `false` to disable TLS verification (default: verify) |
