---
title: "ADR-147: Binary Authorization Scope — Demo Cluster Exempt, HSBC Environments Only"
---

| | |
|---|---|
| **Date** | 2026-04-17 |
| **Status** | Accepted |
| **Category** | security |


## Context

The HSBC security operations runbook (`docs/operations/security-operations.runbook.md`, produced per ADR-128 and ADR-136) specifies that Binary Authorization (BinAuthZ) policies must be enforced (`evaluation_mode = "REQUIRE_ATTESTATION"`, `enforcement_mode = "ENFORCED_BLOCK_AND_AUDIT_LOG"`) on all GKE clusters so that only signed/attested container images can be admitted. [ADR-033: Comprehensive Container Security Improvements](-/adr-033-comprehensive-container-security-improvements.md) reinforces this as part of the supply-chain hardening posture.

### Current State (verified 2026-04-17)

A reusable Binary Authorization module **does** exist at `infrastructure/terraform/modules/binary-authorization/` with:

- `google_binary_authorization_policy.policy` (main.tf lines 19-60) — parameterised via `var.enforcement_mode`.
- `google_binary_authorization_attestor.cosign` — cosign-based signer.

This module is wired up in:

- `infrastructure/terraform/environments/staging/main.tf`
- `infrastructure/terraform/environments/production/main.tf`

However, the only environment that is actually deployed and running — `infrastructure/terraform/environments/gcp-london-demo/main.tf` — contains **no** `binary_authorization` module block (verified via `grep -in 'binary_authorization\|binauthz' infrastructure/terraform/environments/gcp-london-demo/main.tf` → 0 matches). The `google_container_cluster.main` resource (lines 261-320) has no `binary_authorization` block, so the cluster accepts any image from any registry. In practice the cluster's node service accounts have `roles/storage.objectAdmin` on the Artifact Registry bucket only, which narrows the attack surface via IAM, but does not satisfy the runbook mandate.

The net effect: the "Binary Authorization enforced" claim in the runbook is not actually true for any cluster our team currently operates. The mandate is implementation-ready (module exists) but unwired on the demo.

### HSBC Isolation Pattern

Per [ADR-128: Operational Documentation Strategy](--/operations/adr-128-operational-documentation-strategy.md) and the "ADR-128+ HSBC only" feedback in project memory, operational guarantees apply to the HSBC handoff artefact (`build/hsbc/`) deployed by HSBC's own platform team into `graph-olap-platform-{staging,production}`. The demo cluster under `hsbc-graph` GCP project is Sparkling Ideas infrastructure for functional validation and stakeholder demos. BinAuthZ provides a supply-chain guarantee appropriate for regulated banking production, not for a demo cluster whose image source is a single team-operated Artifact Registry with a 2-person commit audience.

---

## Decision

**Rescind the Binary Authorization enforcement mandate for the `gcp-london-demo` environment.** BinAuthZ applies only to HSBC-target environments.

1. The `gcp-london-demo/main.tf` Terraform will remain without a `module "binary_authorization"` block. The running GKE cluster will continue to accept any image pulled from its own Artifact Registry.
2. The `modules/binary-authorization/` module stays in the codebase — it is still used by `environments/staging/main.tf` and `environments/production/main.tf`, which are Sparkling-Ideas-internal targets that may be exercised for integration testing but are not currently deployed (see ADR-128 feedback: those environments are HSBC-pattern demos, not production).
3. The HSBC handoff package (`build/hsbc/`) continues to carry the binary-authorization module and references it from HSBC-targeted Terraform fragments. HSBC's platform team is responsible for: enforcing the policy on their clusters, supplying their own attestors (HSBC internal cosign CA or Binary Authorization vulnerability attestor), and running the Cloud Build / Jenkins signer step that produces attestations at image push time.
4. The runbook's BinAuthZ section continues to be HSBC-facing only, consistent with ADR-128.

### Scope Matrix

