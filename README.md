# Graph OLAP Platform — Build Packages

This repository contains the per-service build packages for the Graph OLAP Platform. Each directory is a self-contained service with its own `Dockerfile`, `Jenkinsfile`, and `Makefile` — ready to be built and deployed independently via Jenkins `gke_CI()`.

## Repositories

| Directory | Type | Description |
|-----------|------|-------------|
| `control-plane` | Container | Central API — manages instances, mappings, snapshots, exports |
| `export-worker` | Container | Async job worker — exports graph data via Starburst |
| `ryugraph-wrapper` | Container | RyuGraph database wrapper — Cypher query interface |
| `falkordb-wrapper` | Container | FalkorDB database wrapper — Cypher query interface |
| `wrapper-proxy` | Container | Nginx reverse proxy — path-based routing to wrapper pods |
| `documentation` | Container | Astro/Starlight documentation site (serves static HTML via nginx) |
| `e2e-tests` | Container | End-to-end test runner — use this to run E2E tests as a containerised job inside GKE |
| `e2e` | Notebooks | E2E test notebooks — use this if you just need the raw notebooks to run manually or via Jupyter. Both options work for E2E validation |
| `graph-olap-schemas` | Python Library | Shared Pydantic schemas (publish to Nexus before building containers) |
| `graph-olap-sdk` | Python Library | Python SDK for Jupyter notebook integration (publish to Nexus before building containers) |

## Prerequisites

The following must be available on the Jenkins build agent or build VM. All packages are available in the HSBC Nexus.

| Tool | Version | Purpose |
|------|---------|---------|
| Node.js | >= 22 | Documentation site build (Astro/Starlight) |
| Python | >= 3.12 | All Python services and libraries |
| Docker | any recent | Container image builds |
| npm | ships with Node 22 | Documentation dependencies |
| pandoc | any recent | Operational docs HTML generation |

**Node.js 10 is not supported.** The documentation build uses ES module syntax (`import from 'node:fs'`) which requires Node >= 14.18, and Astro 6 enforces `engines.node >= 22.12.0`. See https://nodejs.org/en/about/previous-releases for Node release lifecycle.

## Build Order

Python libraries must be published to Nexus **before** container images can build, since containers `pip install` the libraries from Nexus at image build time.

```
Phase 1 (libraries — publish to Nexus):
  1. graph-olap-schemas
  2. graph-olap-sdk

Phase 2 (containers — build + push to GCR):
  3. control-plane
  4. export-worker
  5. ryugraph-wrapper
  6. falkordb-wrapper
  7. wrapper-proxy
  8. documentation
  9. e2e-tests
```

## Building

Each service has a `Jenkinsfile` that calls `gke_CI()` from the shared library. Jenkins handles the full pipeline: build image, run tests, push to GCR.

To build manually (for testing):

```bash
cd <service-directory>
make build    # Docker build
make test     # Run tests
make push     # Push to GCR
```

## Documentation Service

The documentation site was migrated from MkDocs (Python) to **Astro/Starlight** (Node.js). The `documentation/Dockerfile` installs Node 22 inside the container and produces a static HTML site served by nginx on port 3000. Jenkins agents do not need Node installed — the Dockerfile handles everything.

## Notes

- Each service's `build/` directory contains HSBC-specific build assets (certificates, trust store)
- The `vendor/` directory in `ryugraph-wrapper` contains the pre-extracted algo extension binary — no external registry access (`ghcr.io`) is required
- All container images run as non-root user (uid 1009 / `glh`)
- Container images are based on `nexus3.systems.uk.hsbc:18096/com/hsbc/group/itid/es/dc/ubuntu/gcr-ubuntu-2404:latest`
