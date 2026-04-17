---
title: "SDK Modifications for HSBC Dataproc"
sidebar:
  order: 5
---

## Changes from upstream

1. **Base URL**: Points to HSBC GKE ILB (`control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc`)
2. **Authentication**: X-Username header (no Bearer token)
3. **SSL**: Uses HSBC trust store for Nexus registry connectivity
4. **Proxy**: May need HTTPS_PROXY for Dataproc -> GKE routing
