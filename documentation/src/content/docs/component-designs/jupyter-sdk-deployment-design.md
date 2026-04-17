---
title: "Jupyter SDK Deployment Design"
scope: hsbc
---

# Jupyter SDK Deployment Design

## Overview

This document covers packaging, distribution, and deployment of the Graph OLAP Python SDK to enterprise Jupyter notebook clusters. For SDK architecture and implementation, see [jupyter-sdk.design.md](-/jupyter-sdk.design.md).

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

## Installation Options

```bash
# Minimal (control plane only)
pip install graph-olap-sdk

# For analysts (recommended)
pip install graph-olap-sdk[all]

# Everything including Graphistry
pip install graph-olap-sdk[all,enterprise]
```

---

## Zero-Config Jupyter Integration

The SDK provides a "magic" import that auto-configures everything:

```python
# notebook.py - Zero-config Jupyter setup
import os

def init(api_url: str = None, api_key: str = None):
    """
    Initialize Graph OLAP SDK for Jupyter notebooks.

    Auto-discovers configuration from environment variables:
    - GRAPH_OLAP_API_URL: Control plane URL
    - GRAPH_OLAP_API_KEY: API key for authentication
    - GRAPH_OLAP_IN_CLUSTER_MODE: Set to "true" for in-cluster execution (optional)
    - GRAPH_OLAP_NAMESPACE: Kubernetes namespace for service DNS (optional)

    Also configures:
    - itables for automatic interactive DataFrames
    - Polars as default DataFrame backend
    - Rich output for all result types
    """
    api_url = api_url or os.environ.get("GRAPH_OLAP_API_URL")
    api_key = api_key or os.environ.get("GRAPH_OLAP_API_KEY")

    if not api_url:
        raise ValueError(
            "GRAPH_OLAP_API_URL not set. Either pass api_url parameter "
            "or set the environment variable."
        )

    # Configure itables for automatic interactive display
    try:
        import itables
        itables.init_notebook_mode(all_interactive=True)
    except ImportError:
        pass

    from graph_olap import GraphOLAPClient
    return GraphOLAPClient(api_url=api_url, api_key=api_key)


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

## Docker Image for Jupyter Cluster

Build a pre-configured Jupyter image with everything installed:

```dockerfile
# Dockerfile.jupyter
FROM jupyter/datascience-notebook:python-3.11

USER root

# Install system dependencies for graph visualization
RUN apt-get update && apt-get install -y \
    graphviz \
    && rm -rf /var/lib/apt/lists/*

USER ${NB_UID}

# Install SDK with all dependencies
RUN pip install --no-cache-dir \
    graph-olap-sdk[all] \
    jupyterlab-git \
    jupyterlab-lsp

# Pre-configure for best experience
COPY jupyter_notebook_config.py /etc/jupyter/

# Add example notebooks
COPY examples/ /home/jovyan/examples/
```

```python
# jupyter_notebook_config.py - Auto-initialization
c.InteractiveShellApp.exec_lines = [
    # Auto-import common tools
    'import polars as pl',
    'import pandas as pd',
    'import networkx as nx',

    # Initialize itables for all notebooks
    'try:',
    '    import itables; itables.init_notebook_mode(all_interactive=True)',
    'except ImportError: pass',

    # Show welcome message
    'print("Graph OLAP SDK ready. Use: from graph_olap import notebook; client = notebook.connect()")',
]
```

---

## JupyterHub Helm Chart Configuration

For enterprise JupyterHub on Kubernetes:

```yaml
# values.yaml for JupyterHub Helm chart
singleuser:
  image:
    name: your-registry/graph-olap-notebook
    tag: "1.0.0"

  # Pre-set environment variables for auto-discovery
  extraEnv:
    GRAPH_OLAP_API_URL: "https://graph-olap.internal.company.com"

  # Mount API key from secret
  extraVolumes:
    - name: graph-olap-creds
      secret:
        secretName: graph-olap-api-key
  extraVolumeMounts:
    - name: graph-olap-creds
      mountPath: /etc/graph-olap
      readOnly: true

  # Resource allocation
  memory:
    limit: 8G
    guarantee: 2G
  cpu:
    limit: 4
    guarantee: 0.5

  # Persistent storage for notebooks
  storage:
    capacity: 10Gi
    dynamic:
      storageClass: standard

# Allow users to select different profiles
profileList:
  - display_name: "Standard (2GB RAM)"
    description: "For small to medium graphs"
    default: true
  - display_name: "Large (8GB RAM)"
    description: "For large graphs and heavy computation"
    kubespawner_override:
      mem_limit: 8G
      mem_guarantee: 4G
```

---

## IPython Magic Commands

For power users, provide IPython magic commands:

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

## Deployment Process

### 1. Build Docker Image

```bash
docker build -t your-registry/graph-olap-notebook:1.0.0 -f Dockerfile.jupyter .
docker push your-registry/graph-olap-notebook:1.0.0
```

### 2. Create API Key Secret

```bash
kubectl create secret generic graph-olap-api-key \
  --from-literal=api-key=your-api-key-here
```

### 3. Deploy JupyterHub

```bash
helm upgrade --install jupyterhub jupyterhub/jupyterhub \
  -f values.yaml \
  --namespace jupyter
```

### 4. Verify

```python
# In a new notebook
from graph_olap import notebook
client = notebook.connect()  # Should work automatically

# Test query
client.mappings.list()
```

---

## Notebook Styling (CSS Distribution)

**Reference:** [ADR-091: SDK Embedded CSS Distribution](--/process/adr/ux/adr-091-sdk-embedded-css.md)

The SDK embeds the notebook CSS design system for zero-config styling in JupyterHub deployments.

### CSS Access Functions

```python
# styles/__init__.py

from importlib import resources

def get_notebook_css() -> str:
    """Load the notebook CSS from package resources."""
    return resources.files(__package__).joinpath("notebook.css").read_text()
```

### Usage in Init Containers

```bash
# sync-notebooks.sh (in notebook-sync container)

# Get CSS content from installed SDK
CSS_CONTENT=$(python -c "from graph_olap.styles import get_notebook_css; print(get_notebook_css())")

# Write to JupyterLab custom CSS location
mkdir -p /home/jovyan/.jupyter/custom
echo "$CSS_CONTENT" > /home/jovyan/.jupyter/custom/custom.css
chown 1000:100 /home/jovyan/.jupyter/custom/custom.css
```

### Distribution Flow

```
SDK Package                    JupyterHub Pod
┌─────────────┐               ┌─────────────────┐
│ graph_olap/ │               │ Init Container  │
│ styles/     │   pip install │                 │
│ notebook.css│──────────────►│ cp CSS to       │
│ (1506 lines)│               │ ~/.jupyter/     │
└─────────────┘               │ custom/         │
                              └─────────────────┘
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

| Variable | Required | Description |
|----------|----------|-------------|
| `GRAPH_OLAP_API_URL` | Yes | Control plane API URL |
| `GRAPH_OLAP_API_KEY` | Yes | API key for authentication |
| `GRAPH_OLAP_DEFAULT_TIMEOUT` | No | Default request timeout (ms) |
| `GRAPH_OLAP_RETRY_COUNT` | No | Number of retries for failed requests |
| `GRAPH_OLAP_IN_CLUSTER_MODE` | No | Set to "true" for in-cluster execution (Kubernetes service DNS). Default: "false" |
| `GRAPH_OLAP_NAMESPACE` | No | Kubernetes namespace for service DNS (used with in-cluster mode). Default: "graph-olap-local" |
