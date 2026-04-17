---
title: "Container Build Standards"
scope: hsbc
---

# Container Build Standards

## Platform Architecture: AMD64 Only

**All container images MUST be built for `linux/amd64`.**

### Why AMD64?

1. **GKE Compatibility**: Google Kubernetes Engine runs on AMD64 (x86_64) nodes
2. **Consistency**: Same image runs locally and in production
3. **No "Works on My Machine"**: Eliminates architecture-related deployment failures

### What Happens Without AMD64?

```
exec /usr/bin/tini: exec format error
```

This error occurs when an ARM64 image runs on an AMD64 node. The binary format is incompatible.

### Local Development on macOS ARM64 (Apple Silicon)

Docker Desktop on Apple Silicon includes Rosetta 2 emulation. AMD64 containers run with ~10-20% performance overhead, but this ensures:

- What you test locally = what runs in production
- No surprise failures on deployment
- Consistent behavior across all environments

**Do NOT** create separate "local" vs "cloud" builds. This causes drift.

## Earthfile Requirements

Every `FROM` statement using an external image MUST include `--platform=linux/amd64`:

```earthfile
# CORRECT
FROM --platform=linux/amd64 python:3.12-slim
FROM --platform=linux/amd64 quay.io/jupyter/minimal-notebook:python-3.11
FROM --platform=linux/amd64 busybox

# WRONG - will default to host architecture
FROM python:3.12-slim
FROM quay.io/jupyter/minimal-notebook:python-3.11
```

Internal targets that use `FROM +target` inherit the platform from their base.

## Build Validation

The `build-smart.sh` script includes automatic architecture validation:

```bash
# After building, validates the image is AMD64
validate_image_arch "$image"
```

Manual validation:

```bash
./tools/local-dev/scripts/validate-image-arch.sh <image:tag>
```

## Quick Reference

| Question | Answer |
|----------|--------|
| What platform for all images? | `linux/amd64` |
| Can I build ARM64 for faster local builds? | **NO** |
| Can I skip `--platform` on FROM? | **NO** |
| Do macOS ARM64 Macs work? | Yes, via Rosetta emulation |
| Is there a validation script? | Yes: `validate-image-arch.sh` |

---

## Content-Addressable Builds

**Reference:** [ADR-076: Earthfile Build System Modernization](--/process/adr/infrastructure/adr-076-earthfile-build-system-modernization.md)

Every image supports content-addressable tagging via the `TAG` argument:

```dockerfile
ARG TAG=latest
SAVE IMAGE --push ${REGISTRY}control-plane:${TAG}
```

### Usage

```bash
# Build with content hash
earthly +control-plane --TAG=abc123def

# Build with git SHA
earthly +control-plane --TAG=$(git rev-parse --short HEAD)

# Build with staleness detection
SHA=$(./tools/local-dev/scripts/get-component-hash.sh control-plane)
earthly +control-plane --TAG=$SHA
```

### Benefits

- **Immutability** - Same hash = same image content
- **Cache optimization** - Skip rebuild if hash matches deployed image
- **Auditability** - Tag traces back to exact source code

---

## Earthfile Target Conventions

### Standard Targets

| Target | Purpose | Size |
|--------|---------|------|
| `+control-plane` | API server | ~200MB |
| `+export-worker` | Snapshot export jobs | ~200MB |
| `+ryugraph-wrapper` | Ryugraph proxy | ~400MB |
| `+falkordb-wrapper` | FalkorDB proxy | ~400MB |
| `+jupyter-labs` | JupyterHub user image | ~800MB |
| `+notebook-sync` | Git sync init container | ~50MB |
| `+e2e-test` | Standalone test runner | ~500MB |

### Meta Targets

| Target | Purpose |
|--------|---------|
| `+cloud-all` | Build all AMD64 images |
| `+cloud-all-push` | Build and push all images |
| `+e2e-test-build` | Build test artifacts only |

### Target Pattern

Every production target follows this pattern:

```dockerfile
+component-name:
    FROM --platform=linux/amd64 python:3.12-slim

    # Build steps...

    ARG TAG=latest
    ARG REGISTRY=
    SAVE IMAGE --push ${REGISTRY}component-name:${TAG}
```

---

## Related Files

- `/Earthfile` - Build configuration with platform enforcement
- `/tools/local-dev/scripts/validate-image-arch.sh` - Architecture validator
- `/tools/local-dev/scripts/build-smart.sh` - Build script with validation
- `/tools/local-dev/scripts/get-component-hash.sh` - Content hash calculation
