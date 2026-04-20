---
title: "Appendix A: Environment Variables"
scope: hsbc
---

# Appendix A: Environment Variables

This appendix provides a complete reference for all environment variables
**actually read by the Graph OLAP SDK** (`graph-olap-sdk` Python package).

## Overview

The SDK reads configuration from environment variables to keep notebook code
portable across use cases and analyst accounts. On HSBC Dataproc, these are
typically set once in the analyst's notebook bootstrap or in a central
Dataproc profile so that `GraphOLAPClient.from_env()` works without any
arguments.

Only the variables listed below are consumed by the SDK. Anything not in this
list will be silently ignored — **do not** add variables that look SDK-related
but are not grounded in the source; they mislead the next reader.

## Environment Variable Reference

### Core Configuration (read by the SDK)

| Variable | Required | Description | Default | Example |
|----------|----------|-------------|---------|---------|
| `GRAPH_OLAP_API_URL` | **Yes** | Base URL for the control-plane API | *(none — raises `RuntimeError` if unset)* | `https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc` |
| `GRAPH_OLAP_USERNAME` | Strongly recommended | Username sent as `X-Username`. In production the Azure AD / IAP proxy overrides this; in notebooks where no proxy is present, the SDK sends what you set. | `analyst_alice@e2e.local` (dev sentinel) | `alice@hsbc.co.uk` |
| `GRAPH_OLAP_USE_CASE_ID` | No | Use-case identifier sent as `X-Use-Case-Id` (ADR-102) | `e2e_test_role` | `fraud_analytics` |
| `GRAPH_OLAP_PROXY` | No | HTTP proxy URL (falls back to `https_proxy`) | — | `<HSBC_HTTPS_PROXY>` |
| `GRAPH_OLAP_SSL_VERIFY` | No | Verify TLS certificates. Set to `false` / `0` / `no` to disable. | `true` | `false` |
| `GRAPH_OLAP_VERIFY_SSL` | No | Legacy alias for `GRAPH_OLAP_SSL_VERIFY`, read only by `Config.from_env()` | `true` | `false` |

These are the **only** environment variables the SDK (`graph_olap.config`
and `graph_olap.client`) reads. `Config.from_env()` and the
`GraphOLAPClient` constructor additionally read the lowercase `https_proxy`
variable as a secondary fallback for `GRAPH_OLAP_PROXY`.

### Notebook bootstrap (read by `graph_olap.notebook_setup`)

`graph_olap.notebook_setup.setup()` is a helper used in Jupyter / E2E flows.
It reads the core variables above plus:

| Variable | Required | Description | Default | Example |
|----------|----------|-------------|---------|---------|
| `GRAPH_OLAP_IN_CLUSTER_MODE` | No | Enable Kubernetes service DNS resolution | `false` | `true` |
| `GRAPH_OLAP_NAMESPACE` | No | Kubernetes namespace for service DNS | `e2e-test` | `graph-olap-platform` |

| Variable | Purpose |
|----------|---------|
| `GRAPH_OLAP_USERNAME_<PERSONA>` | Per-persona username override used by E2E notebooks (e.g. `GRAPH_OLAP_USERNAME_OPS`) |

### Notebook helper (read by `graph_olap.notebook.wake_starburst`)

The `wake_starburst()` helper reads Starburst connection details (used only
if you call it from a notebook cell):

| Variable | Purpose |
|----------|---------|
| `STARBURST_USER` | Starburst Galaxy username |
| `STARBURST_PASSWORD` | Starburst Galaxy password |
| `STARBURST_TRINO_URL` | Starburst Trino URL |

If these are not set, `wake_starburst()` is a no-op that returns `False`.

### Not wired from the environment

The SDK `Config` dataclass has `timeout` and `max_retries` fields, but
`Config.from_env()` does **not** read `GRAPH_OLAP_TIMEOUT` or
`GRAPH_OLAP_MAX_RETRIES`. Pass them explicitly to `GraphOLAPClient(...)` if
you need non-default values. Setting them in the environment has no effect.

## Detailed Variable Descriptions

### GRAPH_OLAP_API_URL

The base URL of the Graph OLAP control-plane API. In the HSBC deployment
this is the ingress hostname fronted by the Azure AD proxy:

```bash
export GRAPH_OLAP_API_URL="https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc"
```

There is no baked-in default. If this variable is unset and `api_url=` is
not passed to `GraphOLAPClient(...)`, construction raises `RuntimeError`
with an actionable message.

### GRAPH_OLAP_USERNAME

Username sent as `X-Username`. The server resolves the caller's role from
the `role` column of the users table based on this header (ADR-104) — no
JWT or Bearer token parsing occurs at the SDK layer.

**Production behaviour (HSBC):** the Azure AD proxy in front of the
control-plane strips any caller-supplied `X-Username` and rewrites it with
the authenticated identity. Setting `GRAPH_OLAP_USERNAME` in the notebook
therefore has no effect on who the server thinks you are — it only affects
local SDK logging and defaults.

```bash
export GRAPH_OLAP_USERNAME="alice@hsbc.co.uk"
```

### GRAPH_OLAP_USE_CASE_ID

Use-case identifier sent as `X-Use-Case-Id` (ADR-102). The control plane
records it alongside audit events so that platform usage can be attributed
to a specific approved HSBC business use case. Production notebooks should
set this to the approved value for the analyst's workstream; the default
(`e2e_test_role`) is only appropriate for test environments.

```bash
export GRAPH_OLAP_USE_CASE_ID="fraud_analytics"
```

### GRAPH_OLAP_PROXY

