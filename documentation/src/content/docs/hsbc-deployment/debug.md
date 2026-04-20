---
title: "Debug Guide"
sidebar:
  order: 7
---

## Common Issues

### Pod not starting

```bash
kubectl describe pod -n graph-olap-platform -l app=control-plane
kubectl logs -n graph-olap-platform -l app=control-plane --previous
```

### Cloud SQL Proxy connection failure

```bash
kubectl logs -n graph-olap-platform -l app=control-plane -c cloud-sql-proxy
```

### Wrapper proxy returning 502

```bash
kubectl logs -n graph-olap-platform -l app=wrapper-proxy
kubectl exec -n graph-olap-platform deploy/wrapper-proxy -- curl -v http://falkordb-wrapper:8000/health
```

### Checking request headers

```bash
kubectl exec -n graph-olap-platform deploy/graph-olap-control-plane -- \
    curl -v -H "X-Username: testuser" http://localhost:8080/health
```
