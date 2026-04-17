---
title: "UserResource"
---

<div class="nb-header">
  <span class="nb-header__type">Reference</span>
  <h1 class="nb-header__title">UserResource</h1>
  <p class="nb-header__subtitle">User account management</p>
  <div class="nb-header__meta">
    <span class="nb-header__meta-item nb-header__meta-item--duration">10 min</span>
    <span class="nb-header__meta-item nb-header__meta-item--level">
      <span class="nb-difficulty nb-difficulty--advanced">
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
        <span class="nb-difficulty__dot"></span>
      </span>
      Advanced
    </span>
  </div>
  <div class="nb-header__tags"><span class="nb-header__tag">Reference</span><span class="nb-header__tag">API</span><span class="nb-header__tag">Admin</span></div>
</div>

## UserResource

Accessed via `client.users`, this resource manages user accounts. Most
operations require the **admin** or **ops** role.

User data is returned as plain dictionaries with keys: `username`, `email`,
`display_name`, `role`, `is_active`, `created_at`, `updated_at`.

<div class="nb-section">
  <span class="nb-section__number">1</span>
  <div>
    <h2 class="nb-section__title">Setup</h2>
    <p class="nb-section__description">Connect with admin credentials</p>
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
from notebook_setup import provision
personas, _ = provision(USERNAME)
analyst = personas["analyst"]
admin = personas["admin"]
ops = personas["ops"]
client = analyst
```

<div class="nb-section">
  <span class="nb-section__number">2</span>
  <div>
    <h2 class="nb-section__title">Listing Users</h2>
    <p class="nb-section__description">Browse existing user accounts</p>
  </div>
</div>

### `list(is_active=None, limit=50, offset=0) -> list[dict]`

List user accounts with optional filters.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `is_active` | `bool \| None` | `None` | Filter by active status |
| `limit` | `int` | `50` | Maximum results (1--200) |
| `offset` | `int` | `0` | Number of results to skip |

**Returns:** List of user dictionaries.

**Requires:** Admin or Ops role.

```python
users = admin.users.list(limit=5)

print(f"Total users: {len(users)}\n")
for u in users:
    active = "active" if u["is_active"] else "inactive"
    print(f'  {u["username"]:<45} {u["role"]:<10} {active}')
```

```python
# Filter by active status
active_users = admin.users.list(is_active=True)
print(f"Active users: {len(active_users)}")
```

<div class="nb-section">
  <span class="nb-section__number">3</span>
  <div>
    <h2 class="nb-section__title">Getting a User</h2>
    <p class="nb-section__description">Retrieve a single user by username</p>
  </div>
</div>

### `get(username) -> dict`

Retrieve a user by username. Admin/Ops can view any user; other roles can
only view themselves.

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | `str` | Username to look up |

**Returns:** User data dictionary.

**Raises:** `NotFoundError` if the user does not exist.

```python
# Use the analyst client's actual username (namespaced by notebook_setup)
user = admin.users.get(client._config.username)

print(f"username:     {user['username']}")
print(f"email:        {user['email']}")
print(f"role:         {user['role']}")
print(f"display_name: {user['display_name']}")
print(f"is_active:    {user['is_active']}")
```

<div class="nb-section">
  <span class="nb-section__number">4</span>
  <div>
    <h2 class="nb-section__title">Creating Users</h2>
    <p class="nb-section__description">Provision new user accounts</p>
  </div>
</div>

### `create(username, email, display_name, role="analyst") -> dict`

Create a new user account.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `username` | `str` | *required* | Unique username |
| `email` | `str` | *required* | Email address |
| `display_name` | `str` | *required* | Display name |
| `role` | `str` | `"analyst"` | User role (`analyst`, `admin`, or `ops`) |

**Returns:** Created user data.

**Requires:** Admin or Ops role.

```python
test_username = "ref-testuser"

# Idempotent: create or fetch existing user
from graph_olap.exceptions import ConflictError
try:
    new_user = admin.users.create(
        username=test_username,
        email=f"{test_username}@example.com",
        display_name="Reference Test User",
        role="analyst",
    )
    print("Created user:")
