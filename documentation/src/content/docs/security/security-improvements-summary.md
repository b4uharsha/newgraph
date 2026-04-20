---
title: "Security Improvements Summary — Superseded"
scope: hsbc
---

# Security Improvements Summary — Superseded

**Status:** Superseded (2026-04-17)

Prior revisions of this page claimed that the Graph OLAP Platform had implemented a full supply-chain security suite — CI-integrated vulnerability scanning (Trivy, Grype, Safety, TruffleHog, Gitleaks, Checkov, Kubescape), Cosign keyless image signing, Syft-generated SBOM attestations, SLSA Level 2 provenance, Binary Authorization in enforced mode, a `secrets.compare_digest` fix for `verify_internal_api_key`, automated weekly dependency lock-file refresh, and an overall "A+ (95/100)" posture.

Those claims were **not grounded in the shipped system** and have been retracted:

- The CI pipeline has Checkout → Build → Push → Deploy → Verify Rollout → Smoke Test stages and no scanning, signing, SBOM, or attestation step.
- `verify_internal_api_key` no longer exists. [ADR-104](--/process/adr/security/adr-104-database-backed-user-role-management.md) and [ADR-105](--/process/adr/security/adr-105-x-username-header-identity-with-static-default.md) removed the entire internal API key mechanism in favour of NetworkPolicy isolation; see the comment at `packages/control-plane/src/control_plane/config.py:123-124` and the module docstring at `packages/control-plane/src/control_plane/routers/internal/snapshots.py:1-5`.
- Binary Authorization is **not in scope for the HSBC handover** ([ADR-147](--/process/adr/security/adr-147-binauthz-scope.md)).
- Artifact Registry CMEK encryption is **not in scope for the HSBC handover** ([ADR-146](--/process/adr/security/adr-146-cmek-scope.md)).
- Starburst end-user credential passthrough is deferred ([ADR-148](--/process/adr/security/adr-148-starburst-credential-passthrough.md)).
- No Cosign signing, no SBOM generation, no SLSA attestation, and no registry-level vulnerability scanning or cleanup policies are configured today.
- The platform has not been audited against PCI DSS, SOC 2, ISO 27001, or GDPR. Previous compliance claims were removed.

## What is actually shipping

See [container-security-audit.md](container-security-audit.md) for the current, grounded description of:

- Distroless Chainguard Python base images for control-plane, export-worker, and falkordb-wrapper (with the ryugraph-wrapper slim-base exception documented).
- Non-root pod / container security contexts, `drop: [ALL]` capabilities, `seccompProfile: RuntimeDefault` in the Helm charts.
- NetworkPolicy-based isolation of the control-plane and graph-instances namespaces, replacing the removed internal-API shared secret.
- Azure AD authentication proxy at the ingress edge ([ADR-137](--/process/adr/security/adr-137-azure-ad-auth-proxy.md)).
- Owner-based access control for graph nodes ([ADR-144](--/process/adr/security/adr-144-graph-node-owner-access-control.md)).
- An explicit Gaps / Future Work section listing every missing supply-chain control.

## References

- [container-security-audit.md](container-security-audit.md) — current audit
- [transport-security.design.md](--/system-design/transport-security.design.md) — transport-layer configuration
- [authorization.spec.md](--/system-design/authorization.spec.md) — authorization model
- [ADR-104](--/process/adr/security/adr-104-database-backed-user-role-management.md)
- [ADR-105](--/process/adr/security/adr-105-x-username-header-identity-with-static-default.md)
- [ADR-137](--/process/adr/security/adr-137-azure-ad-auth-proxy.md)
- [ADR-144](--/process/adr/security/adr-144-graph-node-owner-access-control.md)
- [ADR-146](--/process/adr/security/adr-146-cmek-scope.md)
- [ADR-147](--/process/adr/security/adr-147-binauthz-scope.md)
- [ADR-148](--/process/adr/security/adr-148-starburst-credential-passthrough.md)
