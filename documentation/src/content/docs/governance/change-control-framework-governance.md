---
title: "Change Control Framework (Deliverance)"
scope: hsbc
---

# Change Control Framework (Deliverance)

## Overview

HSBC mandates Deliverance for all CI/CD pipelines targeting production environments. Deliverance acts as a control and compliance wrapper around underlying automation tools.

## Constraints

- ALL production-impacting CI/CD workflows MUST be governed via Deliverance
- Deliverance is NON-OPTIONAL in regulated environments
- Technical execution delegated to underlying tools; governance via Deliverance

## System Role

| Layer | Tool | Responsibility |
|-------|------|----------------|
| Build execution | Jenkins | Technical build steps |
| Deployment execution | `./infrastructure/cd/deploy.sh` + `kubectl apply -f infrastructure/cd/resources/` (governed by Deliverance) | Technical deployment |
| Change initiation | Deliverance | Formal change requests |
| Change approval | Deliverance | Approval workflows, segregation of duties |
| Audit trail | Deliverance | Immutable records, SOX compliance |

## Governance Scope

Deliverance is the system of record for:
- Change initiation and approval
- Enforcement of production gating policies
- Audit trails and evidentiary compliance

## Compliance

Deliverance is a key mechanism for:
- SOX compliance
- Internal risk requirements
- Segregation of duties enforcement
- End-to-end deployment auditability
