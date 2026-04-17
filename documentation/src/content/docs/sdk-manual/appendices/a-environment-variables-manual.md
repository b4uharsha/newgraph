---
title: "Appendix A: Environment Variables"
scope: hsbc
---

# Appendix A: Environment Variables

This appendix provides a complete reference for all environment variables used by the Graph OLAP SDK.

## Overview

The SDK uses environment variables for configuration, enabling deployment flexibility across development, staging, and production environments. Variables can be set in shell profiles, `.env` files, Kubernetes ConfigMaps, or container orchestration systems.

## Environment Variable Reference

### Core Configuration

| Variable | Required | Description | Default | Example |
|----------|----------|-------------|---------|---------|
| `GRAPH_OLAP_API_URL` | **Yes** | Base URL for the Control Plane API | - | `https://graph-olap.example.com` |
| `GRAPH_OLAP_USERNAME` | **Yes** | Username sent as `X-Username` header; role resolved from users table (ADR-104) | - | `analyst@example.com` |
| `GRAPH_OLAP_USE_CASE_ID` | No | Use-case identifier sent as `X-Use-Case-Id` header (ADR-102) | `e2e_test_role` | `fraud_analytics` |
| `GRAPH_OLAP_PROXY` | No | HTTP proxy URL (falls back to `https_proxy`) | - | `http://proxy.example.com:3128` |
| `GRAPH_OLAP_SSL_VERIFY` | No | Verify SSL certificates (`false` disables) | `true` | `false` |

<!-- Updated for ADR-104/105: API key / Bearer token auth removed; GRAPH_OLAP_INTERNAL_API_KEY is no longer consumed by the SDK. -->

### Kubernetes / In-Cluster Configuration

| Variable | Required | Description | Default | Example |
|----------|----------|-------------|---------|---------|
| `GRAPH_OLAP_IN_CLUSTER_MODE` | No | Enable Kubernetes service DNS resolution | `false` | `true` |
| `GRAPH_OLAP_NAMESPACE` | No | Kubernetes namespace for service DNS | `graph-olap-local` | `graph-olap-platform` |

### SDK Behavior Configuration

> **Not yet wired from the environment.** The SDK `Config` dataclass has
> ``timeout`` and ``max_retries`` fields, but ``Config.from_env()`` does **not**
> currently read ``GRAPH_OLAP_TIMEOUT`` or ``GRAPH_OLAP_MAX_RETRIES``. If you
> need non-default values, pass them explicitly to ``GraphOLAPClient(...)``.
> Setting these variables in Helm values, ConfigMaps, or `.env` files has no
> effect — stop setting them.

## Detailed Variable Descriptions

### GRAPH_OLAP_API_URL

The base URL for connecting to the Graph OLAP Control Plane API.

**Format:** Full URL including protocol (http/https)

**Examples:**
```bash
# HSBC environment (your Graph OLAP API URL via HSBC ingress)
export GRAPH_OLAP_API_URL="https://api.<hsbc-ingress-domain>.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc"

# Kubernetes cluster (in-cluster service DNS)
export GRAPH_OLAP_API_URL="http://control-plane.graph-olap-platform.svc.cluster.local:8000"
```

### GRAPH_OLAP_USERNAME

Username for identifying the caller. The server resolves the user's role from the `role` column in the users table — no token parsing occurs at the API layer (ADR-104).

**Format:** String (typically email or identifier)

**Authentication Header:** `X-Username: {username}`

**Important Production Note:**
In production environments with authentication gateways (e.g., GKE IAP/OIDC), the gateway strips and replaces this header with the validated identity from the authentication layer.

**Example:**
```bash
export GRAPH_OLAP_USERNAME="analyst@example.com"
```

### GRAPH_OLAP_INTERNAL_API_KEY (removed)

> **Removed by ADR-104 / ADR-105.** The SDK no longer consumes
> ``GRAPH_OLAP_INTERNAL_API_KEY`` — identity is carried by the ``X-Username``
> header set by the edge proxy (or by the SDK in dev/test). The variable is
> still used by the **export-worker** backend service for its internal calls
> to the control plane, but it must **not** be set for end-user SDK/notebook
> environments. Remove it from Helm values, ConfigMaps, and `.env` files used
> for JupyterHub/notebook deployments.

### GRAPH_OLAP_IN_CLUSTER_MODE

Enables Kubernetes service DNS resolution for instance connections.

**Format:** `true` or `false` (case-insensitive)

**Behavior when enabled:**
- Instance connections use Kubernetes service DNS names
- Format: `{instance-name}.{namespace}.svc.cluster.local`
- Bypasses external load balancers for direct pod communication

**When to enable:**
- Running in Kubernetes pods (JupyterHub, Jobs)
- E2E tests running inside the cluster
- Any workload that should use internal networking

**Example:**
```bash
export GRAPH_OLAP_IN_CLUSTER_MODE="true"
```

### GRAPH_OLAP_NAMESPACE

Kubernetes namespace for service DNS resolution.

**Format:** Valid Kubernetes namespace name

**Used when:** `GRAPH_OLAP_IN_CLUSTER_MODE` is enabled

**Service DNS Pattern:**
```
{service-name}.{GRAPH_OLAP_NAMESPACE}.svc.cluster.local
```

**Example:**
```bash
export GRAPH_OLAP_NAMESPACE="graph-olap-platform"
# Results in DNS: control-plane.graph-olap-platform.svc.cluster.local
```

## Configuration Precedence

The SDK follows this precedence order (highest to lowest):