except ConflictError:
    new_user = admin.users.get(test_username)
    print("User already exists:")

print(f"  username:     {new_user['username']}")
print(f"  email:        {new_user['email']}")
print(f"  role:         {new_user['role']}")
print(f"  display_name: {new_user['display_name']}")
```

<div class="nb-section">
  <span class="nb-section__number">5</span>
  <div>
    <h2 class="nb-section__title">Updating Users</h2>
    <p class="nb-section__description">Modify user metadata</p>
  </div>
</div>

### `update(username, **kwargs) -> dict`

Update mutable user fields.

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | `str` | Username to update |
| `**kwargs` | | Fields to update: `email`, `display_name`, `is_active` |

**Returns:** Updated user data.

**Requires:** Admin or Ops role.

```python
updated = admin.users.update(
    test_username,
    display_name="Updated Test User",
    email=f"{test_username}-updated@example.com",
)

print(f"display_name: {updated['display_name']}")
print(f"email:        {updated['email']}")
```

<div class="nb-section">
  <span class="nb-section__number">6</span>
  <div>
    <h2 class="nb-section__title">Role Management</h2>
    <p class="nb-section__description">Assign roles to users</p>
  </div>
</div>

### `assign_role(username, role) -> dict`

Change a user's role. Valid roles are `analyst`, `admin`, and `ops`.

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | `str` | Username to update |
| `role` | `str` | New role (`analyst`, `admin`, or `ops`) |

**Returns:** Updated user data.

**Requires:** Admin or Ops role.

```python
try:
    promoted = admin.users.assign_role(test_username, role="admin")
    print(f"Role after promotion: {promoted['role']}")

    # Demote back to analyst
    demoted = admin.users.assign_role(test_username, role="analyst")
    print(f"Role after demotion:  {demoted['role']}")
except Exception as e:
    # assign_role may not be supported on all deployments
    print(f"assign_role not available: {e}")
```

<div class="nb-section">
  <span class="nb-section__number">7</span>
  <div>
    <h2 class="nb-section__title">Deactivation</h2>
    <p class="nb-section__description">Disable user accounts</p>
  </div>
</div>

### `deactivate(username) -> dict`

Deactivate a user account. Deactivated users cannot log in or make API
requests.

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | `str` | Username to deactivate |

**Returns:** Deactivated user data.

**Requires:** Admin or Ops role.

```python
try:
    deactivated = admin.users.deactivate(test_username)
    print(f"User {test_username}: is_active={deactivated['is_active']}")
except Exception as e:
    print(f"deactivate not available: {e}")
```

<div class="nb-section">
  <span class="nb-section__number">8</span>
  <div>
    <h2 class="nb-section__title">Bootstrap</h2>
    <p class="nb-section__description">First-user provisioning</p>
  </div>
</div>

### `bootstrap(username, email, display_name) -> dict`

Bootstrap the very first user with the **ops** role. This method only succeeds
when no users exist in the database -- it is used during initial platform setup.

| Parameter | Type | Description |
|-----------|------|-------------|
| `username` | `str` | Username for the first user |
| `email` | `str` | Email address |
| `display_name` | `str` | Display name |

**Returns:** Created user data with `ops` role.

**Note:** This endpoint is intentionally not demonstrated because it requires an
empty user database. In practice, it is called once during platform
initialization.

<div class="nb-takeaways">
  <h3 class="nb-takeaways__title">Key Takeaways</h3>
  <ul class="nb-takeaways__list">
    <li>Access user management via <code>client.users</code> with an admin or ops client</li>
    <li><code>create()</code> provisions new accounts with a default <code>analyst</code> role</li>
    <li><code>assign_role()</code> promotes or demotes users between <code>analyst</code>, <code>admin</code>, and <code>ops</code></li>
    <li><code>deactivate()</code> disables accounts without deleting them</li>
    <li><code>bootstrap()</code> is a one-time operation for initial platform setup</li>
    <li>All responses are plain dictionaries (no Pydantic model wrapper)</li>
  </ul>
</div>
