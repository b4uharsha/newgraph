---
title: "Advanced Mappings"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Advanced Mappings</h1>
  <p class="nb-header__subtitle">Copy mappings and work with mapping hierarchies</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">Mappings</span><span class="nb-header__tag">Copy</span><span class="nb-header__tag">Hierarchy</span><span class="nb-header__tag">Versioning</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Copying Mappings</strong> - Duplicate and modify mappings</li>
    <li><strong>Mapping Trees</strong> - Version hierarchy</li>
    <li><strong>Version Tracking</strong> - Update mappings with change descriptions</li>
    <li><strong>Version Diffing</strong> - Compare versions to see what changed</li>
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
client = analyst

mapping = client.mappings.list(search="tutorial-customer-graph").items[0]
print(f"Connected to: {client._config.api_url}")
print(f"Using mapping: {mapping.name} (id={mapping.id})")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Copying Mappings</h2>
    <p class="nb-section__description">Duplicate with modifications</p>
  </div>
</div>

```python
# Copy a mapping to create a variation without starting from scratch
# copy(mapping_id, new_name) -- positional args, not keyword
copied = client.mappings.copy(mapping.id, "CustomerGraph-v2")
print(f"Original:  {mapping.name} (id={mapping.id})")
print(f"Copy:      {copied.name} (id={copied.id})")
print(f"Version:   {copied.current_version}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Mapping Hierarchy</h2>
    <p class="nb-section__description">Versions and instances as a tree</p>
  </div>
</div>

```python
# get_tree() returns the mapping's version/snapshot/instance hierarchy
tree = client.mappings.get_tree(mapping.id, include_instances=True)

# tree is a dict keyed by version number
for version_num, version_info in tree.items():
    print(f"Version {version_num}: {version_info['name']}")
    for snap in version_info.get("snapshots", []):
        print(f"  Snapshot: {snap['id']}")
        for inst in snap.get("instances", []):
            print(f"    Instance: {inst}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Version Tracking</h2>
    <p class="nb-section__description">Update mappings and track changes</p>
  </div>
</div>

```python
# Updating a mapping creates a new version automatically.
# Always provide a change_description for audit trail.
from graph_olap.models.mapping import NodeDefinition, EdgeDefinition, PropertyDefinition

# Add a Location node to the copied mapping
location_node = NodeDefinition(
    label="Location",
    sql="SELECT 'HK' as id, 'Hong Kong' as name",
    primary_key={"name": "id", "type": "STRING"},
    properties=[PropertyDefinition(name="name", type="STRING")],
)

updated = client.mappings.update(
    copied.id,
    change_description="Add Location node",
    node_definitions=copied.node_definitions + [location_node],
    edge_definitions=copied.edge_definitions,
)
print(f"Updated mapping: {updated.name}")
print(f"New version:     {updated.current_version}")
print(f"Node labels:     {[n.label for n in updated.node_definitions]}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Version Diffing</h2>
    <p class="nb-section__description">Compare versions to see what changed</p>
  </div>
</div>

```python
# Diff two versions of a mapping to see exactly what changed
diff = client.mappings.diff(copied.id, from_version=1, to_version=2)
print(f"Nodes added:   {diff.summary['nodes_added']}")
print(f"Nodes removed: {diff.summary['nodes_removed']}")
print(f"Edges added:   {diff.summary['edges_added']}")
print(f"Edges removed: {diff.summary['edges_removed']}")

# See the detailed notebook 04_version_diffing for advanced diffing workflows
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>client.mappings.copy(id, new_name=...)</code> duplicates a mapping for experimentation</li>
    <li><code>get_tree(id)</code> shows the version → snapshot → instance hierarchy</li>
    <li><code>update(id, change_description=..., ...)</code> creates a new version with an audit trail</li>
    <li><code>diff(id, from_version, to_version)</code> shows exactly what changed between versions</li>
    <li>See <strong>04_version_diffing</strong> for advanced diff workflows</li>
  </ul>
</div>
