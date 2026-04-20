---
title: "Change Control"
scope: hsbc
---

# Change Control

## What this handover covers

This document records **only the change-control mechanisms owned by this repository**. HSBC's enterprise change-control process (including any internal tooling, approval gates, segregation-of-duties enforcement, audit workflow, or production-gating policy) is HSBC-internal and is **out of scope for this handover** — HSBC's own standards apply when these repositories are onboarded.

## Repository-level change control (what we actually run)

Changes to the code and configuration in this repository are gated by two mechanisms:

1. **Pull-request review.** All changes land via pull requests; merges require review. Branch-protection rules are configured by the owning platform team.
2. **Architecture Decision Records (ADRs).** Architecturally significant decisions are captured as ADRs under `docs/process/adr/` and must be accepted before the corresponding implementation is merged. ADR-143 ("Documentation Impact") additionally requires each change to explicitly consider its documentation impact.

That is the full set of change-control mechanisms this repo defines. It is deliberately narrow.

## Build and deploy pipeline

- Each service repo ships a `Jenkinsfile` that delegates to an HSBC-internal shared Jenkins library (`@Library('container-shared-library@311')`). Technical build/deploy steps are executed by that library.
- Promotion between environments, production gating, and any out-of-band approvals are handled by **HSBC's internal change-control process**, which is not described here.

## What this handover does NOT define

The following are HSBC-internal and are intentionally **not** specified here:

- HSBC's internal change-control tooling, workflow, or approval matrix
- Change categories, freeze windows, or scheduling rules
- RACI, escalation chains, or segregation-of-duties enforcement
- Audit-evidence formats or retention requirements
- SOX / regulatory compliance mappings

When these repositories are onboarded, HSBC's existing standards for the above apply; nothing in this repo overrides or substitutes for them.

## Related ADRs

- **ADR-143** — Documentation accuracy & impact review (the main in-repo change-control gate for docs)
- **ADR-128** — Operational documentation strategy (separates demo-scope docs from HSBC-scope handover docs)
