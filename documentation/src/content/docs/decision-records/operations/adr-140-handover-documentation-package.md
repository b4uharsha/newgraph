---
title: "ADR-140: Handover Documentation Package"
---

| | |
|---|---|
| **Date** | 2026-04-14 |
| **Status** | Proposed |
| **Category** | operations |


## Context

The Graph OLAP Platform has extensive documentation spread across multiple locations in the monorepo. For the HSBC handover, we need a curated set of markdown documents collected into a single `handover/` folder at the project root. This folder serves as the definitive handover package — only documents relevant to HSBC's deployment model (Jenkins CI, `kubectl apply` via `deploy.sh`, Deliverance change control, Cloud Monitoring).

The documentation site is published via the `packages/documentation` node (MkDocs Material, deployed as the `docs` service). During `make repo`, the `tools/repo-split/configs/documentation.yaml` config controls what gets copied into `build/repos/documentation/`. The `handover/` folder should be added to this config so it is dynamically copied into the documentation node at build time.

### The Curation Problem

`docs/document.structure.md` defines a 10-tier documentation hierarchy containing ~120 files across 15+ subdirectories. Much of this content describes **our** development infrastructure (ArgoCD, OrbStack, GKE London dev cluster, GitHub Actions, Argo Rollouts, GHCR) rather than HSBC's target environment. A 12-agent review identified:

- **Severe overlaps**: `domain-and-data.md` and `domain.model.overview.md` share ~500 lines of duplicated content (same aggregates, state machines, ERD)
- **Stale content**: 5 operations docs reference ArgoCD/Argo Rollouts/GHCR that HSBC won't use; security docs reference Auth0 stack removed by ADR-104/112
- **Deprecated content**: All 6 UX design files, 5 UX ADRs, web-application component design — web UI was removed
- **Internal-only content**: All `docs/research/` (removed auth stack), all `docs/plans/` (internal dev planning, marked "not for publication"), `docs/platform/` (depot.dev CI), `docs/testing/` (our test strategy)
- **Wrong format**: `docs/notebooks/` are `.ipynb` (JSON), not markdown — already rendered by the docs site
- **Data conflicts**: Alert thresholds differ between observability design and monitoring runbook; background job intervals differ between architecture doc and service catalogue

### HSBC Deployment Model

| Aspect | Our Development | HSBC Production |
|---|---|---|
| CI | GitHub Actions | Jenkins `gke_CI()` |
| CD | ArgoCD (Helm) | `kubectl apply` via `deploy.sh` |
| Charts | Helm with values overlays | Raw YAML manifests (sed-templated) |
| Change control | Git merge to main | Deliverance approval workflow |
| Monitoring | Grafana dashboards | Cloud Monitoring (GCP console) |
| Registry | GHCR | Nexus / GAR |
| Local dev | OrbStack + Earthly | N/A |

Only documentation that describes the platform itself or HSBC's deployment model should be included.

---

## Decision

Create a `handover/` folder at the project root by selectively copying from `docs/` and `infrastructure/cd/docs/`. A build script copies only HSBC-relevant files, skipping internal development infrastructure documentation.

### Folder Structure

