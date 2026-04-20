---
title: "Transport Security Design"
scope: hsbc
---

# Transport Security Design

## Overview

This document describes the transport-layer security configuration for the Graph OLAP Platform as it is actually deployed. It covers TLS termination at the ingress, TLS to managed services (Cloud SQL, GCS, Starburst), and the Cilium / Dataplane V2 configuration on GKE.

> **Scope note.** Previous revisions of this page made broad compliance claims (PCI DSS, SOC 2, ISO 27001, GDPR) and described security controls that are not implemented in the shipped system. Those claims were not grounded in code or Terraform and have been removed. This document now only describes what is configured in the repository; gaps are listed at the end.

---

## 1. External Traffic (Internet to GKE ingress)

External HTTPS is terminated by the nginx ingress controller in the cluster. Certificates are provisioned and renewed by GKE Managed Certificates; TLS 1.2+ is used.

Relevant values (see `infrastructure/helm/charts/control-plane/values.yaml` and the environment-specific overlays):

```yaml
ingress:
  enabled: true
  tls:
    - secretName: graph-olap-tls
      hosts:
        - <HSBC_API_HOST>
```

The Azure AD authentication proxy described in [ADR-137](--/process/adr/security/adr-137-azure-ad-auth-proxy.md) sits behind the ingress and handles user authentication before requests reach the control plane.

Ingress allow-listing is applied via the `nginx.ingress.kubernetes.io/whitelist-source-range` annotation in the HSBC environment Terraform.

---

## 2. Database Connections (Cloud SQL)

Cloud SQL for PostgreSQL is configured with SSL required and private IP only (`infrastructure/terraform/modules/cloudsql/main.tf`):

```terraform
ip_configuration {
  require_ssl  = true
  ipv4_enabled = false
}
```

The application connection string uses `sslmode=require` with Google-managed server certificates.

---

## 3. Cloud Storage (GCS)

All GCS operations use HTTPS via the Google Cloud Storage SDK. No plaintext transport is configured.

---

## 4. Starburst (External query engine)

Starburst is reached over HTTPS using the URL configured in each service's environment. Per [ADR-148](--/process/adr/security/adr-148-starburst-credential-passthrough.md), end-user credential passthrough to Starburst is **deferred** — the current deployment uses a single service account for Starburst queries, not per-user delegation.

---

## 5. Intra-Cluster Traffic (Pod-to-pod)

The cluster uses GKE Dataplane V2 (Cilium-based). See `infrastructure/terraform/modules/gke/main.tf`:

```terraform
resource "google_container_cluster" "primary" {
  datapath_provider = "ADVANCED_DATAPATH"

  addons_config {
    network_policy_config {
      disabled = false
    }
  }
}
```

NetworkPolicy enforcement (see `infrastructure/helm/charts/system/templates/network-policies.yaml`) restricts which namespaces can reach the control-plane and graph-instances namespaces. This is the mechanism that replaced the removed internal-API shared-secret header (see [ADR-104](--/process/adr/security/adr-104-database-backed-user-role-management.md) and [ADR-105](--/process/adr/security/adr-105-x-username-header-identity-with-static-default.md)).

WireGuard transparent encryption is a Cilium feature available in this data plane, but whether it is turned on in the HSBC environment is an operational toggle set in that environment's Cilium ConfigMap. Treat it as configurable, not as a platform guarantee asserted by this document.

---

## 6. Gaps / Known Limitations

The following are **not** in place. They are listed here so operators and auditors are not misled.

| Area | Current state | Reference |
|---|---|---|
| CMEK (customer-managed encryption keys) | Not in scope for the HSBC handover. | [ADR-146](--/process/adr/security/adr-146-cmek-scope.md) |
| Binary Authorization enforcement | Not in scope for the HSBC handover. | [ADR-147](--/process/adr/security/adr-147-binauthz-scope.md) |
| Starburst credential passthrough | Deferred — single service account is used. | [ADR-148](--/process/adr/security/adr-148-starburst-credential-passthrough.md) |
| Compliance certifications (PCI DSS / SOC 2 / ISO 27001 / GDPR attestation) | The platform has **not** been audited against any of these frameworks. | n/a |
| mTLS between services | Not configured. | n/a |
| Certificate pinning on clients | Not configured. | n/a |

---

## 7. Verification

Operational checks that can be run against a live cluster:

```bash
# External TLS
openssl s_client -connect <HSBC_API_HOST>:443 -servername <HSBC_API_HOST> < /dev/null | grep -E "Protocol|Cipher"

# Cloud SQL SSL from a pod
kubectl -n control-plane exec deploy/control-plane -- psql "$DATABASE_URL" -c "SHOW ssl"
```

---

## References

- [ADR-104 — Database-backed user and role management](--/process/adr/security/adr-104-database-backed-user-role-management.md)
- [ADR-105 — X-Username header identity](--/process/adr/security/adr-105-x-username-header-identity-with-static-default.md)
- [ADR-137 — Azure AD auth proxy](--/process/adr/security/adr-137-azure-ad-auth-proxy.md)
- [ADR-144 — Graph-node owner access control](--/process/adr/security/adr-144-graph-node-owner-access-control.md)
- [ADR-146 — CMEK scope](--/process/adr/security/adr-146-cmek-scope.md)
- [ADR-147 — Binary Authorization scope](--/process/adr/security/adr-147-binauthz-scope.md)
- [ADR-148 — Starburst credential passthrough](--/process/adr/security/adr-148-starburst-credential-passthrough.md)
- [GKE Dataplane V2](https://cloud.google.com/kubernetes-engine/docs/concepts/dataplane-v2)
- [Cloud SQL SSL](https://cloud.google.com/sql/docs/postgres/configure-ssl-instance)

---

## Related Documents

- [Container Security Audit](--/security/container-security-audit.md)
- [Authorization Specification](-/authorization.spec.md)
