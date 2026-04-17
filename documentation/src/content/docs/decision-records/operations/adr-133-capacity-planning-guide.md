---
title: "ADR-133: Capacity Planning Guide"
---

| | |
|---|---|
| **Date** | 2026-04-08 |
| **Status** | Accepted |
| **Category** | operations |


## Context

The Graph OLAP Platform is being handed off to HSBC operations teams who will manage capacity planning for GKE, Cloud SQL, and GCS. Without documented sizing formulas and scaling procedures, the receiving team would need to derive capacity models from first principles by studying Helm charts, Terraform modules, and production metrics.

The platform has several distinct scaling dimensions that interact with each other:

1. **Graph instances** are the primary capacity driver. Each instance is a pod consuming 2--32 GB of memory depending on wrapper type and snapshot size (platform default `sizing.maxMemoryGb` is 32 GB; environments may override lower). The maximum number of concurrent instances determines the required node pool size.
2. **JupyterHub users** each consume a notebook pod (256 Mi--1 Gi RAM). Idle culling at 30 minutes limits the steady-state count, but peak concurrent users during business hours can spike.
3. **Export workers** are lightweight (256 Mi each) but scale via KEDA from 0 to 5 replicas. Export throughput is limited by Starburst resource groups and GCS write speed, not worker resources.
4. **Cloud SQL** connection pool size (default 25 per control-plane replica) and storage growth from metadata accumulation require periodic review.
5. **GCS** storage grows with snapshot count and export frequency. Lifecycle rules manage cleanup, but retention policies must be tuned to usage patterns.

Without a capacity planning guide, operators risk either over-provisioning (wasting budget) or under-provisioning (causing pod scheduling failures and degraded user experience).

---

## Decision

Create a capacity planning guide (`docs/operations/capacity-planning.manual.md`) that covers:

1. **Current resource allocation** -- table of all services with CPU/memory requests and limits
2. **Sizing formulas** -- compute node pool size, Cloud SQL tier, and GCS capacity from usage parameters
3. **Scaling procedures** -- step-by-step instructions for horizontal, vertical, node pool, and database scaling
4. **Resource governance** -- platform-enforced limits (per-user, per-cluster) and GKE/GCP quotas
5. **Monitoring for capacity** -- metrics and thresholds that indicate capacity pressure
6. **Cost estimation** -- approximate GCP cost per graph instance, per user, and per export job

The guide provides concrete formulas that operators can use to translate business requirements (e.g., "support 30 concurrent graph instances and 20 JupyterHub users") into infrastructure specifications (node count, machine type, Cloud SQL tier).

---

## Consequences

**Positive:**

- Operators can right-size infrastructure for projected workloads without guesswork
- Cost estimation enables budget planning before scaling events
- Scaling procedures reduce risk of configuration errors during capacity changes
- Resource governance documentation prevents accidental cluster exhaustion

**Negative:**

- Formulas are approximations based on current workload profiles and may need recalibration as usage patterns evolve
- Cost estimates are point-in-time and may drift as GCP pricing changes
- Guide must be updated when Helm chart defaults or resource governance values change
- The guide hardcodes ~35 numeric values (resource requests, governance limits, machine types, autoscaler bounds) that are duplicated from Helm charts and Terraform modules. Without a CI check or automated drift detection, these values can silently diverge from the live configuration. The capacity review cadence (quarterly) partially mitigates this but does not eliminate the risk of operators acting on stale numbers
- The guide must clearly distinguish platform defaults from environment-specific overrides (e.g. GKE London demo values), since operators need to know which values they can expect to match their deployment

---

## Alternatives Considered

### Alternative 1: Rely on GKE Autoscaler Without Documentation

Let the cluster autoscaler and HPA handle all capacity decisions automatically without documenting sizing formulas or scaling procedures.

**Rejected:** Autoscalers react to current load but cannot plan for future growth. Operations teams need to set autoscaler bounds (min/max nodes), choose machine types, and size Cloud SQL -- all of which require capacity modelling. Undocumented autoscaler configuration also makes it difficult to reason about cost implications of usage growth.

### Alternative 2: Spreadsheet-Based Capacity Model

Provide an interactive spreadsheet or calculator tool instead of a static document.

**Rejected:** A spreadsheet is harder to version-control, review in pull requests, and keep in sync with Helm values. A Markdown document with formulas serves the same purpose, integrates with the existing documentation set, and can be updated alongside infrastructure changes in the same commit.

### Alternative 3: Embed Capacity Guidance in the Platform Operations Manual

Add capacity planning as a section within the existing platform operations manual (ADR-129) rather than a standalone document.

**Rejected:** The platform operations manual already covers daily operations, maintenance, troubleshooting, and scaling at a procedural level. Capacity planning addresses a different concern (forecasting and right-sizing) with a different audience (capacity planners and budget owners, not on-call operators). Keeping them separate allows each document to stay focused and within the 300--500 line target. The capacity planning guide should reference ADR-129 for scaling execution steps rather than duplicating kubectl/gcloud commands.

### Alternative 4: Generate Capacity Data from Helm Values and Terraform Modules

Derive resource tables, governance limits, and sizing parameters automatically from Helm `values.yaml` and Terraform variable defaults, eliminating manual synchronisation.

**Rejected:** Generation can produce accurate resource tables and governance defaults, but cannot capture the operational context around each number -- when to change it, what the trade-offs are, and how values interact across scaling dimensions. A generated document also requires a generation pipeline to maintain. However, the guide should note which values are sourced from Helm charts vs Terraform so operators can verify currency, and a future CI check validating key values against the source of truth would reduce drift risk.

---

## References

- [Platform Operations Architecture](--/--/--/architecture/platform-operations.md) -- SLOs, cost model, node pool configuration
- [Detailed Architecture](--/--/--/architecture/detailed-architecture.md) -- resource management, dynamic sizing, governance limits
- [ADR-051: Wrapper Resource Allocation Strategy](--/infrastructure/adr-051-wrapper-resource-allocation-strategy.md) -- Ryugraph vs FalkorDB memory rationale
- [ADR-068: Wrapper Resource Optimization](--/infrastructure/adr-068-wrapper-resource-optimization.md) -- 75% reduction in wrapper resource requests
- [ADR-129: Platform Operations Manual](adr-129-platform-operations-manual.md) -- companion operations manual; scaling execution steps
- [Observability Design](--/--/--/operations/observability.design.md) -- Resource metrics, monitoring
- [ADR-135: Troubleshooting Guide](adr-135-troubleshooting-guide.md) -- diagnostic trees for capacity-related failures
