---
title: "ADR-130: Incident Response Runbook"
---

| | |
|---|---|
| **Date** | 2026-04-08 |
| **Status** | Accepted |
| **Category** | operations |


## Context

The Graph OLAP Platform runs on a private GKE cluster with multiple interdependent services (control plane, export workers, graph wrappers, JupyterHub) and external dependencies (Cloud SQL, GCS, Starburst Galaxy). When incidents occur, responders need a structured process for triage, investigation, and resolution -- particularly during the handoff period when institutional knowledge of the platform is still being built within HSBC.

Without a formal incident response runbook, responders must diagnose issues ad hoc, leading to longer resolution times and inconsistent incident handling. The platform's architecture creates specific failure modes (stuck graph instances, export worker backlogs, database connection exhaustion) that require targeted playbooks rather than generic Kubernetes troubleshooting.

HSBC's operational model requires defined severity levels, escalation paths, and response SLAs that align with their existing ITSM processes.

---

## Decision

Create an incident response runbook (`docs/operations/incident-response.runbook.md`) that covers:

1. **Severity classification** -- P1 through P4 with clear criteria for each level
2. **Escalation matrix** -- contacts and escalation paths per severity
3. **Response SLAs** -- time to acknowledge and time to resolve per severity
4. **Incident workflow** -- Detect, Triage, Investigate, Resolve, Post-mortem
5. **Common incident playbooks** -- step-by-step procedures for nine failure scenarios derived from the platform's risk assessment and alert rules: control plane unresponsive, database connection exhaustion, export worker backlog, stuck graph instances, JupyterHub pod failures, GCS permission errors, high wrapper memory usage, unauthorized data access, and data leakage via snapshots
6. **Post-incident process** -- blameless post-mortem template and action item tracking
7. **Communication templates** -- stakeholder notification formats

Each playbook includes numbered diagnostic and resolution steps so that a responder with Kubernetes experience but no Graph OLAP-specific knowledge can follow them during an incident.

---

## Consequences

**Positive:**

- Reduces mean time to resolution by providing pre-built diagnostic steps
- Ensures consistent incident handling across the ops team
- Aligns with HSBC ITSM severity and escalation standards
- Enables effective incident response during the knowledge transfer period
- Provides post-mortem structure for continuous improvement

**Negative:**

- Playbooks may not cover every possible failure scenario
- Escalation contacts must be updated as team composition changes
- HSBC-specific ITSM tool integration (ServiceNow, etc.) is not covered and must be added by the receiving team

---

## Alternatives Considered

### 1. Rely on generic Kubernetes troubleshooting guides

We considered pointing the ops team to standard Kubernetes runbooks and GKE documentation instead of creating platform-specific playbooks. This was rejected because:

- The Graph OLAP Platform has domain-specific failure modes (stuck graph instances, export backlogs, staleness detection) that generic Kubernetes docs do not cover
- Responders need to interact with the control plane API (not just kubectl) to diagnose and resolve many issues
- Generic guides would not include the correct escalation paths or SLA targets

### 2. Combine operations manual and incident response into one document

We considered a single unified operations document covering both routine operations and incident response. This was rejected because:

- The audiences overlap but usage patterns differ: the operations manual is used proactively during shifts, while the runbook is used reactively during incidents
- Keeping them separate allows the runbook to be printed or bookmarked independently for quick access during P1 incidents
- Different review cadences: the operations manual changes when platform features change, while the runbook changes when new failure modes are discovered

### 3. Automated incident response via PagerDuty/Opsgenie integrations

We considered building automated remediation (auto-restart, auto-scale) triggered by alerts. This was rejected for the initial handoff because:

- HSBC's SOX change control process requires human approval for production changes
- Automated remediation requires higher confidence in the alert accuracy than we have at handoff
- The runbook provides the foundation; automation can be layered on top once the ops team has operational experience with the platform

---

## References

- [Observability Design](--/--/--/operations/observability.design.md) -- alert rules, severity levels, dashboards
- [Platform Operations Architecture](--/--/--/architecture/platform-operations.md) -- SLOs, disaster recovery, risk assessment
- [ADR-129: Platform Operations Manual](adr-129-platform-operations-manual.md) -- companion day-to-day operations guide
- [Change Control Framework](--/--/--/governance/change-control-framework.governance.md) -- Deliverance SOX compliance framework
- [ADR-131: Monitoring and Alerting Runbook](adr-131-monitoring-alerting-runbook.md) -- alert response procedures referenced by the runbook's alert-to-playbook mapping
