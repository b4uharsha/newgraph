"""Global configuration repository for database operations."""

from dataclasses import dataclass
from typing import Any

from control_plane.config import get_settings
from control_plane.repositories.base import (
    BaseRepository,
    parse_timestamp,
    utc_now,
)


@dataclass
class ConfigEntry:
    """A global configuration entry."""

    key: str
    value: str
    description: str | None
    updated_at: str
    updated_by: str


# Default configuration values
DEFAULT_CONFIG = {
    "lifecycle.mapping.default_ttl": (None, "Default mapping TTL (null = no expiry)"),
    "lifecycle.mapping.default_inactivity": ("P30D", "Default mapping inactivity timeout"),
    "lifecycle.mapping.max_ttl": ("P365D", "Maximum allowed mapping TTL"),
    "lifecycle.snapshot.default_ttl": ("P7D", "Default snapshot TTL"),
    "lifecycle.snapshot.default_inactivity": ("P3D", "Default snapshot inactivity timeout"),
    "lifecycle.snapshot.max_ttl": ("P30D", "Maximum allowed snapshot TTL"),
    "lifecycle.instance.default_ttl": ("PT24H", "Default instance TTL"),
    "lifecycle.instance.default_inactivity": ("PT4H", "Default instance inactivity timeout"),
    "lifecycle.instance.max_ttl": ("P7D", "Maximum allowed instance TTL"),
    "concurrency.per_analyst": ("5", "Max instances per analyst"),
    "concurrency.cluster_total": ("50", "Max instances cluster-wide"),
    "maintenance.enabled": ("0", "Maintenance mode on/off (0 or 1)"),
    "maintenance.message": ("System is under maintenance", "Message shown during maintenance"),
    "cache.metadata.ttl_hours": ("24", "Schema metadata cache TTL in hours"),
    "export.max_duration_seconds": ("3600", "Max export job duration before timeout (1 hour)"),
}


