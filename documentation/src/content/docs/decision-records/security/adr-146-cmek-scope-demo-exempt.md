---
title: "ADR-146: CMEK Scope — Demo Cluster Exempt, HSBC Environments Only"
---

| | |
|---|---|
| **Date** | 2026-04-17 |
| **Status** | Accepted |
| **Category** | security |


## Context

[ADR-032: Architectural Review Gaps for Banking Context](--/process/adr-032-architectural-review-gaps-for-banking-context.md) identified "Missing key management architecture (KMS/CMEK)" as a P1 security gap that must be addressed before a banking production deployment. The HSBC operations runbooks (ADR-128 series) and `docs/operations/security-operations.runbook.md` presume that all data at rest is encrypted with customer-managed KMS keys (CMEK).

### Current State (verified 2026-04-17)

The running `gcp-london-demo` environment does **not** implement CMEK:

- No `google_kms_key_ring` or `google_kms_crypto_key` resources exist anywhere under `infrastructure/terraform/` (verified via `grep -r 'google_kms' infrastructure/terraform/`).
- `infrastructure/terraform/modules/gcs/main.tf` does expose an *optional* `kms_key_name` variable (lines 44-50) which wires `default_kms_key_name` into `google_storage_bucket.encryption`, but it is never set by any environment: `environments/gcp-london-demo/main.tf` declares the `google_storage_bucket.snapshots` resource inline (lines 442-465) without any `encryption` block.
- `google_sql_database_instance.main` (lines 393-418) uses default Google-managed encryption; there is no `encryption_key_name` argument.
- The `modules/secret-manager/` module stores Starburst credentials using default Google-managed encryption.

In short: all data at rest (GCS snapshots, Cloud SQL PostgreSQL, Secret Manager payloads) uses Google-managed encryption keys in the demo environment. The CMEK mandate from ADR-032 is therefore **unimplemented** in the only running cluster.

### HSBC Isolation Pattern

[ADR-128: Operational Documentation Strategy](--/operations/adr-128-operational-documentation-strategy.md) establishes that operational guarantees (audit-trail capture via Deliverance change control, segregation of duties, raw-kubectl deployment model, `graph-olap-platform/staging/production` namespace targets) apply to the **HSBC handoff artefact** — a separate deliverable built via `make hsbc` into `build/hsbc/` — and not to the Sparkling Ideas demo cluster, which runs under the internal demo GCP project in a different region. The demo cluster exists for functional validation, notebook E2E testing, and stakeholder demonstrations; it holds no real banking data, is IP-whitelisted to Sparkling Ideas office IPs only ([ADR-112](-/adr-112-remove-auth0-replace-with-ip-whitelisting.md)), and its GCS lifecycle rule deletes all contents after 7 days.

---

## Decision

**Rescind the CMEK mandate for the `gcp-london-demo` environment.** CMEK applies only to HSBC-target environments.

1. The `gcp-london-demo` Terraform stack will continue to rely on Google-managed encryption keys for Cloud SQL, GCS, and Secret Manager. This decision is explicit, not an oversight.
2. The CMEK implementation obligation (per ADR-032) is transferred to the HSBC handoff package. HSBC's own platform team will provision the KMS keyring, crypto keys, IAM bindings, and rotation policy inside their `graph-olap-platform-{staging,production}` projects, using their bank-standard key hierarchy. Our handoff delivers the *Terraform module plumbing* (already present in `modules/gcs/` via `var.kms_key_name`) but not the key material.
3. The HSBC `security-operations.runbook.md` continues to reference CMEK procedures; those procedures apply to HSBC environments only and will be validated by HSBC during their deploy.
4. No CMEK terraform will be added to `environments/staging/main.tf` or `environments/production/main.tf` in this repository either — those environments are demo infrastructure targets not used for HSBC handoff and follow the same "demo" classification.

### Scope Matrix

