---
title: "Container Image Supply Chain Governance"
scope: hsbc
---

# Container Image Supply Chain Governance

## Overview

All container images for Graph OLAP Platform workloads are sourced exclusively from private Google Artifact Registry (GAR). No public container images are referenced at runtime.

## Constraints

- All images MUST be sourced from private GAR
- External images introduced ONLY via Image Acquisition Process (IAP)
- Images MUST have CyberFlow approval before use

## Systems

| System | Role |
|--------|------|
| **CyberFlow** | Governance and approval orchestration (HSBC internal) |
| **Aqua Security** | Enterprise container security scanning |
| **HSBC Nexus** | Golden image repository, system of record |
| **Google Artifact Registry** | Runtime registry for GCP workloads |

## Image Acquisition Process (IAP)

External or vendor images are introduced via the IAP:

1. **Request** - Submitted via CyberFlow
2. **Scan** - Aqua Security performs container scanning
3. **Approve** - ITSO approval based on security assessment
4. **Store** - Approved image stored in HSBC Nexus (immutable, auditable)
5. **Promote** - Controlled pipeline promotes to private GAR
6. **Pull** - GKE workloads pull from GAR using scoped service accounts

## Governance Model

- **CyberFlow** acts as governance and control layer
- **Nexus** provides immutability, provenance, and auditability
- **GAR** functions solely as runtime registry (not system of record)
- Image promotion, patching, and rotation follow the same controlled lifecycle
