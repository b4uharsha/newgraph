---
title: "FavoriteResource"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">FavoriteResource</h1>
  <p class="nb-header__subtitle">Bookmark frequently used resources</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">5 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span></div>
</div>

## FavoriteResource

Accessed via `client.favorites`, this resource lets users bookmark frequently
used mappings or instances for quick access.

Favorites are per-user and support two resource types: `mapping` and `instance`.

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the platform and find a mapping to favorite</p>
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
from notebook_setup import provision, CUSTOMER_NODE, SHARES_ACCOUNT_EDGE
personas, _ = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst

# Create a mapping to use as favorite target
ref_mapping = client.mappings.create(
    name="ref-fav-target",
    node_definitions=[CUSTOMER_NODE],
    edge_definitions=[SHARES_ACCOUNT_EDGE],
)
print(f"Using mapping [{ref_mapping.id}] as favorite target")
```

```python
# Use the tracked mapping created in setup
mapping_id = ref_mapping.id
print(f"Favoriting mapping: [{mapping_id}]")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Adding Favorites</h2>
    <p class="nb-section__description">Bookmark a resource</p>
  </div>
</div>

### `add(resource_type, resource_id) -> Favorite`

Add a resource to the current user's favorites.

| Parameter | Type | Description |
|-----------|------|-------------|
| `resource_type` | `str` | `"mapping"` or `"instance"` |
| `resource_id` | `int` | ID of the resource to bookmark |

**Returns:** `Favorite` object with `resource_type`, `resource_id`, `resource_name`, and `created_at`.

**Raises:** `NotFoundError` if the resource does not exist. `ConflictError` if already favorited.

```python
fav = client.favorites.add("mapping", mapping_id)

print(f"Type:    {fav.resource_type}")
print(f"ID:      {fav.resource_id}")
print(f"Name:    {fav.resource_name}")
print(f"Added:   {fav.created_at}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Listing Favorites</h2>
    <p class="nb-section__description">View bookmarked resources</p>
  </div>
</div>

### `list(resource_type=None) -> list[Favorite]`

List the current user's favorites, optionally filtered by resource type.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resource_type` | `str \| None` | `None` | Filter by `"mapping"` or `"instance"` |

**Returns:** List of `Favorite` objects.

```python
# List all favorites
favorites = client.favorites.list()
print(f"Total favorites: {len(favorites)}\n")

for fav in favorites:
    print(f"  {fav.resource_type}: {fav.resource_name} (id={fav.resource_id})")
```

```python
# Filter by resource type
mapping_favs = client.favorites.list(resource_type="mapping")
instance_favs = client.favorites.list(resource_type="instance")

print(f"Mapping favorites:  {len(mapping_favs)}")
print(f"Instance favorites: {len(instance_favs)}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Removing Favorites</h2>
    <p class="nb-section__description">Un-bookmark a resource</p>
  </div>
</div>

### `remove(resource_type, resource_id) -> None`

Remove a resource from the current user's favorites.

| Parameter | Type | Description |
|-----------|------|-------------|
| `resource_type` | `str` | `"mapping"` or `"instance"` |
| `resource_id` | `int` | ID of the resource to un-bookmark |

**Raises:** `NotFoundError` if the favorite does not exist.

```python
client.favorites.remove("mapping", mapping_id)
print("Favorite removed.")

# Verify it is gone
favorites = client.favorites.list()
print(f"Remaining favorites: {len(favorites)}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li><code>client.favorites</code> manages per-user bookmarks for mappings and instances</li>
    <li><code>add()</code> returns a <code>Favorite</code> object with the resource name and timestamp</li>
    <li><code>list()</code> accepts an optional <code>resource_type</code> filter</li>
    <li><code>remove()</code> deletes a bookmark -- it does not affect the underlying resource</li>
  </ul>
</div>
