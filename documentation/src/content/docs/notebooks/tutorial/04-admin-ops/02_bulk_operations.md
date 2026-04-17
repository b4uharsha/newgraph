---
title: "Bulk Operations"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Bulk Operations</h1>
  <p class="nb-header__subtitle">Safely perform bulk delete and management operations</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">25 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Admin</span><span class="nb-header__tag">Bulk</span><span class="nb-header__tag">Delete</span><span class="nb-header__tag">Safety</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Bulk Delete</strong> — Delete multiple resources with dry-run preview</li>
    <li><strong>Filtering</strong> — Select resources by name prefix, status, or creator</li>
    <li><strong>Dry Run vs Execute</strong> — Preview matches before committing</li>
    <li><strong>Safety Mechanisms</strong> — <code>expected_count</code> guard and 100-resource limit</li>
  </ul>
</div>

```python
# Cell 1 — Parameters
USERNAME = "_FILL_ME_IN_"  # Set your email before running
```

```python
# Cell 2 — Connect
from graph_olap import GraphOLAPClient
client = GraphOLAPClient(username=USERNAME)

# Cell 3 — Provision
from notebook_setup import provision
personas, conn = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]

client = admin
print(f"Connected to: {admin._config.api_url}")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Dry Run Preview</h2>
    <p class="nb-section__description">Always preview what would be deleted before executing</p>
  </div>
</div>

```python
# Preview what would be deleted (dry run — no resources are removed)
preview = client.admin.bulk_delete(
    resource_type="instance",
    filters={"name_prefix": "test-", "status": "terminated"},
    reason="cleanup old test instances",
    dry_run=True,
)

print(f"Would delete {preview['matched_count']} instances")
print(f"Matched IDs: {preview['matched_ids']}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Filter Types</h2>
    <p class="nb-section__description">Select resources by name prefix, status, or creator</p>
  </div>
</div>

```python
# Available filter keys for bulk_delete:
#
#   name_prefix  — match resources whose name starts with a string
#   status       — filter by resource status
#
# Filters are combined with AND logic.

# Example: preview instances matching a prefix
preview = client.admin.bulk_delete(
    resource_type="instance",
    filters={"name_prefix": "cleanup-demo-"},
    reason="cleanup demo instances",
    dry_run=True,
)

print(f"Matched {preview['matched_count']} instances")
if preview["matched_ids"]:
    for iid in preview["matched_ids"]:
        print(f"  - {iid}")
else:
    print("  (none matched — expected for a demo prefix)")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Executing the Delete</h2>
    <p class="nb-section__description">Move from dry run to actual deletion</p>
  </div>
</div>

```python
# Available filter keys for bulk_delete:
#
#   name_prefix  — match instances whose name starts with a string
#   status       — "terminated", "running", "stopped", etc.
#   created_by   — username of the analyst who created them
#
# Filters are combined with AND logic.

# Example: find terminated instances with a specific prefix
preview = client.admin.bulk_delete(
    resource_type="instance",
    filters={"name_prefix": "cleanup-demo-"},
    reason="cleanup demo instances",
    dry_run=True,
)

print(f"Matched {preview['matched_count']} instances")
if preview["matched_ids"]:
    for iid in preview["matched_ids"]:
        print(f"  - {iid}")
else:
    print("  (none matched — this is expected for a demo prefix)")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Safety Mechanisms</h2>
    <p class="nb-section__description"><code>expected_count</code> guard and hard limits</p>
  </div>
</div>

```python
# Safety mechanism 1: expected_count
# If the actual matched count differs from expected_count, the API
# returns an error and deletes nothing. This prevents surprises when
# filters match more resources than anticipated.

# Safety mechanism 2: hard limit of 100 resources per call
# The API refuses requests that would delete more than 100 resources
# in a single call. Split larger cleanups into batches.

# Example: expected_count mismatch (would raise an error)
# result = client.admin.bulk_delete(
#     resource_type="instance",
#     filters={"name_prefix": "test-", "status": "terminated"},
#     reason="cleanup",
#     expected_count=5,   # but 12 actually match -> error
#     dry_run=False,
# )

print("Safety mechanisms:")
print("  1. expected_count — must match actual matched_count or delete is refused")
print("  2. Hard limit    — max 100 resources per bulk_delete call")
print("  3. dry_run=True  — always preview before executing")
print("  4. reason        — every delete is audit-logged with a reason string")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>bulk_delete()</code> requires <code>resource_type</code>, <code>filters</code>, and <code>reason</code></li>
    <li>Always run with <code>dry_run=True</code> first to preview matched resources</li>
    <li>Pass <code>expected_count</code> when executing — the API refuses if the count does not match</li>
    <li>A hard limit of 100 resources per call prevents runaway deletions</li>
    <li>Filter by <code>name_prefix</code>, <code>status</code>, or <code>created_by</code> (combined with AND logic)</li>
  </ul>
</div>
