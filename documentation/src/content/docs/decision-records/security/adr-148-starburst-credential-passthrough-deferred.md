---
title: "ADR-148: Starburst Credential Pass-Through — Deferred to HSBC Handoff, Supersedes ADR-098"
---

| | |
|---|---|
| **Date** | 2026-04-17 |
| **Status** | Accepted |
| **Category** | security |
| **Supersedes** | [ADR-098: Starburst Credential Pass-Through for Export Worker](-/adr-098-starburst-credential-passthrough.md) (status was `Proposed`, never accepted) |


## Context

[ADR-098: Starburst Credential Pass-Through for Export Worker](-/adr-098-starburst-credential-passthrough.md) (Proposed, 2026-03-14) described an end-to-end credential flow in which the control-plane would fetch per-user Starburst credentials and roles from GCP Secret Manager's `genai-secret` JSON blob, pass them through to the export worker in `ExportJob` metadata, and the worker would authenticate per-job with the correct LDAP service account plus `SET ROLE`. That design targets HSBC's production Starburst deployment (LDAP Basic Auth + role-scoped authorization).

### Current State (verified 2026-04-17)

The export worker **does not** implement ADR-098. Evidence:

- `infrastructure/terraform/environments/gcp-london-demo/main.tf` lines 1496-1506: `kubernetes_secret.export_worker_secrets` is populated with a single static `STARBURST_PASSWORD` pulled from the Starburst Galaxy `data.kubernetes_secret.starburst_credentials` at apply time.
- The umbrella chart values at lines 865-874 wire this secret into the worker as `envFrom.secretRef`, making `STARBURST_PASSWORD` a process-scope environment variable for the lifetime of the pod.
- The worker has no Secret Manager client code path and no `SET ROLE` call — it uses the single hardcoded user `graph-olap-e2e@hsbcgraph.galaxy.starburst.io` (line 880) for every job regardless of submitter.
- No per-user credential is stored anywhere in the `ExportJob` payload (see control-plane schema `.swarm/schema.sql` → `export_jobs` table).

The demo cluster connects to Starburst **Galaxy** (a cloud SaaS), not HSBC's on-prem Starburst. Galaxy uses a single service-account token model ("graph-olap-e2e" user) — it does not expose the LDAP + `SET ROLE` pattern ADR-098 targets. In other words, the ADR-098 pattern has no functional target in the demo environment: there is no place to exercise it.

### Why ADR-098 Was Never Implemented

1. **No target deployment.** HSBC's on-prem Starburst is not available to the Sparkling Ideas team; Starburst Galaxy is the only Starburst we can talk to, and it doesn't need the pattern.
2. **Auth model divergence.** Per [ADR-112: Remove Auth0 and All Authentication](-/adr-112-remove-auth0-replace-with-ip-whitelisting.md), the demo stack has no per-user authentication at all — there is no "current user" to map to a Starburst role. The X-Username header ([ADR-105](-/adr-105-x-username-header-identity-with-static-default.md)) provides an identity hint but not an auth context.
3. **ADR-115 conditional role guard.** [ADR-115: Conditional Starburst Role Guard](--/system-design/adr-115-conditional-starburst-role-guard.md) already introduced an environment-sensitive `SET ROLE` code path that is *enabled* for HSBC and *bypassed* for Galaxy. The pass-through from control-plane to worker is the remaining missing piece.
4. **Galaxy doesn't need it.** Galaxy's single-service-account model is actually the correct pattern for a demo; forcing ADR-098 on the demo would require inventing fake users and roles.

### Relationship to HSBC Handoff

HSBC will deploy the export-worker image into their own GKE cluster talking to their own on-prem Starburst. They will need: (a) Secret Manager access in the worker pod, (b) a mapping from `ExportJob.submitter` to Starburst role, (c) `SET ROLE` issued after connect. None of that is testable in the demo environment.

---

## Decision

**Supersede ADR-098.** Defer the per-user Starburst credential pass-through design to the HSBC handoff timeline, to be implemented alongside HSBC's on-prem Starburst integration.

1. **Supersede ADR-098** (its status moves from Proposed to Superseded by ADR-148). ADR-098's context and proposed flow remain useful reference material but the ADR is not a committed design for this repo.
2. **Demo cluster behaviour stays as-is.** Static `STARBURST_PASSWORD` via `kubernetes_secret` stays. Single service-account model matches Galaxy's auth capabilities. No per-user credential flow will be added to the demo.
3. **Implementation obligation transfers to HSBC handoff.** When HSBC wires up their on-prem Starburst, they (or Sparkling Ideas working on the HSBC branch of the handoff artefact) will implement:
   - Secret Manager client in the export worker (read `genai-secret`, JSON key = service account name).
   - Per-job credential selection: `ExportJob.starburst_user` + role carried from control-plane to worker.
   - `cursor.execute("SET ROLE ...")` after connect, gated by the existing ADR-115 conditional role guard.
   - Short-lived in-memory credential cache (no on-disk persistence, no logging).
