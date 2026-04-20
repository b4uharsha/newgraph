---
title: "Jupyter / Dataproc Setup"
sidebar:
  order: 4
---

## Prerequisites

- HSBC Dataproc cluster with Jupyter component
- Network route to GKE internal load balancer
- `graph-olap-sdk` installed (from Nexus PyPI)

## SDK Installation on Dataproc

```bash
pip install --extra-index-url https://nexus302.systems.uk.hsbc:8081/nexus/repository/pypi-hosted-iHub-dev-n3p/simple/ graph-olap-sdk
```

## Proxy Configuration

If Dataproc cannot reach the GKE ILB directly, configure an HTTP proxy:

```python
import os

# Required: point the SDK at the HSBC Control Plane and tag cost attribution
os.environ["GRAPH_OLAP_API_URL"] = "https://<HSBC_API_HOST>"
os.environ["GRAPH_OLAP_USE_CASE_ID"] = "<hsbc-use-case>"  # for Starburst cost attribution

# Optional: HTTPS proxy if Dataproc cannot reach the GKE ILB directly
os.environ["HTTPS_PROXY"] = "http://proxy.hsbc:8080"
```
