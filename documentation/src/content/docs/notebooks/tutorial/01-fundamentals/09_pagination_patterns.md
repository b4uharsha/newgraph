---
title: "Pagination Patterns"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Pagination Patterns</h1>
  <p class="nb-header__subtitle">Navigate large result sets with the PaginatedList API</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">15 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Pagination</span><span class="nb-header__tag">PaginatedList</span><span class="nb-header__tag">Filtering</span><span class="nb-header__tag">Sorting</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Paginated Responses</strong> - Understand <code>PaginatedList</code> properties: items, total, has_more, page_count</li>
    <li><strong>Iteration & Indexing</strong> - Iterate, index, and measure pages with Python protocols</li>
    <li><strong>Paging Through Results</strong> - Walk through all pages with offset/limit loops</li>
    <li><strong>Filtering, Sorting & Search</strong> - Narrow results server-side by status, name, or field order</li>
  </ul>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the platform and provision tutorial data</p>
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

print(f"Connected | {conn.query_scalar('MATCH (n) RETURN count(n)')} nodes")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Understanding PaginatedList</h2>
    <p class="nb-section__description">Inspect the properties every list endpoint returns</p>
  </div>
</div>

```python
# List mappings with a small page size
page = client.mappings.list(limit=2, offset=0)

print(f"Items on page: {len(page.items)}")
print(f"Total items:   {page.total}")
print(f"Offset:        {page.offset}")
print(f"Limit:         {page.limit}")
print(f"Has more:      {page.has_more}")
print(f"Page count:    {page.page_count}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Iterating and Indexing</h2>
    <p class="nb-section__description">Use Python protocols to work with page contents</p>
  </div>
</div>

```python
# Direct iteration
for mapping in page:
    print(f"  [{mapping.id}] {mapping.name}")

# Length
print(f"\nItems in page: {len(page)}")

# Index access
first = page[0]
print(f"First item: {first.name}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Paging Through All Results</h2>
    <p class="nb-section__description">Walk every page with an offset/limit loop</p>
  </div>
</div>

```python
# Collect all mappings across pages
all_mappings = []
offset = 0
limit = 10

while True:
    page = client.mappings.list(limit=limit, offset=offset)
    all_mappings.extend(page.items)
    if not page.has_more:
        break
    offset += limit

print(f"Retrieved {len(all_mappings)} mappings across {(len(all_mappings) + limit - 1) // limit} pages")
for m in all_mappings[:5]:
    print(f"  [{m.id}] {m.name}")
if len(all_mappings) > 5:
    print(f"  ... and {len(all_mappings) - 5} more")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Filtering and Searching</h2>
    <p class="nb-section__description">Narrow results server-side before they reach your code</p>
  </div>
</div>

```python
# Search by name pattern
results = client.mappings.list(search="customer")
print(f"Mappings matching 'customer': {results.total}")
for m in results:
    print(f"  [{m.id}] {m.name}")
```

```python
# Filter instances by status
running = client.instances.list(status="running", limit=5)
print(f"Running instances: {running.total}")
for inst in running:
    print(f"  [{inst.id}] {inst.name} ({inst.status})")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Sorting</h2>
    <p class="nb-section__description">Control the order of results with sort_by and sort_order</p>
  </div>
</div>

```python
# Sort mappings by name
sorted_page = client.mappings.list(sort_by="name", sort_order="asc", limit=5)
print("Mappings sorted by name:")
for m in sorted_page:
    print(f"  [{m.id}] {m.name}")

# Sort by creation date (newest first)
recent = client.mappings.list(sort_by="created_at", sort_order="desc", limit=3)
print("\nMost recent mappings:")
for m in recent:
    print(f"  [{m.id}] {m.name} (created {m.created_at})")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>All list endpoints return <code>PaginatedList</code> with <code>.items</code>, <code>.total</code>, <code>.has_more</code>, and <code>.page_count</code></li>
    <li>Use <code>offset</code> and <code>limit</code> to page through large result sets</li>
    <li>Filter by status, search by name, and sort by any field to find what you need</li>
    <li><code>PaginatedList</code> supports direct iteration, <code>len()</code>, and index access</li>
  </ul>
</div>