4. **No duplicate ADR required at handoff time.** When HSBC implementation begins, update ADR-148 with a "Handoff Implementation Notes" appendix rather than creating ADR-149+. The design space is small enough that a second ADR would be noise.
5. **Related ADRs.** [ADR-095: Server-Side JWT Claim Extraction](-/adr-095-jwt-claim-extraction.md) (also Proposed) becomes a prerequisite for the per-user credential flow — but it too is HSBC-only given ADR-112. We explicitly do not make ADR-095 a blocker here; the HSBC implementation can choose either JWT-claim-based or X-Username-header-based role selection.

---

## Consequences

**Positive:**

- Removes ADR-149 Tier-B.14 drift: the ADR index no longer claims a Proposed design is the intended pattern when the actual pattern is "static service account".
- Avoids building per-user infrastructure that has no functional target in the Galaxy-backed demo and can only be validated against HSBC's Starburst.
- Preserves all useful research from ADR-098 (HSBC connection pattern, `SET ROLE` mechanics, Secret Manager JSON layout) by keeping the file in the tree with "Superseded by ADR-148" rather than deleting it.
- Keeps the demo worker codepath simple and readable — there is exactly one way to authenticate to Starburst in demo mode.

**Negative:**

- The export worker will acquire real per-user credential-handling code only during HSBC handoff, not earlier. This is a short-notice implementation burden for whoever wires up HSBC Starburst.
- HSBC might expect a working per-user flow at demo time ("can you show us role-based access to Starburst?") — we cannot. Mitigated by: Galaxy does not support the pattern anyway, so the demo can only ever be a mock.
- ADR-098's `ExportJob` schema extensions (new columns for `starburst_user`, `starburst_role`) remain unapplied; when HSBC work begins, a database migration will be needed.

---

## Documentation Impact

| Source file | Change required |
|-------------|----------------|
| `docs/process/adr/security/adr-098-starburst-credential-passthrough.md` | **No edit to the ADR body** (per task boundary). However, when this ADR merges, update the ADR index to show ADR-098 status as "Superseded by ADR-148". |
| `docs/process/adr/README.md` | Add ADR-148 entry and change ADR-098 status column to "Superseded by ADR-148". |
| `docs/architecture/export-worker.design.md` (if it cites ADR-098 as the target design) | Add note that the per-user pass-through is deferred to HSBC handoff per ADR-148. Demo uses single service account. |
| `docs/security/authentication.design.md` (if it references per-user Starburst credentials) | Scope the per-user flow to HSBC environments only. |

Files that do **not** need updating: the export worker source code (current static-password behaviour is the documented target state); `infrastructure/terraform/environments/gcp-london-demo/main.tf` (static secret is correct); the `ExportJob` schema (`export_jobs` table in `.swarm/schema.sql` — no columns to add).

---

## Alternatives Considered

1. **Implement ADR-098 now against a mock.** Rejected: mocking HSBC's Starburst would mean hand-rolling a fake LDAP + role server in the demo namespace. High effort, zero production signal.
2. **Implement ADR-098 partially (Secret Manager wiring only, no `SET ROLE`).** Rejected: half an auth flow is more dangerous than none — it would make the worker *look* like it's doing per-user auth while still using a single account, inviting false-confidence audit findings.
3. **Leave ADR-098 in Proposed status indefinitely.** Rejected: ADR-149 is specifically remediating indefinite-Proposed drift. This ADR is the closure.
4. **Delete ADR-098 outright.** Rejected: the HSBC connection-pattern analysis in ADR-098 is genuinely useful reference material for whoever implements the HSBC side of the flow. Better to supersede than to delete.
5. **Accept ADR-098 as-is, mark implementation as future work.** Rejected: ADR-098 is written as a concrete proposed design for *this* codebase; leaving it Accepted while the code does the opposite is exactly the drift pattern ADR-149 flags.

---

## References

- [ADR-098: Starburst Credential Pass-Through for Export Worker](-/adr-098-starburst-credential-passthrough.md) — the superseded ADR
- [ADR-095: Server-Side JWT Claim Extraction for M2M Tokens](-/adr-095-jwt-claim-extraction.md)
- [ADR-105: X-Username Header Identity with Static Default](-/adr-105-x-username-header-identity-with-static-default.md)
- [ADR-112: Remove Auth0 and All Authentication, Replace with IP Whitelisting](-/adr-112-remove-auth0-replace-with-ip-whitelisting.md)
- [ADR-115: Conditional Starburst Role Guard for Multi-Environment Support](--/system-design/adr-115-conditional-starburst-role-guard.md)
- [ADR-128: Operational Documentation Strategy for HSBC Handoff](--/operations/adr-128-operational-documentation-strategy.md)
- [ADR-149: Implementation-vs-Documentation Drift Remediation](--/process/adr-149-implementation-vs-documentation-drift-remediation.md)
- `infrastructure/terraform/environments/gcp-london-demo/main.tf` lines 1496-1506 — static `STARBURST_PASSWORD` secret (current behaviour)
- `infrastructure/terraform/environments/gcp-london-demo/main.tf` lines 865-874 — Helm values wiring the static secret into the worker
