---
title: "User Management"
---

<div class="nb-header">
  <span class="nb-header__type">Tutorial</span>
  <h1 class="nb-header__title">User Management</h1>
  <p class="nb-header__subtitle">Create, manage, and deactivate user accounts with role-based access</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">25 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--intermediate">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Intermediate
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Users</span><span class="nb-header__tag">Roles</span><span class="nb-header__tag">Admin</span><span class="nb-header__tag">Access Control</span></div>
</div>

<div class="nb-objectives">
  <h3 class="nb-objectives__title">What You'll Learn</h3>
  <ul class="nb-objectives__list">
    <li><strong>Create Users</strong> - Provision new accounts with role assignment</li>
    <li><strong>List &amp; Filter</strong> - Retrieve users and filter by active status</li>
    <li><strong>Update Metadata</strong> - Change email, display name, and reactivate accounts</li>
    <li><strong>Role Assignment</strong> - Promote and demote between analyst, admin, and ops</li>
    <li><strong>Deactivate Users</strong> - Disable departed team members without deletion</li>
  </ul>
</div>

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect to the platform and provision personas</p>
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

# Carol (admin) manages users in this tutorial
carol = admin
print("Carol (admin) ready for user management")
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">The Role Hierarchy</h2>
    <p class="nb-section__description">Three levels of access: analyst, admin, and ops</p>
  </div>
</div>

```python
# The three roles, from least to most privileged
roles = ["analyst", "admin", "ops"]
print("Role hierarchy (least \u2192 most privileged):")
for i, role in enumerate(roles):
    print(f"  {'  ' * i}{role}")
print("\nAnalysts: query and analyze graphs")
print("Admins:   manage users + analyst capabilities")
print("Ops:      platform configuration + admin capabilities")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Creating Users</h2>
    <p class="nb-section__description">Provision new accounts with default or explicit roles</p>
  </div>
</div>

```python
from graph_olap.exceptions import ConflictError

# Carol creates Alice (analyst)
try:
    alice = carol.users.create(
        username="tutorial-alice",
        email="alice@example.com",
        display_name="Alice Johnson",
        role="analyst",
    )
    print("Created Alice:")
except ConflictError:
    alice = carol.users.get("tutorial-alice")
    print("Alice already exists:")

print(f"  username: {alice['username']}")
print(f"  role:     {alice['role']}")
print(f"  active:   {alice['is_active']}")
```

```python
# Carol creates Bob (analyst)
try:
    bob = carol.users.create(
        username="tutorial-bob",
        email="bob@example.com",
        display_name="Bob Smith",
        role="analyst",
    )
    print("Created Bob:")
except ConflictError:
    bob = carol.users.get("tutorial-bob")
    print("Bob already exists:")

print(f"  username: {bob['username']}")
print(f"  role:     {bob['role']}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Listing and Filtering Users</h2>
    <p class="nb-section__description">Retrieve users with optional active-status filtering</p>
  </div>
</div>

```python
# List all users
users = carol.users.list(limit=10)
print(f"Total users: {len(users)}\n")
for u in users:
    status = "active" if u["is_active"] else "inactive"
    print(f"  {u['username']:<35} {u['role']:<10} {status}")
```

```python
# Filter by active status
active = carol.users.list(is_active=True)
print(f"Active users: {len(active)}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Updating User Metadata</h2>
    <p class="nb-section__description">Change display name, email, or reactivate accounts</p>
  </div>
</div>

```python
updated = carol.users.update(
    "tutorial-alice",
    display_name="Alice J. Johnson",
    email="alice.johnson@example.com",
)
print(f"Updated Alice:")
print(f"  display_name: {updated['display_name']}")
print(f"  email:        {updated['email']}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Role Assignment</h2>
    <p class="nb-section__description">Promote or demote users between analyst, admin, and ops</p>
  </div>
</div>

```python
# Promote Alice to admin
try:
    promoted = carol.users.assign_role("tutorial-alice", role="admin")
    print(f"Alice promoted: role={promoted['role']}")
except Exception as e:
    print(f"assign_role: {e}")

# Demote back to analyst
try:
    demoted = carol.users.assign_role("tutorial-alice", role="analyst")
    print(f"Alice demoted:  role={demoted['role']}")
except Exception as e:
    print(f"assign_role: {e}")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Deactivating Users</h2>
    <p class="nb-section__description">When a team member departs, deactivate rather than delete</p>
  </div>
</div>

```python
try:
    deactivated = carol.users.deactivate("tutorial-bob")
    print(f"Deactivated Bob: is_active={deactivated['is_active']}")
except Exception as e:
    print(f"deactivate: {e}")

# Verify Bob appears as inactive
bob_check = carol.users.get("tutorial-bob")
print(f"Bob status:      is_active={bob_check['is_active']}")
```

```python
# Reactivate by updating is_active
reactivated = carol.users.update("tutorial-bob", is_active=True)
print(f"Reactivated Bob: is_active={reactivated['is_active']}")
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
  <div>
    <h2 class="nb-section__title">Bootstrap (First-Time Setup)</h2>
    <p class="nb-section__description">One-time provisioning of the first ops user on an empty database</p>
  </div>
</div>

```python
# bootstrap() is a one-time operation for initial platform setup.
# It only works when no users exist in the database.
#
# ops.users.bootstrap(
#     username="platform-admin",
#     email="admin@company.com",
#     display_name="Platform Admin",
# )
# Returns: dict with role="ops"
print("bootstrap() creates the first ops user during initial setup")
print("It only succeeds when the user database is empty")
```

```python
# Clean up tutorial users
for username in ["tutorial-alice", "tutorial-bob"]:
    try:
        carol.users.deactivate(username)
    except Exception:
        pass
print("Tutorial users cleaned up")
```

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Access user management via <code>client.users</code> with an admin or ops client</li>
    <li><code>create()</code> provisions new accounts with a default <code>analyst</code> role</li>
    <li><code>list()</code> and <code>get()</code> retrieve user data; filter with <code>is_active</code></li>
    <li><code>assign_role()</code> promotes or demotes between <code>analyst</code>, <code>admin</code>, and <code>ops</code></li>
    <li><code>deactivate()</code> disables accounts without deleting them -- preferred over deletion</li>
    <li><code>bootstrap()</code> is a one-time operation for initial platform provisioning</li>
  </ul>
</div>