class GlobalConfigRepository(BaseRepository):
    """Repository for global configuration database operations."""

    async def get(self, key: str) -> ConfigEntry | None:
        """Get a configuration entry by key.

        Args:
            key: Configuration key

        Returns:
            ConfigEntry or None if not found
        """
        sql = """
            SELECT key, value, description, updated_at, updated_by
            FROM global_config
            WHERE key = :key
        """
        row = await self._fetch_one(sql, {"key": key})
        if row is None:
            return None
        return self._row_to_config_entry(row)

    async def get_value(self, key: str, default: str | None = None) -> str | None:
        """Get just the value for a configuration key.

        Args:
            key: Configuration key
            default: Default value if not found

        Returns:
            Configuration value or default
        """
        sql = "SELECT value FROM global_config WHERE key = :key"
        value = await self._fetch_scalar(sql, {"key": key})
        return value if value is not None else default

    async def get_int(self, key: str, default: int = 0) -> int:
        """Get configuration value as integer.

        Args:
            key: Configuration key
            default: Default value if not found or not parseable

        Returns:
            Integer value
        """
        value = await self.get_value(key)
        if value is None:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        """Get configuration value as boolean.

        Args:
            key: Configuration key
            default: Default value if not found

        Returns:
            Boolean value (treats '1', 'true', 'yes' as True)
        """
        value = await self.get_value(key)
        if value is None:
            return default
        return value.lower() in ("1", "true", "yes")

    async def list_all(self) -> list[ConfigEntry]:
        """List all configuration entries.

        Returns:
            List of ConfigEntry objects
        """
        sql = """
            SELECT key, value, description, updated_at, updated_by
            FROM global_config
            ORDER BY key
        """
        rows = await self._fetch_all(sql, {})
        return [self._row_to_config_entry(row) for row in rows]

    async def list_by_prefix(self, prefix: str) -> list[ConfigEntry]:
        """List configuration entries with a key prefix.

        Args:
            prefix: Key prefix (e.g., 'lifecycle.')

        Returns:
            List of ConfigEntry objects
        """
        sql = """
            SELECT key, value, description, updated_at, updated_by
            FROM global_config
            WHERE key LIKE :prefix
            ORDER BY key
        """
        rows = await self._fetch_all(sql, {"prefix": f"{prefix}%"})
        return [self._row_to_config_entry(row) for row in rows]

    async def set(
        self,
        key: str,
        value: str,
        updated_by: str,
        description: str | None = None,
    ) -> ConfigEntry:
        """Set a configuration value.

        Creates the entry if it doesn't exist, updates if it does.

        Args:
            key: Configuration key
            value: Configuration value
            updated_by: Username of the user making the change
            description: Optional description

        Returns:
            Updated ConfigEntry
        """
        now = utc_now()

        # Try update first
        update_sql = """
            UPDATE global_config
            SET value = :value,
                description = COALESCE(:description, description),
                updated_at = :updated_at,
                updated_by = :updated_by
            WHERE key = :key
        """
        result = await self._execute(
            update_sql,
            {
                "key": key,
                "value": value,
                "description": description,
                "updated_at": now,
                "updated_by": updated_by,
            },
        )

        if result.rowcount == 0:
            # Insert new entry
            insert_sql = """
                INSERT INTO global_config (key, value, description, updated_at, updated_by)
                VALUES (:key, :value, :description, :updated_at, :updated_by)
            """
            await self._execute(
                insert_sql,
                {
                    "key": key,
                    "value": value,
                    "description": description,
                    "updated_at": now,
                    "updated_by": updated_by,
                },
            )

        return ConfigEntry(
            key=key,
            value=value,
            description=description,
            updated_at=now,
            updated_by=updated_by,
        )

    async def delete(self, key: str) -> bool:
        """Delete a configuration entry.

        Args:
            key: Configuration key

        Returns:
            True if entry was deleted
        """
        sql = "DELETE FROM global_config WHERE key = :key"
        result = await self._execute(sql, {"key": key})
        return result.rowcount > 0

    async def seed_defaults(self, updated_by: str = "system") -> int:
        """Seed default configuration values if not already set.

        Concurrency limits are read from environment variables (via Settings)
        to allow Helm configuration.

        Args:
            updated_by: Username for the seeded entries

        Returns:
            Number of entries created
        """
        now = utc_now()
        created = 0

        # Get settings for configurable defaults
        settings = get_settings()

        # Override hardcoded defaults with settings values
        config_overrides = {
            "concurrency.per_analyst": str(settings.concurrency_per_analyst),
            "concurrency.cluster_total": str(settings.concurrency_cluster_total),
        }

        for key, (value, description) in DEFAULT_CONFIG.items():
            # Check if already exists
            existing = await self.get(key)
            if existing is None:
                # Use override if available, otherwise use hardcoded default
                final_value = config_overrides.get(key, value)
                sql = """
                    INSERT INTO global_config (key, value, description, updated_at, updated_by)
                    VALUES (:key, :value, :description, :updated_at, :updated_by)
                """
                await self._execute(
                    sql,
                    {
                        "key": key,
                        "value": final_value if final_value is not None else "",
                        "description": description,
                        "updated_at": now,
                        "updated_by": updated_by,
                    },
                )
                created += 1

        return created

    async def get_lifecycle_config(self, resource_type: str) -> dict[str, Any]:
        """Get lifecycle configuration for a resource type.

        Args:
            resource_type: 'mapping', 'snapshot', or 'instance'

        Returns:
            Dictionary with default_ttl, default_inactivity, max_ttl
        """
        prefix = f"lifecycle.{resource_type}."
        entries = await self.list_by_prefix(prefix)

        config = {}
        for entry in entries:
            # Extract suffix (e.g., 'default_ttl' from 'lifecycle.instance.default_ttl')
            suffix = entry.key.replace(prefix, "")
            config[suffix] = entry.value if entry.value else None

        return config

    async def get_concurrency_limits(self) -> dict[str, int]:
        """Get concurrency limit configuration.

        Returns:
            Dictionary with per_analyst and cluster_total limits
        """
        per_analyst = await self.get_int("concurrency.per_analyst", 5)
        cluster_total = await self.get_int("concurrency.cluster_total", 50)

        return {
            "per_analyst": per_analyst,
            "cluster_total": cluster_total,
        }

    async def is_maintenance_mode(self) -> bool:
        """Check if system is in maintenance mode.

        Returns:
            True if maintenance mode is enabled
        """
        return await self.get_bool("maintenance.enabled", False)

    async def get_maintenance_message(self) -> str:
        """Get maintenance mode message.

        Returns:
            Maintenance message
        """
        return (
            await self.get_value("maintenance.message", "System is under maintenance")
            or "System is under maintenance"
        )

    async def get_config_with_metadata(self, key: str) -> dict[str, Any] | None:
        """Get configuration entry with metadata (updated_at, updated_by).

        Args:
            key: Configuration key

        Returns:
            Dictionary with value and metadata, or None if not found
        """
        sql = """
            SELECT key, value, description, updated_at, updated_by
            FROM global_config
            WHERE key = :key
        """
        row = await self._fetch_one(sql, {"key": key})
        if row is None:
            return None
        return {
            "key": row.key,
            "value": row.value,
            "description": row.description,
            "updated_at": parse_timestamp(row.updated_at),
            "updated_by": row.updated_by,
        }

    async def get_export_config(self) -> dict[str, Any]:
        """Get export configuration.

        Returns:
            Dictionary with max_duration_seconds and metadata
        """
        max_duration = await self.get_int("export.max_duration_seconds", 3600)
        config = await self.get_config_with_metadata("export.max_duration_seconds")

        return {
            "max_duration_seconds": max_duration,
            "updated_at": config.get("updated_at") if config else None,
            "updated_by": config.get("updated_by") if config else None,
        }

    def _row_to_config_entry(self, row) -> ConfigEntry:
        """Convert database row to ConfigEntry object."""
        return ConfigEntry(
            key=row.key,
            value=row.value,
            description=row.description,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )
