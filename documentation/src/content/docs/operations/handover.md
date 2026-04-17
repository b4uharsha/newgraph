---
title: Handover
sidebar:
  order: 0
---

## Key Handover Topics

### GCS Bucket Management

The control-plane deletes snapshot Parquet data from GCS when graphs are terminated (cascade delete). If the Workload Identity binding is misconfigured, cleanup silently fails and data accumulates. A bucket lifecycle rule acts as a backstop.

- [GCS Bucket Management](/operations/gcs-bucket-management/) — log queries for failures, health checks, bucket lifecycle TTL configuration, relationship to application TTLs
- [Configuration Reference — GCS Bucket Permissions](/operations/configuration-reference/#gcs-bucket-permissions) — required IAM permissions and diagnostic commands
- [Known Issues — GCS Bucket Permission Failure](/operations/known-issues/#gcs-bucket-permission-failure-silently-disables-cleanup) — failure mode and workaround

### Configuration Parameters

All configurable parameters across all services, with defaults and where to change them:

- [Configuration Reference](/operations/configuration-reference/) — complete reference (control-plane, export worker, wrappers, SDK, runtime database config)
- [Configuration Reference — Background Job Intervals](/operations/configuration-reference/#background-job-intervals) — reconciliation, lifecycle, orchestration, schema cache intervals
- [Configuration Reference — Runtime Configuration](/operations/configuration-reference/#runtime-configuration-database-global_config) — parameters changeable at runtime via API (snapshot TTL, concurrency limits, maintenance mode)

### Polling Interval Adjustments

The instance orchestration and export reconciliation jobs default to 5-second intervals, which is aggressive for production. Recommended: increase to 30 seconds.

- [Configuration Reference — Background Job Intervals](/operations/configuration-reference/#background-job-intervals) — how to configure intervals
- [Job Sequence — Recommended Interval Tuning](/operations/job-sequence/#recommended-interval-tuning) — recommended values with rationale

### Known Issues

Issues and limitations known at handover, including schema cache connectivity, GCS permissions, snapshot TTL safety gap, and authentication:

- [Known Issues](/operations/known-issues/) — full list with severity, impact, and workarounds

### Job Sequence and Dependencies

How background jobs interact, the end-to-end flow from mapping creation to queryable graph, and job dependency diagrams:

- [Job Sequence](/operations/job-sequence/) — job inventory, Mermaid sequence diagram, dependency flowchart

### Database Schema

PostgreSQL schema with full DDL, entity relationships, constraints, indexes, migration strategy, and atomic claiming SQL:

- [Data Model Specification](/architecture/data-model-spec/) — complete database schema
- [Domain Model Overview](/architecture/domain-model-overview/) — DDD aggregates, state machines, domain events, ubiquitous language glossary

### Authentication and Active Directory Integration

The platform currently uses IP whitelisting with self-declared `X-Username` headers. The planned production model is Azure AD (Entra ID) via oauth2-proxy. No application code changes are required — purely infrastructure configuration:

- [Platform Operations Manual](/operations/platform-operations-manual/) — current auth model and Azure AD migration plan (7 phases)
- [Security Operations Runbook](/operations/security-operations-runbook/) — access control procedures and known X-Username trust limitation
- [Authorization](/architecture/authorization/) — RBAC roles (Analyst/Admin/Ops), permission matrix, ownership model
- [Authorization Spec](/security/authorization-spec/) — enforcement code and endpoint-level permissions

---

## Reading Order by Role

### Platform Operations (Day-to-day operators, on-call engineers)

Start here on day 1:

1. [Service Catalogue](/operations/service-catalogue-manual/) — what services exist, their dependencies, health endpoints
2. [Platform Operations Manual](/operations/platform-operations-manual/) — daily health checks, maintenance, configuration
3. [Incident Response Runbook](/operations/incident-response-runbook/) — severity classification, escalation, playbooks
4. [HSBC Deployment Quick Reference](/hsbc-deployment/) — hostnames, namespace, project coordinates
5. [Known Issues](/operations/known-issues/) — what to watch out for
6. [Configuration Reference](/operations/configuration-reference/) — all tuneable parameters

Then in week 1:

7. [Monitoring and Alerting Runbook](/operations/monitoring-alerting-runbook/) — alert catalogue, diagnostic queries
8. [Troubleshooting Runbook](/operations/troubleshooting-runbook/) — symptom-indexed diagnostic guide
9. [Disaster Recovery Runbook](/operations/disaster-recovery-runbook/) — backup inventory, RPO/RTO, recovery procedures
10. [Security Operations Runbook](/operations/security-operations-runbook/) — secret rotation, vulnerability management
11. [Capacity Planning Manual](/operations/capacity-planning-manual/) — sizing, scaling, cost estimation
12. [Job Sequence](/operations/job-sequence/) — background job dependencies and tuning

### Architects and Technical Leads

1. [Detailed Architecture](/architecture/detailed-architecture/) — C4 views, component topology, resource model
2. [Requirements](/architecture/requirements/) — functional requirements, user roles, glossary
3. [Architectural Guardrails](/architecture/architectural-guardrails/) — locked technology decisions, mandatory patterns
4. [Domain and Data Model](/architecture/domain-and-data/) — DDD aggregates, state machines, data flows
5. [System Architecture Design](/architecture/system-architecture-design/) — data-flow matrix, error-recovery matrix
6. [Authorization](/architecture/authorization/) — RBAC roles, permission matrix, ownership model
7. [SDK Architecture](/architecture/sdk-architecture/) — Python SDK internals, resource managers
8. [Data Model Specification](/architecture/data-model-spec/) — PostgreSQL schema, DDL, migrations
9. [Domain Model Overview](/architecture/domain-model-overview/) — ubiquitous language, domain events, concurrency rules

### Developers (Maintaining and extending the platform)

1. [Code Walkthrough](/developer-guide/code-walkthrough/) — end-to-end execution path with file:line references
2. [System Architecture Design](/architecture/system-architecture-design/) — component boundaries, API conventions
3. [API Common Specification](/api/api-common-spec/) — shared conventions, error codes, authentication
4. [Control Plane Design](/component-designs/control-plane-design/) — the central service
5. Individual [API specs](/api/api-common-spec/) and [component designs](/component-designs/control-plane-design/) as needed
6. [HSBC Deployment Architecture](/hsbc-deployment/architecture/) — Jenkins CI, deploy.sh model
7. [Development Standards](/standards/python-linting-standards/) — Python linting, logging, commenting, container builds
8. [Configuration Reference](/operations/configuration-reference/) — all environment variables and defaults
9. [Job Sequence](/operations/job-sequence/) — background job architecture

### Analysts and Data Scientists (Using the SDK in Jupyter)

1. [Getting Started](/sdk-manual/01-getting-started-manual/) — installation and first SDK call
2. [Core Concepts](/sdk-manual/02-core-concepts-manual/) — mappings, instances, snapshots
3. [API Reference](/sdk-manual/03-api-reference-manual/) — complete SDK API with examples
4. [Graph Algorithms](/sdk-manual/04-graph-algorithms-manual/) — algorithm guide
5. [Advanced Topics](/sdk-manual/05-advanced-topics-manual/) — performance tuning, caching, error handling
6. [Examples](/sdk-manual/06-examples-manual/) — working code examples
7. [Error Codes](/sdk-manual/appendices/b-error-codes-manual/) — troubleshooting reference

---

## Folder Contents

| Folder | Contents |
|---|---|
| [operations/](/operations/platform-operations-manual/) | Platform operations manuals, runbooks, configuration reference, known issues, job sequence |
| [architecture/](/architecture/detailed-architecture/) | System architecture, domain model, data model, requirements, guardrails, diagrams |
| [api/](/api/api-common-spec/) | HTTP API specifications (9 endpoint groups + shared conventions) |
| [component-designs/](/component-designs/control-plane-design/) | Per-service technical designs (18 documents) |
| [security/](/security/authorization-spec/) | Container security audit, transport security, authorization spec |
| [governance/](/governance/change-control-framework-governance/) | Change control framework (Deliverance/SOX), container supply chain |
| [standards/](/standards/python-linting-standards/) | Python linting, logging, commenting standards; container build standards; notebook design system |
| [sdk-manual/](/sdk-manual/01-getting-started-manual/) | SDK user manual (6 chapters + 4 appendices) |
| [developer-guide/](/developer-guide/code-walkthrough/) | Code walkthrough for developers taking over the codebase |
| [hsbc-deployment/](/hsbc-deployment/) | HSBC-specific deployment docs (hostnames, Nexus URLs, Jenkins model, debug commands) |
| [reference/](/reference/data-pipeline-reference/) | Technical reference (data pipeline, RyuGraph NetworkX, RyuGraph performance) |

---

## Q&A

### How do I use the FalkorDB API? Can you give examples?

FalkorDB usage is documented across several pages in the SDK manual:

- **[Getting Started](/sdk-manual/01-getting-started-manual/)** — quick-start examples that create a FalkorDB instance with `wrapper_type=WrapperType.FALKORDB` and run a first query.
- **[API Reference](/sdk-manual/03-api-reference-manual/)** — the `WrapperType` enum, accepted string forms, and a side-by-side comparison of RyuGraph and FalkorDB to help you pick the right backend.
- **[Graph Algorithms](/sdk-manual/04-graph-algorithms-manual/)** — section 4, "FalkorDB Algorithms (`conn.algo`)", covers the native Cypher procedures exposed by FalkorDB. Note that NetworkX integration is **not** available on FalkorDB instances; use RyuGraph if you need NetworkX.
- **[Examples](/sdk-manual/06-examples-manual/)** — around fifteen worked end-to-end examples that use `WrapperType.FALKORDB`, from basic connections to full analytical workflows.
- **[FalkorDB Wrapper Design](/component-designs/falkordb-wrapper-design/)** — internal design of the wrapper service itself. Useful for developers and operators, not for end users writing queries.

The most useful starting points for analysts are the quick-start in *Getting Started* and section 4 of the *Graph Algorithms* manual.

### What's the difference between the RyuGraph and FalkorDB wrapper APIs?

**Short answer:** both expose Cypher over HTTP with the same request/response shape, the same liveness/readiness contract, and the same generic algorithm runner. The meaningful differences are (1) RyuGraph has a NetworkX router and FalkorDB does not, (2) RyuGraph's \`/query\` rejects mutation keywords at the router layer while FalkorDB does not, (3) the algorithm routers expose slightly different auxiliary endpoints, and (4) FalkorDB exposes schema/query at the top level while RyuGraph nests them under prefixed paths.

**Shared surface (identical for both wrappers):**

- \`POST /query\` — execute a Cypher query. Same \`QueryRequest\` / \`QueryResponse\` models, same \`timeout_ms\`, same \`parameters\` dict.
- \`GET /schema\` — return the loaded graph's node labels and relationship types.
- \`GET /lock\` — cooperative exclusive-access lock for long-running operations.
- \`GET /health\` — Kubernetes liveness. Always 200 while the FastAPI process is alive. Does **not** gate on database readiness.
- \`GET /ready\` — Kubernetes readiness. 503 until the snapshot has been loaded into the engine, 200 after.
- \`GET /status\` — detailed pod status: instance/snapshot/mapping IDs, readiness flag, node/edge counts once loaded, memory usage, lock state.
- \`POST /algo/{algorithm_name}\` — run a named native algorithm asynchronously.
- \`GET /algo/status/{execution_id}\` — poll a running algorithm.
- \`GET /algo/algorithms\` and \`GET /algo/algorithms/{algorithm_name}\` — algorithm catalogue and detail lookup.

**RyuGraph-only:**

- \`POST /algo/shortest_path\` — dedicated endpoint for shortest-path queries (FalkorDB equivalent is the generic \`POST /algo/{algorithm_name}\` with \`algorithm_name=shortest_path\`).
- \`POST /networkx/{algorithm_name}\`, \`GET /networkx/algorithms\`, \`GET /networkx/algorithms/{algorithm_name}\` — the NetworkX router. Runs algorithms that FalkorDB-native Cypher does not implement (PageRank, betweenness/closeness/eigenvector/Katz/harmonic/load/degree centrality, and friends) by materialising the graph into a NetworkX DiGraph. **FalkorDB wrapper has no equivalent — if you need NetworkX algorithms, launch a RyuGraph instance.**
- **Router-layer mutation guard.** \`POST /query\` hard-rejects the keywords \`CREATE\`, \`SET\`, \`DELETE\`, \`REMOVE\`, \`MERGE\`, \`DROP\` with a 400 before the query reaches the engine. Read-only by construction.

**FalkorDB-only:**

- \`GET /algo/executions\` — list all algorithm executions on this instance.
- \`DELETE /algo/executions/{execution_id}\` — cancel or clean up an execution.
- **No router-layer mutation guard.** \`POST /query\` passes mutation keywords through; the engine's own read-only posture is the only guard. Queries that would mutate state are rejected by the FalkorDB engine, not by the wrapper.

**Cosmetic internal difference (developers only):**

- RyuGraph routers declare their prefix on the \`APIRouter(prefix=...)\`; routes inside declare just \`""\`. FalkorDB routers declare no prefix and every route carries its own path. The external HTTP surface is the same.

**When to use which:**

- **FalkorDB** — default for most workloads. Lower memory footprint, faster load, identical Cypher surface for reads and native graph algorithms.
- **RyuGraph (Kuzu)** — pick this when you need NetworkX algorithms, a dedicated \`/shortest_path\` endpoint, or router-enforced read-only semantics.

See [API Reference — Wrapper Types](/sdk-manual/03-api-reference-manual/) for the SDK-facing comparison and [FalkorDB Wrapper Design](/component-designs/falkordb-wrapper-design/) / [RyuGraph Wrapper Design](/component-designs/ryugraph-wrapper-design/) for the internal design of each service.

### How do I set the use case ID when constructing the SDK client?

This is already supported. `GraphOLAPClient` accepts an optional `use_case_id` keyword argument, which is sent as the `X-Use-Case-Id` header on every request (see ADR-102). The resolution order is:

1. The `use_case_id` keyword argument passed to the constructor.
2. The `GRAPH_OLAP_USE_CASE_ID` environment variable.
3. The built-in default (`e2e_test_role`).

```python
from graph_olap import GraphOLAPClient

client = GraphOLAPClient(
    username="alice@hsbc.co.uk",
    use_case_id="fraud_analytics",
)
```

See the [API Reference](/sdk-manual/03-api-reference-manual/) for the full constructor signature.

### How do we make the use case ID required instead of optional?

Currently `use_case_id` is nullable throughout the stack — the SDK falls back to `e2e_test_role` if `GRAPH_OLAP_USE_CASE_ID` is unset, the control plane stores `NULL` in `export_jobs.starburst_role`, and the export worker fails the job only at queue-processing time (late failure). Three changes move the enforcement to the earliest possible point in each layer.

**Layer 1 — SDK (`packages/graph-olap-sdk/src/graph_olap/config.py`)**

Remove the `None` default and raise at construction time if the env var is absent:

```python
# BEFORE (line 39)
use_case_id: str | None = None

# AFTER
use_case_id: str
```

```python
# from_env() — BEFORE (line 83)
use_case_id = os.environ.get("GRAPH_OLAP_USE_CASE_ID", "e2e_test_role")

# from_env() — AFTER
use_case_id = os.environ.get("GRAPH_OLAP_USE_CASE_ID")
if not use_case_id:
    raise RuntimeError(
        "GRAPH_OLAP_USE_CASE_ID is not set. "
        "Set it to your Starburst use case ID (e.g. uc_glh_dev)."
    )
```

**Layer 2 — Control plane API (`packages/control-plane/src/control_plane/middleware/identity.py`)**

Add a `400 USE_CASE_ID_REQUIRED` guard immediately after the existing `x_username` check (line 53). The FastAPI parameter binding stays `str | None` — enforcement is explicit:

```python
if not x_use_case_id:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "USE_CASE_ID_REQUIRED",
            "message": "X-Use-Case-Id header required.",
        },
    )
```

**Layer 3 — Control plane domain (`packages/control-plane/src/control_plane/models/domain.py`)**

Remove the `None` default so the dataclass enforces the constraint at construction time:

```python
# BEFORE (line 66)
use_case_id: str | None = None  # From X-Use-Case-Id header (ADR-102)

# AFTER
use_case_id: str  # From X-Use-Case-Id header (ADR-102) — required
```

**Export worker — no change needed.** The guard at `worker.py:241–248` already hard-fails jobs with a missing `starburst_role`. With the three changes above a job without `starburst_role` should never reach the queue; the worker guard becomes a last-resort safety net.

See [ADR-102](/architecture/system-architecture-design/) for the full use case ID flow and the rationale for env-var-based configuration.

### Should the use case ID be stored on the mapping itself?

**Short answer:** probably not — a SQL query over \`export_jobs.starburst_role\` already answers "which Starburst roles ran against mapping X?" without schema changes. Adding a \`mapping.use_case_id\` column reads well but turns into an ACL-by-another-name the moment you enforce header/column matching, and conflicts with the no-ACL collaboration model documented in [Authorization — §4.1 Collaboration Patterns](/architecture/authorization/#41-collaboration-patterns).

**Design debate (Queen vs. Devil's Advocate):**

*The case for storing it* (Queen):

- Persist \`use_case_id\` as a required, middleware-sourced column on \`mappings\`, immutable after creation, surfaced in \`mappings.list()\` and \`mappings.get()\`.
- Instance creation compares \`user.use_case_id\` to \`mapping.use_case_id\` and returns \`403 USE_CASE_ID_MISMATCH\` on divergence; export jobs source \`starburst_role\` from the mapping rather than the request header.
- One Alembic migration adds the column nullable, backfills existing rows with a sentinel \`legacy_unowned\`, then flips to \`NOT NULL\`. \`copy()\` writes the caller's \`use_case_id\`, not the source's.

*The case against* (Devil's Advocate):

- **\`copy()\` becomes incoherent.** Inherit the source's ID → the caller's exports 403. Overwrite with the caller's ID → the "authored under" audit claim is a lie. Clear it → the new mapping is mystery-tagged.
- **It is an ACL by the back door.** \`authorization.md §4.1\` explicitly says the platform has no ACLs, grants, or delegation. Gating exports on \`mapping.use_case_id\` equality is exactly per-mapping authorization keyed on team identity, with one column instead of a table.
- **The audit need is already met.** Every export persists its role as \`export_jobs.starburst_role\`. The auditor's question — *"which roles ran against mapping 42?"* — is \`SELECT DISTINCT starburst_role FROM export_jobs ej JOIN snapshots s ON ej.snapshot_id=s.id WHERE s.mapping_id=42\`. No schema change, no migration, no copy-semantics debate.
- **Shared mappings break.** A customer-graph mapping legitimately exported by five teams needs five \`use_case_id\` values; pinning one at author time forces four teams to copy-and-pollute.
- **Three sources of truth.** Header, mapping column, and \`export_jobs.starburst_role\` — with no defined precedence when they disagree.
- **Backfill is a trap.** Existing rows have no value. Nullable-forever undermines any later enforcement; required-with-backfill asks Ops to retroactively invent the "right" use case per legacy mapping and be accountable when they guess wrong.

**Recommended path:**

1. Ship an audit query or \`GET /api/mappings/{id}/audit\` endpoint sourced from \`export_jobs\` — one afternoon of work, no migration, no ACL drift.
2. If HSBC compliance later requires per-team mapping isolation, treat it as an ACL programme (separate ADR, separate RFC), not as a string column.
3. If a purely advisory "suggested use_case_id" field is wanted, mark it non-enforced and accept that it's documentation, not policy.

Full design, file-by-file change list, and migration shape: \`docs/process/adr/data-model/\` (ADR to be authored if direction (1) is rejected).

### How do I use maintenance mode — how do I set it, when should I set it, and what do users see?

**Short answer:** the toggle exists at `PUT /api/config/maintenance` (Ops role), but enforcement is **not currently wired** in the control-plane — setting `maintenance.enabled=1` records state in the database but does not block writes. Maintenance windows must be coordinated out-of-band until the gap is fixed.

- Full operator procedure, scenarios, and intended response shape: [Platform Operations Manual — §2.7 Maintenance Mode](/operations/platform-operations-manual/#27-maintenance-mode).
- Enforcement gap and fix plan: [Known Issues — Maintenance Mode Enforcement Not Wired](/operations/known-issues/#maintenance-mode-enforcement-not-wired).
- Step-by-step fix (files to change, dependency implementation, SDK mapping, integration tests): [Maintenance Mode Fix](/operations/maintenance-mode-fix/).
- API schemas: [API — Admin & Ops Spec — Set Maintenance Mode](/api/api-admin-ops-spec/#set-maintenance-mode).

### What happens when the maximum number of graph instances is reached?

**Short answer:** the control plane enforces five governance limits (`per_analyst`, `cluster_total`, `instance_memory`, `user_memory`, `cluster_memory`) and rejects the creating call with `409 CONCURRENCY_LIMIT_EXCEEDED`. The error payload's `details.limit_type` field tells the operator exactly which limit fired. Read endpoints continue to work normally.

- Full diagnostic runbook (all five `limit_type` values, exact curl and kubectl commands, resolution steps per limit type): [Troubleshooting — Instance Limit Reached](/operations/troubleshooting-runbook/#instance-limit-reached--409-concurrency_limit_exceeded).
- Runtime knobs: [Configuration Reference — Runtime Configuration](/operations/configuration-reference/#runtime-configuration-database-global_config).
- Governance model in context: [Capacity Planning Manual — §6 Resource Governance](/operations/capacity-planning-manual/#6-resource-governance).

### How do users share mappings?

**Short answer:** there is no "share" feature. The platform has no ACLs, grants, ownership transfer, or delegation. Analysts collaborate through three SDK-level patterns:

1. **Read any mapping.** `client.mappings.list()` returns every mapping on the platform regardless of owner; `client.mappings.get(id)` and `client.mappings.list_versions(id)` work on any mapping. The mapping catalogue is a shared reference.
2. **Fork by copy.** `client.mappings.copy(mapping_id=42, new_name="My Copy")` creates a new mapping owned by the caller, seeded from the current version of the source. No upstream link, no automatic sync — call `copy(...)` again if you need to catch up with the original.
3. **Ask an Admin for in-place edits.** `client.mappings.update(...)` on a teammate's mapping raises `PermissionDeniedError` (HTTP 403) unless the caller is Admin or Ops. If a shared analytical model needs to change for everyone already using it, an Admin is the only path.

What you cannot do: share with specific teammates, transfer ownership, merge two mappings, or query across multiple mappings.

- Full analyst walkthrough with code examples: [SDK Manual — Core Concepts — Working With Other Users' Mappings](/sdk-manual/02-core-concepts-manual/#working-with-other-users-mappings).
- Architecture model and rationale: [Authorization — §4.1 Collaboration Patterns](/architecture/authorization/#41-collaboration-patterns).
- Permission matrix: [Authorization — §3.1 Data Resources](/architecture/authorization/#31-data-resources).
- API reference (for admins / integrators): [API — Mappings — `POST /mappings/:id/copy`](/api/api-mappings-spec/#post-mappingsidcopy).

### Can an analyst query another user's graph instance?

**Short answer:** yes. Any authenticated user can run read-only Cypher queries against any running instance, including instances owned by other users. The wrapper's `/query` endpoint is intentionally unauthenticated at the wrapper level and rejects mutating Cypher keywords (`CREATE`, `SET`, `DELETE`, `MERGE`, `REMOVE`, `DROP`) at `ryugraph-wrapper/routers/query.py:56`, so cross-user access is read-only. This is consistent with the "Read any" rule for instance metadata — instances and the data loaded into them are treated as a shared read catalogue for analysts.

Algorithm execution was intended to be **owner-only** — see the separate Q&A entry below for current status and the fix plan.

- Authoritative permission matrix: [Authorization & Access Control — §3.1](/architecture/authorization/#31-data-resources).
- Enforcement spec: [Authorization Specification — Ownership Model point 6](/security/authorization-spec/#ownership-model).
- Requirements model: [Requirements — Analyst permissions](/architecture/requirements/#user-roles--permissions) (already documents this as "Query any; algorithms own only").

If cross-user query access is a concern for the HSBC deployment, the fix is to add an authorization dependency on the wrapper's `/query` route that calls the same `/authorize` endpoint used by the algorithm path. This is a wrapper-side change only and does not require control-plane changes.

### Where are the diagrams for async jobs and the flow around graph creation?

**Short answer:** there is no message bus — the platform uses a **polling + reconciliation** model, not event-driven architecture. Background jobs poll Postgres for `pending`/`creating` rows every 5–30 seconds and reconcile database state against Kubernetes pod state. The `instance_events` table exists but the write path is a stub (see [Known Issues — Instance Events Not Written to Database](/operations/known-issues/#instance-events-not-written-to-database)).

- **Canonical async-jobs doc:** [Job Sequence](/operations/job-sequence/) — end-to-end sequence diagram (analyst SDK → control-plane → export-worker → wrapper), job-dependency flowchart split between user-triggered and background paths, job inventory, and recommended interval tuning.
- **Graph creation and lifecycle:** [System Architecture Design](/architecture/system-architecture-design/) — snapshot creation flow, snapshot and instance state machines, instance startup flow, wrapper selection, deletion dependency chain, algorithm and query execution flows.
- **Export worker (the async heavy-lifter):** [Export Worker Design](/component-designs/export-worker-design/) — architecture diagram and snapshot export sequence.
- **Code-level walkthrough:** [Developer Guide — Code Walkthrough](/developer-guide/code-walkthrough/) — end-to-end request flow diagram with file:line references.
- **State machines and domain events:** [Domain Model Overview](/architecture/domain-model-overview/) — aggregate state diagrams for mapping, snapshot, and instance, plus the domain event catalogue.
- **Per-service background job diagrams:** [Control Plane Design](/component-designs/control-plane-design/) — reconciliation, lifecycle, resource-monitor, and schema-cache jobs.
- **Ops-facing job summary:** [Platform Operations Manual — §8 Background Jobs](/operations/platform-operations-manual/#8-background-jobs).

### Can an analyst run algorithms on another analyst's graph instance?

**Short answer:** not by design intent, but the enforcement was temporarily removed and has not yet been restored. Until ADR-144 is implemented, treat the instance URL slug as a secret.

**Background:** `AlgorithmPermissionDep` — a FastAPI dependency applied to `/algo/*` and `/networkx/*` on both wrappers — enforced owner-only algorithm access. It used a two-path check:

1. **Fast path:** compare the `X-Username` request header against `WRAPPER_OWNER_ID` (the owner's username, baked into the pod at startup). Matches are allowed immediately with no network call.
2. **Slow path:** call `GET /api/internal/instances/{url_slug}/authorize?username=<user>` on the control plane, which returns `{"allowed": true}` for Admin/Ops or the instance owner, and `{"allowed": false}` otherwise.

The dependency was removed in April 2026 (commit `a11e9ed8`) because the slow path returned HTTP 401 in the HSBC environment. Root cause: the wrapper was calling the **external** control-plane URL (which goes through the HSBC auth proxy), rather than the in-cluster service address. The `/authorize` endpoint itself requires no API key — the 401 came from the proxy in front of it, not from the control plane.

**Current posture:** any user who knows a graph instance's URL slug can call `/algo/*` and `/networkx/*` on that pod. Access is gated only by network policy and the unguessability of the UUID slug — not by identity enforcement.

**Interim mitigation:** do not expose URL slugs in shared notebook output, log aggregation dashboards, or error messages.

**Planned fix (ADR-144):** re-add `AlgorithmPermissionDep` to all four algorithm router endpoints and route the slow-path authorise call to the in-cluster CP service (`WRAPPER_CONTROL_PLANE_INTERNAL_URL` env var) rather than the external URL. Full implementation checklist, affected files, and testing plan:

> `docs/process/adr/security/adr-144-graph-node-owner-access-control.md`

### How do I scale the cluster and manage cost?

**Short answer:** before changing any node pool, confirm whether the bottleneck is the platform governance cap or real infrastructure exhaustion — scaling the node pool alone does not help if the control-plane cap is the limiter. The cheapest lever is usually the runtime config, not Terraform.

- Full operator checklist (diagnose → platform limits → instance node pool → control-plane node pool → cost levers → verify): [Capacity Planning Manual — §9 Operational Scaling Checklist](/operations/capacity-planning-manual/#9-operational-scaling-checklist).
- Derivations, sizing formulas, and per-unit costs: [Capacity Planning Manual — §§1–8](/operations/capacity-planning-manual/).
- Scaling execution steps: [Platform Operations Manual — §5 Scaling Operations](/operations/platform-operations-manual/#5-scaling-operations).

### Why does the schema browser show no catalogs or tables?

The control-plane schema cache cannot reach Starburst. The background job runs on startup and every 24 hours — if the connection to the Starburst coordinator fails, the cache is never populated and all `/api/schema/*` endpoints return empty results. The failure is logged but does not crash the pod.

**The known root cause in GKE London:** `GRAPH_OLAP_STARBURST_URL` is set to an empty string in the control-plane ConfigMap (`infrastructure/cd/resources/control-plane-configmap.yaml`), even though the export-worker ConfigMap has the correct URL (`https://wsdv-hk-dev.hk.hsbc:8443`).

**How to confirm the cache is empty:**

```
GET /api/schema/admin/stats   →   total_catalogs: 0,  last_refresh: null
```

`last_refresh: null` means the refresh job has never completed successfully since the pod last started.

**How to find the error in logs:**

Search Cloud Logging for `jsonPayload.event="schema_cache_refresh_failed"`. The `error` field in the log payload names the root cause — common values are an empty URL (DNS resolution failure), a connection refused error (wrong port or host), or an HTTP 401/403 (wrong credentials or role).

**How to fix:**

1. Set `GRAPH_OLAP_STARBURST_URL: "https://wsdv-hk-dev.hk.hsbc:8443"` in `infrastructure/cd/resources/control-plane-configmap.yaml`.
2. Commit, push, and let ArgoCD sync (or force-sync with `argocd app sync graph-olap-control-plane`). The pods roll automatically.
3. Trigger an immediate cache refresh — no need to wait 24 hours:
   ```
   POST /api/schema/admin/refresh   (requires Ops role)
   ```
4. Confirm with the stats endpoint — `total_catalogs` should be non-zero within a few minutes.

> Full step-by-step debug guide, log reference, and connectivity test procedure: [operations/starburst-schema-cache-debug.md](/operations/starburst-schema-cache-debug/)

