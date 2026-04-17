"""Unit tests for SSL handling in create_engine_for_settings."""

from unittest.mock import MagicMock, patch

from control_plane.infrastructure.database import create_engine_for_settings


class TestDatabaseSSL:
    """Tests that localhost connections disable SSL (Cloud SQL Proxy handles encryption)."""

    def _make_settings(self, database_url: str) -> MagicMock:
        """Create a mock Settings with the given database_url."""
        settings = MagicMock()
        settings.database_url = database_url
        settings.async_database_url = database_url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )
        settings.db_echo = False
        settings.db_pool_size = 5
        settings.db_max_overflow = 2
        return settings

    @patch("control_plane.infrastructure.database.create_async_engine")
    def test_localhost_disables_ssl(self, mock_create: MagicMock) -> None:
        """Localhost URL should pass connect_args={"ssl": None}."""
        settings = self._make_settings("postgresql://user:pass@localhost:5432/db")
        create_engine_for_settings(settings)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["connect_args"] == {"ssl": None}

    @patch("control_plane.infrastructure.database.create_async_engine")
    def test_loopback_ip_disables_ssl(self, mock_create: MagicMock) -> None:
        """127.0.0.1 URL should pass connect_args={"ssl": None}."""
        settings = self._make_settings("postgresql://user:pass@127.0.0.1:5432/db")
        create_engine_for_settings(settings)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["connect_args"] == {"ssl": None}

    @patch("control_plane.infrastructure.database.create_async_engine")
    def test_remote_host_does_not_disable_ssl(self, mock_create: MagicMock) -> None:
        """Remote URL should pass empty connect_args (SSL left to driver defaults)."""
        settings = self._make_settings("postgresql://user:pass@db.example.com:5432/db")
        create_engine_for_settings(settings)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["connect_args"] == {}