| Environment | Location | CMEK Required | Responsibility |
|-------------|----------|---------------|----------------|
| `gcp-london-demo` | This repo, Sparkling Ideas GCP project | No | Sparkling Ideas (exempt — demo) |
| HSBC `graph-olap-platform-staging` | HSBC GCP tenant | Yes | HSBC platform team |
| HSBC `graph-olap-platform-production` | HSBC GCP tenant | Yes | HSBC platform team |

---

## Consequences

**Positive:**

- No further work or spend on the demo cluster: CMEK adds ~$1-3/month per key plus operational complexity that provides zero security benefit for a cluster containing no real data and accessible only from whitelisted office IPs.
- Clean separation of concerns: Sparkling Ideas owns the demo, HSBC owns HSBC infrastructure. Matches the isolation pattern already codified by ADR-128.
- Removes a documentation-vs-reality drift that ADR-149 flagged as Tier-A item 10.
- HSBC retains full control over key management, rotation, HSM selection, and audit integration — which they would almost certainly demand anyway even if we pre-provisioned keys.

**Negative:**

- The runbooks at `docs/operations/security-operations.runbook.md` (HSBC-facing) describe CMEK procedures that cannot be rehearsed against the demo cluster. Mitigated by the HSBC-only scope note already present in those runbooks (see ADR-128 feedback "ADR-128+ HSBC only").
- ADR-032's P1 "key management architecture" item remains unsatisfied for our own environments and must be re-raised if the demo cluster is ever repurposed to hold customer data.
- Any audit that samples "all ADRs mandating CMEK" against "all running clusters" will surface a gap; this ADR is the written justification for that gap.

---

## Documentation Impact

| Source file | Change required |
|-------------|----------------|
| `docs/operations/security-operations.runbook.md` | Add a scope note at the top stating the CMEK section applies to HSBC staging/production only; `gcp-london-demo` is exempt per ADR-146. |
| `docs/architecture/security.design.md` (if it references CMEK as implemented) | Update to cite ADR-146 and distinguish "mandated for HSBC" vs "not implemented in demo". |
| `docs/process/decision.log.md` | No change — this ADR is the resolution. |

Files that do **not** need updating: `infrastructure/terraform/environments/gcp-london-demo/main.tf` (no change — current state is the target state); `modules/gcs/variables.tf` (the optional `kms_key_name` plumbing stays as-is for HSBC use).

---

## Alternatives Considered

1. **Implement CMEK in the demo cluster.** Rejected: adds cost and operational overhead for a cluster that contains no banking data, is IP-whitelisted, and auto-expires all GCS objects after 7 days. Would require provisioning a KMS keyring, crypto keys for GCS/Cloud SQL/Secret Manager, IAM bindings for each service account, and rotation policy — ~1 week of work for zero residual risk reduction.
2. **Defer with a target date ("will implement before HSBC handoff").** Rejected: there is no mechanism by which the demo cluster could be promoted to HSBC production — the handoff is a separate Terraform stack deployed by HSBC into their own GCP tenant. "Deferred" would be a standing debt with no honest closure path.
3. **Supersede ADR-032's CMEK clause.** Rejected: ADR-032 remains correct for HSBC environments. We are not rejecting the mandate, only scoping it.

---

## References

- [ADR-032: Architectural Review Gaps for Banking Context](--/process/adr-032-architectural-review-gaps-for-banking-context.md)
- [ADR-112: Remove Auth0 and All Authentication, Replace with IP Whitelisting](-/adr-112-remove-auth0-replace-with-ip-whitelisting.md)
- [ADR-128: Operational Documentation Strategy for HSBC Handoff](--/operations/adr-128-operational-documentation-strategy.md)
- [ADR-149: Implementation-vs-Documentation Drift Remediation](--/process/adr-149-implementation-vs-documentation-drift-remediation.md)
- `infrastructure/terraform/environments/gcp-london-demo/main.tf` — demo environment with no KMS resources
- `infrastructure/terraform/modules/gcs/main.tf` lines 44-50 — optional `kms_key_name` plumbing (unused in any environment)
