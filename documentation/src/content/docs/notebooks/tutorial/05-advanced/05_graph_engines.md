---
title: "Graph Engines"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Graph Engines</h1>
  <p class="nb-header__subtitle">Compare Ryugraph and FalkorDB wrappers</p>
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
  <div class="nb-header__tags"><span class="nb-header__tag">FalkorDB</span><span class="nb-header__tag">Ryugraph</span><span class="nb-header__tag">Engines</span><span class="nb-header__tag">Performance</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Engine Comparison</strong> - Ryugraph vs FalkorDB capabilities</li>
    <li><strong>Choosing an Engine</strong> - When to use which</li>
    <li><strong>Performance Characteristics</strong> - Speed and memory tradeoffs</li>
    <li><strong>Migration Between Engines</strong> - Switching wrappers</li>
  </ul>
</div>

```python
# Cell 1 — Parameters
USERNAME = "_FILL_ME_IN_"  # Set your email before running
```

```python
# Cell 2 — Connect
from graph_olap import GraphOLAPClient
from graph_olap_schemas import WrapperType
client = GraphOLAPClient(username=USERNAME)

# Cell 3 — Provision
from notebook_setup import provision
personas, conn = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst

# Find the tutorial mapping by name (not by index — parallel CI has multiple)
mappings = client.mappings.list()
tutorial_mappings = [m for m in mappings if "tutorial-customer-graph" in m.name]
mapping = tutorial_mappings[0] if tutorial_mappings else mappings.items[0]
MAPPING_ID = mapping.id
print(f"Using mapping: {mapping.name} (id={MAPPING_ID})")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Engine Overview</h2>
    <p class="nb-section__description">Ryugraph and FalkorDB</p>
  </div>
</div>

```python
from graph_olap_schemas import WrapperType

# The WrapperType enum defines the available graph engines
print("Available engine types:")
print(f"  - {WrapperType.RYUGRAPH}  (in-memory, optimised for graph algorithms)")
print(f"  - {WrapperType.FALKORDB}  (Redis-based, persistent, production-ready)")

# Ryugraph: Pure in-memory graph engine
#   - Fastest query execution for analytics workloads
#   - Rich native algorithm library (PageRank, community detection, etc.)
#   - Full NetworkX algorithm support
#   - Data lives only while the instance is running
#
# FalkorDB: Redis-backed graph database
#   - Persistent storage via Redis
#   - Good for production serving and dashboards
#   - Subset of native algorithms (BFS, shortest path)
#   - Cypher query compatibility
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Feature Comparison</h2>
    <p class="nb-section__description">Capabilities and limitations</p>
  </div>
</div>

```python
# Terminate the shared provision instance to free capacity
# (this notebook creates its own Ryugraph + FalkorDB instances)
try:
    shared_instance = client.instances.list(search="tutorial-instance", status="running")
    for inst in shared_instance.items:
        if "tutorial-instance" in inst.name:
            client.instances.terminate(inst.id)
            print(f"Terminated shared instance {inst.id} ({inst.name})")
            import time; time.sleep(3)
except Exception as e:
    print(f"Note: {e}")

# Create a Ryugraph instance (in-memory, fast algorithms)
ryugraph_instance = client.instances.create_and_wait(
    mapping_id=MAPPING_ID,
    name="tutorial-ryugraph",
    wrapper_type=WrapperType.RYUGRAPH,
    timeout=300,
    ttl="PT1H",
)
print(f"Ryugraph instance: {ryugraph_instance.id}  status={ryugraph_instance.status}")

# Create a FalkorDB instance (Redis-backed, persistent)
falkordb_instance = client.instances.create_and_wait(
    mapping_id=MAPPING_ID,
    name="tutorial-falkordb",
    wrapper_type=WrapperType.FALKORDB,
    timeout=300,
    ttl="PT1H",
)
print(f"FalkorDB instance: {falkordb_instance.id}  status={falkordb_instance.status}")

# Both engines support Cypher queries through the same connection interface
conn_ryu = client.instances.connect(ryugraph_instance.id)
conn_fdb = client.instances.connect(falkordb_instance.id)
print(f"\nConnected to both engines")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Algorithm Availability</h2>
    <p class="nb-section__description">Algorithms are per-instance, not per-engine type</p>
  </div>
</div>

```python
# Algorithm discovery is per-instance via the connection object
# There is NO client.instances.available_algorithms() method.

