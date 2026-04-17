---
title: "ADR-132: Disaster Recovery Plan"
---

| | |
|---|---|
| **Date** | 2026-04-08 |
| **Status** | Accepted |
| **Category** | operations |


## Context

The Graph OLAP Platform runs on a GKE private cluster with Cloud SQL PostgreSQL for metadata, Google Cloud Storage for snapshots and exports, and ephemeral graph instances managed by the control plane. As the platform is handed off to HSBC, operational teams need a clear disaster recovery plan that defines:

1. **Recovery targets** -- RPO and RTO per component.
2. **Backup inventory** -- what is backed up, how often, where, and how long it is retained.
3. **Recovery procedures** -- step-by-step instructions for restoring each component.
4. **Data classification** -- which data is critical versus reconstructable.
5. **DR testing schedule** -- how often to validate recovery procedures.
6. **External dependencies** -- how recovery is affected by third-party services (Starburst Galaxy).

Additionally, Cloud SQL metadata includes user identifiers and session data that may constitute PII under HSBC's data classification policies. All backup and recovery procedures must account for encryption-at-rest requirements and role-based access control.

Without a formal DR plan:

- There is no agreed RPO/RTO and no way to measure recovery success.
- Operators may not know that graph instances are ephemeral and can be recreated from source data, leading to unnecessary panic during outages.
- Cloud SQL point-in-time recovery and GCS versioning are configured but undocumented from an operational perspective.
- HSBC compliance requires documented DR procedures for production systems.

---

## Decision

Create a disaster recovery runbook at `docs/operations/disaster-recovery.runbook.md` that provides:

1. **RPO/RTO targets** per component with a recovery priority table.
2. **Backup inventory** covering Cloud SQL automated backups, GCS bucket versioning, GKE etcd (managed by Google), and Helm/Terraform manifests in Git.
3. **Recovery procedures** for five scenarios: full platform rebuild, database restore, single service recovery, GCS data recovery, and graph instance recreation.
4. **Data classification** distinguishing critical data (PostgreSQL metadata), important data (GCS snapshots), and reconstructable data (graph instances).
5. **Failover procedures** if the primary GKE cluster becomes unavailable, with prerequisites for cross-region recovery (Terraform state replication, container image availability).
6. **DR testing schedule** with acceptance criteria and assigned ownership.
7. **Communication plan** for DR events.
8. **External dependency matrix** identifying third-party services (Starburst Galaxy) required for recovery and fallback behaviour when they are unavailable.
9. **Access control requirements** specifying which roles may execute recovery procedures and break-glass authorisation for emergencies.

RPO/RTO targets (5 minutes / 4 hours for a full platform rebuild) represent technical recovery time and exclude change-control approval overhead. The runbook documents this caveat and HSBC operations must account for Deliverance emergency change-request lead time when setting SLA commitments.

The runbook is self-contained for operational use but references design documents for architecture details.

---

## Consequences

**Positive:**

- HSBC operators have documented, testable recovery procedures.
- Clear RPO/RTO targets enable SLA commitments and compliance reporting.
- Data classification prevents wasted effort recovering reconstructable data.
- DR testing schedule ensures procedures remain valid as the platform evolves.

**Negative:**

- DR procedures must be updated when infrastructure changes (new services, different backup configurations).
- Estimated recovery times are based on current data volumes and may need recalibration as the platform scales.
- Full platform rebuild procedure is complex and requires access to Terraform state and container registry.
- Graph instance recreation depends on Starburst Galaxy availability; if Starburst is also down, the platform recovers in a degraded state (metadata and exports available, but no live graph queries).
- Cross-region failover requires Terraform state bucket and Artifact Registry to be replicated to a secondary region; without this, the failover procedure is not executable during a regional outage.
- Cloud SQL backup retention and GCS versioning settings must be verified against Terraform configuration to ensure documented RPO targets are achievable.

---

## Alternatives Considered

### 1. Multi-Region Active-Active Deployment

Run the platform simultaneously in two GCP regions with automatic failover.

**Rejected because:**

- The platform serves internal HSBC analysts, not external customers with strict uptime SLAs.
- Cloud SQL cross-region replication adds significant cost and operational complexity.
- Graph instances are ephemeral and can be recreated in minutes; multi-region replication for them is wasteful.
- The RPO/RTO targets (5 min / 4 hours) are achievable with single-region backups and a documented rebuild procedure.
- Can be revisited if usage patterns change or stricter SLAs are required.

### 2. Velero Cluster-Level Backups

Use Velero to take full Kubernetes cluster snapshots (namespaces, PVCs, configs).

**Rejected because:**

- GKE manages etcd backups automatically; Velero adds a redundant backup layer.
- The platform's persistent state lives in Cloud SQL and GCS, not in Kubernetes PVCs.
- Helm charts and Terraform are the source of truth for Kubernetes resources; restoring from Git is more reliable than restoring stale Velero snapshots.
- Velero adds another component to maintain and monitor.

### 3. Warm Standby in Secondary Region

Maintain a pre-provisioned GKE cluster and Cloud SQL replica in a secondary GCP region, kept idle until activation. Activation time would be under 30 minutes versus 2-4 hours for a cold rebuild.

**Rejected because:**

- The additional infrastructure cost (idle GKE cluster, cross-region Cloud SQL replica) is not justified for an internal analytics platform with a 4-hour RTO target.
- Cloud SQL cross-region replicas require careful management of promotion and failback procedures, adding operational complexity.
- The current single-region approach with documented rebuild procedures meets the agreed RPO/RTO targets.
- Can be revisited if the platform becomes business-critical with a sub-1-hour RTO requirement, or if cross-region failover is mandated by HSBC policy.

### 4. No Formal DR Plan (Ad-Hoc Recovery)

Rely on Cloud SQL automated backups and GCS versioning without documenting explicit procedures.

**Rejected because:**

- HSBC compliance requires documented DR procedures for production systems.
- Ad-hoc recovery under pressure leads to mistakes and longer downtime.
- Without documented RPO/RTO targets, there is no way to measure recovery success.
- Knowledge of the platform's recovery characteristics is currently held by the development team and must be transferred to HSBC operations.

---

## References

- [Observability Design](--/--/--/operations/observability.design.md) -- monitoring and alerting architecture
- [Deployment Design](--/--/--/operations/deployment.design.md) -- deployment architecture and infrastructure
- [Deployment and Rollback Procedures](--/--/--/operations/deployment-rollback-procedures.md) -- rollback strategy
- [Disaster Recovery Runbook](--/--/--/operations/disaster-recovery.runbook.md) -- the runbook itself
- [Platform Operations Architecture](--/--/--/architecture/platform-operations.md) -- DR targets, RTO/RPO
- [Security Operations Runbook](--/--/--/operations/security-operations.runbook.md) -- security procedures and access control
