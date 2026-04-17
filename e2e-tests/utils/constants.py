"""E2E test constants - single source of truth.

This module provides test prefix information derived from notebooks.yaml.
Used for resource cleanup and orphan detection.
"""

from pathlib import Path
from typing import Any

import yaml


def _load_notebook_config() -> dict[str, Any]:
    """Load notebook configuration from YAML."""
    config_path = Path(__file__).parent.parent / "notebooks.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def _build_prefix_map() -> dict[str, str]:
    """Build notebook -> prefix mapping from notebooks.yaml.

    Returns:
        Dict mapping notebook filename to test prefix
        e.g., {"03_managing_resources.ipynb": "CrudTest", ...}
    """
    config = _load_notebook_config()
    notebooks = config.get("notebooks", {})

    return {
        f"{name}.ipynb": nb_config.get("prefix")
        for name, nb_config in notebooks.items()
        if nb_config and nb_config.get("prefix")
    }


def _build_test_prefixes() -> list[str]:
    """Get all unique test prefixes from notebooks.yaml.

    Returns:
        Sorted list of unique test prefixes
        e.g., ["AdminTest", "AlgoTest", "AuthTest", ...]
    """
    config = _load_notebook_config()
    notebooks = config.get("notebooks", {})

    return sorted({
        nb_config.get("prefix")
        for nb_config in notebooks.values()
        if nb_config and nb_config.get("prefix")
    })


# Build mappings once at module load time
NOTEBOOK_PREFIX_MAP: dict[str, str] = _build_prefix_map()
TEST_PREFIXES: list[str] = _build_test_prefixes()
TEST_PREFIXES_WITH_DASH: list[str] = [f"{p}-" for p in TEST_PREFIXES]


def get_test_prefix(notebook_name: str) -> str | None:
    """Get the test prefix for a notebook.

    Args:
        notebook_name: The notebook filename (e.g., "03_managing_resources.ipynb")

    Returns:
        The test prefix (e.g., "CrudTest") or None if not a test notebook
    """
    return NOTEBOOK_PREFIX_MAP.get(notebook_name)


def is_test_resource_name(name: str) -> bool:
    """Check if a resource name matches any test prefix.

    Args:
        name: Resource name to check

    Returns:
        True if the name starts with any test prefix
    """
    return any(name.startswith(prefix) for prefix in TEST_PREFIXES_WITH_DASH)
