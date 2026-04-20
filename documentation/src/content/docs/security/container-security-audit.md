---
title: "Container Security Audit"
scope: hsbc
---

# Container Security Audit

**Date:** 2026-04-17
**Scope:** Docker images in `docker/`, CI pipeline, Helm charts in `infrastructure/helm/charts/`, Terraform modules in `infrastructure/terraform/`, Python source in `packages/control-plane/`, `packages/export-worker/`
**Standards referenced:** CIS Docker Benchmark, NIST SP 800-190

> **Scope note.** This document describes what is **actually shipping** in this repository as of the date above. Claims in prior revisions that referenced vulnerability scanning (Trivy/Grype/Syft), Cosign signing, SBOM attestation, SLSA-L2 provenance, or enforced Binary Authorization were not grounded in the shipped system and have been removed. Remaining gaps are listed explicitly in section 5 so operators are not misled.

---

## 1. Executive Summary

The platform uses distroless Chainguard Python base images for three of the four service images, runs as non-root by default, drops all Linux capabilities, and isolates internal APIs with Kubernetes NetworkPolicy rather than a shared secret (per [ADR-104](--/process/adr/security/adr-104-database-backed-user-role-management.md) and [ADR-105](--/process/adr/security/adr-105-x-username-header-identity-with-static-default.md)).

Strengths (verified in-tree):

- Multi-stage builds for all four service Dockerfiles.
- Chainguard distroless runtime stage for control-plane, export-worker, and falkordb-wrapper.
- Non-root user enforced at both pod and container level in the Helm charts.
- `drop: [ALL]` capabilities and `allowPrivilegeEscalation: false` in chart values.
- NetworkPolicy-based isolation of control-plane and graph-instances namespaces.
- Internal-API shared-secret authentication removed — replaced with network-level trust.
- Azure AD authentication proxy at the ingress edge (see [ADR-137](--/process/adr/security/adr-137-azure-ad-auth-proxy.md)).

Gaps (the deployed system does **not** have these today — see section 5):

- No automated container or dependency vulnerability scanning in CI.
- No image signing (Cosign or otherwise) and no SBOM generation.
- No SLSA provenance attestation.
- Binary Authorization is not in scope for the HSBC handover ([ADR-147](--/process/adr/security/adr-147-binauthz-scope.md)).
- Customer-managed encryption keys (CMEK) for Artifact Registry / other GCP resources are not in scope for the HSBC handover ([ADR-146](--/process/adr/security/adr-146-cmek-scope.md)).
- `readOnlyRootFilesystem: false` in both control-plane and export-worker charts (Python `.pyc` cache writes).
- `ryugraph-wrapper` uses `python:3.12-slim` rather than Chainguard because ryugraph does not publish manylinux wheels for Python 3.13+.

---

## 2. Container Images

All images are built from the monorepo root against the Dockerfiles in `docker/`. There is no per-package Dockerfile (i.e. `packages/*/Dockerfile` does not exist).

| Image | Dockerfile | Base (runtime stage) | Non-root | Shell in runtime |
|---|---|---|---|---|
| control-plane | `docker/control-plane.Dockerfile` | `cgr.dev/chainguard/python:latest` | yes (UID 65532) | no |
| export-worker | `docker/export-worker.Dockerfile` | `cgr.dev/chainguard/python:latest` | yes (UID 65532) | no |
| falkordb-wrapper | `docker/falkordb-wrapper.Dockerfile` | `cgr.dev/chainguard/python:latest` | yes (UID 65532) | no |
| ryugraph-wrapper | `docker/ryugraph-wrapper.Dockerfile` | `python:3.12-slim` | yes (chart-enforced) | yes |
| e2e-tests | `docker/e2e-tests.Dockerfile` | `cgr.dev/chainguard/python:latest-dev` | n/a (test image) | — |

### 2.1 Chainguard distroless runtime (control-plane, export-worker, falkordb-wrapper)

- Builder stage uses `cgr.dev/chainguard/python:latest-dev` (has `pip`, shell, build tools). Example: `docker/control-plane.Dockerfile:12`.
- Runtime stage uses `cgr.dev/chainguard/python:latest` (no shell, no `pip`, no `curl`). Example: `docker/control-plane.Dockerfile:66`, `docker/export-worker.Dockerfile:71`, `docker/falkordb-wrapper.Dockerfile:122`.
- Runs as Chainguard's default nonroot user (UID 65532); `COPY --chown=nonroot:nonroot` is used for both the virtualenv and application source.
- `HEALTHCHECK` directives are deliberately absent — the runtime image has no `curl`, `pgrep`, or shell, so image-level healthchecks are handled by Kubernetes liveness/readiness probes instead. This is documented in the Dockerfiles (for example `docker/control-plane.Dockerfile:111-116`, `docker/falkordb-wrapper.Dockerfile:172-177`).
- OCI labels are set from `BUILD_DATE`, `VCS_REF`, and `VERSION` build args (`docker/control-plane.Dockerfile:73-83`).

