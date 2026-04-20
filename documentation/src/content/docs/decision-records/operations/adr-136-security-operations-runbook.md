---
title: "ADR-136: Security Operations Runbook"
---

| | |
|---|---|
| **Date** | 2026-04-08 |
| **Status** | Accepted |
| **Category** | operations |


## Context

The Graph OLAP Platform is being handed off to HSBC operational teams. The platform's security posture is documented across several files -- the container security audit, security improvements summary, and container supply chain governance -- but there is no single operational runbook that tells an operator *how* to perform day-to-day security operations.

Without a security operations runbook:

1. **Secret rotation risk** -- operators may not know which secrets exist, where they are stored, or how to rotate them without downtime.
2. **Incident response gaps** -- there is no documented procedure for responding to a compromised credential or a detected vulnerability.
3. **Compliance drift** -- periodic security tasks (access reviews, vulnerability scans, certificate renewals) are not tracked, leading to audit findings.
4. **HSBC onboarding gap** -- new security operators have no reference for the platform's specific secret inventory, access control model, or compliance requirements.

The platform uses Google Secret Manager for secrets, Workload Identity for GCP access, and IP whitelisting for ingress access control (ADR-112 removed Auth0 and replaced it with nginx ingress IP whitelisting and X-Username header identity). Container supply-chain governance (image scanning, runtime protection, artifact repository) is an HSBC-owned pipeline — the specific tooling chosen by HSBC is out of scope for this runbook. These operational details need to be consolidated into a single runbook.

> **Note:** ADR-112 removed Auth0 and all OIDC infrastructure from the platform. The current access control model is IP whitelisting at the ingress layer with application-level identity via X-Username headers. HSBC production may require integration with enterprise IAM (e.g., CyberArk, Active Directory); the access control section of the runbook must be updated when the HSBC authentication mechanism is finalised.

The existing documentation landscape:

- **Container security audit** assesses the current posture and recommends improvements but does not provide operational procedures.
- **Security improvements summary** documents what controls were implemented but not how to operate them day-to-day.
- **Container supply chain governance** defines the image acquisition process but not secret rotation, access reviews, or compliance evidence collection.
- **Incident response runbook** (ADR-130) covers incident handling but not routine security operations.

---

## Decision

Create a security operations runbook at `docs/operations/security-operations.runbook.md` that provides:

1. **Secret inventory and rotation** -- a complete inventory of all secrets (database credentials, API keys, GCS service accounts), their storage locations, and step-by-step rotation procedures for each type, including emergency rotation for compromised credentials.
2. **Certificate management** -- TLS certificate inventory, renewal procedures, and emergency re-issuance steps.
3. **Vulnerability management** -- container image scanning schedule, CVSS-based triage process, patching procedures, and SBOM generation.
4. **Access control operations** -- ingress IP whitelist management, X-Username identity model, service account management, and periodic access review procedures. (To be extended when HSBC production authentication mechanism is finalised.)
5. **Security monitoring** -- suspicious activity indicators, Cloud Logging queries for security events, and indicators of compromise.
6. **Compliance operations** -- audit preparation, Deliverance change-control integration, and evidence-collection procedures (specific regulatory frameworks are HSBC-owned and referenced rather than asserted).
7. **Hardening checklist** -- periodic verification of security controls across the cluster.

The runbook references the container security audit and supply chain governance documents for architectural details. It does not duplicate security architecture or scanning tool configuration. For security incidents (compromised credentials, detected intrusions), the runbook provides immediate containment steps and then hands off to the [Incident Response Runbook](adr-130-incident-response-runbook.md) for formal incident management -- the boundary is: ADR-136 owns containment and routine operations, ADR-130 owns the incident lifecycle.

Key design choices within the runbook:

- **Secret rotation is documented per-secret-type** rather than as a generic procedure, because each secret has different tooling (gcloud, Starburst Galaxy console) and different downstream restart requirements.
- **Emergency rotation is a separate section** from routine rotation, with an emphasis on speed over caution.
- **The hardening checklist is designed for monthly execution** with kubectl verification commands, so that drift can be detected before an audit rather than during one.
- **Compliance evidence collection** maps each audit requirement (as defined by HSBC's central compliance function) to a specific data source and collection command.
- **Rotation procedures include rollback steps** so that operators can recover if a service fails to restart after credential rotation (re-enable previous secret version, then investigate).
- **Enterprise-wide regulatory requirements** (PRA operational resilience, DORA ICT risk management, third-party risk registers) are owned by HSBC's central compliance function and are not duplicated in this platform-specific runbook.

---

## Consequences

**Positive:**

- Operators have a single reference for all security operational tasks.
- Secret rotation procedures reduce the risk of downtime during credential changes.
- Compliance tasks are explicitly listed, reducing the chance of audit findings.
- HSBC security teams can onboard without relying on the original development team.

**Negative:**

- Runbook must be updated when new secrets, services, or compliance requirements are added. ADR-128 defines the maintenance plan: annual full review, update triggers on infrastructure changes, and a 90-day hypercare period post-handoff.
- The access control section documents the current IP whitelisting model (ADR-112). When HSBC production authentication is finalised (enterprise IAM, OIDC, or other), the access control procedures, user provisioning/deprovisioning, and periodic access review sections must be rewritten.
- Some procedures (image-acquisition approvals, Deliverance change requests, SOC escalations) depend on HSBC-internal systems and workflows not controlled by the platform team; the specific HSBC tooling used for those workflows is HSBC-owned and not asserted by this runbook.

---

## Alternatives Considered

**Rely on HSBC's existing security runbook templates.** Rejected because this platform has platform-specific secrets, service accounts, and tooling (Workload Identity, cosign, IP whitelisting) that generic HSBC templates would not cover. A platform-specific runbook is needed alongside any organisation-wide procedures.

**Automate all security operations and skip the runbook.** Rejected because while automation is implemented where possible (CI/CD scanning, Dependabot, automatic certificate renewal), many operations still require human judgment (access reviews, vulnerability triage, incident response). The runbook captures the human procedures.

---

## References

- [ADR-112: Remove Auth0 and Replace with IP Whitelisting](--/security/adr-112-remove-auth0-replace-with-ip-whitelisting.md) -- current access control model
- [ADR-128: Operational Documentation Strategy](adr-128-operational-documentation-strategy.md) -- parent strategy, maintenance plan, authoring standards
- [ADR-130: Incident Response Runbook](adr-130-incident-response-runbook.md) -- incident lifecycle management (ADR-136 hands off to ADR-130 after containment)
- [Container Security Audit](--/--/--/security/container-security-audit.md) -- security posture assessment
- [Security Improvements Summary](--/--/--/security/security-improvements-summary.md) -- implemented security controls
- [Container Supply Chain Governance](--/--/--/governance/container-supply-chain.governance.md) -- image acquisition process
- [Observability Design](--/--/--/operations/observability.design.md) -- logging and monitoring architecture
- [Security Operations Runbook](--/--/--/operations/security-operations.runbook.md) -- the runbook itself
- [Deployment Design](--/--/--/operations/deployment.design.md) -- Secret management, access controls
- [Change Control Framework](--/--/--/governance/change-control-framework.governance.md) -- Deliverance change-control framework
- [Platform Operations Architecture](--/--/--/architecture/platform-operations.md) -- Security controls matrix
