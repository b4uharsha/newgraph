---
title: "Reference Notebooks"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">Reference Notebooks</h1>
  <p class="nb-header__subtitle">Complete API reference for the Graph OLAP platform</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">2 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">Index</span></div>
</div>

## Reference Documentation

The reference notebooks provide executable API documentation for every public class and method
in the Graph OLAP Python SDK. Each notebook includes parameter tables, return types, error cases,
and runnable code examples.

### SDK Reference

The [SDK reference notebooks](sdk/) cover all 13 resource classes:

| Category | Notebooks | Role |
|----------|-----------|------|
| **Client & Core** | `GraphOLAPClient`, `InstanceResource`, `InstanceConnection`, `MappingResource` | analyst |
| **Algorithms** | `AlgorithmManager` + `NetworkXManager` (combined) | analyst |
| **Data & Discovery** | `SchemaResource`, `FavoriteResource`, `HealthResource` | analyst |
| **Administration** | `UserResource`, `AdminResource`, `OpsResource` | admin / ops |
| **Types & Errors** | Models, Exceptions | analyst |

All notebooks use the `notebook_setup` pattern with automatic resource tracking and cleanup.
