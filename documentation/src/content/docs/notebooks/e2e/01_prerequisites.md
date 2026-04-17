---
title: "Prerequisites"
---

<div class="nb-callout nb-callout--warning">
  <span class="nb-sr-only">Warning:</span>
  <span class="nb-callout__icon" aria-hidden="true"></span>
  <div class="nb-callout__content">
    <div class="nb-callout__title">Not for Jupyter</div>
    <div class="nb-callout__body">
      These E2E notebooks are <strong>not designed to run in JupyterHub or an interactive Jupyter kernel</strong>. They are executed standalone by the test runner (<code>make test TYPE=e2e CLUSTER=gke-london</code>) and depend on pytest fixtures, environment variables, and cluster-provisioned personas that are not present in an interactive session.
      <br/><br/>
      Opening them in Jupyter will surface missing imports, undefined fixtures, and cleanup failures. Use the tutorials under <code>docs/notebooks/tutorials/</code> for interactive learning.
    </div>
  </div>
</div>

<div class="nb-header">
  <span class="nb-header__type">E2E Test</span>
  <h1 class="nb-header__title">Prerequisites</h1>
  <p class="nb-header__subtitle">Verify setup and connectivity</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">5 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">E2E Test</span><span class="nb-header__tag">Test</span></div>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Verify SDK Installation</h2>
  </div>
</div>

```python
# Import SDK and check version
import sys

import graph_olap

print(f"SDK Version: {graph_olap.__version__}")
print(f"Python Version: {sys.version}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Initialize SDK Client</h2>
  </div>
</div>

```python
# Initialize SDK client using setup()
from graph_olap.notebook_setup import setup

# Connect to the control plane - auto-discovers from environment variables
ctx = setup()
client = ctx.client

print("SDK Client initialized successfully!")
print(f"   Connected to: {client._http.base_url}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Test Control Plane Connectivity</h2>
  </div>
</div>

```python
# Test basic connectivity with health check
try:
    health = client.health.check()
    print(f"✅ Control Plane Status: healthy")
    print(f"Response: {health}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    print("\nTroubleshooting:")
    print("1. Check if control-plane pod is running:")
    print("   kubectl get pods -n e2e-test -l app=control-plane")
    print("2. Check control-plane logs:")
    print("   kubectl logs -n e2e-test -l app=control-plane")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">List Available E2E Test Notebooks</h2>
  </div>
</div>

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>SDK installation and version verified</li>
    <li>Control plane connectivity confirmed</li>
    <li>Environment variables validated</li>
  </ul>
</div>

```python
# List all available notebooks
import os
from pathlib import Path

notebooks_dir = Path("/home/jovyan/work/notebooks")

if notebooks_dir.exists():
    notebooks = sorted([f.name for f in notebooks_dir.glob("*.ipynb")])
    print(f"Available E2E Test Notebooks ({len(notebooks)}):")
    print("\n" + "="*60)
    for i, nb in enumerate(notebooks, 1):
        print(f"{i:2d}. {nb}")
    print("="*60)
else:
    print(f"❌ Notebooks directory not found: {notebooks_dir}")
```

## Recommended Test Execution Order

When running E2E tests, follow this order:

1. **`sdk_smoke_test.ipynb`** - Quick sanity checks (must run first)
2. **`sdk_crud_test.ipynb`** - Basic CRUD operations
3. **`sdk_query_test.ipynb`** - Query execution
4. **`sdk_schema_test.ipynb`** - Schema introspection
5. **`sdk_algorithm_test.ipynb`** - Algorithm execution
6. **`sdk_workflow_test.ipynb`** - Multi-step workflows

Other notebooks can be run as needed for specific feature testing.

## Quick Reference: Jupyter Shortcuts

### Cell Execution
- **Shift + Enter**: Run cell and move to next
- **Ctrl + Enter**: Run cell without moving
- **Alt + Enter**: Run cell and insert new cell below

### Cell Management
- **ESC then A**: Insert cell above
- **ESC then B**: Insert cell below
- **ESC then DD**: Delete cell
- **ESC then M**: Convert to Markdown
- **ESC then Y**: Convert to Code

### Other
- **ESC then H**: Show all keyboard shortcuts
- **Shift + Tab**: Show function signature (when cursor on function)

## Need Help?

See `/tools/local-dev/README.md` for full documentation on:
- Starting/stopping Jupyter Labs
- Viewing logs
- Troubleshooting connectivity issues
- Running automated tests with Papermill

Or visit the project documentation at the control-plane API docs.

```python
ctx.teardown()
```
