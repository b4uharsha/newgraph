---
title: "Version Diffing"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Version Diffing</h1>
  <p class="nb-header__subtitle">Compare mapping versions and track schema evolution</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">30 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Versioning</span><span class="nb-header__tag">Diff</span><span class="nb-header__tag">Schema</span><span class="nb-header__tag">Evolution</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Version Comparison</strong> - Compare two mapping versions</li>
    <li><strong>Diff Types</strong> - Added, removed, modified elements</li>
    <li><strong>Schema Evolution</strong> - Track changes over time</li>
    <li><strong>Migration Planning</strong> - Plan data migrations from diffs</li>
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
from graph_olap.models.mapping import NodeDefinition, EdgeDefinition, PropertyDefinition
from graph_olap.utils.diff import render_diff_summary, render_diff_details, diff_to_dict

personas, conn = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst

print(f"Connected to: {client._config.api_url}")

# Create a dedicated mapping for version-diffing demos
mapping = client.mappings.create(
    name="DiffDemo",
    node_definitions=[
        NodeDefinition(
            label="Customer",
            sql="SELECT '1' as id, 'Alice' as name",
            primary_key={"name": "id", "type": "STRING"},
            properties=[PropertyDefinition(name="name", type="STRING")],
        ),
    ],
    edge_definitions=[],
)

# Create version 2 by adding a Location node
client.mappings.update(
    mapping.id,
    change_description="Add Location node",
    node_definitions=mapping.node_definitions + [
        NodeDefinition(
            label="Location",
            sql="SELECT 'HK' as id, 'Hong Kong' as name",
            primary_key={"name": "id", "type": "STRING"},
            properties=[PropertyDefinition(name="name", type="STRING")],
        ),
    ],
    edge_definitions=mapping.edge_definitions,
)
print(f"Mapping: {mapping.name} (id={mapping.id}) -- 2 versions created")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Comparing Versions</h2>
    <p class="nb-section__description">Create a diff</p>
  </div>
</div>

```python
# Compare version 1 to version 2
diff = client.mappings.diff(mapping.id, from_version=1, to_version=2)

# The summary dict gives quick counts
print("=== Diff Summary (v1 → v2) ===")
print(f"Nodes added:    {diff.summary['nodes_added']}")
print(f"Nodes removed:  {diff.summary['nodes_removed']}")
print(f"Nodes modified: {diff.summary['nodes_modified']}")
print(f"Edges added:    {diff.summary['edges_added']}")
print(f"Edges removed:  {diff.summary['edges_removed']}")

# Expected output:
# === Diff Summary (v1 → v2) ===
# Nodes added:    1
# Nodes removed:  0
# Nodes modified: 0
# Edges added:    0
# Edges removed:  0
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Understanding Diffs</h2>
    <p class="nb-section__description">Interpreting changes</p>
  </div>
</div>

```python
# Detailed changes are in diff.changes, keyed by "nodes" and "edges"
print("=== Node Changes ===")
for change in diff.changes["nodes"]:
    # change_type is one of: "added", "removed", "modified"
    prefix = {"added": "+", "removed": "-", "modified": "~"}[change.change_type]
    print(f"  {prefix} {change.label}  (change_type={change.change_type})")

    # For modified nodes, fields_changed shows what specifically changed
    if change.fields_changed:
        for field in change.fields_changed:
            print(f"      field: {field}")

print()
print("=== Edge Changes ===")
for change in diff.changes["edges"]:
    prefix = {"added": "+", "removed": "-", "modified": "~"}[change.change_type]
    print(f"  {prefix} {change.type}  (change_type={change.change_type})")

# Expected output:
# === Node Changes ===
#   + Location  (change_type=added)
#
# === Edge Changes ===
#   (none — edges unchanged between v1 and v2)
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Reverse Diffs</h2>
    <p class="nb-section__description">Swap from/to to invert the perspective</p>
  </div>
</div>

```python
# Reverse diff: v2 → v1 inverts the change types
reverse = client.mappings.diff(mapping.id, from_version=2, to_version=1)

print("=== Reverse Diff Summary (v2 → v1) ===")
print(f"Nodes added:    {reverse.summary['nodes_added']}")
print(f"Nodes removed:  {reverse.summary['nodes_removed']}")

print()
for change in reverse.changes["nodes"]:
    print(f"  {change.change_type}: {change.label}")

# Expected output:
# === Reverse Diff Summary (v2 → v1) ===
# Nodes added:    0
# Nodes removed:  1
#
#   removed: Location
#
# Note: What was "added" in v1→v2 becomes "removed" in v2→v1
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">SDK Rendering Utilities</h2>
    <p class="nb-section__description">Built-in helpers for formatting and serialising diffs</p>
  </div>
</div>

```python
# render_diff_summary prints a formatted summary table
render_diff_summary(diff)

# render_diff_details shows each change with optional from/to values
render_diff_details(diff, show_from_to=True)

# diff_to_dict serialises the diff to a plain dict (useful for JSON export)
d = diff_to_dict(diff)
print(f"\nSerialized keys: {list(d.keys())}")
# d['changes'] is a flat list of all changes
print(f"Total changes: {len(d['changes'])}")
for change in d['changes']:
    print(f"  {change.get('change_type', '?')}: {change.get('label', change.get('type', '?'))} ({change.get('kind', 'node')})")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>client.mappings.diff(id, from_version, to_version)</code> compares any two versions of a mapping</li>
    <li><code>diff.summary</code> gives counts of added, removed, and modified nodes/edges</li>
    <li><code>diff.changes["nodes"]</code> contains detailed change objects with <code>change_type</code>, <code>label</code>, and <code>fields_changed</code></li>
    <li>Swapping <code>from_version</code> and <code>to_version</code> inverts the change types (added becomes removed)</li>
    <li>SDK utilities <code>render_diff_summary</code>, <code>render_diff_details</code>, and <code>diff_to_dict</code> format and serialise diffs</li>
  </ul>
</div>

```python
# Cleanup: delete the DiffDemo mapping created in this notebook
try:
    client.mappings.delete(mapping.id)
    print(f"Deleted: {mapping.name}")
except Exception as e:
    print(f"Mapping cleanup: {e}")
```
