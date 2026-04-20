---
title: "SDK Modifications for HSBC Dataproc"
sidebar:
  order: 5
---

## Changes from upstream

1. **Base URL**: Points at the HSBC-provisioned GKE ingress (`<HSBC_API_HOST>`)
   for Control Plane / lifecycle calls via the `GRAPH_OLAP_API_URL` env var.
2. **Wrapper query routing**: Cypher queries use the same ingress host with the
   `/wrapper/<url_slug>/query` path. The wrapper-proxy (nginx) is a server-side
   routing layer — analysts do **not** configure a separate URL.
3. **Authentication**: `X-Username` header (no Bearer token or API key).
4. **SSL verification**: `GRAPH_OLAP_SSL_VERIFY=false` is available for
   corporate-proxy MITM inspection scenarios. `pip install` from HSBC Nexus
   uses the system trust store.
5. **Proxy**: May need `HTTPS_PROXY` set if the Dataproc node cannot reach the
   GKE ingress directly.