### 2.2 ryugraph-wrapper (python:3.12-slim)

`docker/ryugraph-wrapper.Dockerfile:1-10` documents why Chainguard is not used: the `ryugraph` package does not publish manylinux wheels for Python 3.13+, and Chainguard `python:latest` is Python 3.14. The chart-level `runAsNonRoot` setting still applies to the running container, but the image itself is not distroless.

### 2.3 Supply-chain dependency handling

- `graph-olap-schemas` is installed from the monorepo (`packages/graph-olap-schemas/`) in every image — see `docker/control-plane.Dockerfile:34`, `docker/export-worker.Dockerfile:40`, `docker/falkordb-wrapper.Dockerfile:37`, `docker/ryugraph-wrapper.Dockerfile:33`.
- export-worker, falkordb-wrapper, and ryugraph-wrapper honour a `requirements.lock` file when present (e.g. `docker/export-worker.Dockerfile:50-66`). control-plane installs an explicit, hard-coded dependency list inside the Dockerfile (`docker/control-plane.Dockerfile:44-61`) for Docker-build reproducibility.

---

## 3. CI/CD Pipeline

CI builds the container images, pushes them to the internal registry, and deploys them to the target cluster. The pipeline does **not** include vulnerability scanning, SBOM generation, image signing, or attestation attachment; those are listed as gaps in section 5.

Rollback on deployment failure is handled by running `kubectl rollout undo` against the affected deployments.

No long-lived service-account keys are mounted into the CI agent; cluster credentials are resolved via Workload Identity.

---

## 4. Runtime Hardening (Helm charts)

### 4.1 Pod and container security context

`infrastructure/helm/charts/control-plane/values.yaml:45-61`:

```yaml
podSecurityContext:
  runAsUser: 65532
  runAsGroup: 65532
  runAsNonRoot: true
  fsGroup: 65532
  seccompProfile:
    type: RuntimeDefault

securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
  # readOnlyRootFilesystem disabled - Python needs to write .pyc cache files
  readOnlyRootFilesystem: false
```

The same block is present in `infrastructure/helm/charts/export-worker/values.yaml:44-57`. The deployment template wires these into the pod and container via `{{- toYaml .Values.podSecurityContext | nindent 8 }}` and `{{- toYaml .Values.securityContext | nindent 12 }}` (`infrastructure/helm/charts/control-plane/templates/deployment.yaml:29-46`).

### 4.2 NetworkPolicy isolation

`infrastructure/helm/charts/system/templates/network-policies.yaml` ships several policies that are enabled via chart values:

- **Default-deny ingress** for both the control-plane namespace and the graph-instances namespace (`network-policies.yaml:1-30`).
- **Allow DNS** egress to `kube-system` on UDP/TCP 53 (`network-policies.yaml:32-80`).
- **Allow control-plane to graph-instances** on TCP 8080 and 9090, scoped by namespaceSelector (`network-policies.yaml:82-132`).
- **Allow ingress controller to control-plane** on TCP 8080 (`network-policies.yaml:134-158`).
- **Allow Cloud SQL egress** to a configurable CIDR on TCP 5432 (`network-policies.yaml:160-181`).
- **Allow Google APIs egress** to `169.254.169.254/32` (metadata server) and `199.36.153.8/30` (Private Google Access) on 80/443 (`network-policies.yaml:183-241`).

These policies are what now provides the "internal API" isolation that used to be handled by a shared-secret header — see section 4.3.

### 4.3 Internal-API authentication (removed)

Prior revisions of this document described a `verify_internal_api_key` FastAPI dependency protected by `secrets.compare_digest`. That function no longer exists. [ADR-104](--/process/adr/security/adr-104-database-backed-user-role-management.md) and [ADR-105](--/process/adr/security/adr-105-x-username-header-identity-with-static-default.md) removed it entirely:

- `packages/control-plane/src/control_plane/config.py:123-124` explicitly documents the removal: *"Internal API key removed (ADR-104/105). Internal endpoints are protected by network policy, not by a shared secret."*
- `packages/control-plane/src/control_plane/routers/internal/snapshots.py:1-5` repeats the rationale at the module level.

Internal endpoints are now reachable only from pods permitted by the NetworkPolicies above.

### 4.4 Edge authentication (Azure AD auth proxy)

External ingress paths are protected by the Azure AD authentication proxy described in [ADR-137](--/process/adr/security/adr-137-azure-ad-auth-proxy.md). The proxy terminates the Azure AD OIDC flow and forwards authenticated requests to the control plane with the identity headers (`X-Username`, `X-User-Role`) that [ADR-105](--/process/adr/security/adr-105-x-username-header-identity-with-static-default.md) requires.

### 4.5 Resource-level authorization (ADR-144 owner ACL)

