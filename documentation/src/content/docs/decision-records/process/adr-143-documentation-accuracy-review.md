---
title: "ADR-143: Documentation Accuracy Review — Findings and Remediation"
---

| | |
|---|---|
| **Date** | 2026-04-16 |
| **Status** | Accepted |
| **Category** | process |


## Context

On 2026-04-16 an expert swarm review was run across the pages published in the Starlight documentation site (as defined by `tools/repo-split/build-handover.sh` and the Starlight content pipeline established in ADR-142). Each expert was assigned a domain scope and performed read-only analysis against the source files in `docs/`, `infrastructure/cd/docs/`, and the build-pipeline scripts. The full raw findings are captured in `docs/reports/doc-impl-validation-2026-04-16.md` (104 findings returned across 11 completed experts; one expert crashed mid-run and was not retried).

The review surfaced the six recurring drift patterns described below. The counts below reflect the recurring **patterns** that require fixes across multiple files, not individual finding rows — a single pattern (for example "Auth model not updated after ADR-104") accounts for a large share of the raw finding rows.

### Drift Pattern 1 — Auth model not updated after ADR-104

ADR-104 replaced JWT/Bearer token authentication and the `X-User-Role` header with DB-stored user records and the `X-Username` header. Eight or more documents still describe the superseded model: they reference JWT tokens, Bearer auth, `X-User-Role`, and role extraction middleware that no longer exists. Affected docs include architecture authorization references, the SDK API reference, the authorization spec, and several component-design docs for the control plane and export worker.

### Drift Pattern 2 — Stale cloud-infrastructure references after ADR-025

ADR-025 removed Cloud Pub/Sub, Cloud Tasks, Cloud Functions, and Cloud Run from the export-worker architecture in favour of database polling + APScheduler. Multiple docs still describe the event-driven pipeline with these GCP managed services, including the export-worker component design, the architecture overview, and some API specifications.

### Drift Pattern 3 — Wrong HSBC deployment coordinates

The HSBC deployment README stated the GKE cluster region as `europe-west2` (London) with an incorrect project name. The actual deployed cluster is in `asia-east2` (Hong Kong), project `hsbc-12636856-udlhk-dev`. Several operations docs echoed the wrong region and hostnames.

### Drift Pattern 4 — Background-job intervals wrong in six or more files

The export-reconciliation interval is hardcoded to **5 seconds** (fast-poll for near-real-time propagation). Six or more documents describe it as 1 minute or 5 minutes. ADR-040 ("Conservative Job Intervals — 5 Minutes Default") documents the *default* interval policy; the export-reconciliation job is a deliberate exception to that policy. The exception is not documented anywhere.

Additionally, several files list **5 background jobs** when the actual count is **6** — the Resource Monitor job is missing from these inventories.

### Drift Pattern 5 — Stale API field names and database column references

Multiple docs reference `owner_id` or `owner_name` as a field on mapping/instance records. The actual database column is `owner_username`. API spec examples, curl samples in the SDK manual, and the data-model spec all needed updating. A related issue: one tutorial had the storage characteristics of Ryugraph and FalkorDB inverted (Ryugraph uses KuzuDB and is disk-persisted; FalkorDB uses Redis and is in-memory).

### Drift Pattern 6 — Invalid Makefile targets in standards documents

Development-standards and contribution-guide documents reference `make type-check` and `make check` as commands developers should run. Neither target exists in the Makefile. The valid targets are enumerated in CLAUDE.md and ADR-077; the docs were written before a Makefile consolidation removed these targets.

### Why drift accumulates

1. **ADRs record decisions but do not require doc updates as a gate.** Nothing in the current process forces a documentation pass when an ADR is accepted. ADR-104 changed auth, ADR-025 changed the export pipeline, but the owned documentation was not identified or updated at decision time.
2. **The Starlight pipeline adds a transformation layer.** Docs are authored in `docs/`, transformed by `build-handover.sh` and `build-starlight.sh`, and published. The transformation step makes it non-trivial to cross-reference which published page corresponds to which source file, which delays spot-corrections.
3. **No periodic accuracy review existed.** This swarm review is the first systematic pass across the published Starlight pages.

---

## Decision

**Apply the identified fixes to the source files in `docs/` and `infrastructure/cd/docs/`, organised against the six drift patterns below rather than a flat finding count.**

### Remediation scope

Each of the six drift patterns is addressed as follows:

1. **Auth model (ADR-104):** Update all files that reference JWT, Bearer tokens, `X-User-Role`, or the auth middleware to describe the current model: DB-backed user records, `X-Username` header, role column, no token parsing in the API. Add explicit "Updated for ADR-104" notes where the change is non-obvious.