```
handover/
├── README.md                          # Index: what's here, reading order by role
│
├── operations/                        # For Platform Operations team
│   ├── platform-operations.manual.md
│   ├── service-catalogue.manual.md
│   ├── capacity-planning.manual.md
│   ├── incident-response.runbook.md
│   ├── monitoring-alerting.runbook.md
│   ├── disaster-recovery.runbook.md
│   ├── troubleshooting.runbook.md
│   └── security-operations.runbook.md
│
├── architecture/                      # For Architects & Technical Leads
│   ├── detailed-architecture.md
│   ├── domain-and-data.md
│   ├── sdk-architecture.md
│   ├── platform-operations.md
│   ├── authorization.md
│   ├── system.architecture.design.md
│   ├── data.model.spec.md
│   ├── domain.model.overview.md
│   ├── requirements.md
│   ├── architectural.guardrails.md
│   └── diagrams/                      # Rendered SVG architecture diagrams
│
├── api/                               # For Developers & Integrators
│   ├── api.common.spec.md
│   ├── api.instances.spec.md
│   ├── api.mappings.spec.md
│   ├── api.snapshots.spec.md
│   ├── api.admin-ops.spec.md
│   ├── api.favorites.spec.md
│   ├── api.wrapper.spec.md
│   ├── api.starburst.spec.md
│   └── api.internal.spec.md
│
├── component-designs/                 # For Developers maintaining each service
│   ├── control-plane.design.md
│   ├── control-plane.services.design.md
│   ├── control-plane.background-jobs.design.md
│   ├── control-plane.mapping-generator.design.md
│   ├── export-worker.design.md
│   ├── export-worker.clients.design.md
│   ├── ryugraph-wrapper.design.md
│   ├── ryugraph-wrapper.services.design.md
│   ├── falkordb-wrapper.design.md
│   ├── jupyter-sdk.design.md
│   ├── jupyter-sdk.connection.design.md
│   ├── jupyter-sdk.algorithms.design.md
│   ├── jupyter-sdk.algorithms.native.design.md
│   ├── jupyter-sdk.algorithms.networkx.design.md
│   ├── jupyter-sdk.deployment.design.md
│   ├── jupyter-sdk.models.spec.md
│   ├── instance-lifecycle-management.design.md
│   └── e2e-tests.design.md
│
├── security/                          # For Security & Compliance teams
│   ├── container-security-audit.md
│   ├── security-improvements-summary.md
│   ├── transport-security.design.md
│   └── authorization.spec.md
│
├── governance/                        # For Compliance & Change Management
│   ├── container-supply-chain.governance.md
│   └── change-control-framework.governance.md
│
├── standards/                         # For all developers
│   ├── python-commenting-standards.md
│   ├── python-linting-standards.md
│   ├── python-logging-standards.md
│   ├── container-build-standards.md
│   └── notebook-design-system.md
│
├── sdk-manual/                        # For Analysts & Data Scientists
│   ├── 01-getting-started.manual.md
│   ├── 02-core-concepts.manual.md
│   ├── 03-api-reference.manual.md
│   ├── 04-graph-algorithms.manual.md
│   ├── 05-advanced-topics.manual.md
│   ├── 06-examples.manual.md
│   └── appendices/
│       ├── a-environment-variables.manual.md
│       ├── b-error-codes.manual.md
│       ├── c-cypher-reference.manual.md
│       └── d-algorithm-reference.manual.md
│
├── developer-guide/                   # For Developers taking over the codebase
│   └── code-walkthrough.md
│
├── hsbc-deployment/                   # HSBC-specific deployment docs
│   ├── README.md                      # Quick reference (hostnames, namespace, project)
│   ├── architecture.md                # 12-step request flow, Jenkins CI model
│   ├── debug.md                       # kubectl diagnostic recipes
│   ├── jupyter.md                     # Nexus PyPI URL, Dataproc SDK install
│   ├── query.md                       # Live API curl recipes
│   ├── sdk-notebook-changes.md        # 4 HSBC-specific SDK modifications
│   └── saml.md                        # X-Username model vs deferred SAML
│
└── reference/                         # Technical reference
    ├── data-pipeline.reference.md
    ├── ryugraph-networkx.reference.md
    └── ryugraph-performance.reference.md
```

### Source Mapping

| Handover path | Source path |
|---|---|
| `operations/*.md` | `docs/operations/` (8 manuals + runbooks only) |
| `architecture/*.md` | `docs/architecture/*.md` + `docs/system-design/system.architecture.design.md` + `docs/system-design/data.model.spec.md` + `docs/system-design/domain.model.overview.md` + `docs/foundation/*.md` |
| `architecture/diagrams/` | `docs/architecture/diagrams/` |
| `api/*.md` | `docs/system-design/api.common.spec.md` + `docs/system-design/api/*.spec.md` |
| `component-designs/*.md` | `docs/component-designs/*.md` (excluding DEPRECATED files) |
| `security/*.md` | `docs/security/*.md` + `docs/system-design/transport-security.design.md` + `docs/system-design/authorization.spec.md` |
| `governance/*.md` | `docs/governance/*.md` |
| `standards/*.md` | `docs/standards/*.md` |
| `sdk-manual/` | `docs/user-manual/sdk/` |
| `developer-guide/code-walkthrough.md` | `docs/developer-guide/code-walkthrough.md` |
| `hsbc-deployment/` | `infrastructure/cd/docs/` (substantive files only, not empty-stub runbooks) |
| `reference/*.md` | `docs/reference/data-pipeline.reference.md` + `docs/reference/ryugraph-*.reference.md` |

### Excluded Content (Not HSBC-Relevant)

The build script explicitly skips these files and directories. They describe our internal development infrastructure, not the platform HSBC is receiving.

#### Entire directories excluded