| Environment | BinAuthZ Module Wired | Enforcement Mode | Responsibility |
|-------------|----------------------|------------------|----------------|
| `gcp-london-demo` | No | N/A (not deployed) | Sparkling Ideas (exempt — demo) |
| Local OrbStack | N/A (not GKE) | N/A | Sparkling Ideas |
| Sparkling Ideas `staging` (if deployed) | Yes (module wired) | `DRYRUN_AUDIT_LOG_ONLY` | Sparkling Ideas |
| HSBC `graph-olap-platform-staging` | Yes (HSBC to wire) | `DRYRUN_AUDIT_LOG_ONLY` then `ENFORCED_BLOCK_AND_AUDIT_LOG` | HSBC platform team |
| HSBC `graph-olap-platform-production` | Yes (HSBC to wire) | `ENFORCED_BLOCK_AND_AUDIT_LOG` | HSBC platform team |

---

## Consequences

**Positive:**

- Demo cluster deploy remains simple and fast: no attestor infrastructure, no signer step in the image build pipeline, no "policy blocked deployment" incidents during `make push TARGET=gke-london`.
- Clean ownership boundary matching ADR-128: we ship the Terraform module, HSBC wires and operates the policy.
- Removes the ADR-149 Tier-A.10 drift (runbook mandates policy; demo doesn't have it).
- Preserves the module as a reusable, ready-to-wire building block for HSBC.

**Negative:**

- The demo cluster has no supply-chain guarantee — a compromised Artifact Registry or a careless `docker push` would be admitted. Mitigated by: (a) single-team push audience, (b) IP whitelist on ingress, (c) no real banking data at rest, (d) IAM already restricts registry push to a handful of service accounts.
- The runbook's BinAuthZ procedures cannot be rehearsed against the running demo cluster. This is intentional and consistent with ADR-128's scope.
- If HSBC asks for a demo of BinAuthZ in action, we must stand up a one-off enforcing cluster; the module makes that a <1-day exercise.

---

## Documentation Impact

| Source file | Change required |
|-------------|----------------|
| `docs/operations/security-operations.runbook.md` | Add scope note: BinAuthZ section applies to HSBC staging/production only; `gcp-london-demo` is exempt per ADR-147. |
| `docs/architecture/security.design.md` (if it claims BinAuthZ is implemented in demo) | Update to cite ADR-147: module exists, demo not wired, HSBC wires at deploy time. |
| `docs/operations/deployment.design.md` | If it describes a "build-then-attest" pipeline as mandatory, add a note that attestation is HSBC-only; demo pipeline has no signer step. |

Files that do **not** need updating: `infrastructure/terraform/environments/gcp-london-demo/main.tf` (no change — current state is the target state); `infrastructure/terraform/modules/binary-authorization/` (stays unchanged, still used by HSBC handoff).

---

## Alternatives Considered

1. **Wire up BinAuthZ in the demo cluster in `DRYRUN_AUDIT_LOG_ONLY` mode.** Rejected: would require standing up at least one attestor, teaching the image build pipeline to produce attestations, and managing the signer key — several days of work for audit-log output nobody reads.
2. **Wire up BinAuthZ in the demo cluster in `ENFORCED_BLOCK_AND_AUDIT_LOG` mode.** Rejected: would guarantee that the next "hotfix via `make push`" deploy blocks at the admission webhook unless we also solve signed image distribution, which is not a demo-cluster problem.
3. **Defer with a target date.** Rejected: same reasoning as ADR-146 — the demo cluster is never going to become HSBC production, so there is no natural closure date. An open-ended deferral is just a soft version of this rescission.
4. **Supersede ADR-033 / runbook mandate.** Rejected: the mandate remains correct for HSBC environments. We are scoping it, not overturning it.

---

## References

- [ADR-033: Comprehensive Container Security Improvements](-/adr-033-comprehensive-container-security-improvements.md)
- [ADR-128: Operational Documentation Strategy for HSBC Handoff](--/operations/adr-128-operational-documentation-strategy.md)
- [ADR-136: Security Operations Runbook](--/operations/adr-136-security-operations-runbook.md)
- [ADR-149: Implementation-vs-Documentation Drift Remediation](--/process/adr-149-implementation-vs-documentation-drift-remediation.md)
- [ADR-146: CMEK Scope — Demo Cluster Exempt, HSBC Environments Only](-/adr-146-cmek-scope-demo-exempt.md) — parallel scoping decision
- `infrastructure/terraform/modules/binary-authorization/main.tf` — the (ready but unwired in demo) module
- `infrastructure/terraform/environments/gcp-london-demo/main.tf` — demo environment without BinAuthZ
- `infrastructure/terraform/environments/staging/main.tf`, `environments/production/main.tf` — where the module is wired
