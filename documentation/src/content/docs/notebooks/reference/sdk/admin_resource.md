---
title: "AdminResource"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">AdminResource</h1>
  <p class="nb-header__subtitle">Administrative bulk operations</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span><span class="nb-header__tag">Admin</span></div>
</div>

## AdminResource

Accessed via `client.admin`, this resource provides privileged bulk
operations that require the Admin role. It is used for operational
cleanup tasks such as deleting stale test instances or expired resources.

All operations enforce safety constraints: at least one filter is required,
a maximum of 100 deletions per request, and an optional `expected_count`
guard to prevent accidental mass deletion.

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect as an admin user</p>
  </div>
</div>

```python
# Cell 1 — Parameters
USERNAME = "_FILL_ME_IN_"  # Set your email before running
```

```python
# Cell 2 — Connect
from graph_olap import GraphOLAPClient
client = GraphOLAPClient(username=USERNAME)
```

```python
# Cell 3 — Provision
from notebook_setup import provision
personas, _ = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Bulk Delete</h2>
    <p class="nb-section__description">Safely delete resources in bulk</p>
  </div>
</div>

### `bulk_delete(resource_type, filters, reason, expected_count=None, dry_run=False) -> dict`

Bulk delete resources matching the given filters. Designed for operational
cleanup with multiple safety guards built in.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resource_type` | `str` | *required* | `"instance"`, `"snapshot"`, or `"mapping"` |
| `filters` | `dict` | *required* | At least one filter required (see below) |
| `reason` | `str` | *required* | Reason for deletion (written to audit log) |
| `expected_count` | `int \| None` | `None` | Safety check -- must match actual count or request fails |
| `dry_run` | `bool` | `False` | If `True`, return what *would* be deleted without deleting |

**Available filters:**

| Filter | Description |
|--------|-------------|
| `name_prefix` | Match resources whose name starts with prefix |
| `created_by` | Match resources created by a specific username |
| `older_than_hours` | Match resources older than N hours |
| `status` | Match resources with a specific status |

**Returns:** `dict` with `matched_count`, `matched_ids` (dry run) or `deleted_count`, `failed_count` (execute).

**Raises:**
- `ForbiddenError` -- user does not have Admin role
- `ValidationError` -- no filters provided, matched > 100, or count mismatch

**Safety features:**
- At least one filter is always required
- Maximum 100 deletions per request
- `expected_count` validation prevents surprises
- Full audit logging of every deletion

#### Recommended pattern: dry run first, then execute

Always perform a dry run to inspect what will be deleted, then pass the
matched count as `expected_count` in the real call. This two-step pattern
prevents accidental mass deletion.

```python
# Step 1: Dry run -- see what WOULD be deleted
preview = admin.admin.bulk_delete(
    resource_type="instance",
    filters={"status": "terminated"},
    reason="cleanup-terminated-instances",
    dry_run=True,
)

print(f"Would delete {preview['matched_count']} instances")
print(f"IDs: {preview['matched_ids']}")
```

```python
# Step 2: Execute with expected_count safety check
result = admin.admin.bulk_delete(
    resource_type="instance",
    filters={"status": "terminated"},
    reason="cleanup-terminated-instances",
    expected_count=preview["matched_count"],  # must match or request fails
    dry_run=False,
)

print(f"Deleted: {result['deleted_count']}")
print(f"Failed:  {len(result.get('failed_ids', []))}")
```

#### Multiple filters

Filters are combined with AND logic. This example targets old test instances
created by a specific user.

```python
# Combine filters for precise targeting
preview = admin.admin.bulk_delete(
    resource_type="instance",
    filters={
        "name_prefix": "E2ETest-",
        "older_than_hours": 24,
    },
    reason="cleanup-old-e2e-instances",
    dry_run=True,
)

print(f"Matched: {preview['matched_count']} instances")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Always use <code>dry_run=True</code> first to preview what will be deleted</li>
    <li>Pass <code>expected_count</code> from the dry-run result to guard against race conditions</li>
    <li>At least one filter is required -- you cannot bulk-delete without constraints</li>
    <li>Maximum 100 deletions per request -- split larger cleanups into batches</li>
    <li>Every deletion is written to the audit log with the provided <code>reason</code></li>
  </ul>
</div>
