---
title: "Container Build Standards"
scope: hsbc
---

<!-- Verified against Makefile on 2026-04-20 -->

# Container Build Standards

This document describes how service container images are built and tagged in the HSBC Graph OLAP Platform. Images are produced by Jenkins from each service's Dockerfile and pushed to the HSBC-approved internal registry.

## Table of Contents

1. [Platform Architecture](#platform-architecture)
2. [Dockerfile Conventions](#dockerfile-conventions)
3. [Image Tagging](#image-tagging)
4. [Jenkins Build Pipeline](#jenkins-build-pipeline)
5. [Services and Images](#services-and-images)

## Platform Architecture

### linux/amd64 Only

All service images are built for `linux/amd64`. The target clusters run on x86_64 nodes, and producing a single architecture avoids drift between build and runtime.

If a non-amd64 image ever reaches a node, container startup fails with:

```
exec /usr/bin/tini: exec format error
```

### Enforcing the Platform

Every Dockerfile pins the base image platform explicitly:

```dockerfile
FROM --platform=linux/amd64 python:3.12-slim
```

Pin the platform on every `FROM` that pulls an external image. Do not rely on the builder's host architecture.

## Dockerfile Conventions

Every service Dockerfile should:

1. Pin a specific base image digest or minor version (never `:latest`)
2. Set `--platform=linux/amd64` on all external `FROM` lines
3. Use a non-root runtime user
4. Keep the final image minimal (multi-stage builds where practical)
5. Expose only the ports the service actually listens on
6. Set `ENTRYPOINT` / `CMD` explicitly (no shell-form wrappers)

**Base-image exception:** `ryugraph-wrapper` uses `python:3.12-slim` rather than a distroless base because the Kuzu wheel requires glibc-linked native extensions. The rationale is pinned in the wrapper's Dockerfile.

Example skeleton:

```dockerfile
FROM --platform=linux/amd64 python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

COPY src/ ./src/

FROM --platform=linux/amd64 python:3.12-slim AS runtime

RUN useradd --system --uid 10001 --create-home app
WORKDIR /app
COPY --from=builder /build /app

USER 10001
EXPOSE 8080
ENTRYPOINT ["python", "-m", "control_plane"]
```

## Image Tagging

Images are tagged with a **content-hash** derived from the Dockerfile and its build context. This produces immutable, content-addressable tags that identify the exact bytes of every layer, independent of the git commit that happens to be checked out:

```
<registry>/graph-olap/control-plane:hash-<content-sha>
```

Rules:

- `make build` (run from the repo root) produces images tagged `hash-<content-sha>` — the content-addressable build pattern used by the platform. Identical inputs yield identical tags, so rebuilds are no-ops and promotions never mutate a tag's contents.
- Never re-tag or overwrite an existing `hash-*` tag.
- Promote between environments by referencing the same `hash-*` tag, not by re-building.
- `latest` is not used in any environment.
- The `hash-*` tagging scheme is the authoritative contract shared with [`governance/container-supply-chain-governance.md`](--/governance/container-supply-chain-governance.md), which mandates content-hash tags end-to-end.

## Jenkins Build Pipeline

Service images are built by Jenkins. Pipeline stages invoke the same `make build` targets developers use locally, and push the resulting `hash-*` tags to the target Artifact Registry:

```groovy
stage('Build control-plane image') {
    steps {
        sh 'make build SVC=control-plane'
        sh 'make push TARGET=<artifact-registry> SVC=control-plane'
    }
}
```

The image tag pushed here is `hash-<content-sha>` produced by the Makefile; Jenkins does not compute or pass a git SHA. The detailed Docker invocation, platform pinning, and push wiring live in the shared Jenkins `container-shared-library` — pipelines call that library rather than hand-rolling `docker build` / `docker push` commands.

Notes:

- The target Artifact Registry is configured per environment as a Jenkins environment variable or via the shared library.
- Authentication to the registry is handled by Jenkins credentials, not by developer machines.
- Each service has its own Dockerfile and its own pipeline stage, but all stages delegate to the shared library for consistency.
- Build context is scoped to each service directory (enforced by `make build SVC=...`) to keep images small and builds cacheable.

## Services and Images

The platform publishes the following images. Each has its own Dockerfile and independent build stage:

| Image | Purpose |
|-------|---------|
| `control-plane` | API server for mappings, snapshots, and exports |
| `export-worker` | Snapshot export job runner |
| `ryugraph-wrapper` | Ryugraph proxy service |
| `falkordb-wrapper` | FalkorDB proxy service |
| `jupyter-labs` | JupyterHub user image |
| `notebook-sync` | Notebook git-sync init container |

Each image is built independently so a change to one service does not invalidate the others' caches.