| Path | Reason |
|---|---|
| `docs/ux-design/` | All 6 files DEPRECATED — web UI was removed from the platform |
| `docs/plans/` | Internal planning documents, marked "not for publication" in `document.structure.md` |
| `docs/research/` | Internal research, marked "not for publication"; all 4 files describe the removed Auth0 stack or unimplemented features |
| `docs/platform/` | `depot-dev.mdx` — our CI tool configuration |
| `docs/notebooks/` | `.ipynb` files (JSON, not markdown); already rendered by the docs site |
| `docs/testing/` | Our internal test strategy (`control-plane-testing-strategy.md`) |
| `docs/user-guide/` | MkDocs navigation page (`index.md`), not content |
| `infrastructure/cd/docs/runbooks/` | All 7 files are empty `## TODO` stubs with zero content |

#### Individual files excluded from `docs/operations/`

| File | Reason |
|---|---|
| `deployment.design.md` | Describes GitHub Actions CI + ArgoCD CD + Helm values overlays — HSBC uses Jenkins + kubectl |
| `deployment-rollback-procedures.md` | Entirely based on Argo Rollouts canary strategy HSBC won't have |
| `argocd-quickstart.md` | 100% ArgoCD/Argo Rollouts content |
| `observability.design.md` | Describes our Grafana/PagerDuty/Slack setup; HSBC uses Cloud Monitoring |
| `container-registry-setup.md` | Describes GHCR as current; HSBC uses Nexus/GAR |
| `devops-implementation-plan.md` | Roadmap for our ArgoCD/GitHub Actions pipeline |
| `distroless-migration.md` | Our container migration work |
| `testing.strategy.md` | Our E2E testing framework and test pyramid |
| `e2e-testing-scenarios.md` | Our E2E test scenarios against our clusters |
| `e2e-tests.runbook.md` | Our E2E test execution procedures |

#### Individual files excluded from other directories

| File | Reason |
|---|---|
| `docs/reference/gke-configuration.reference.md` | Our GKE London dev cluster config (node pools, networking, Workload Identity) |
| `docs/component-designs/web-application.design.DEPRECATED.md` | Web application was removed from the platform |
| `docs/component-designs/e2e-tests.reference.md` | Our E2E test reference |
| `docs/solutions-architecture-overview.md` | Empty stub — every field is `*[To be completed]*` |
| `docs/process/CLAUDE.md` | AI assistant development instructions — internal tooling |
| `docs/process/DOCUMENTATION_GAP_ANALYSIS.md` | Internal quality audit from January, partially outdated |
| `docs/developer-guide/index.md` | MkDocs navigation page, not content |
| `docs/system-design/api.quick-reference.md` | Redundant subset of `api.common.spec.md` |

#### ADR exclusions

| Category | Excluded ADRs | Reason |
|---|---|---|
| UX | ADR-007, 013, 014, 015, 016 | Describe removed web UI; explicitly marked SUPERSEDED |
| Superseded | ADR-018, 020, 035 | Moved to `superseded/`; decisions overturned |
| Security | ADR-084, 085, 095 | Describe Auth0/JWT/oauth2-proxy stack removed by ADR-104/112 |
| Process | ADR-082 | CLAUDE.md AI tooling — internal dev process |
| Testing | Most of 28 testing ADRs | Internal test framework evolution (k3d, nginx ingress, Trino emulation) |
| Infrastructure | ADR-034 (Argo Rollouts), ADR-056 (OrbStack), ADR-060 (content-addressable builds), ADR-065 (Helm+ArgoCD), ADR-072 (remove local Trino), ADR-076 (Earthfile), ADR-083 (multi-env Helm values), ADR-089 (Terraform image tags), ADR-111 (OrbStack zero-dep), ADR-113 (revert GCS emulation), ADR-114 (remove Starburst emulator) | Describe our dev/test infrastructure, not HSBC's |

### Known Issues Requiring Annotation Before Handover

These files are included but contain stale sections that should be annotated:

| File | Issue |
|---|---|
| `container-security-audit.md` | Section 4.2 references internal API key removed by ADR-104 |
| `authorization.spec.md` | Related Documents still links ADR-084/085 (removed); missing ADR-112 reference |
| `api.snapshots.spec.md` | All public endpoints disabled; retained for internal data model reference |
| `security-improvements-summary.md` | Timing-attack fix may be moot after ADR-104 removed internal API key |

### Known Data Conflicts to Resolve

| Conflict | File A | File B | Notes |
|---|---|---|---|
| Alert thresholds | `observability.design.md` (excluded) | `monitoring-alerting.runbook.md` (included) | HighErrorRate: 5% vs 1%; HighLatency: 5s vs 2s. Runbook is authoritative for HSBC |
| Background job intervals | `architecture/platform-operations.md` | `service-catalogue.manual.md` | 5min vs 30s. Service catalogue is more recent (2026-04-08) |

### Integration with `make repo`

Two changes are required:

**1. Add `handover/` to `tools/repo-split/configs/documentation.yaml`:**

