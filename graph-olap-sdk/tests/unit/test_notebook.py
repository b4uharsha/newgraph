"""Tests for notebook helper module."""

from unittest.mock import MagicMock, patch

import pytest

from graph_olap import notebook
from graph_olap.client import GraphOLAPClient


class TestConnect:
    """Tests for notebook.connect()."""

    def test_connect_with_env_vars(self, monkeypatch):
        """Test connecting using environment variables."""
        monkeypatch.setenv("GRAPH_OLAP_API_URL", "https://api.example.com")
        monkeypatch.setenv("GRAPH_OLAP_USERNAME", "test-user@example.com")

        client = notebook.connect()

        assert client is not None
        assert isinstance(client, GraphOLAPClient)
        assert client._config.api_url == "https://api.example.com"
        assert client._config.username == "test-user@example.com"

    def test_connect_with_explicit_params(self, monkeypatch):
        """Test connecting with explicit parameters."""
        # Set a default in env that will be overridden
        monkeypatch.setenv("GRAPH_OLAP_API_URL", "https://default.example.com")

        client = notebook.connect(
            api_url="https://override.example.com",
            username="override-user@example.com",
        )

        assert client._config.api_url == "https://override.example.com"
        assert client._config.username == "override-user@example.com"

    def test_connect_with_additional_kwargs(self, monkeypatch):
        """Test connecting with additional configuration options."""
        monkeypatch.setenv("GRAPH_OLAP_API_URL", "https://api.example.com")

        client = notebook.connect(timeout=60, max_retries=5)

        assert client._config.timeout == 60
        assert client._config.max_retries == 5

    def test_connect_missing_api_url(self, monkeypatch):
        """Test that connect fails without API URL."""
        # Remove API URL from environment
        monkeypatch.delenv("GRAPH_OLAP_API_URL", raising=False)

        with pytest.raises(ValueError, match="GRAPH_OLAP_API_URL"):
            notebook.connect()

    def test_connect_stores_global_client(self, monkeypatch):
        """Test that connect stores the client globally."""
        monkeypatch.setenv("GRAPH_OLAP_API_URL", "https://api.example.com")

        client = notebook.connect()

        # Should be retrievable via get_client()
        assert notebook.get_client() is client

    @patch("graph_olap.notebook._setup_itables")
    def test_connect_calls_setup_itables(self, mock_setup, monkeypatch):
        """Test that connect initializes itables."""
        monkeypatch.setenv("GRAPH_OLAP_API_URL", "https://api.example.com")

        notebook.connect()

        mock_setup.assert_called_once()


class TestInit:
    """Tests for notebook.init() alias."""

    def test_init_is_alias_for_connect(self, monkeypatch):
        """Test that init() works the same as connect()."""
        monkeypatch.setenv("GRAPH_OLAP_API_URL", "https://api.example.com")

        client = notebook.init(username="test-user@example.com")

        assert isinstance(client, GraphOLAPClient)
        assert client._config.username == "test-user@example.com"


class TestGetClient:
    """Tests for notebook.get_client()."""

    def test_get_client_returns_none_initially(self):
        """Test that get_client returns None before connect."""
        # Reset global state
        notebook._current_client = None

        assert notebook.get_client() is None

    def test_get_client_returns_connected_client(self, monkeypatch):
        """Test that get_client returns the client after connect."""
        monkeypatch.setenv("GRAPH_OLAP_API_URL", "https://api.example.com")

        client = notebook.connect()

        assert notebook.get_client() is client


class TestSetupItables:
    """Tests for _setup_itables()."""

    def test_setup_itables_success(self):
        """Test successful itables setup."""
        # Mock itables at the import level
        mock_itables = MagicMock()
        with patch.dict("sys.modules", {"itables": mock_itables}):
            notebook._setup_itables()
            mock_itables.init_notebook_mode.assert_called_once_with(all_interactive=True)

    def test_setup_itables_not_installed(self):
        """Test that missing itables is handled gracefully."""
        # Simulate ImportError by removing from sys.modules
        with patch("builtins.__import__", side_effect=ImportError):
            # Should not raise
            notebook._setup_itables()


class TestSetupDisplay:
    """Tests for _setup_display()."""

    def test_setup_display_with_ipython(self):
        """Test setup display when IPython is available."""
        mock_ip = MagicMock()
        mock_get_ipython = MagicMock(return_value=mock_ip)
        mock_ipython = MagicMock()
        mock_ipython.get_ipython = mock_get_ipython

        with patch.dict("sys.modules", {"IPython": mock_ipython}):
            # Should not raise
            notebook._setup_display()

    def test_setup_display_without_ipython_kernel(self):
        """Test setup display when not in IPython kernel."""
        mock_get_ipython = MagicMock(return_value=None)
        mock_ipython = MagicMock()
        mock_ipython.get_ipython = mock_get_ipython

        with patch.dict("sys.modules", {"IPython": mock_ipython}):
            # Should not raise
            notebook._setup_display()

    def test_setup_display_ipython_not_installed(self):
        """Test that missing IPython is handled gracefully."""
        with patch("builtins.__import__", side_effect=ImportError):
            # Should not raise
            notebook._setup_display()
