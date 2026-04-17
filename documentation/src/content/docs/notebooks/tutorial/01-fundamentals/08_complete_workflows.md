---
title: "Complete Workflows"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Complete Workflows</h1>
  <p class="nb-header__subtitle">End-to-end patterns for common graph analytics tasks</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">45 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Workflow</span><span class="nb-header__tag">Patterns</span><span class="nb-header__tag">Best Practices</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Setup</strong> - Connect to the platform</li>
    <li><strong>Discovery</strong> - Explore mappings and warehouse schema</li>
    <li><strong>Instance and Query</strong> - Deploy a graph and run Cypher queries</li>
    <li><strong>Cleanup</strong> - Extend or terminate instances when finished</li>
  </ul>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the platform</p>
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

# Cell 3 — Provision
from notebook_setup import provision
personas, conn = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst

print(f"Connected to: {client._config.api_url}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Discovery Workflow</h2>
    <p class="nb-section__description">Explore mappings and schema before querying</p>
  </div>
</div>

```python
# Step 1: List available mappings
mappings = client.mappings.list()
print(f"Available mappings: {len(mappings)}")
for m in mappings:
    print(f"  [{m.id}] {m.name}")

# Step 2: Browse the warehouse schema
catalogs = client.schema.list_catalogs()
for cat in catalogs:
    schemas = client.schema.list_schemas(cat.catalog_name)
    for s in schemas:
        tables = client.schema.list_tables(cat.catalog_name, s.schema_name)
        print(f"\n{cat.catalog_name}.{s.schema_name}:")
        for t in tables:
            print(f"  {t.table_name}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Instance and Query Workflow</h2>
    <p class="nb-section__description">Create an instance, run queries, and analyze results</p>
  </div>
</div>

```python
from graph_olap_schemas import WrapperType

# Step 3: Create an instance from the tutorial mapping
tutorial_mappings = [m for m in mappings if "tutorial-customer-graph" in m.name]
mapping = tutorial_mappings[0] if tutorial_mappings else mappings[0]

instance = client.instances.create_and_wait(
    mapping_id=mapping.id,
    name="workflow-demo",
    wrapper_type=WrapperType.RYUGRAPH,
    ttl="PT1H",
    timeout=300,
)
print(f"Instance '{instance.name}' is {instance.status}")

# Step 4: Connect and query HSBC customer data
demo_conn = client.instances.connect(instance.id)

result = demo_conn.query("""
    MATCH (c:Customer)
    RETURN c.id AS name
    LIMIT 5
""")
result.show()

# Step 5: Count edges
edge_count = demo_conn.query_scalar("MATCH ()-[r:SHARES_ACCOUNT]->() RETURN count(r)")
print(f"\nSHARES_ACCOUNT edges: {edge_count}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Cleanup Workflow</h2>
    <p class="nb-section__description">Extend or terminate instances when finished</p>
  </div>
</div>

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Discovery: use <code>client.mappings.list()</code> and <code>client.schema.*</code> to explore data</li>
    <li>Deployment: use <code>client.instances.create_and_wait(mapping_id=...)</code> to spin up a graph</li>
    <li>Querying: use <code>conn.query()</code> for Cypher and <code>conn.query_scalar()</code> for single values</li>
    <li>Cleanup: always <code>terminate()</code> instances when finished to free resources</li>
  </ul>
</div>

```python
# Clean up the demo instance we created
try:
    client.instances.terminate(instance.id)
    print(f"Terminated instance: {instance.name}")
except Exception as e:
    print(f"Cleanup: {e}")
```
