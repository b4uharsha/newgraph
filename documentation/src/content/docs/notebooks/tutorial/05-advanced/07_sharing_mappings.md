---
title: "Sharing Mappings"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">Sharing Mappings</h1>
  <p class="nb-header__subtitle">Collaborate on mappings through list, copy, and admin-bypass patterns</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">20 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Mappings</span><span class="nb-header__tag">Collaboration</span><span class="nb-header__tag">Permissions</span><span class="nb-header__tag">Ownership</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Read any mapping</strong> - The catalogue is a shared reference; every analyst can list and inspect every mapping</li>
    <li><strong>Fork by copy</strong> - <code>client.mappings.copy(...)</code> creates an independent mapping owned by you</li>
    <li><strong>Admin-bypass edits</strong> - Admin or Ops can <code>update()</code> any mapping for in-place team-wide changes</li>
    <li><strong>Permission boundaries</strong> - Why <code>update()</code> on a teammate's mapping raises <code>PermissionDeniedError</code></li>
  </ul>
</div>

> **Background:** the platform has no ACLs, grants, ownership transfer, or "share" feature. Every mapping has exactly one owner, set at creation time and immutable. Collaboration happens through the three patterns below — see the [SDK Manual — Working With Other Users' Mappings](/sdk-manual/02-core-concepts-manual/#working-with-other-users-mappings) for the full narrative.

```python
# Cell 1 — Parameters
USERNAME = "_FILL_ME_IN_"  # Set your email before running
```

```python
# Cell 2 — Connect and provision personas
from graph_olap import GraphOLAPClient
from graph_olap.exceptions import PermissionDeniedError

from notebook_setup import provision

personas, conn = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]

# Pick a mapping from the catalogue — treat this as "a teammate's mapping"
teammate_mapping = analyst.mappings.list(search="tutorial-customer-graph").items[0]
print(f"Teammate's mapping: {teammate_mapping.name} (id={teammate_mapping.id}, owner={teammate_mapping.owner_username})")
```

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Pattern 1 — Read Any Mapping</h2>
    <p class="nb-section__description">The mapping catalogue is a shared reference. Read operations work on any mapping regardless of owner.</p>
  </div>
</div>

```python
# list() returns every mapping on the platform, not just yours
all_mappings = analyst.mappings.list(limit=5)
print(f"Catalogue size: {all_mappings.total}")
for m in all_mappings.items:
    print(f"  [{m.id}] {m.name} (owner: {m.owner_username})")

# get() and list_versions() work on any mapping id
versions = analyst.mappings.list_versions(teammate_mapping.id)
print(f"\n{teammate_mapping.name} has {len(versions)} version(s)")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Pattern 2 — Fork by Copy</h2>
    <p class="nb-section__description">Build on a teammate's mapping without modifying the original. The copy is yours to evolve.</p>
  </div>
</div>

```python
# copy() creates a new mapping owned by the caller, seeded from the source's current version
my_fork = analyst.mappings.copy(teammate_mapping.id, "MyFork-CustomerGraph")
print(f"Source:   [{teammate_mapping.id}] {teammate_mapping.name} (owner: {teammate_mapping.owner_username})")
print(f"My fork:  [{my_fork.id}] {my_fork.name} (owner: {my_fork.owner_username}, version: v{my_fork.current_version})")

# The fork is fully independent — no upstream link, no automatic sync.
# If the source mapping evolves, call copy() again to catch up.
```

```python
# You own the fork, so you can update it
updated = analyst.mappings.update(
    my_fork.id,
    change_description="Customised description for my analysis",
    description="My forked copy of the customer graph",
)
print(f"Updated fork to v{updated.current_version}: {updated.description}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Pattern 3 — Admin-Bypass for Shared Edits</h2>
    <p class="nb-section__description">When a mapping the whole team uses needs to change in place, only Admin or Ops can do it.</p>
  </div>
</div>

```python
# Calling update() on a mapping you don't own raises PermissionDeniedError (HTTP 403)
# Here we simulate trying to update a mapping owned by someone else.
# To demo the boundary we temporarily act as admin, who owns different resources.
admin_mapping = admin.mappings.list(owner=admin._config.username, limit=1).items

if admin_mapping:
    target = admin_mapping[0]
    try:
        analyst.mappings.update(
            target.id,
            change_description="analyst trying to edit admin's mapping",
            description="This will fail",
        )
    except PermissionDeniedError as e:
        print(f"Analyst cannot update admin's mapping: {e}")

    # Admin bypasses the ownership check
    bypassed = admin.mappings.update(
        target.id,
        change_description="admin in-place edit on behalf of team",
        description="Updated by admin for everyone",
    )
    print(f"Admin updated {target.name} to v{bypassed.current_version}")
else:
    print("(No admin-owned mapping available to demo the bypass)")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">What You Cannot Do</h2>
    <p class="nb-section__description">Collaboration features that don't exist on the platform</p>
  </div>
</div>

The platform intentionally does **not** provide:

- Sharing a mapping with specific teammates (no ACLs or grants)
- Transferring ownership of a mapping
- Merging two mappings
- Querying across multiple mappings in one call
- An upstream/downstream link between a fork and its source

For policy and rationale, see [Authorization — §4.1 Collaboration Patterns](/architecture/authorization/#41-collaboration-patterns).

```python
# Cleanup — delete the fork you created
analyst.mappings.delete(my_fork.id)
print(f"Deleted fork {my_fork.name}")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>The mapping catalogue is <strong>shared reference data</strong> — every analyst can <code>list()</code>, <code>get()</code>, and <code>list_versions()</code> on any mapping</li>
    <li><code>mappings.copy(id, new_name)</code> is the collaboration primitive — it creates an independent mapping owned by you</li>
    <li>A fork has <strong>no upstream link</strong> — call <code>copy()</code> again to pick up the source's latest changes</li>
    <li><code>update()</code> on another user's mapping raises <code>PermissionDeniedError</code>; only <strong>Admin</strong> or <strong>Ops</strong> can bypass ownership</li>
    <li>There is no "share with user X" feature, no ACL, no transfer of ownership — collaboration is by copy or by admin</li>
  </ul>
</div>

**See also:**

- [SDK Manual — Working With Other Users' Mappings](/sdk-manual/02-core-concepts-manual/#working-with-other-users-mappings) — full narrative walkthrough
- [Authorization — §3.1 Data Resources](/architecture/authorization/#31-data-resources) — permission matrix
- [API — `POST /mappings/:id/copy`](/api/api-mappings-spec/#post-mappingsidcopy) — REST reference for admins and integrators
- [03_advanced_mappings](03_advanced_mappings/) — hierarchy, versioning, and diffing
