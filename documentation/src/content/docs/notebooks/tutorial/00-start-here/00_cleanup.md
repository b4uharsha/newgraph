---
title: "Tutorial Cleanup"
---

<div class="nb-header">
  <span class="nb-header__type">Utility</span>
  <h1 class="nb-header__title">Tutorial Cleanup</h1>
  <p class="nb-header__subtitle">Remove stale tutorial instances, mappings, and personas</p>
</div>

```python
USERNAME = "_FILL_ME_IN_"  # Your email — used to derive the tutorial namespace
```

```python
import os
import time

from notebook_setup import make_namespace
from graph_olap import GraphOLAPClient

namespace = make_namespace(USERNAME)
ops_username = os.environ.get("SYSTEM_OPS_USER", "ops_dave@e2e.local")
analyst_username = f"analyst@e2e.{namespace}.local"

print(f"Cleaning tutorial namespace: {namespace}")
print(f"  analyst: {analyst_username}")

# 1. Terminate instances
terminated = 0
client = GraphOLAPClient(username=analyst_username)
for status in ("running", "starting", "waiting_for_snapshot"):
    for inst in client.instances.list(owner=analyst_username, status=status, limit=200).items:
        try:
            client.instances.terminate(inst.id)
            terminated += 1
            print(f"  Terminated instance {inst.id} ({inst.name})")
        except Exception:
            pass
client.close()

if terminated > 0:
    print("  Waiting 5s for snapshot cascade...")
    time.sleep(5)

# 2. Delete mappings
deleted = 0
client = GraphOLAPClient(username=analyst_username)
for m in client.mappings.list(owner=analyst_username, limit=200).items:
    try:
        client.mappings.delete(m.id)
        deleted += 1
        print(f"  Deleted mapping {m.id} ({m.name})")
    except Exception as e:
        print(f"  Failed to delete mapping {m.id}: {e}")
client.close()

# 3. Deactivate personas
deactivated = 0
ops_client = GraphOLAPClient(username=ops_username)
for role in ("analyst", "admin", "ops"):
    persona = f"{role}@e2e.{namespace}.local"
    try:
        ops_client.users.deactivate(persona)
        deactivated += 1
        print(f"  Deactivated persona: {persona}")
    except Exception:
        pass
ops_client.close()

print(f"\nDone: {terminated} instances, {deleted} mappings, {deactivated} personas")
```