# --- Ryugraph algorithms ---
ryu_native = conn_ryu.algo.algorithms()
ryu_nx = conn_ryu.networkx.algorithms()

print("=== Ryugraph: Native Algorithms ===")
for algo in sorted(ryu_native, key=lambda a: a["name"] if isinstance(a, dict) else a):
    name = algo["name"] if isinstance(algo, dict) else algo
    print(f"  - {name}")

print(f"\n=== Ryugraph: NetworkX Algorithms ({len(ryu_nx)} available) ===")
# Show first 10 for brevity
for algo in sorted(ryu_nx, key=lambda a: a["name"] if isinstance(a, dict) else a)[:10]:
    name = algo["name"] if isinstance(algo, dict) else algo
    print(f"  - {name}")
if len(ryu_nx) > 10:
    print(f"  ... and {len(ryu_nx) - 10} more")

# --- FalkorDB algorithms ---
fdb_native = conn_fdb.algo.algorithms()
fdb_nx = conn_fdb.networkx.algorithms()

print(f"\n=== FalkorDB: Native Algorithms ===")
for algo in sorted(fdb_native, key=lambda a: a["name"] if isinstance(a, dict) else a):
    name = algo["name"] if isinstance(algo, dict) else algo
    print(f"  - {name}")

print(f"\n=== FalkorDB: NetworkX Algorithms ({len(fdb_nx)} available) ===")
for algo in sorted(fdb_nx, key=lambda a: a["name"] if isinstance(a, dict) else a)[:10]:
    name = algo["name"] if isinstance(algo, dict) else algo
    print(f"  - {name}")
if len(fdb_nx) > 10:
    print(f"  ... and {len(fdb_nx) - 10} more")

# Expected: Ryugraph typically has more native algorithms than FalkorDB.
# Both engines expose NetworkX algorithms, but the exact list may differ.
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Choosing the Right Engine</h2>
    <p class="nb-section__description">Decision framework</p>
  </div>
</div>

Decision framework: which engine to use?

┌─────────────────────────┬─────────────────┬─────────────────┐
│ Criterion               │ Ryugraph        │ FalkorDB        │
├─────────────────────────┼─────────────────┼─────────────────┤
│ Storage                 │ In-memory only  │ Redis-persisted │
│ Query speed             │ Fastest         │ Fast            │
│ Native algorithms       │ Many            │ Subset (BFS,    │
│                         │ (PageRank, etc) │  shortest path) │
│ NetworkX algorithms     │ Full support    │ Full support    │
│ Persistence             │ None            │ Yes             │
│ Best for                │ Analytics,      │ Production      │
│                         │ exploration     │ serving, apps   │
│ Horizontal scaling      │ No              │ Yes (Redis)     │
└─────────────────────────┴─────────────────┴─────────────────┘

Rule of thumb:
- Exploring data or running heavy algorithms? → Ryugraph
- Building a dashboard or serving API queries? → FalkorDB
- Need persistence across restarts? → FalkorDB
- Need maximum algorithm coverage? → Ryugraph

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Use <code>WrapperType.RYUGRAPH</code> or <code>WrapperType.FALKORDB</code> with <code>client.instances.create_and_wait()</code></li>
    <li>Ryugraph is in-memory with the richest native algorithm set; FalkorDB is Redis-backed and persistent</li>
    <li>Algorithm availability is per-instance: use <code>conn.algo.algorithms()</code> and <code>conn.networkx.algorithms()</code></li>
    <li>Both engines share the same Cypher query interface via <code>conn.query()</code></li>
    <li>Choose Ryugraph for analytics/exploration, FalkorDB for production serving</li>
  </ul>
</div>

```python
# Cleanup: terminate instances created in this notebook
for inst in [ryugraph_instance, falkordb_instance]:
    try:
        client.instances.terminate(inst.id)
        print(f"Terminated instance {inst.id}")
    except Exception as e:
        print(f"Instance cleanup: {e}")
```