HTTP proxy URL. Used for egress from Dataproc notebook pods that need to
reach the control-plane through an HSBC proxy. Falls back to the lowercase
`https_proxy` environment variable if `GRAPH_OLAP_PROXY` is unset.

```bash
export GRAPH_OLAP_PROXY="<HSBC_HTTPS_PROXY>"
```

### GRAPH_OLAP_SSL_VERIFY

Whether to verify TLS certificates on HTTPS calls. Defaults to `true`.
Only set to `false` in isolated test environments — disabling certificate
verification against the HSBC control-plane voids transport-layer integrity.

```bash
export GRAPH_OLAP_SSL_VERIFY="false"   # dev/test only
```

## Configuration Precedence

The SDK follows this precedence order (highest to lowest):

1. **Explicit constructor arguments** — direct kwargs to `GraphOLAPClient()`
2. **`from_env()` parameter overrides** — kwargs passed to `GraphOLAPClient.from_env()`
3. **Environment variables** — the variables listed above
4. **Baked-in defaults** — only for `use_case_id` and `GRAPH_OLAP_USERNAME` (dev sentinel)

```python
# Environment: GRAPH_OLAP_API_URL="https://prod.example.com"

# Explicit kwarg wins
client = GraphOLAPClient(username="alice@hsbc.co.uk", api_url="https://staging.example.com")

# from_env() override wins over the env var
client = GraphOLAPClient.from_env(api_url="https://dev.example.com")

# No override — uses the env var
client = GraphOLAPClient.from_env()
```

## Typical HSBC Dataproc Notebook Setup

```bash
# Inside the Dataproc notebook (or set by the Dataproc profile)
export GRAPH_OLAP_API_URL="https://control-plane-graph-olap-platform.hsbc-12636856-udlhk-dev.dev.gcp.cloud.hk.hsbc"
export GRAPH_OLAP_USE_CASE_ID="fraud_analytics"      # approved use case
# GRAPH_OLAP_USERNAME is overridden by the Azure AD proxy in production,
# but keep it set for local logging/identification.
export GRAPH_OLAP_USERNAME="alice@hsbc.co.uk"
```

Then from Python:

```python
from graph_olap import GraphOLAPClient
client = GraphOLAPClient.from_env()
```

## Validation and Troubleshooting

### Verify configuration

```python
import os

required = ["GRAPH_OLAP_API_URL"]
optional = [
    "GRAPH_OLAP_USERNAME",
    "GRAPH_OLAP_USE_CASE_ID",
    "GRAPH_OLAP_PROXY",
    "GRAPH_OLAP_SSL_VERIFY",
]

for var in required:
    value = os.environ.get(var)
    print(f"{var}: {value or 'NOT SET (required)'}")
for var in optional:
    value = os.environ.get(var)
    print(f"{var}: {value or 'not set'}")
```

### Common issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `RuntimeError: GRAPH_OLAP_API_URL is not set` | Missing required variable | Set `GRAPH_OLAP_API_URL` to the HSBC control-plane ingress URL |
| `AuthenticationError: 401` | Unknown username on the server | Verify the Azure AD proxy is rewriting `X-Username` to a user that exists in the platform users table |
| `ForbiddenError: 403` | User exists but lacks the required role for that endpoint | Contact your platform operator to have the user's role updated |
| Connection refused / name resolution failure | Wrong `GRAPH_OLAP_API_URL` or proxy misconfigured | Check the URL against the operator handoff notes; set `GRAPH_OLAP_PROXY` if egress requires it |

## Removed / Phantom Variables

The following variables appeared in earlier drafts of this appendix but are
**not** read by the SDK. Remove them from any notebook bootstrap, Helm
values, or `.env` file if present — they have no effect at runtime.

| Variable | Status | Notes |
|----------|--------|-------|
| `GRAPH_OLAP_INTERNAL_API_KEY` | Not read by the SDK (ADR-104/105) | Only used by the `export-worker` backend for its internal call to the control-plane; never set it on analyst notebook environments |
| `GRAPH_OLAP_TIMEOUT` | Not wired | `Config.from_env()` does not read it; pass `timeout=` to `GraphOLAPClient(...)` |
| `GRAPH_OLAP_MAX_RETRIES` | Not wired | As above; pass `max_retries=` |
<!-- GRAPH_OLAP_IN_CLUSTER_MODE and GRAPH_OLAP_NAMESPACE ARE read by the SDK
     (see resources/instances.py:426,434) — intentionally NOT in this "not read"
     table. Their documented purpose is covered under "Notebook bootstrap". -->
| `GRAPH_OLAP_SKIP_HEALTH_CHECK` | Not read by the SDK | Health checks are gated by `create_and_wait`'s `health_check_timeout` argument, not an env var |
| `GRAPH_OLAP_API_KEY` | Never read by the SDK | API-key / Bearer-token auth was removed (ADR-104/105); identity is carried by `X-Username` |
| `GRAPH_OLAP_WRAPPER_INGRESS_CLASS` | Never read by the SDK | Ingress class is set by the wrapper Helm chart, not at SDK runtime |

If these variables appear in ConfigMaps, Helm values, or operator runbooks
used to configure the SDK side, update those artifacts — they will mislead
the next operator who reads them.

## See Also

- [01-getting-started.manual.md](--/01-getting-started.manual.md) — SDK quick start
- [02-core-concepts.manual.md](--/02-core-concepts.manual.md) — Authentication, identity headers, roles
- [Appendix B: Error Codes](-/b-error-codes.manual.md) — Error handling reference
