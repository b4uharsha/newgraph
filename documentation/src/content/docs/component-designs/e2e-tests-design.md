---
title: "E2E Tests Design"
scope: demo
---

# E2E Tests Design

<!-- scope:hsbc -->
## HSBC Conformance E2E

**Scope:** This section is the only portion of this document that applies to the HSBC-shipped package. The rest of this document describes the internal demo E2E harness (OrbStack + Earthly) that is **not** part of the HSBC delivery.

**Build system:** HSBC conformance tests are built and executed by Jenkins. Images are pushed to `gcr.io/hsbc-12636856-udlhk-dev/com/hsbc/wholesale/data/` and deployed to the target cluster via `./infrastructure/cd/deploy.sh` + `kubectl apply`. There is no GitHub Actions, ArgoCD, Helm release, Earthly, or OrbStack component in the HSBC pipeline.

**What conformance tests must cover:**

1. **Control Plane API contract** — CRUD over mappings, snapshots, instances; favorites; `/api/schema/*` browse/search; internal status/metrics callbacks.
2. **Wrapper API contract** — `/query`, `/algo/{name}`, `/networkx/{name}`, `/subgraph`, `/lock`, `/schema`, `/health`, `/status`, `/shutdown`.
3. **Pod lifecycle** — instance provisioning, termination, orphan reconciliation.
4. **Export workflow** — Starburst UNLOAD submission, poll, Parquet landing in the target GCS bucket.

**Execution model:** Conformance tests run as a Kubernetes Job inside the target HSBC cluster, authenticated against the in-cluster Control Plane service. They MUST NOT rely on developer-laptop tooling (OrbStack, Earthly, `make up`, `localhost:30081`) or on dev-cluster artefacts (fake-gcs-server, trino-proxy, embedded Derby metastore).

**Isolation:** Each conformance run uses a dedicated, short-lived namespace; cleanup runs before and after the suite.
<!-- /scope:hsbc -->

