"""User repository for database operations.

Roles are stored in the database (ADR-104). The auth middleware reads the
role from the DB record during request authentication.
"""

from control_plane.models import User, UserRole
from control_plane.repositories.base import (
    BaseRepository,
    parse_timestamp,
    utc_now,
)


class UserRepository(BaseRepository):
    """Repository for user database operations.

    Users must be provisioned in advance (ADR-104). Role is stored in the DB
    and read by auth middleware on each request.
    """

    async def get_by_username(self, username: str) -> User | None:
        """Get user by username.

        Args:
            username: User's username (primary key)

        Returns:
            User domain object or None if not found
        """
        sql = """
            SELECT username, email, display_name, role,
                   role_changed_at, role_changed_by,
                   created_at, updated_at, last_login_at, is_active
            FROM users
            WHERE username = :username
        """
        row = await self._fetch_one(sql, {"username": username})
        if row is None:
            return None
        return self._row_to_user(row)

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email address.

        Args:
            email: User's email address

        Returns:
            User domain object or None if not found
        """
        sql = """
            SELECT username, email, display_name, role,
                   role_changed_at, role_changed_by,
                   created_at, updated_at, last_login_at, is_active
            FROM users
            WHERE email = :email
        """
        row = await self._fetch_one(sql, {"email": email})
        if row is None:
            return None
        return self._row_to_user(row)

    async def list_users(
        self,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """List users with optional filters.

        Args:
            is_active: Filter by active status
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Tuple of (list of User objects, total count)
        """
        conditions = []
        params: dict = {"limit": limit, "offset": offset}

        if is_active is not None:
            conditions.append("is_active = :is_active")
            params["is_active"] = 1 if is_active else 0

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        count_sql = f"SELECT COUNT(*) FROM users WHERE {where_clause}"
        total = await self._fetch_scalar(count_sql, params)

        # Get paginated results
        sql = f"""
            SELECT username, email, display_name, role,
                   role_changed_at, role_changed_by,
                   created_at, updated_at, last_login_at, is_active
            FROM users
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """
        rows = await self._fetch_all(sql, params)
        users = [self._row_to_user(row) for row in rows]

        return users, total

    async def create(self, user: User) -> User:
        """Create a new user.

        Args:
            user: User domain object to create

        Returns:
            Created User with timestamps set
        """
        now = utc_now()
        sql = """
            INSERT INTO users (username, email, display_name, role,
                             created_at, updated_at, last_login_at, is_active)
            VALUES (:username, :email, :display_name, :role,
                    :created_at, :updated_at, :last_login_at, :is_active)
        """
        await self._execute(
            sql,
            {
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role.value,
                "created_at": now,
                "updated_at": now,
                "last_login_at": None,
                "is_active": 1 if user.is_active else 0,
            },
        )

        user.created_at = parse_timestamp(now)
        user.updated_at = parse_timestamp(now)
        return user

    async def ensure_exists(self, username: str, *, email: str | None = None) -> User:
        """Ensure user exists in database, creating if needed.

        This is the primary method for auto-creating users from request headers
        or JWT claims. Called by auth middleware when a new username is seen.

        Args:
            username: User's username (from X-Username header or JWT claim)
            email: Optional email address (from JWT claim). If not provided,
                   generates a placeholder email.

        Returns:
            User domain object (existing or newly created)
        """
        user = await self.get_by_username(username)
        if user is None:
            # Check if email is already taken by another user
            if email:
                existing_user = await self.get_by_email(email)
                if existing_user:
                    # Email already taken - use placeholder to avoid conflict
                    email = f"{username}@auto.local"
            user = User(
                username=username,
                email=email or f"{username}@auto.local",
                display_name=username,
                is_active=True,
            )
            user = await self.create(user)
        elif email and user.email != email:
            # Check if new email is already taken by another user
            existing_user = await self.get_by_email(email)
            if existing_user is None:
                # Safe to update - email not in use
                user.email = email
                user = await self.update(user)
            # If email is taken, skip update and keep current email
        return user

    async def update(self, user: User) -> User:
        """Update an existing user.

        Args:
            user: User domain object with updated values

        Returns:
            Updated User
        """
        now = utc_now()
        sql = """
            UPDATE users
            SET email = :email,
                display_name = :display_name,
                role = :role,
                updated_at = :updated_at,
                is_active = :is_active
            WHERE username = :username
        """
        await self._execute(
            sql,
            {
                "username": user.username,
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role.value,
                "updated_at": now,
                "is_active": 1 if user.is_active else 0,
            },
        )

        user.updated_at = parse_timestamp(now)
        return user

    async def update_last_login(self, username: str) -> None:
        """Update user's last login timestamp.

        Args:
            username: User's username
        """
        now = utc_now()
        sql = """
            UPDATE users
            SET last_login_at = :last_login_at,
                updated_at = :updated_at
            WHERE username = :username
        """
        await self._execute(
            sql,
            {
                "username": username,
                "last_login_at": now,
                "updated_at": now,
            },
        )

    async def deactivate(self, username: str) -> bool:
        """Deactivate a user account.

        Args:
            username: User's username

        Returns:
            True if user was found and deactivated
        """
        now = utc_now()
        sql = """
            UPDATE users
            SET is_active = 0,
                updated_at = :updated_at
            WHERE username = :username
        """
        result = await self._execute(sql, {"username": username, "updated_at": now})
        return result.rowcount > 0

    async def exists(self, username: str) -> bool:
        """Check if user exists.

        Args:
            username: User's username

        Returns:
            True if user exists
        """
        sql = "SELECT 1 FROM users WHERE username = :username"
        row = await self._fetch_one(sql, {"username": username})
        return row is not None

    async def create_with_role(
        self, username: str, email: str, display_name: str, role: UserRole,
    ) -> User:
        """Create a new user with a specific role (ADR-104)."""
        user = User(
            username=username,
            email=email,
            display_name=display_name,
            role=role,
        )
        return await self.create(user)

    async def assign_role(
        self, username: str, role: UserRole, changed_by: str,
    ) -> User | None:
        """Assign a role to a user (ADR-104).

        Records who made the change and when.
        """
        now = utc_now()
        sql = """
            UPDATE users
            SET role = :role,
                role_changed_at = :role_changed_at,
                role_changed_by = :role_changed_by,
                updated_at = :updated_at
            WHERE username = :username
        """
        result = await self._execute(
            sql,
            {
                "username": username,
                "role": role.value,
                "role_changed_at": now,
                "role_changed_by": changed_by,
                "updated_at": now,
            },
        )
        if result.rowcount == 0:
            return None
        return await self.get_by_username(username)

    async def update_fields(
        self, username: str, **kwargs,
    ) -> User | None:
        """Update specific fields on a user (ADR-104)."""
        user = await self.get_by_username(username)
        if user is None:
            return None

        if "email" in kwargs and kwargs["email"] is not None:
            user.email = kwargs["email"]
        if "display_name" in kwargs and kwargs["display_name"] is not None:
            user.display_name = kwargs["display_name"]
        if "is_active" in kwargs and kwargs["is_active"] is not None:
            user.is_active = kwargs["is_active"]

        return await self.update(user)

    async def count(self) -> int:
        """Count total users in the database (ADR-104)."""
        sql = "SELECT COUNT(*) AS cnt FROM users"
        row = await self._fetch_one(sql, {})
        return row.cnt if row else 0

    def _row_to_user(self, row) -> User:
        """Convert database row to User domain object."""
        return User(
            username=row.username,
            email=row.email,
            display_name=row.display_name,
            role=UserRole(row.role),
            role_changed_at=parse_timestamp(getattr(row, "role_changed_at", None)),
            role_changed_by=getattr(row, "role_changed_by", None),
            created_at=parse_timestamp(row.created_at),
            updated_at=parse_timestamp(row.updated_at),
            last_login_at=parse_timestamp(row.last_login_at),
            is_active=bool(row.is_active),
        )
