---
title: "ADR-129: Platform Operations Manual"
---

| | |
|---|---|
| **Date** | 2026-04-08 |
| **Status** | Accepted |
| **Category** | operations |


## Context

The Graph OLAP Platform is being handed off to HSBC operations teams who will manage the platform in production on GKE. Without a comprehensive operations manual, the receiving team would need to reverse-engineer operational procedures from source code, Helm charts, and Terraform modules. This creates risk during the handoff period and increases mean time to resolution for routine operational tasks.

The platform has several components with distinct operational characteristics: a stateless control plane with database dependencies, ephemeral graph instance pods managed through an API, KEDA-scaled export workers, and a JupyterHub deployment with idle pod culling. Each requires specific operational knowledge that must be documented for the HSBC ops team.

HSBC deploys via Jenkins CI and kubectl apply (not Helm/ArgoCD), which means operational commands must be adapted to their toolchain. SOX change control via Deliverance applies to all production changes.

This ADR is part of a coordinated set of eight operational documents defined in [ADR-128: Operational Documentation Strategy](adr-128-operational-documentation-strategy.md). ADR-128 establishes the document taxonomy (`.manual.md` vs `.runbook.md`), delivery priorities, authoring standards, and cross-reference conventions that govern this manual.

---

## Decision

Create a comprehensive platform operations manual (`docs/operations/platform-operations.manual.md`) that covers:

1. **Daily operations** -- health checks, log review, resource monitoring
2. **Routine maintenance** -- database maintenance, GCS cleanup, certificate renewal, configuration changes, secret rotation
3. **Instance management** -- lifecycle operations and troubleshooting
4. **JupyterHub operations** -- user management, pod culling, notebook sync
5. **Scaling operations** -- horizontal and vertical scaling procedures
6. **Deployment and rollback** -- pre-deploy checklist, Jenkins/kubectl deployment flow, post-deploy verification, rollback via `kubectl rollout undo`
7. **Backup procedures** -- PostgreSQL and GCS snapshot management
8. **Background jobs** -- APScheduler job inventory, health checks, manual triggers
9. **Common commands** -- kubectl commands adapted for HSBC's deployment model
10. **Operational SLAs** -- target uptime, response times, capacity limits
11. **Disaster recovery summary** -- RTO/RPO table with recovery methods per component (summary only; full procedures are in [ADR-132: Disaster Recovery Plan](adr-132-disaster-recovery-plan.md))

The manual also includes a Quick Reference table and an Authentication section as unnumbered preamble for immediate operator use.

The manual is written for an operations team that has Kubernetes experience but no prior knowledge of the Graph OLAP Platform internals. All Kubernetes management commands use kubectl (not Helm or ArgoCD) to align with HSBC's deployment toolchain. API operations use curl, GCP operations use gcloud/gsutil, and structured log queries use python3.

**Service scope:** The manual covers the services with active operational procedures: control-plane, export-worker, graph instances (ryugraph-wrapper/falkordb-wrapper), and JupyterHub. Services without dedicated operational procedures (wrapper-proxy, extension-server, notebook-sync, docs) are inventoried in the [Service Catalogue (ADR-134)](adr-134-service-catalogue.md) and follow standard pod restart/log inspection patterns.

---

## Consequences

**Positive:**

- HSBC ops team can operate the platform independently from day one, after populating environment-specific configuration values (Auth0 tenant, GCP project, bucket names)
- Reduces knowledge transfer time during handoff
- Provides a single reference for all routine operational tasks
- Standardises operational procedures to reduce human error
- Aligns commands with HSBC's Jenkins + kubectl deployment model

**Negative:**

- Manual must be kept up to date as the platform evolves; maintenance obligations (annual review, 90-day hypercare period, version tracking) are defined in [ADR-128](adr-128-operational-documentation-strategy.md)
- Commands contain environment-specific placeholders (`<BUCKET_NAME>`, `<CLOUD_SQL_INSTANCE>`, `<PROJECT>`, Auth0 domain/client IDs) that must be populated for the HSBC environment before the manual is copy-paste-ready
- Some procedures depend on runtime assumptions about container images (installed packages such as python3/sqlalchemy, environment variables such as `DATABASE_URL`) that may change between versions
- The Authentication section assumes Auth0 as the identity provider; if HSBC uses a different IdP or OAuth flow, the token acquisition procedure must be adapted
- Section 11 (Disaster Recovery summary) duplicates RTO/RPO data from [ADR-132](adr-132-disaster-recovery-plan.md), creating a consistency maintenance burden
- kubectl-based commands lack the idempotency guarantees of GitOps workflows

---

## Alternatives Considered

### 1. Embed operational procedures in existing design documents

We considered adding operational sections to `deployment.design.md` and `observability.design.md` rather than creating a standalone manual. This was rejected because:

- Design documents serve architects and developers; operations manuals serve the ops team
- Mixing audiences in a single document leads to information overload
- The HSBC ops team needs a single, self-contained reference without needing to read architectural context

### 2. Wiki-only documentation (no versioned markdown)

We considered maintaining operations documentation solely in the internal wiki (Confluence/SharePoint). This was rejected because:

- Wiki documentation drifts from the codebase without review gates
- Versioned markdown in the repository ensures the manual is updated alongside code changes
- The manual can be reviewed in the same pull request as the code it documents

### 3. Automated runbook generation from Helm/Terraform

We considered generating operational commands dynamically from the Helm charts and Terraform modules. This was rejected because:

- Automated generation cannot capture operational judgment, troubleshooting decision trees, or the situational context that operators need around each command
- While generated commands could be adapted from Helm to kubectl output, the manual's value is in the human-readable procedures (when to run, what to check, what to do if it fails), not the commands themselves
- Maintaining a generation pipeline adds toolchain complexity without reducing the core authoring effort

---

## References

- [ADR-128: Operational Documentation Strategy](adr-128-operational-documentation-strategy.md) -- parent strategy governing all 8 operational documents
- [ADR-130: Incident Response Runbook](adr-130-incident-response-runbook.md) -- escalation from operational issues
- [ADR-131: Monitoring and Alerting Runbook](adr-131-monitoring-alerting-runbook.md) -- alert response procedures for metrics referenced in Section 1.3
- [ADR-132: Disaster Recovery Plan](adr-132-disaster-recovery-plan.md) -- full DR procedures summarised in Section 11
- [ADR-133: Capacity Planning Guide](adr-133-capacity-planning-guide.md) -- resource sizing and scaling thresholds referenced in Section 10
- [ADR-134: Service Catalogue](adr-134-service-catalogue.md) -- service inventory referenced throughout; covers services not in this manual's scope
- [ADR-135: Troubleshooting Guide](adr-135-troubleshooting-guide.md) -- deeper diagnostic trees complementing Section 3.2
- [Deployment Design](--/--/--/operations/deployment.design.md) -- deployment architecture and Helm charts
- [Platform Operations Architecture](--/--/--/architecture/platform-operations.md) -- SLOs, observability, background jobs
- [Observability Design](--/--/--/operations/observability.design.md) -- logging, metrics, alerting
