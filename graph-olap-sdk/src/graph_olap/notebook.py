"""Notebook styling and Starburst cluster management.

This module provides:
- Automatic CSS injection for styled tables and callouts in Jupyter
- itables configuration for interactive DataFrames
- Starburst Galaxy cluster wake-up utility

Notebook setup (client creation, persona handling, resource tracking) is
handled by ``graph_olap.notebook_setup.setup()``.
"""

from __future__ import annotations

# Track if styles have been set up
_styles_setup_done: bool = False


def _setup_itables() -> None:
    """Configure itables for automatic interactive display."""
    try:
        import itables

        itables.init_notebook_mode(all_interactive=True)
    except ImportError:
        pass  # itables not installed, skip


def _setup_notebook_styles() -> None:
    """Inject notebook CSS into IPython display.

    Loads CSS from the SDK package resources, ensuring styles are always
    available regardless of the notebook's working directory.

    This function is called automatically on module import and is idempotent.
    """
    global _styles_setup_done
    if _styles_setup_done:
        return
    _styles_setup_done = True

    try:
        from IPython import get_ipython
        from IPython.display import HTML, display

        ip = get_ipython()
        if ip is None:
            return

        # Load CSS from SDK package resources (always available)
        from graph_olap.styles import get_notebook_css

        css = get_notebook_css()
        display(HTML(f"<style>\n{css}\n</style>"))

    except ImportError:
        pass  # IPython not available or styles package missing


def wake_starburst(timeout: int = 60, quiet: bool = False) -> bool:
    """Wake Starburst Galaxy cluster and wait until ready.

    Starburst Galaxy clusters auto-suspend after 5 minutes of inactivity.
    Call this before operations that require Starburst (snapshot creation,
    data export) to ensure the cluster is awake.

    Args:
        timeout: Maximum seconds to wait for cluster to be ready
        quiet: If True, suppress progress messages

    Returns:
        True if cluster is ready, False if wake-up failed or timed out

    Environment Variables:
        STARBURST_USER: Galaxy service account username
        STARBURST_PASSWORD: Galaxy service account password
        STARBURST_TRINO_URL: Trino endpoint (default: hsbcgraph-test.trino.galaxy.starburst.io)

    Example:
        >>> from graph_olap.notebook import wake_starburst
        >>> wake_starburst()  # Ensure cluster is awake before creating instances
    """
    import os
    import time

    starburst_user = os.environ.get("STARBURST_USER")
    starburst_password = os.environ.get("STARBURST_PASSWORD")
    trino_url = os.environ.get(
        "STARBURST_TRINO_URL",
        "https://hsbcgraph-test.trino.galaxy.starburst.io",
    )

    if not starburst_user or not starburst_password:
        if not quiet:
            print("⚠️  Starburst credentials not set, skipping cluster wake-up")
        return False

    try:
        import httpx

        with httpx.Client(
            auth=(starburst_user, starburst_password), timeout=30
        ) as client:
            if not quiet:
                print("🔄 Waking Starburst cluster...")

            # Send query to wake cluster
            response = client.post(
                f"{trino_url}/v1/statement",
                content="SELECT 1",
                headers={"X-Trino-User": starburst_user},
            )

            if response.status_code != 200:
                if not quiet:
                    print(f"⚠️  Wake-up request failed: HTTP {response.status_code}")
                return False

            # Poll until ready
            start = time.time()
            while time.time() - start < timeout:
                info = client.get(f"{trino_url}/v1/info")
                if info.status_code == 200 and not info.json().get("starting", True):
                    if not quiet:
                        print("✅ Starburst cluster is ready")
                    return True
                time.sleep(2)

            if not quiet:
                print(f"⚠️  Cluster still starting after {timeout}s, proceeding anyway")
            return True

    except Exception as e:
        if not quiet:
            print(f"⚠️  Failed to wake cluster: {e}")
        return False


# =============================================================================
# Module-level initialization
# =============================================================================

# Automatically inject styling functions when this module is imported.
# This allows notebooks to use styled_table(), callout(), etc. immediately
# after `from graph_olap import notebook`, without waiting for test() call.
_setup_notebook_styles()