Owner-based access control for graph nodes is enforced by the control plane per [ADR-144](--/process/adr/security/adr-144-graph-node-owner-access-control.md). See [authorization.spec.md](--/system-design/authorization.spec.md) for the full role/permission matrix.

---

## 5. Gaps / Future Work

The following controls are **not** present in the shipped system today. They are listed here so operators are not surprised.

| Gap | Current state | Reference |
|---|---|---|
| Container vulnerability scanning in CI | Not implemented. | — |
| Dependency vulnerability scanning | Not implemented. | — |
| SBOM generation (Syft, CycloneDX, SPDX) | Not implemented. | — |
| Image signing (Cosign keyless or keyed) | Not implemented. | — |
| SLSA provenance attestation | Not implemented. | — |
| Binary Authorization | **Not in scope for the HSBC handover** — the platform does not claim Binauthz enforcement. | [ADR-147](--/process/adr/security/adr-147-binauthz-scope.md) |
| Artifact Registry CMEK encryption | **Not in scope for the HSBC handover** — the platform does not claim CMEK coverage. | [ADR-146](--/process/adr/security/adr-146-cmek-scope.md) |
| Starburst end-user credential passthrough | Deferred — queries run under a single service account. | [ADR-148](--/process/adr/security/adr-148-starburst-credential-passthrough.md) |
| Read-only root filesystem | Disabled because Python writes `.pyc` cache files. | `infrastructure/helm/charts/control-plane/values.yaml:60-61`, `export-worker/values.yaml:55-57` |
| `.dockerignore` files for each image | Not present at the monorepo root or per-package. The build context is the repo root, so a root-level `.dockerignore` would have broad impact and needs design. | — |
| `ryugraph-wrapper` distroless migration | Blocked on upstream `ryugraph` wheels for Python 3.13+. | `docker/ryugraph-wrapper.Dockerfile:1-10` |

---

## 6. Compliance Mapping (honest view)

Only controls that are actually present are marked as Pass. Items listed under section 5 are marked as Gap. This section maps **technical controls** against published guidance; it does **not** represent a formal certification or audit result.

### CIS Docker Benchmark (selected)

| Rule | Requirement | Status |
|---|---|---|
| 4.1 | Create non-root user for container | Pass — Chainguard default UID 65532 + chart-enforced `runAsNonRoot`. |
| 4.2 | Use trusted base images | Pass — Chainguard for three services; `python:3.12-slim` for ryugraph-wrapper with documented rationale. |
| 4.3 | Do not install unnecessary packages | Pass — multi-stage builds; runtime stage has no pip/shell for Chainguard images. |
| 4.5 | Enable Content Trust | Gap — no image signing. |
| 4.6 | Add HEALTHCHECK | n/a at image level — Chainguard has no shell; health is via K8s probes. |
| 4.7 | Don't use `apt-get update` alone | Pass — combined with install in builder stages. |
| 4.9 | Use COPY not ADD | Pass — only `COPY` used. |
| 4.10 | No secrets in images | Pass — secrets injected via env from K8s Secrets. |
| 5.3 | Restrict Linux kernel capabilities | Pass — `drop: [ALL]` in chart values. |
| 5.4 | Don't use privileged containers | Pass — application pods are unprivileged. |
| 5.12 | Mount root as read-only | Gap — see section 5. |
| 5.25 | Restrict container syscalls | Pass — `seccompProfile.type: RuntimeDefault`. |

### NIST SP 800-190 (selected)

| Control | Status |
|---|---|
| Image hardening (minimal base, non-root) | Pass (Chainguard) / partial (ryugraph-wrapper slim). |
| Image scanning | Gap. |
| Image signing | Gap. |
| Registry vulnerability scanning | Gap. |
| Orchestrator / node security | Pass — GKE managed nodes, Workload Identity. |
| Container runtime hardening (capabilities, seccomp) | Pass. |
| Read-only root filesystem | Gap. |

---

## 7. References

- [ADR-104 — Database-backed user and role management](--/process/adr/security/adr-104-database-backed-user-role-management.md)
- [ADR-105 — X-Username header identity with static default](--/process/adr/security/adr-105-x-username-header-identity-with-static-default.md)
- [ADR-137 — Azure AD auth proxy](--/process/adr/security/adr-137-azure-ad-auth-proxy.md)
- [ADR-144 — Graph-node owner access control](--/process/adr/security/adr-144-graph-node-owner-access-control.md)
- [ADR-146 — CMEK scope](--/process/adr/security/adr-146-cmek-scope.md)
- [ADR-147 — Binary Authorization scope](--/process/adr/security/adr-147-binauthz-scope.md)
- [ADR-148 — Starburst credential passthrough](--/process/adr/security/adr-148-starburst-credential-passthrough.md)
- `docker/*.Dockerfile` — image definitions
- `infrastructure/helm/charts/control-plane/values.yaml`, `export-worker/values.yaml` — security contexts
- `infrastructure/helm/charts/system/templates/network-policies.yaml` — NetworkPolicy isolation