```yaml
files:
  # ... existing entries ...
  - src: handover
    dest: docs/handover
```

**2. Create a build script `tools/repo-split/build-handover.sh`:**

A shell script that copies files from their source locations into `handover/`, applying the inclusion/exclusion rules above. Invoked by `build-repos.sh` before copying.

### What This Does NOT Do

- Does NOT modify `mkdocs.yml` or the MkDocs navigation
- Does NOT create new documentation — only copies existing files
- Does NOT change the source of truth — `docs/` remains authoritative
- Does NOT affect any other repo-split config (only `documentation.yaml`)
- Does NOT include our development infrastructure docs (ArgoCD, OrbStack, GKE London, GitHub Actions, Argo Rollouts, GHCR, Earthly, depot.dev)

### Scope Frontmatter + ADR Allow-List (Added 2026-04-17 per ADR-149 Update §3)

Per ADR-149 Update §2's Pattern 10 finding ("demo assumptions leaking into handoff") and the Update §3 implementation, the build script now applies **content-level scope filtering** in addition to the filename allow-list above.

**`scope:` YAML frontmatter** — every markdown file under `docs/` may declare one of three values:

| `scope:` | Behaviour |
|---|---|
| `hsbc` | Copy unchanged. Default for handover-bound content. |
| `demo` | Copy with warning. Reserve for content deliberately published but demo-relevant. |
| `internal` | **Never copied.** Build refuses files with this marker even if the filename is allow-listed. |

**Inline fenced blocks** — `` marks demo-specific paragraphs inside an otherwise HSBC-scope file. `build-handover.sh` strips these blocks pre-copy via `strip_demo_fences`.

**Grep-lint** — `build-handover.sh` runs an inline grep (`grep_lint_runbook`) over the 9 ADR-128 runbooks looking for forbidden tokens (`helm`, `argocd`, `TARGET=gke-london`, `TARGET=local`, `orbstack`, `europe-west2`, `us-central1`, `github.com/sparkling-ideas`, `trivy`, `cosign`, `syft`, `grype`, `dependabot`). Exception allow-list: `helm rollback jupyter-labs` and `helm upgrade jupyter-labs` (upstream Zero-to-JupyterHub chart, ADR-128-exempt). Warnings-only in this iteration; promotion to blocking is a future sprint.

**ADR allow-list** — `copy_adrs()` copies the 17 HSBC-scope ADRs (**128-138, 140, 143, 144, 146-148**) from `docs/process/adr/` into `handover/decision-records/`. The Starlight sidebar (`packages/documentation/astro.config.*`) registers a "Decision Records" section pointing at the copied tree. All other ADRs remain excluded by default.

See [ADR-149 Update §3](--/process/adr-149-implementation-vs-documentation-drift-remediation.md) for the swarm-driven implementation log and verification steps.

---

## Consequences

**Positive:**
- Single folder containing only HSBC-relevant documentation, organised by audience
- Dynamically generated during `make repo` — always in sync with source
- Explicit exclusion list prevents internal dev docs from leaking into the handover
- HSBC team gets a clear entry point (`handover/README.md`) with role-based reading order
- HSBC CD docs (`infrastructure/cd/docs/`) are surfaced alongside the platform docs for the first time

**Negative:**
- Adds one more step to the repo-split build pipeline
- If source files are renamed/moved, the build script must be updated
- Cross-references within copied documents will point to original `docs/` paths, not `handover/` paths
- The exclusion list must be maintained as new docs are added

---

## Alternatives Considered

**1. Copy all of `docs/` wholesale**
Rejected. Contains extensive internal dev infrastructure documentation (ArgoCD, OrbStack, GKE London, GitHub Actions, Argo Rollouts) that would confuse HSBC operators and developers. Also contains deprecated content (UX design), empty stubs, and `.ipynb` files that aren't markdown.

**2. Symlinks instead of copies**
Rejected. Symlinks break in the repo-split output and don't work in Docker builds.

**3. Generate handover docs from scratch**
Rejected. The documentation already exists and is comprehensive. Copying is faster and ensures consistency.

**4. Add handover navigation to mkdocs.yml**
Out of scope. The handover folder is a static collection of markdown files for direct reading, not a new section in the documentation site.

---

## References

- [ADR-128: Operational Documentation Strategy](adr-128-operational-documentation-strategy.md) — The ops docs that form the core of the handover operations section
- [Document Structure](--/--/document.structure.md) — Canonical documentation structure definition (lists all docs including excluded ones)
- [Repo-split config](--/--/--/tools/repo-split/configs/documentation-yaml) — Documentation node build config
- [build-repos.sh](--/--/--/tools/repo-split/build-repos-sh) — Repo-split build script