1. **Explicit constructor arguments** - Direct parameters to `GraphOLAPClient()`
2. **`from_env()` parameter overrides** - Arguments passed to `GraphOLAPClient.from_env()`
3. **Environment variables** - Values from the shell environment
4. **Default values** - Built-in SDK defaults

**Example:**
```python
# Environment: GRAPH_OLAP_API_URL="https://prod.example.com"

# Constructor takes precedence
client = GraphOLAPClient(api_url="https://staging.example.com")
# Uses: https://staging.example.com

# from_env() override takes precedence over environment
client = GraphOLAPClient.from_env(api_url="https://dev.example.com")
# Uses: https://dev.example.com

# No override - uses environment variable
client = GraphOLAPClient.from_env()
# Uses: https://prod.example.com
```

## Environment-Specific Configurations

### E2E Testing (In-Cluster)

```bash
# Injected via Kubernetes Job spec
GRAPH_OLAP_API_URL="http://control-plane.graph-olap-local.svc.cluster.local:8000"
GRAPH_OLAP_USERNAME="e2e_test@e2e.local"
GRAPH_OLAP_IN_CLUSTER_MODE="true"
GRAPH_OLAP_NAMESPACE="graph-olap-local"
```

### Production (GKE with IAP)

```bash
# Injected via Kubernetes ConfigMap/Secrets
# In production the IAP gateway sets X-Username from the authenticated session;
# GRAPH_OLAP_USERNAME is only used in dev/test (no gateway).
GRAPH_OLAP_API_URL="https://api.<hsbc-ingress-domain>.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc"
GRAPH_OLAP_IN_CLUSTER_MODE="true"
GRAPH_OLAP_NAMESPACE="graph-olap-platform"
```

## JupyterHub Configuration

When deploying JupyterHub with the SDK, configure environment variables in the Helm values:

```yaml
# values.yaml
singleuser:
  extraEnv:
    GRAPH_OLAP_API_URL: "http://control-plane.graph-olap-local.svc.cluster.local:8000"
    GRAPH_OLAP_IN_CLUSTER_MODE: "true"
    GRAPH_OLAP_NAMESPACE: "graph-olap-local"
  # Username is injected by JupyterHub from the authenticated session
  # (X-Username header set by the hub singleuser spawner)
```

## Validation and Troubleshooting

### Verify Configuration

```python
import os

# Check required variables
required = ["GRAPH_OLAP_API_URL", "GRAPH_OLAP_USERNAME"]
for var in required:
    value = os.environ.get(var)
    if value:
        print(f"{var}: {value[:20]}...")  # Truncate for security
    else:
        print(f"{var}: NOT SET (required)")

# Check optional variables
optional = [
    "GRAPH_OLAP_USE_CASE_ID",
    "GRAPH_OLAP_IN_CLUSTER_MODE",
    "GRAPH_OLAP_NAMESPACE",
    "GRAPH_OLAP_PROXY",
    "GRAPH_OLAP_SSL_VERIFY",
]
for var in optional:
    value = os.environ.get(var)
    if value:
        # Mask sensitive values
        if "KEY" in var:
            print(f"{var}: ***masked***")
        else:
            print(f"{var}: {value}")
    else:
        print(f"{var}: not set")
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `ValueError: GRAPH_OLAP_API_URL not set` | Missing required variable | Set `GRAPH_OLAP_API_URL` in environment |
| `ValueError: username is required` | Missing `GRAPH_OLAP_USERNAME` | Set `GRAPH_OLAP_USERNAME` in environment |
| `AuthenticationError: 401` | Unknown or invalid username | Verify `GRAPH_OLAP_USERNAME` matches a DB user record |
| `Connection refused` | Wrong URL or service not running | Check `GRAPH_OLAP_API_URL` and service status |
| `DNS resolution failed` | In-cluster mode misconfigured | Verify namespace and `IN_CLUSTER_MODE` settings |
| `ForbiddenError: 403` | Insufficient permissions | Check user's role in the users table |

## Removed / Phantom Variables

The following variables were documented in earlier drafts but are **not**
consumed by the current SDK, control plane, or export worker. Remove them
from Helm values, ConfigMaps, Terraform, and `.env` files if present.

| Variable | Status | Notes |
|----------|--------|-------|
| `GRAPH_OLAP_INTERNAL_API_KEY` | Removed from SDK (ADR-104/105) | Still used internally by export-worker → control-plane; never set for user/notebook pods |
| `GRAPH_OLAP_TIMEOUT` | Not wired | ``Config.from_env()`` does not read it; pass ``timeout`` to ``GraphOLAPClient(...)`` |
| `GRAPH_OLAP_MAX_RETRIES` | Not wired | Same as above; pass ``max_retries`` to ``GraphOLAPClient(...)`` |
| `GRAPH_OLAP_WRAPPER_INGRESS_CLASS` | Removed (post-ADR-101) | Ingress class is now set by the wrapper Helm chart; no longer a runtime setting |
| `EXPORT_CLAIM_BATCH_SIZE` | Never implemented | Not a field in `export_worker.config.Settings`. Use `CLAIM_LIMIT` (default 10) instead |

If these variables appear in Terraform ConfigMaps, Helm values, or operator
runbooks, update those artifacts — they have no effect at runtime and will
mislead the next operator who reads them.

## See Also

- [SDK Quick Start](--/01-getting-started.manual.html) - Getting started guide
- [02-core-concepts.manual.md](--/02-core-concepts.manual.md) - Authentication, identity headers, roles
- [Appendix B: Error Codes](-/b-error-codes.manual.md) - Error handling reference
