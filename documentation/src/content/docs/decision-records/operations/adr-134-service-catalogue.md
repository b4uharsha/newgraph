---
title: "ADR-134: Service Catalogue"
---

| | |
|---|---|
| **Date** | 2026-04-08 |
| **Status** | Accepted |
| **Category** | operations |


## Context

The Graph OLAP Platform consists of multiple deployable services (platform services, dynamically created wrapper pods, and JupyterHub) plus infrastructure dependencies (Cloud SQL, GCS, Starburst Galaxy). When the platform is handed off to HSBC operations, the receiving team needs a single document that answers "what services exist, how do they relate to each other, and what does each one do?" without requiring access to source code or Helm charts.

Current documentation describes the architecture at a conceptual level (C4 diagrams, component responsibilities) but does not provide the operational details an on-call engineer needs: port numbers, health check endpoints, restart safety, environment variables, and dependency ordering. This information is scattered across Helm values files, Dockerfiles, and source code.

A service catalogue serves as the "single pane of glass" that a new operator reads first. It answers the questions that arise during incidents: "Can I restart this service safely?", "What does this service depend on?", "What port should I check?", and "What environment variables configure this service?"

---

## Decision

Create a service catalogue (`docs/operations/service-catalogue.manual.md`) that provides:

1. **Service inventory table** -- name, type, port, health endpoint, replicas, criticality
2. **Dependency map** -- Mermaid diagram of service-to-service and service-to-infrastructure dependencies, with companion lookup table
3. **Per-service details** -- purpose, endpoints, dependencies, data stores, health checks, restart safety, scaling characteristics, key configuration
4. **Infrastructure dependencies** -- Cloud SQL, GCS, GKE API, Workload Identity
5. **External dependencies** -- Starburst Galaxy, authentication provider
6. **Network topology** -- Mermaid diagram of internal communication model, ingress routing
7. **Port map** -- complete port listing for all services
8. **Configuration reference** -- key environment variables per service

The catalogue is written for an operations engineer with Kubernetes experience but no prior knowledge of the Graph OLAP Platform. All information is self-contained and does not require access to source code.

---

## Consequences

**Positive:**

- New operators can understand the full service landscape in a single reading
- Incident responders can quickly identify dependencies and blast radius of any failure
- Port map and health check table eliminate guesswork during troubleshooting
- Restart safety documentation prevents accidental data loss during maintenance

**Negative:**

- Catalogue must be kept in sync as services are added, removed, or reconfigured; without a review cadence or CI check, it will drift -- the same risk cited against the wiki alternative. Maintenance obligations (including review cadence and ownership) are defined in [ADR-128](adr-128-operational-documentation-strategy.md)
- If catalogue values (ports, environment variables, job intervals) are incorrect at handoff time, operators will trust them over live configuration, potentially worsening incidents rather than preventing them
- Some operational details (e.g., exact environment variable values) are environment-specific and may differ between demo and production deployments
- Document is a snapshot; operators must verify against live configuration for production changes

---

## Alternatives Considered

### Alternative 1: Auto-Generated Service Catalogue from Helm Charts

Use a tool to generate the service catalogue automatically from Helm chart values, Kubernetes manifests, and Docker labels.

**Rejected:** Auto-generation captures structural facts (ports, resource limits, replica counts) but cannot capture operational knowledge (restart safety, scaling recommendations, dependency rationale, troubleshooting context). The most valuable parts of the catalogue are the human-authored descriptions that explain *why* a service exists and *how* it should be operated, not just *what* it is configured to do. A manually authored document with periodic review is more useful than an auto-generated one that lacks operational context.

### Alternative 2: Wiki or Confluence Page

Maintain the service catalogue in a wiki system (e.g., Confluence) rather than a Markdown file in the repository.

**Rejected:** Wiki pages are decoupled from the codebase and frequently drift out of sync with actual service configuration. By keeping the catalogue in the repository alongside Helm charts and Terraform modules, it can be updated in the same pull request as infrastructure changes. The HSBC handoff package is self-contained -- all documentation must be included in the repository.

### Alternative 3: Combine with Architecture Documentation

Add service operational details to the existing detailed architecture document instead of creating a separate catalogue.

**Rejected:** The architecture documentation (C4 diagrams, component decomposition) is written for enterprise architects and focuses on design rationale. The service catalogue is written for on-call operators and focuses on runtime details (ports, health checks, restart safety). Different audiences, different purposes, different update cadences. Combining them would bloat the architecture document and dilute both audiences.

---

## References

- [Detailed Architecture](--/--/--/architecture/detailed-architecture.md) -- C4 diagrams, container decomposition
- [Platform Operations Architecture](--/--/--/architecture/platform-operations.md) -- technology stack, SLOs, background jobs
- [ADR-129: Platform Operations Manual](adr-129-platform-operations-manual.md) -- companion operations manual
- [ADR-133: Capacity Planning Guide](adr-133-capacity-planning-guide.md) -- resource allocation and scaling
- [Deployment Design](--/--/--/operations/deployment.design.md) -- Helm charts, service configs
- [ADR-135: Troubleshooting Guide](adr-135-troubleshooting-guide.md) -- diagnostic trees for service failures referenced in the catalogue
