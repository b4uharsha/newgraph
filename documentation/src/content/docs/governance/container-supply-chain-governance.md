---
title: "Container Image Supply Chain"
scope: hsbc
---

# Container Image Supply Chain

## What this handover covers

This document describes how **this demo's** container images are produced and tagged by the build pipeline we ship. HSBC's wider image-governance controls (approval workflow, scanning tooling, golden-image provenance, vulnerability SLAs, vendor-image onboarding) are HSBC-internal and are **out of scope for this handover** — HSBC's own standards apply when these repositories are onboarded.

## Build pipeline (what we actually run)

Each service repository ships a `Jenkinsfile` that delegates to an HSBC-internal shared library:

```groovy
@Library('container-shared-library@311') _
gke_CI()
```

All technical build steps (checkout, Docker build, image push, deploy) are executed by that shared library on HSBC Jenkins. This repo owns only:

- The `Dockerfile` for each service
- The `Jenkinsfile` entry point above
- Build helpers under `tools/repo-split/` that generate per-repo artefacts

## Base images

- All service Dockerfiles pull base images and language packages (npm, pip, apt) from the **HSBC Nexus proxy** — they do not reference public registries at runtime build. See the per-service Dockerfiles under `tools/repo-split/templates/` for the exact `FROM` lines.
- No public-registry pulls are introduced by this repo.

## Image tagging

- Images are tagged by **content hash** — the same source tree always produces the same tag, so pushes are idempotent and image identity is reproducible.
- Helm values files are updated to reference the pushed tag as part of the push stage.
- The `algo` graph extension is **baked into the FalkorDB wrapper image at build time** rather than downloaded at runtime (ADR-138). The vendored binary is committed to the repo with its `sha256` recorded in `tools/repo-split/vendor/README.md`.

## Registry

- Runtime images are pushed to HSBC Google Artifact Registry inside the HSBC GCP project provided for this workload.
- The specific GAR path is configured per environment by HSBC infra; this repo does not assume a particular project ID.

## What this handover does NOT define

The following are HSBC-internal concerns and are intentionally **not** specified here:

- Container vulnerability scanning tooling, schedules, or severity SLAs
- Image-approval workflows, golden-image registration, or vendor-image onboarding
- Binary Authorization / admission policies (deferred — see ADR-147)
- Image signing or attestation requirements
- Patching cadence for base images

HSBC's existing enterprise standards for each of the above apply once these services are onboarded; nothing in this repo overrides them.

## Related ADRs

- **ADR-138** — Vendor algo extension binary in git (reproducible builds, no runtime download)
- **ADR-147** — Binary Authorization scope (deferred for this demo)
- **ADR-143** — Documentation accuracy review (why this file is deliberately minimal)
