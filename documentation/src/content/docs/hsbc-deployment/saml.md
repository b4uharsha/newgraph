---
title: "SAML / SSO Integration Status"
sidebar:
  order: 3
---

## Current State

Authentication uses **X-Username header** passed by the SDK. The control-plane
performs a database role lookup to determine user permissions.

JWT/SAML integration was planned (ADR-098) but deferred. The current model
(ADR-104, ADR-105) is simpler and sufficient for the Dataproc -> API path
where network-level trust exists.

## Open Questions

- Will HSBC require SAML SSO for the API endpoint?
- Is X-Username sufficient given the ILB + NetworkPolicy boundary?
