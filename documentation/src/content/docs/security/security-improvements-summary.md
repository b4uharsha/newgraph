---
title: "Security Improvements Summary — Superseded"
scope: hsbc
---

# Security Improvements Summary — Superseded

**Status:** Superseded (2026-04-17)

Prior revisions of this page claimed that the Graph OLAP Platform had implemented a full supply-chain security suite — GitHub Actions vulnerability scanning (Trivy, Grype, Safety, TruffleHog, Gitleaks, Checkov, Kubescape), Cosign keyless image signing, Syft-generated SBOM attestations, SLSA Level 2 provenance, Binary Authorization in enforced mode, a `secrets.compare_digest` fix for `verify_internal_api_key`, a weekly Dependabot + `pip-compile` lock-file workflow, and an overall "A+ (95/100)" posture.

Those claims were **not grounded in the shipped system** and have been retracted:

- There is no `.github/` directory at the repo root. CI is Jenkins (`Jenkinsfile`), which has Checkout → Build → Push → Deploy → Verify Rollout → Smoke Test stages and no scanning, signing, SBOM, or attestation step.
- `verify_internal_api_key` no longer exists. [ADR-104](--/process/adr/security/adr-104-database-backed-user-role-management.md) and [ADR-105](--/process/adr/security/adr-105-x-username-header-identity-with-static-default.md) removed the entire internal API key mechanism in favour of NetworkPolicy isolation; see the comment at `packages/control-plane/src/control_plane/config.py:123-124` and the module docstring at `packages/control-plane/src/control_plane/routers/internal/snapshots.py:1-5`.
- Binary Authorization is not deployed to the `gcp-london-demo` environment at all. The `staging` and `production` environments instantiate the module only in `DRYRUN_AUDIT_LOG_ONLY` mode (`infrastructure/terraform/environments/staging/main.tf:303-322`, `production/main.tf:217-233`).
- No Cosign signing, no SBOM generation, no SLSA attestation, and no registry-level vulnerability scanning or cleanup policies are configured today.

## What is actually shipping

See [container-security-audit.md](container-security-audit.md) for the current, grounded description of:

- Distroless Chainguard Python base images for control-plane, export-worker, and falkordb-wrapper (with the ryugraph-wrapper slim-base exception documented).
- Non-root pod / container security contexts, `drop: [ALL]` capabilities, `seccompProfile: RuntimeDefault` in the Helm charts.
- NetworkPolicy-based isolation of the control-plane and graph-instances namespaces, replacing the removed internal-API shared secret.
- Jenkins CI pipeline that builds, pushes, and deploys via `kubectl set image` with `rollout undo` on failure.
- An explicit Gaps / Future Work section listing every missing supply-chain control (image scanning, signing, SBOM, SLSA provenance, Binary Authorization enforcement, read-only root filesystem).

## References

- [container-security-audit.md](container-security-audit.md) — current audit
- [ADR-104](--/process/adr/security/adr-104-database-backed-user-role-management.md)
- [ADR-105](--/process/adr/security/adr-105-x-username-header-identity-with-static-default.md)
