---
title: "ADR-135: Troubleshooting Guide"
---

| | |
|---|---|
| **Date** | 2026-04-08 |
| **Status** | Accepted |
| **Category** | operations |


## Context

The Graph OLAP Platform is being handed off to HSBC operational teams. While the observability stack is defined in [observability.design.md](--/--/--/operations/observability.design.md) and the [Monitoring and Alerting Runbook](--/--/--/operations/monitoring-alerting.runbook.md) covers alert response, there is no consolidated guide for systematic troubleshooting of the platform's services.

Without a troubleshooting guide:

1. **Inconsistent diagnosis** -- engineers follow ad-hoc investigation paths, missing common root causes.
2. **Repeated failures** -- known issues (asyncpg SSL errors per [ADR-058](--/infrastructure/adr-058-asyncpg-ssl-connection-syntax.md), wrapper OOM, GCS permission misconfigurations) are rediscovered rather than looked up.
3. **Slow resolution** -- responders must read source code and design documents to understand failure modes.
4. **HSBC onboarding gap** -- new operators cannot self-serve on common problems without access to the original development team.

The platform has several known failure patterns documented across ADRs and observed in production. These need to be consolidated into a single, symptom-indexed reference. Existing documentation covers adjacent concerns but not symptom-based diagnosis:

- [Observability design](--/--/--/operations/observability.design.md) defines *what* is monitored (metrics, log format, alert rules) but not how to investigate failures.
- [Monitoring and Alerting Runbook](--/--/--/operations/monitoring-alerting.runbook.md) tells operators what to do when an alert fires but does not cover symptoms that appear without an alert (e.g., user reports, gradual degradation).
- [E2E Tests Runbook](--/--/--/operations/e2e-tests.runbook.md) covers test-specific troubleshooting but not general production issues.
- Individual ADRs document decisions but are not indexed by symptom.

---

## Decision

Create a troubleshooting guide at `docs/operations/troubleshooting.runbook.md` that provides:

1. **Triage routing note** -- a short preamble directing operators: if you arrived from a fired alert, start with the [Monitoring and Alerting Runbook](--/--/--/operations/monitoring-alerting.runbook.md); if you are investigating a symptom without a matching alert (user report, gradual degradation), continue here.
2. **Diagnostic methodology** -- a systematic four-step approach (health check, logs, resources, dependencies) that all operators follow before diving into symptom-specific sections.
3. **Quick health check commands** -- kubectl and curl commands for rapid cluster and service assessment.
4. **Symptom-based troubleshooting** -- each entry follows a consistent four-part template (symptoms, possible causes ranked by likelihood, numbered diagnostic steps, numbered resolution steps). Resolution steps that modify production state include an inline Deliverance change-request requirement. Each entry ends with an escalation step: if unresolved after a stated time, escalate to a named team via the [Incident Response Runbook](--/--/--/operations/incident-response.runbook.md). Covers API errors (5xx, 4xx, latency), graph instance lifecycle issues, export pipeline failures, JupyterHub and notebook problems, wrapper pod failures, database issues (including asyncpg SSL per [ADR-058](--/infrastructure/adr-058-asyncpg-ssl-connection-syntax.md)), GCS permission errors, TLS certificate expiry, secret rotation failures, and infrastructure pressure.
5. **Log analysis guide** -- how to read structured JSON logs, key fields for correlation (trace_id, user_id, component), and Cloud Logging filter expressions.
6. **Database troubleshooting** -- connection pool exhaustion, slow queries, migration failures.
7. **Network troubleshooting** -- DNS resolution, service discovery, ingress configuration.

The guide references the [observability design document](--/--/--/operations/observability.design.md) for metric definitions and log format, and the [Service Catalogue (ADR-134)](adr-134-service-catalogue.md) for service inventory, ports, and health endpoints. It does not duplicate metric schemas or Terraform configuration.

When the guide exceeds 1200 lines, symptom entries should be split into per-domain files (e.g., `troubleshooting-database.runbook.md`) with a short index remaining at the current path.

---

## Consequences

**Positive:**

- Operators have a single symptom-indexed reference for diagnosing production issues.
- Consistent diagnostic methodology reduces mean time to resolution.
- Known failure patterns are captured permanently rather than as tribal knowledge.
- HSBC operators can self-serve on common problems from the first week of operations.
- Explicit escalation steps in every entry prevent L1 operators from spending hours before seeking help.
- Inline Deliverance callouts on destructive resolution steps enforce HSBC change-control compliance at the point of action, not just in a preamble.

**Negative:**

- Guide must be updated when new failure modes are discovered or services change. Every post-incident review that identifies a novel failure mode should produce a new symptom entry; the maintenance cadence defined in [ADR-128](adr-128-operational-documentation-strategy.md) (review triggers, annual review, 90-day hypercare) governs ongoing updates.
- Kubectl commands may need adjustment if namespace or label conventions change.
- Some troubleshooting steps reference internal GCP resources (Cloud SQL, GCS buckets) whose names are environment-specific.
- At 17 symptom entries the guide already approaches the 800-line document target; further growth will require splitting into per-domain files (see Decision section).

---

## Alternatives Considered

**Embed troubleshooting in each service's README.** Rejected because operators need a single entry point indexed by symptom, not by service. A user-reported "slow API" symptom may involve the control plane, database, or wrapper pod -- the troubleshooting guide must span services.

**Extend the Monitoring and Alerting Runbook (ADR-131) with deeper diagnostic trees.** Rejected because ADR-131 is structured by alert name, not by symptom. Many troubleshooting scenarios begin without an alert (user reports, gradual degradation, post-incident investigation). Merging both audiences into one document would exceed the line target and conflate two different entry points: "an alert fired" vs. "something seems wrong." The triage routing note at the top of each runbook makes the boundary explicit.

**Use a wiki or Confluence page.** Rejected because the guide should live alongside the code and be versioned with the same Git workflow. Wikis drift from the actual system faster than in-repo documentation.

---

## References

- [ADR-128: Operational Documentation Strategy](adr-128-operational-documentation-strategy.md) -- parent strategy governing all 8 operational documents, including maintenance plan
- [ADR-130: Incident Response Runbook](adr-130-incident-response-runbook.md) -- escalation procedures referenced by symptom entries
- [ADR-131: Monitoring and Alerting Runbook](adr-131-monitoring-alerting-runbook.md) -- alert-by-alert response; handles fired alerts (this guide handles symptoms without a matching alert)
- [ADR-134: Service Catalogue](adr-134-service-catalogue.md) -- service inventory, ports, health endpoints, dependency map
- [ADR-058: asyncpg SSL Connection Syntax](--/infrastructure/adr-058-asyncpg-ssl-connection-syntax.md) -- asyncpg SSL failure pattern referenced in database troubleshooting
- [Observability Design](--/--/--/operations/observability.design.md) -- metrics, logging, alerting architecture
- [Monitoring and Alerting Runbook](--/--/--/operations/monitoring-alerting.runbook.md) -- the runbook itself
- [E2E Tests Runbook](--/--/--/operations/e2e-tests.runbook.md) -- test execution and cleanup
- [Troubleshooting Runbook](--/--/--/operations/troubleshooting.runbook.md) -- the runbook produced by this ADR
