---
title: "Managing Favorites"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Managing Favorites</h1>
  <p class="nb-header__subtitle">Bookmark and organize your frequently used resources</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--beginner">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Beginner
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Favorites</span><span class="nb-header__tag">Bookmarks</span><span class="nb-header__tag">Organization</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Adding Favorites</strong> - Bookmark mappings and instances</li>
    <li><strong>Listing Favorites</strong> - View your bookmarked resources</li>
    <li><strong>Filtering</strong> - Filter favorites by resource type</li>
    <li><strong>Quick Access</strong> - Rapidly access favorite resources</li>
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

mapping = client.mappings.list().items[0]
print(f"Connected to: {client._config.api_url}")
print(f"Using mapping: {mapping.name} (id={mapping.id})")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Adding Favorites</h2>
    <p class="nb-section__description">Bookmark any resource</p>
  </div>
</div>

```python
# Add a mapping to favorites
favorite = client.favorites.add(
    resource_type="mapping",
    resource_id=mapping.id,
)
print(f"Added to favorites: {favorite.resource_type} {favorite.resource_id}")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Viewing Favorites</h2>
    <p class="nb-section__description">List and filter bookmarks</p>
  </div>
</div>

```python
# List all favorites
favorites = client.favorites.list()
for fav in favorites:
    print(f"{fav.resource_type}: {fav.resource_id}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Managing Favorites</h2>
    <p class="nb-section__description">Update and remove bookmarks</p>
  </div>
</div>

```python
# Filter by type
mapping_favs = client.favorites.list(resource_type="mapping")
print(f"Mapping favorites: {len(mapping_favs)}")
```

```python
# Remove a favorite
client.favorites.remove(
    resource_type=favorite.resource_type,
    resource_id=favorite.resource_id,
)
print(f"Removed favorite: {favorite.resource_type} {favorite.resource_id}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Favorite any resource type (mapping, instance)</li>
    <li>Favorites are identified by (resource_type, resource_id)</li>
    <li>Filter favorites by resource type</li>
    <li>Quick access to frequently used resources</li>
  </ul>
</div>