2. **Stale cloud references (ADR-025):** Remove all references to Cloud Pub/Sub, Cloud Tasks, Cloud Functions, and Cloud Run from docs that describe the export pipeline. Replace with the correct description: APScheduler background job polling the `export_jobs` table, calling Starburst Galaxy directly.

3. **HSBC deployment coordinates:** Correct all occurrences of `europe-west2` / wrong project name to `asia-east2` / `hsbc-12636856-udlhk-dev`. Audit all hostnames and load-balancer IPs in the deployment docs for accuracy. (HSBC does not use ArgoCD — CD is `kubectl apply` via `cd/deploy.sh`, so any ArgoCD URLs in HSBC-facing docs are stale scope leaks and must be removed or rewritten.)

4. **Background-job intervals:** Change every "1 minute" / "5 minute" description of the export-reconciliation interval to "5 seconds". Add a callout explaining this is a deliberate exception to the ADR-040 default policy. Update job inventories to list 6 jobs and include the Resource Monitor.

5. **Stale field names / inverted storage descriptions:** Replace `owner_id` / `owner_name` with `owner_username` throughout. Correct the Ryugraph/FalkorDB storage description in the affected tutorial.

6. **Invalid Makefile targets:** Replace `make type-check` and `make check` with the correct targets from ADR-077 (`make lint`, `make test`, etc.).

### Ongoing accuracy process

To prevent recurrence:

- **ADR template update:** The ADR template (in `docs/process/CLAUDE.md`) gains a "Documentation Impact" section. When an ADR changes an observable system behaviour, the author must list which doc files need updating and verify the updates before the ADR is marked Accepted.
- **Pre-handoff doc review:** Before each HSBC handover package build (`make hsbc`), run a targeted accuracy check against the six drift patterns documented here, focusing on the highest-risk sections: auth model, deployment coordinates, and API field names.

---

## Consequences

**Positive:**

- The published Starlight pages reflect current system behaviour after fixes are applied.
- The six recurring drift patterns are documented so future ADR authors know which doc sections to update when they change related subsystems.
- The "Documentation Impact" addition to the ADR template creates a lightweight gate that ties doc updates to the decision they stem from.

**Negative:**

- **One-time remediation effort.** Edits span every `docs/` domain touched by the six drift patterns. Each edit must go to the source (not the Starlight content tree, per ADR-142). This is non-trivial manual work.
- **ADR template change adds friction.** Requiring a "Documentation Impact" section on every ADR means authors must identify affected docs at decision time, which may not always be obvious — particularly for ADRs that change implementation details with indirect documentation coverage.

---

## Alternatives Considered

### Alternative 1: Fix only the highest-severity issues

Prioritise the auth model drift (ADR-104) and HSBC deployment coordinates as the two highest-risk categories (incorrect security documentation; incorrect operational runbook data). Leave interval and field-name corrections for a follow-on pass.

Rejected because the Starlight site is part of the HSBC handover package. Shipping a handover with known inaccuracies in any category — even low-severity ones like Makefile targets — signals poor quality assurance to the receiving team. A full pass is warranted.

### Alternative 2: Add automated drift detection (lint the docs)

Write a script that grep-scans published docs for known stale strings (e.g., `X-User-Role`, `europe-west2`, `Cloud Pub/Sub`, `make type-check`) and fails the build if any are found.

Considered and recommended as a **future enhancement** (not this ADR). It requires maintaining a list of prohibited strings that must be updated when decisions change — which is the same coordination problem as today, just pushed to a different artefact. The ADR template "Documentation Impact" section is a lighter-weight first step; once the six drift patterns are cleared, a regression list is easier to define.

---

## References

- [ADR-104](--/security/adr-104-database-backed-user-role-management.md) — Auth model changed; primary source of Drift Pattern 1
- [ADR-025](--/system-design/adr-025-export-worker-architecture-simplification.md) — Cloud services removed; primary source of Drift Pattern 2
- [ADR-040](--/system-design/adr-040-conservative-job-intervals.md) — Default job interval policy; export-reconciliation exception not documented
- [ADR-077](adr-077-unified-8-target-makefile.md) — Authoritative Makefile target list
- [ADR-142](--/infrastructure/adr-142-starlight-content-single-source-of-truth.md) — Starlight content pipeline; edits must go to `docs/` not `src/content/docs/`
- `tools/repo-split/build-handover.sh` — defines exactly which source files are published in the Starlight site
- `docs/process/CLAUDE.md` — ADR template (to be updated with "Documentation Impact" section per this ADR)
